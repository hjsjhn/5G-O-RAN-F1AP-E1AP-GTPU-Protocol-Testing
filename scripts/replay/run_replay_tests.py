#!/usr/bin/env python3
"""Encode replay testcases and validate generated packets with tshark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from encode_gtpu import encode_packet as encode_gtpu_packet
from encode_gtpu import load_case as load_gtpu_case
from encode_gtpu import write_pcap
from encode_sctp_template import (
    encode_packet as encode_sctp_packet,
    extract_sctp_data_payload,
    generate_control_payload,
    load_case as load_sctp_case,
    resolve_template,
)


def run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return proc.stdout


def tshark_version() -> str:
    return run(["tshark", "--version"]).splitlines()[0]


def tshark_rows(pcap: Path, display_filter: str, fields: list[str]) -> list[dict[str, str]]:
    cmd = [
        "tshark",
        "-r",
        str(pcap),
        "-Y",
        display_filter,
        "-T",
        "fields",
        "-E",
        "header=y",
        "-E",
        "separator=\t",
        "-E",
        "occurrence=a",
        "-E",
        "aggregator=,",
    ]
    for field in fields:
        cmd.extend(["-e", field])
    output = run(cmd)
    if not output.strip():
        return []
    return [dict(row) for row in csv.DictReader(output.splitlines(), delimiter="\t")]


def tshark_count(pcap: Path, display_filter: str) -> int:
    output = run(
        ["tshark", "-r", str(pcap), "-Y", display_filter, "-T", "fields", "-e", "frame.number"]
    )
    return len([line for line in output.splitlines() if line])


def stage4_normalized_record(pcap: Path, case_id: str, protocol: str) -> dict:
    output_dir = Path("json/replay_results/normalized") / case_id
    pcap_arg = "--gtpu-pcap" if protocol == "GTP-U" else "--sctp-pcap"
    record_type = "gtpu_packets" if protocol == "GTP-U" else "control_plane_packets"
    run(
        [
            sys.executable,
            "scripts/parse/normalize_pcaps.py",
            pcap_arg,
            str(pcap),
            "--prefix",
            case_id,
            "-o",
            str(output_dir),
        ]
    )
    records = json.loads((output_dir / f"{case_id}_{record_type}.json").read_text(encoding="utf-8"))
    return records[0] if records else {}


def validate_case(case_path: Path, pcap_dir: Path) -> dict:
    raw_case = json.loads(case_path.read_text(encoding="utf-8"))
    if raw_case.get("protocol") == "GTP-U":
        case = load_gtpu_case(case_path)
        packet = encode_gtpu_packet(case)
        source_payload = None
        generated_payload = None
        mutation = None
    else:
        case = load_sctp_case(case_path)
        _, template = resolve_template(case, case_path)
        source_payload = bytes.fromhex(template["payload"]["hex"])
        generated_payload, mutation = generate_control_payload(case, template)
        packet = encode_sctp_packet(case, case_path, generated_payload)
    case_id = case["id"]
    pcap_path = pcap_dir / f"{case_id}.pcap"
    write_pcap(pcap_path, [packet])

    expect = case.get("expect", {})
    expected_fields = expect.get("fields", {})
    fields = list(expected_fields)
    display_filter = expect.get("display_filter", "gtp")
    rows = tshark_rows(pcap_path, display_filter, fields)

    checks: list[dict] = []
    expected_count = expect.get("packet_count", 1)
    checks.append(
        {
            "name": "packet_count",
            "expected": expected_count,
            "actual": len(rows),
            "passed": len(rows) == expected_count,
        }
    )
    malformed_count = tshark_count(pcap_path, "_ws.malformed")
    checks.append(
        {
            "name": "not_malformed",
            "expected": 0,
            "actual": malformed_count,
            "passed": malformed_count == 0,
        }
    )

    first = rows[0] if rows else {}
    for field, expected in expected_fields.items():
        actual = first.get(field, "")
        checks.append(
            {
                "name": field,
                "expected": str(expected),
                "actual": actual,
                "passed": actual == str(expected),
            }
        )

    normalized = None
    if source_payload is not None:
        round_trip = extract_sctp_data_payload(packet)
        checks.append(
            {
                "name": "generated_aper_payload_round_trip",
                "expected": generated_payload.hex(),
                "actual": round_trip.hex(),
                "passed": round_trip == generated_payload,
            }
        )
        if mutation is not None:
            checks.extend(
                [
                    {
                        "name": "structured_source_ie_matches_decoded_template",
                        "expected": case["structured_ies"][mutation["field"]],
                        "actual": mutation["before"],
                        "passed": mutation["before"]
                        == case["structured_ies"][mutation["field"]],
                    },
                    {
                        "name": "structured_mutation_applied",
                        "expected": case["mutation"]["value"],
                        "actual": mutation["after"],
                        "passed": mutation["after"] == case["mutation"]["value"],
                    },
                    {
                        "name": "mutation_changes_aper_payload",
                        "expected": True,
                        "actual": source_payload != generated_payload,
                        "passed": source_payload != generated_payload,
                    },
                ]
            )
    normalized_expect = expect.get("normalized", {})
    if normalized_expect:
        normalized = stage4_normalized_record(pcap_path, case_id, case["protocol"])
        if case["protocol"] == "GTP-U":
            actual_normalized = {
                "protocol": normalized.get("protocol"),
                "teid": normalized.get("gtp", {}).get("teid"),
                "message_type": normalized.get("gtp", {}).get("message_type"),
                "outer_src": normalized.get("outer_ip", {}).get("src"),
                "outer_dst": normalized.get("outer_ip", {}).get("dst"),
                "inner_src": normalized.get("inner_ip", {}).get("src"),
                "inner_dst": normalized.get("inner_ip", {}).get("dst"),
            }
        else:
            actual_normalized = {
                "protocol": normalized.get("protocol"),
                "procedure_code": normalized.get("procedure", {}).get("code"),
                "procedure_name": normalized.get("procedure", {}).get("name"),
                "ies": normalized.get("ies", {}),
            }
        for name, expected in normalized_expect.items():
            if name == "ies":
                for ie_name, ie_expected in expected.items():
                    actual = actual_normalized["ies"].get(ie_name)
                    checks.append(
                        {
                            "name": f"stage4_normalized.ies.{ie_name}",
                            "expected": ie_expected,
                            "actual": actual,
                            "passed": actual == ie_expected,
                        }
                    )
                continue
            actual = actual_normalized.get(name)
            checks.append(
                {
                    "name": f"stage4_normalized.{name}",
                    "expected": expected,
                    "actual": actual,
                    "passed": actual == expected,
                }
            )

    payload_evidence = None
    if source_payload is not None:
        payload_evidence = {
            "source_sha256": hashlib.sha256(source_payload).hexdigest(),
            "generated_sha256": hashlib.sha256(generated_payload).hexdigest(),
            "changed": source_payload != generated_payload,
            "mutation": mutation,
        }
    return {
        "id": case_id,
        "description": case.get("description", ""),
        "protocol": case["protocol"],
        "source_case": str(case_path),
        "generated_pcap": str(pcap_path),
        "display_filter": display_filter,
        "stage4_normalized": normalized,
        "payload_evidence": payload_evidence,
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=Path("tests/replay/cases"),
        help="directory containing replay testcase JSON files",
    )
    parser.add_argument(
        "--pcap-dir",
        type=Path,
        default=Path("captures/generated/replay"),
        help="directory for generated pcap files",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("json/replay_results/latest.json"),
        help="structured replay test result JSON",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not shutil.which("tshark"):
        raise SystemExit("tshark is required but was not found in PATH")

    case_paths = sorted(args.cases_dir.glob("*.json"))
    if not case_paths:
        raise SystemExit(f"no replay testcases found in {args.cases_dir}")

    results = [validate_case(path, args.pcap_dir) for path in case_paths]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tshark_version": tshark_version(),
        "total": len(results),
        "passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "results": results,
    }
    write_json(args.output, summary)

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['id']}")
        for check in result["checks"]:
            if not check["passed"]:
                print(
                    f"  {check['name']}: expected={check['expected']!r} actual={check['actual']!r}"
                )
    print(f"Result: {args.output}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except subprocess.CalledProcessError as exc:
        print(exc.stderr, file=sys.stderr)
        raise SystemExit(exc.returncode) from exc

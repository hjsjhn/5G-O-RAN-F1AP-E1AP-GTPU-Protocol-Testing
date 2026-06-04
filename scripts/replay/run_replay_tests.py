#!/usr/bin/env python3
"""Encode replay testcases and validate generated packets with tshark."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from encode_gtpu import encode_packet, load_case, write_pcap


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


def validate_case(case_path: Path, pcap_dir: Path) -> dict:
    case = load_case(case_path)
    case_id = case["id"]
    pcap_path = pcap_dir / f"{case_id}.pcap"
    write_pcap(pcap_path, [encode_packet(case)])

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

    return {
        "id": case_id,
        "description": case.get("description", ""),
        "protocol": case["protocol"],
        "source_case": str(case_path),
        "generated_pcap": str(pcap_path),
        "display_filter": display_filter,
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

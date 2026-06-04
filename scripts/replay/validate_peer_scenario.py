#!/usr/bin/env python3
"""Validate F1AP/E1AP peer recognition and responses from controlled UE flows."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


TARGETS = [
    ("F1AP", "UEContextSetupRequest", "UEContextSetupResponse", "du", "cu_cp", "pdu"),
    ("F1AP", "UEContextModificationRequest", "UEContextModificationResponse", "du", "cu_cp", "pdu"),
    ("F1AP", "UEContextReleaseCommand", "UEContextReleaseComplete", "du", "cu_cp", "release"),
    ("E1AP", "BearerContextSetupRequest", "BearerContextSetupResponse", "cu_up", "cu_cp", "pdu"),
    ("E1AP", "BearerContextModificationRequest", "BearerContextModificationResponse", "cu_up", "cu_cp", "pdu"),
    ("E1AP", "BearerContextReleaseCommand", "BearerContextReleaseComplete", "cu_up", "cu_cp", "release"),
]


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_logs(result_dir: Path) -> dict[str, str]:
    run_id = result_dir.name
    log_dir = Path("logs/flows") / run_id
    return {
        path.stem: path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(log_dir.glob("*.log"))
    }


def control_records(result_dir: Path) -> list[dict]:
    path = next((result_dir / "normalized").glob("*_control_plane_packets.json"))
    return read_json(path)


def captured(records: list[dict], protocol: str, message: str) -> bool:
    return any(
        record.get("protocol") == protocol and message in (record.get("procedure", {}).get("name") or "")
        for record in records
    )


def log_has(logs: dict[str, str], component: str, direction: str, message: str) -> bool:
    return re.search(rf"{direction} PDU .*{re.escape(message)}", logs.get(component, "")) is not None


def validate_target(target: tuple[str, str, str, str, str, str], contexts: dict[str, dict]) -> dict:
    protocol, request, response, receiver, initiator, context_name = target
    context = contexts[context_name]
    l2 = captured(context["control"], protocol, request)
    l3 = l2 and log_has(context["logs"], receiver, "Rx", request)
    response_captured = captured(context["control"], protocol, response)
    response_received = log_has(context["logs"], initiator, "Rx", response)
    l4 = l3 and response_captured and response_received
    return {
        "protocol": protocol,
        "message": request,
        "peer": receiver,
        "expected_response": response,
        "levels": {"L1": True, "L2": l2, "L3": l3, "L4": l4},
        "evidence": {
            "target_captured": l2,
            "peer_rx_log": l3,
            "response_captured": response_captured,
            "initiator_rx_response_log": response_received,
        },
    }


def write_markdown(path: Path, result: dict) -> None:
    lines = [
        "# Stage 5C.4 Peer Validation Result",
        "",
        f"- Result: **{result['result']}**",
        f"- PDU flow: `{result['flows']['pdu']}`",
        f"- Release flow: `{result['flows']['release']}`",
        "",
        "| Protocol | Message | Peer | L3 | L4 | Response |",
        "|---|---|---|---|---|---|",
    ]
    for case in result["control_cases"]:
        lines.append(
            f"| {case['protocol']} | {case['message']} | {case['peer']} | "
            f"{'PASS' if case['levels']['L3'] else 'FAIL'} | "
            f"{'PASS' if case['levels']['L4'] else 'FAIL'} | {case['expected_response']} |"
        )
    gtpu = result["gtpu"]
    lines.extend(
        [
            "",
            "## GTP-U",
            "",
            f"- L3 peer recognition: **{'PASS' if gtpu['levels']['L3'] else 'FAIL'}**",
            f"- L4 state advance and UE delivery: **{'PASS' if gtpu['levels']['L4'] else 'FAIL'}**",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdu-result-dir", type=Path, required=True)
    parser.add_argument("--release-result-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    contexts = {
        "pdu": {"control": control_records(args.pdu_result_dir), "logs": read_logs(args.pdu_result_dir)},
        "release": {
            "control": control_records(args.release_result_dir),
            "logs": read_logs(args.release_result_dir),
        },
    }
    control_cases = [validate_target(target, contexts) for target in TARGETS]
    gtpu = read_json(args.pdu_result_dir / "live_gtpu_result.json")
    passed = all(case["levels"]["L3"] and case["levels"]["L4"] for case in control_cases)
    passed = passed and gtpu["levels"]["L3"] and gtpu["levels"]["L4"]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if passed else "FAIL",
        "flows": {"pdu": args.pdu_result_dir.name, "release": args.release_result_dir.name},
        "control_cases": control_cases,
        "gtpu": gtpu,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(args.output.with_suffix(".md"), result)
    print(f"[{result['result']}] Stage 5C.4 peer validation")
    print(args.output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

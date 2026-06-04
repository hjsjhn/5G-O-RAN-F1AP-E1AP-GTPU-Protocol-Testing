#!/usr/bin/env python3
"""Build a cross-protocol timeline and validate an automated UE flow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ENDPOINT_NAMES = {
    "10.53.1.2": "AMF",
    "10.53.1.3": "UPF",
    "10.53.1.4": "CU-CP",
    "10.53.1.5": "CU-UP",
    "10.53.1.6": "DU",
    "172.18.10.2": "CU-UP",
    "172.18.10.3": "DU",
}


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_logs(log_dir: Path) -> dict[str, str]:
    return {
        path.stem: path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(log_dir.glob("*.log"))
    }


def direction(src: str | None, dst: str | None) -> str:
    return f"{ENDPOINT_NAMES.get(src, src)}->{ENDPOINT_NAMES.get(dst, dst)}"


def build_timeline(control: list[dict], gtpu: list[dict]) -> list[dict]:
    events: list[dict] = []
    for record in control:
        src = record["ip"]["src"]
        dst = record["ip"]["dst"]
        events.append(
            {
                "time_epoch": record["time_epoch"],
                "time_relative": record["time_relative"],
                "protocol": record["protocol"],
                "message": record["procedure"]["name"],
                "procedure_code": record["procedure"]["code"],
                "direction": direction(src, dst),
                "frame": record["frame"],
                "correlation": record["ies"],
            }
        )
    for record in gtpu:
        src = record["outer_ip"]["src"]
        dst = record["outer_ip"]["dst"]
        events.append(
            {
                "time_epoch": record["time_epoch"],
                "time_relative": record["time_relative"],
                "protocol": "GTP-U",
                "message": record["gtp"]["message_type"],
                "procedure_code": None,
                "direction": direction(src, dst),
                "frame": record["frame"],
                "correlation": {
                    "teid": record["gtp"]["teid"],
                    "qfi": record["gtp"]["qfi"],
                    "inner_ip": record["inner_ip"],
                },
            }
        )
    return sorted(events, key=lambda event: (event["time_epoch"] or 0, event["frame"] or 0))


def message_names(control: list[dict], protocol: str) -> list[str]:
    return [
        record["procedure"]["name"] or ""
        for record in control
        if record["protocol"] == protocol
    ]


def add_check(checks: list[dict], name: str, passed: bool, evidence: str) -> None:
    checks.append({"name": name, "passed": passed, "evidence": evidence})


def has_message(names: list[str], text: str) -> bool:
    return any(text in name for name in names)


def has_log(logs: dict[str, str], component: str, text: str) -> bool:
    return text.lower() in logs.get(component, "").lower()


def validate_flow(flow: str, control: list[dict], gtpu: list[dict], logs: dict[str, str]) -> list[dict]:
    checks: list[dict] = []
    names = {protocol: message_names(control, protocol) for protocol in ("F1AP", "E1AP", "NGAP")}

    required_messages = {
        "F1AP": ["UEContextSetupRequest", "UEContextSetupResponse", "UEContextModificationRequest"],
        "E1AP": ["BearerContextSetupRequest", "BearerContextSetupResponse"],
        "NGAP": ["InitialUEMessage", "PDUSessionResourceSetupRequest", "PDUSessionResourceSetupResponse"],
    }
    for protocol, messages in required_messages.items():
        for message in messages:
            add_check(
                checks,
                f"{protocol}:{message}",
                has_message(names[protocol], message),
                f"captured {protocol} procedure {message}",
            )

    add_check(checks, "GTP-U:current_tunnel_traffic", bool(gtpu), f"captured {len(gtpu)} GTP-U packets")
    add_check(
        checks,
        "UE:registration_accept",
        has_log(logs, "ue", "Handling Registration Accept"),
        "UE log contains Registration Accept handling",
    )
    add_check(
        checks,
        "UE:pdu_session_established",
        has_log(logs, "ue", "PDU Session Establishment successful"),
        "UE log contains successful PDU Session establishment",
    )
    add_check(
        checks,
        "CU-CP:pdu_session_state",
        has_log(logs, "cu_cp", "BearerContextSetupResponse")
        and has_log(logs, "cu_cp", "UEContextModificationResponse"),
        "CU-CP log contains E1 bearer setup and F1 UE modification responses",
    )
    add_check(
        checks,
        "CU-UP:tunnel_state",
        has_log(logs, "cu_up", "GTPU NGU Rx configured")
        and has_log(logs, "cu_up", "GTPU NR-U Tx configured"),
        "CU-UP log contains configured NG-U and NR-U tunnels",
    )
    add_check(
        checks,
        "DU:ue_context_state",
        has_log(logs, "du", "UEContextModificationResponse"),
        "DU log contains UEContextModificationResponse",
    )
    add_check(
        checks,
        "Open5GS:session_state",
        has_log(logs, "amf", "Number of AMF-Sessions is now 1"),
        "AMF log contains an active AMF session",
    )

    if flow == "registration_release":
        release_messages = {
            "F1AP": ["UEContextReleaseCommand", "UEContextReleaseComplete"],
            "E1AP": ["BearerContextReleaseCommand", "BearerContextReleaseComplete"],
            "NGAP": ["UEContextReleaseRequest", "UEContextReleaseCommand", "UEContextReleaseComplete"],
        }
        for protocol, messages in release_messages.items():
            for message in messages:
                add_check(
                    checks,
                    f"{protocol}:{message}",
                    has_message(names[protocol], message),
                    f"captured {protocol} procedure {message}",
                )
        add_check(
            checks,
            "CU-CP:release_state",
            has_log(logs, "cu_cp", "BearerContextReleaseComplete")
            and has_log(logs, "cu_cp", "UEContextReleaseComplete"),
            "CU-CP log contains completed E1 and F1 release procedures",
        )
        add_check(
            checks,
            "CU-UP:release_state",
            has_log(logs, "cu_up", "Disconnecting PDU session"),
            "CU-UP log contains PDU session disconnect",
        )
        add_check(
            checks,
            "DU:release_state",
            has_log(logs, "du", "UEContextReleaseCommand"),
            "DU log contains the received F1 UEContextReleaseCommand; the F1AP check independently requires Complete",
        )
        add_check(
            checks,
            "Open5GS:release_state",
            has_log(logs, "amf", "UE Context Release"),
            "AMF log contains UE Context Release",
        )
        add_check(
            checks,
            "UE:rrc_release",
            has_log(logs, "ue", "rrcRelease"),
            "UE log contains an RRC Release message",
        )
    return checks


def write_markdown(path: Path, result: dict) -> None:
    lines = [
        f"# UE Flow Result: {result['flow']}",
        "",
        f"- Run: `{result['run_id']}`",
        f"- Result: **{result['result']}**",
        f"- Control messages: {result['counts']['control_messages']}",
        f"- GTP-U packets: {result['counts']['gtpu_packets']}",
        "",
        "## Checks",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    for check in result["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"| `{check['name']}` | {status} | {check['evidence']} |")
    lines.extend(["", "## Timeline", "", "| Time | Protocol | Direction | Message | Frame |", "|---|---|---|---|---|"])
    for event in result["timeline"]:
        lines.append(
            f"| {event['time_relative']} | {event['protocol']} | {event['direction']} | "
            f"{event['message']} | {event['frame']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flow", choices=("registration_pdu_session", "registration_release"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--gtpu", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    control = read_json(args.control)
    gtpu = read_json(args.gtpu)
    logs = read_logs(args.log_dir)
    checks = validate_flow(args.flow, control, gtpu, logs)
    timeline = build_timeline(control, gtpu)
    passed = all(check["passed"] for check in checks)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id,
        "flow": args.flow,
        "result": "PASS" if passed else "FAIL",
        "counts": {"control_messages": len(control), "gtpu_packets": len(gtpu), "timeline_events": len(timeline)},
        "checks": checks,
        "timeline": timeline,
        "artifacts": {
            "control": str(args.control),
            "gtpu": str(args.gtpu),
            "logs": str(args.log_dir),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(args.output.with_suffix(".md"), result)
    print(f"[{result['result']}] {args.flow}")
    print(args.output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

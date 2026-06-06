#!/usr/bin/env python3
"""Build a cross-protocol timeline and validate an automated UE flow."""

from __future__ import annotations

import argparse
import json
import sys
import time
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


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    result: dict = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id,
        "flow": args.flow,
        "result": "PENDING",
        "counts": {},
        "checks": [],
        "timeline": [],
        "artifacts": {
            "control": str(args.control),
            "gtpu": str(args.gtpu),
            "logs": str(args.log_dir),
        },
    }
    write_result(args.output, result)

    print(f"Reading capture data for {args.flow}...")
    control = read_json(args.control)
    gtpu = read_json(args.gtpu)

    result["counts"] = {"control_messages": len(control), "gtpu_packets": len(gtpu), "timeline_events": 0}
    write_result(args.output, result)

    print("Building timeline...")
    timeline = build_timeline(control, gtpu)
    result["timeline"] = timeline
    result["counts"]["timeline_events"] = len(timeline)
    write_result(args.output, result)

    print("Reading component logs...")
    logs = read_logs(args.log_dir)

    names = {protocol: message_names(control, protocol) for protocol in ("F1AP", "E1AP", "NGAP")}
    checks: list[dict] = result["checks"]

    check_groups: list[tuple[list[tuple[str, bool, str]], str]] = []

    group_ngap_init = [
        ("NGAP:InitialUEMessage", has_message(names["NGAP"], "InitialUEMessage"), "captured NGAP procedure InitialUEMessage"),
    ]
    check_groups.append((group_ngap_init, "NGAP initial UE"))

    group_f1ap_setup = []
    for message in ["UEContextSetupRequest", "UEContextSetupResponse"]:
        group_f1ap_setup.append((f"F1AP:{message}", has_message(names["F1AP"], message), f"captured F1AP procedure {message}"))
    check_groups.append((group_f1ap_setup, "F1AP UE context setup"))

    group_e1ap = []
    for message in ["BearerContextSetupRequest", "BearerContextSetupResponse"]:
        group_e1ap.append((f"E1AP:{message}", has_message(names["E1AP"], message), f"captured E1AP procedure {message}"))
    check_groups.append((group_e1ap, "E1AP bearer setup"))

    group_ngap_pdu_req = [
        ("NGAP:PDUSessionResourceSetupRequest", has_message(names["NGAP"], "PDUSessionResourceSetupRequest"), "captured NGAP procedure PDUSessionResourceSetupRequest"),
    ]
    check_groups.append((group_ngap_pdu_req, "NGAP PDU Session request"))

    group_f1ap_mod = [
        ("F1AP:UEContextModificationRequest", has_message(names["F1AP"], "UEContextModificationRequest"), "captured F1AP procedure UEContextModificationRequest"),
    ]
    check_groups.append((group_f1ap_mod, "F1AP UE context modification"))

    group_ngap_pdu_resp = [
        ("NGAP:PDUSessionResourceSetupResponse", has_message(names["NGAP"], "PDUSessionResourceSetupResponse"), "captured NGAP procedure PDUSessionResourceSetupResponse"),
    ]
    check_groups.append((group_ngap_pdu_resp, "NGAP PDU Session response"))

    group_gtpu = [("GTP-U:current_tunnel_traffic", bool(gtpu), f"captured {len(gtpu)} GTP-U packets")]
    check_groups.append((group_gtpu, "GTP-U traffic"))

    group_ue = [
        ("UE:registration_accept", has_log(logs, "ue", "Handling Registration Accept"), "UE log contains Registration Accept handling"),
        ("UE:pdu_session_established", has_log(logs, "ue", "PDU Session Establishment successful"), "UE log contains successful PDU Session establishment"),
    ]
    check_groups.append((group_ue, "UE state"))

    group_ran = [
        ("CU-CP:pdu_session_state", has_log(logs, "cu_cp", "BearerContextSetupResponse") and has_log(logs, "cu_cp", "UEContextModificationResponse"), "CU-CP log contains E1 bearer setup and F1 UE modification responses"),
        ("CU-UP:tunnel_state", has_log(logs, "cu_up", "GTPU NGU Rx configured") and has_log(logs, "cu_up", "GTPU NR-U Tx configured"), "CU-UP log contains configured NG-U and NR-U tunnels"),
        ("DU:ue_context_state", has_log(logs, "du", "UEContextModificationResponse"), "DU log contains UEContextModificationResponse"),
    ]
    check_groups.append((group_ran, "RAN component state"))

    group_core = [
        ("Open5GS:session_state", has_log(logs, "amf", "Number of AMF-Sessions is now 1"), "AMF log contains an active AMF session"),
    ]
    check_groups.append((group_core, "Core state"))

    if args.flow == "registration_release":
        group_ngap_release_req = [
            ("NGAP:UEContextReleaseRequest", has_message(names["NGAP"], "UEContextReleaseRequest"), "captured NGAP procedure UEContextReleaseRequest"),
        ]
        check_groups.append((group_ngap_release_req, "NGAP release request"))

        group_ngap_release_cmd = [
            ("NGAP:UEContextReleaseCommand", has_message(names["NGAP"], "UEContextReleaseCommand"), "captured NGAP procedure UEContextReleaseCommand"),
        ]
        check_groups.append((group_ngap_release_cmd, "NGAP release command"))

        group_e1ap_release = []
        for message in ["BearerContextReleaseCommand", "BearerContextReleaseComplete"]:
            group_e1ap_release.append((f"E1AP:{message}", has_message(names["E1AP"], message), f"captured E1AP procedure {message}"))
        check_groups.append((group_e1ap_release, "E1AP release"))

        group_f1ap_release = []
        for message in ["UEContextReleaseCommand", "UEContextReleaseComplete"]:
            group_f1ap_release.append((f"F1AP:{message}", has_message(names["F1AP"], message), f"captured F1AP procedure {message}"))
        check_groups.append((group_f1ap_release, "F1AP release"))

        group_ngap_release_complete = [
            ("NGAP:UEContextReleaseComplete", has_message(names["NGAP"], "UEContextReleaseComplete"), "captured NGAP procedure UEContextReleaseComplete"),
        ]
        check_groups.append((group_ngap_release_complete, "NGAP release complete"))

        group_release_state = [
            ("CU-CP:release_state", has_log(logs, "cu_cp", "BearerContextReleaseComplete") and has_log(logs, "cu_cp", "UEContextReleaseComplete"), "CU-CP log contains completed E1 and F1 release procedures"),
            ("CU-UP:release_state", has_log(logs, "cu_up", "Disconnecting PDU session"), "CU-UP log contains PDU session disconnect"),
            ("DU:release_state", has_log(logs, "du", "UEContextReleaseCommand"), "DU log contains the received F1 UEContextReleaseCommand; the F1AP check independently requires Complete"),
            ("Open5GS:release_state", has_log(logs, "amf", "UE Context Release"), "AMF log contains UE Context Release"),
            ("UE:rrc_release", has_log(logs, "ue", "rrcRelease"), "UE log contains an RRC Release message"),
        ]
        check_groups.append((group_release_state, "Release state"))

    for group_items, group_label in check_groups:
        print(f"Checking {group_label}...")
        for name, passed, evidence in group_items:
            add_check(checks, name, passed, evidence)
        write_result(args.output, result)
        time.sleep(1)

    passed = all(check["passed"] for check in checks)
    result["result"] = "PASS" if passed else "FAIL"
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    write_result(args.output, result)
    write_markdown(args.output.with_suffix(".md"), result)
    print(f"[{result['result']}] {args.flow}")
    print(args.output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

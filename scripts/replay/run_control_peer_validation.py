#!/usr/bin/env python3
"""Run isolated generated F1AP/E1AP testcases against the real CU-CP peer."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from encode_gtpu import write_pcap
from encode_sctp_template import encode_packet as encode_sctp_packet


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_MAIN = PROJECT_ROOT / "docker/compose/docker-compose.yml"
COMPOSE_SPLIT = PROJECT_ROOT / "docker/compose/docker-compose.split.yml"
COMPOSE_EVIDENCE = PROJECT_ROOT / "docker/compose/docker-compose.flow-evidence.yml"
CONTROL_CASES_PATH = PROJECT_ROOT / "tests/replay/live_cases/control_peer_cases.json"


def load_case_definitions() -> dict[str, dict]:
    document = json.loads(CONTROL_CASES_PATH.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not isinstance(document.get("cases"), list):
        raise ValueError(f"{CONTROL_CASES_PATH}: invalid live control testcase manifest")
    return {case["id"]: case for case in document["cases"]}


CASES = load_case_definitions()


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=PROJECT_ROOT, check=check, text=True, capture_output=True
    )


def cu_cp_logs() -> list[str]:
    output = run(["docker", "logs", "srsran_cu_cp"], check=False)
    return (output.stdout + output.stderr).splitlines()


def parse_endpoint_output(output: str) -> list[dict]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


def timestamp_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()


def peer_log_matches(lines: list[str], case: dict) -> list[str]:
    marker = "[CU-CP-F1]" if case["protocol"] == "F1AP" else "[CU-CP-E1]"
    tid = f"tid={case['transaction_id']}"
    return [
        line
        for line in lines
        if marker in line and "Rx PDU" in line and tid in line and case["message"] in line
    ]


def verify_l2(definition: dict, payload: bytes) -> dict:
    protocol_filter = definition["protocol"].lower()
    ppid = 62 if definition["protocol"] == "F1AP" else 64
    dst_port = 38472 if definition["protocol"] == "F1AP" else 38462
    with tempfile.TemporaryDirectory(prefix="stage5c4-control-l2-") as directory:
        root = Path(directory)
        template_path = root / "template.json"
        pcap_path = root / "generated.pcap"
        template = {
            "schema_version": 1,
            "message": definition["message"],
            "direction": {"src_ip": "192.0.2.10", "dst_ip": "192.0.2.20"},
            "transport": {
                "src_port": 39000,
                "dst_port": dst_port,
                "ppid": ppid,
                "tsn": 1,
                "stream_id": 0,
                "stream_sequence": 0,
            },
            "payload": {"hex": payload.hex(), "length": len(payload)},
        }
        template_path.write_text(json.dumps(template), encoding="utf-8")
        packet = encode_sctp_packet(
            {
                "schema_version": 1,
                "id": definition["id"],
                "protocol": definition["protocol"],
                "template": str(template_path),
            },
            payload=payload,
        )
        write_pcap(pcap_path, [packet])
        procedure = run(
            [
                "tshark",
                "-r",
                str(pcap_path),
                "-Y",
                protocol_filter,
                "-T",
                "fields",
                "-e",
                f"{protocol_filter}.procedureCode",
            ],
            check=False,
        )
        malformed = run(
            [
                "tshark",
                "-r",
                str(pcap_path),
                "-Y",
                "_ws.malformed",
                "-T",
                "fields",
                "-e",
                "frame.number",
            ],
            check=False,
        )
    procedures = [line for line in procedure.stdout.splitlines() if line]
    malformed_frames = [line for line in malformed.stdout.splitlines() if line]
    return {
        "protocol_recognized": procedure.returncode == 0 and bool(procedures),
        "procedure_code": procedures[0] if procedures else None,
        "procedure_matches": procedures == [str(definition["procedure_code"])],
        "malformed_frames": malformed_frames,
        "passed": (
            procedure.returncode == 0
            and procedures == [str(definition["procedure_code"])]
            and malformed.returncode == 0
            and not malformed_frames
        ),
    }


def evaluate_case(raw: dict, peer_lines: list[str]) -> dict:
    definition = CASES[raw["case_id"]]
    payload = bytes.fromhex(raw["payload_hex"])
    response = bytes.fromhex(raw["response_hex"])
    l2 = verify_l2(definition, payload)
    logs = peer_log_matches(peer_lines, definition)
    response_matches = (
        bool(response)
        and raw["response_procedure_code"] == definition["procedure_code"]
        and raw["response_outcome"] in {"successfulOutcome", "unsuccessfulOutcome"}
    )
    return {
        "case_id": raw["case_id"],
        "protocol": definition["protocol"],
        "message": definition["message"],
        "transaction_id": definition["transaction_id"],
        "generated_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "generated_payload_length": len(payload),
        "send_time": timestamp_from_ms(raw["send_epoch_ms"]),
        "peer": "srsRAN CU-CP",
        "l2_tshark": l2,
        "peer_receive_log": logs,
        "response": {
            "message": definition["responses"].get(raw["response_outcome"]),
            "procedure_code": raw["response_procedure_code"],
            "outcome": raw["response_outcome"],
            "payload_sha256": hashlib.sha256(response).hexdigest() if response else None,
            "payload_length": len(response),
        },
        "levels": {
            "L1": bool(payload),
            "L2": l2["passed"],
            "L3": bool(logs),
            "L4": bool(logs) and response_matches,
        },
    }


def prepare_isolated_peer_scenario() -> None:
    run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_MAIN),
            "-f",
            str(COMPOSE_SPLIT),
            "-f",
            str(COMPOSE_EVIDENCE),
            "up",
            "-d",
            "--force-recreate",
            "cu-cp",
            "cu-up",
            "du",
        ]
    )
    for _ in range(90):
        if run(["./scripts/env/check_core_ready.sh"], check=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("flow-evidence baseline did not become healthy")
    run(["docker", "stop", "srsran_du", "srsran_cu_up"])
    time.sleep(2)


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="run the isolated local peer scenario")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("json/replay_results/stage5c4/control_peer_validation.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.live:
        result = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "result": "DRY-RUN",
            "safety": "no SCTP association created; use --live only in the local isolated environment",
            "planned_cases": list(CASES),
        }
        write_result(args.output, result)
        print("[DRY-RUN] generated F1AP/E1AP peer validation")
        return 0

    test_error: str | None = None
    restore_error: str | None = None
    evaluated: list[dict] = []
    try:
        run(["./scripts/env/check_core_ready.sh"])
        prepare_isolated_peer_scenario()
        log_offset = len(cu_cp_logs())
        endpoint_results: list[dict] = []
        for protocol in ("f1ap", "e1ap"):
            completed = run(["./scripts/replay/run_protocol_peer_endpoint.sh", protocol])
            endpoint_results.extend(parse_endpoint_output(completed.stdout))
        peer_lines = cu_cp_logs()[log_offset:]
        evaluated = [evaluate_case(case, peer_lines) for case in endpoint_results]
        if len(evaluated) != len(CASES):
            test_error = f"expected {len(CASES)} endpoint cases, received {len(evaluated)}"
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        test_error = str(exc)
    finally:
        restored = run(["./scripts/env/restore_baseline.sh"], check=False)
        if restored.returncode != 0:
            restore_error = (restored.stdout + restored.stderr).strip()

    l3_count = sum(case["levels"]["L3"] for case in evaluated)
    l2_all = len(evaluated) == len(CASES) and all(case["levels"]["L2"] for case in evaluated)
    f1_l4 = any(case["protocol"] == "F1AP" and case["levels"]["L4"] for case in evaluated)
    e1_l4 = any(case["protocol"] == "E1AP" and case["levels"]["L4"] for case in evaluated)
    passed = (
        test_error is None
        and restore_error is None
        and l2_all
        and l3_count >= 5
        and f1_l4
        and e1_l4
    )
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if passed else "FAIL",
        "classification": "generated_testcase_live_peer_validation",
        "requirements": {
            "all_generated_payloads_l2": l2_all,
            "at_least_five_l3": {"actual": l3_count, "passed": l3_count >= 5},
            "f1ap_at_least_one_l4": f1_l4,
            "e1ap_at_least_one_l4": e1_l4,
            "baseline_restored": restore_error is None,
        },
        "test_error": test_error,
        "restore_error": restore_error,
        "cases": evaluated,
    }
    write_result(args.output, result)
    print(f"[{result['result']}] generated F1AP/E1AP peer validation")
    print(args.output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

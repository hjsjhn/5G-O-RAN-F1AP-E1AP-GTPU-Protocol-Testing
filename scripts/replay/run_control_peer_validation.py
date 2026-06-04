#!/usr/bin/env python3
"""Run JSON-driven F1AP/E1AP payloads through pcap validation and a real CU-CP peer."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from encode_gtpu import write_pcap
from encode_sctp_template import (
    encode_packet as encode_sctp_packet,
    extract_sctp_data_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_MAIN = PROJECT_ROOT / "docker/compose/docker-compose.yml"
COMPOSE_SPLIT = PROJECT_ROOT / "docker/compose/docker-compose.split.yml"
COMPOSE_EVIDENCE = PROJECT_ROOT / "docker/compose/docker-compose.flow-evidence.yml"
CONTROL_CASES_PATH = PROJECT_ROOT / "tests/replay/live_cases/control_peer_cases.json"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=PROJECT_ROOT, check=check, text=True, capture_output=True
    )


def load_case_definitions() -> list[dict]:
    manifest = json.loads(CONTROL_CASES_PATH.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2 or not isinstance(manifest.get("case_paths"), list):
        raise ValueError(f"{CONTROL_CASES_PATH}: invalid live control testcase manifest")
    cases = []
    seen = set()
    for relative_path in manifest["case_paths"]:
        path = PROJECT_ROOT / relative_path
        case = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "schema_version",
            "id",
            "protocol",
            "message",
            "procedure_code",
            "transaction_id",
            "mutable_ies",
            "structured_ies",
            "expected_response",
            "expect",
        }
        if case.get("schema_version") != 1 or not required.issubset(case):
            raise ValueError(f"{path}: incomplete live control testcase")
        if case["protocol"] not in {"F1AP", "E1AP"}:
            raise ValueError(f"{path}: unsupported protocol")
        if case["id"] in seen:
            raise ValueError(f"{path}: duplicate case ID {case['id']}")
        if case["structured_ies"].get("transaction_id") != case["transaction_id"]:
            raise ValueError(f"{path}: transaction_id must match structured_ies")
        if not set(case["mutable_ies"]).issubset(case["structured_ies"]):
            raise ValueError(f"{path}: mutable_ies must reference structured_ies")
        seen.add(case["id"])
        case["json_input_path"] = relative_path
        cases.append(case)
    return cases


CASES = load_case_definitions()


def generator_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int)):
        return str(value)
    raise ValueError(f"unsupported structured IE value: {value!r}")


def generate_payload(case: dict) -> dict:
    cmd = [
        "./scripts/replay/run_control_peer_payload_generator.sh",
        case["protocol"],
        case["message"],
    ]
    cmd.extend(
        f"{name}={generator_value(value)}" for name, value in case["structured_ies"].items()
    )
    completed = run(cmd)
    json_lines = [line for line in completed.stdout.splitlines() if line.startswith("{")]
    if not json_lines:
        raise ValueError(f"{case['id']}: payload generator returned no JSON")
    generated = json.loads(json_lines[-1])
    if (
        generated.get("protocol") != case["protocol"]
        or generated.get("message") != case["message"]
        or generated.get("transaction_id") != case["transaction_id"]
    ):
        raise ValueError(f"{case['id']}: generator output does not match JSON input")
    payload = bytes.fromhex(generated["payload_hex"])
    if not payload:
        raise ValueError(f"{case['id']}: generator returned an empty payload")
    return {
        "payload": payload,
        "json_generated_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "generator_output": {
            "protocol": generated["protocol"],
            "message": generated["message"],
            "transaction_id": generated["transaction_id"],
        },
    }


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
        "occurrence=f",
    ]
    for field in fields:
        cmd.extend(["-e", field])
    completed = run(cmd, check=False)
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    return list(csv.DictReader(completed.stdout.splitlines(), delimiter="\t"))


def read_single_packet_from_pcap(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) < 40 or struct.unpack_from("<I", data)[0] != 0xA1B2C3D4:
        raise ValueError(f"{path}: unsupported or truncated pcap")
    _, _, included_length, original_length = struct.unpack_from("<IIII", data, 24)
    packet_end = 40 + included_length
    if included_length != original_length or packet_end != len(data):
        raise ValueError(f"{path}: expected one complete, uncropped packet")
    return data[40:packet_end]


def build_pcap_and_verify_l2(case: dict, payload: bytes) -> dict:
    ppid = 62 if case["protocol"] == "F1AP" else 64
    dst_port = 38472 if case["protocol"] == "F1AP" else 38462
    with tempfile.TemporaryDirectory(prefix="stage5c4-json-control-") as directory:
        root = Path(directory)
        template_path = root / "template.json"
        pcap_path = root / "generated.pcap"
        template = {
            "schema_version": 1,
            "message": case["message"],
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
                "id": case["id"],
                "protocol": case["protocol"],
                "template": str(template_path),
            },
            payload=payload,
        )
        write_pcap(pcap_path, [packet])
        pcap_payload = extract_sctp_data_payload(read_single_packet_from_pcap(pcap_path))
        expected_fields = case["expect"]["fields"]
        rows = tshark_rows(pcap_path, case["expect"]["display_filter"], list(expected_fields))
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
    actual_fields = rows[0] if len(rows) == 1 else {}
    field_checks = {
        field: {
            "expected": str(expected),
            "actual": actual_fields.get(field),
            "passed": actual_fields.get(field) == str(expected),
        }
        for field, expected in expected_fields.items()
    }
    malformed_frames = [line for line in malformed.stdout.splitlines() if line]
    return {
        "display_filter": case["expect"]["display_filter"],
        "protocol_recognized": len(rows) == 1,
        "field_checks": field_checks,
        "malformed_frames": malformed_frames,
        "pcap_payload_sha256": hashlib.sha256(pcap_payload).hexdigest(),
        "pcap_payload_source": "read_back_from_written_pcap",
        "pcap_payload_matches_generated": pcap_payload == payload,
        "passed": (
            len(rows) == 1
            and all(check["passed"] for check in field_checks.values())
            and malformed.returncode == 0
            and not malformed_frames
            and pcap_payload == payload
        ),
    }


def prepare_payloads() -> list[dict]:
    prepared = []
    for case in CASES:
        generated = generate_payload(case)
        generated["case"] = case
        generated["l2_tshark"] = build_pcap_and_verify_l2(case, generated["payload"])
        prepared.append(generated)
    return prepared


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


def expected_response_message(case: dict, outcome: str) -> str | None:
    return case["expected_response"]["outcomes"].get(outcome)


def evaluate_case(prepared: dict, raw: dict, peer_lines: list[str]) -> dict:
    case = prepared["case"]
    sent_payload = bytes.fromhex(raw["payload_hex"])
    sent_hash = hashlib.sha256(sent_payload).hexdigest()
    generated_hash = prepared["json_generated_payload_sha256"]
    pcap_hash = prepared["l2_tshark"]["pcap_payload_sha256"]
    hash_consistency = generated_hash == pcap_hash == sent_hash
    request_matches = (
        raw["request_procedure_code"] == case["procedure_code"]
        and raw["request_transaction_id"] == case["transaction_id"]
        and raw["request_message"] == case["message"]
    )
    logs = peer_log_matches(peer_lines, case)
    response = bytes.fromhex(raw["response_hex"])
    response_message = expected_response_message(case, raw["response_outcome"])
    response_checks = {
        "present": bool(response),
        "procedure_code_matches": raw["response_procedure_code"] == case["procedure_code"],
        "outcome_expected": response_message is not None,
        "message_matches": response_message == raw["response_message"],
        "transaction_id_matches": raw["response_transaction_id"] == case["transaction_id"],
    }
    l1 = bool(prepared["payload"]) and prepared["l2_tshark"]["pcap_payload_matches_generated"]
    l2 = prepared["l2_tshark"]["passed"]
    l3 = l1 and l2 and hash_consistency and request_matches and bool(logs)
    l4 = l3 and all(response_checks.values())
    return {
        "case_id": case["id"],
        "json_input_path": case["json_input_path"],
        "protocol": case["protocol"],
        "message": case["message"],
        "procedure_code": case["procedure_code"],
        "transaction_id": case["transaction_id"],
        "mutable_ies": case["mutable_ies"],
        "payload_hashes": {
            "json_generated_payload_sha256": generated_hash,
            "pcap_payload_sha256": pcap_hash,
            "sent_payload_sha256": sent_hash,
            "all_equal": hash_consistency,
        },
        "generator_output": prepared["generator_output"],
        "endpoint_decoded_request": {
            "procedure_code": raw["request_procedure_code"],
            "transaction_id": raw["request_transaction_id"],
            "message": raw["request_message"],
            "matches_json": request_matches,
        },
        "send_time": timestamp_from_ms(raw["send_epoch_ms"]),
        "peer": "srsRAN CU-CP",
        "l2_tshark": prepared["l2_tshark"],
        "peer_receive_log": logs,
        "response": {
            "message": raw["response_message"],
            "expected_message": response_message,
            "procedure_code": raw["response_procedure_code"],
            "outcome": raw["response_outcome"],
            "transaction_id": raw["response_transaction_id"],
            "payload_sha256": hashlib.sha256(response).hexdigest() if response else None,
            "payload_length": len(response),
            "checks": response_checks,
        },
        "levels": {"L1": l1, "L2": l2, "L3": l3, "L4": l4},
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


def run_endpoint(protocol: str, prepared: list[dict]) -> list[dict]:
    cmd = ["./scripts/replay/run_protocol_peer_endpoint.sh", protocol.lower()]
    for item in prepared:
        if item["case"]["protocol"] == protocol:
            cmd.extend([item["case"]["id"], item["payload"].hex()])
    return parse_endpoint_output(run(cmd).stdout)


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
    prepared = prepare_payloads()
    if not args.live:
        result = {
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "result": "DRY-RUN",
            "safety": "no SCTP association created; JSON payload generation and L2 validation only",
            "cases": [
                {
                    "case_id": item["case"]["id"],
                    "json_input_path": item["case"]["json_input_path"],
                    "json_generated_payload_sha256": item["json_generated_payload_sha256"],
                    "l2_tshark": item["l2_tshark"],
                }
                for item in prepared
            ],
        }
        write_result(args.output, result)
        print("[DRY-RUN] JSON-driven F1AP/E1AP payload generation and L2 validation")
        return 0 if all(item["l2_tshark"]["passed"] for item in prepared) else 1

    test_error: str | None = None
    restore_error: str | None = None
    evaluated: list[dict] = []
    try:
        run(["./scripts/env/check_core_ready.sh"])
        prepare_isolated_peer_scenario()
        log_offset = len(cu_cp_logs())
        endpoint_results = run_endpoint("F1AP", prepared) + run_endpoint("E1AP", prepared)
        raw_by_id = {result["case_id"]: result for result in endpoint_results}
        if len(raw_by_id) != len(CASES):
            raise ValueError(f"expected {len(CASES)} endpoint cases, received {len(raw_by_id)}")
        peer_lines = cu_cp_logs()[log_offset:]
        evaluated = [
            evaluate_case(item, raw_by_id[item["case"]["id"]], peer_lines) for item in prepared
        ]
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        test_error = str(exc)
    finally:
        restored = run(["./scripts/env/restore_baseline.sh"], check=False)
        if restored.returncode != 0:
            restore_error = (restored.stdout + restored.stderr).strip()

    complete_l3 = sum(
        case["levels"]["L3"] and case["payload_hashes"]["all_equal"] for case in evaluated
    )
    all_l2 = len(evaluated) == len(CASES) and all(case["levels"]["L2"] for case in evaluated)
    all_hashes_equal = len(evaluated) == len(CASES) and all(
        case["payload_hashes"]["all_equal"] for case in evaluated
    )
    f1_l4 = any(case["protocol"] == "F1AP" and case["levels"]["L4"] for case in evaluated)
    e1_l4 = any(case["protocol"] == "E1AP" and case["levels"]["L4"] for case in evaluated)
    passed = (
        test_error is None
        and restore_error is None
        and all_l2
        and all_hashes_equal
        and complete_l3 >= 5
        and f1_l4
        and e1_l4
    )
    result = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if passed else "FAIL",
        "classification": "json_generated_same_payload_live_peer_validation",
        "requirements": {
            "all_generated_payloads_l2": all_l2,
            "all_json_pcap_sent_hashes_equal": all_hashes_equal,
            "at_least_five_complete_chain_l3": {
                "actual": complete_l3,
                "passed": complete_l3 >= 5,
            },
            "f1ap_at_least_one_strict_l4": f1_l4,
            "e1ap_at_least_one_strict_l4": e1_l4,
            "baseline_restored": restore_error is None,
        },
        "test_error": test_error,
        "restore_error": restore_error,
        "cases": evaluated,
    }
    write_result(args.output, result)
    print(f"[{result['result']}] JSON-driven same-payload F1AP/E1AP peer validation")
    print(args.output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

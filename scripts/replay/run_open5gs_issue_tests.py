#!/usr/bin/env python3
"""Run default-dry-run Open5GS issue-driven testcase replays."""

from __future__ import annotations

import argparse
import json
import re
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NRF_LOG_PATH = PROJECT_ROOT / "docker/open5gs-5gc/log/nrf.log"
AMF_LOG_PATH = PROJECT_ROOT / "docker/open5gs-5gc/log/amf.log"
SMF_LOG_PATH = PROJECT_ROOT / "docker/open5gs-5gc/log/smf.log"
UPF_LOG_PATH = PROJECT_ROOT / "docker/open5gs-5gc/log/upf.log"
CURL_BODY_PATH = "/tmp/open5gs_issue_body.txt"
CURL_MARKER = "__CODE__:"
DEFAULT_CASE = Path("tests/replay/open5gs_issues/nrf_requester_features_overflow.json")
DEFAULT_OUTPUT = Path("json/replay_results/stage5c6/open5gs_issue_results.json")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="send the issue payload into the local Docker Open5GS environment",
    )
    parser.add_argument(
        "--case",
        type=Path,
        default=DEFAULT_CASE,
        help="issue testcase JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="structured result JSON path",
    )
    return parser.parse_args(argv)


def load_case(path: Path) -> dict:
    case = json.loads(path.read_text(encoding="utf-8"))
    required = ["schema_version", "id", "component", "protocol", "transport", "target"]
    missing = [field for field in required if field not in case]
    if missing:
        raise ValueError(f"{path}: missing required fields: {', '.join(missing)}")
    if case["schema_version"] != 1:
        raise ValueError(f"{path}: unsupported schema_version={case['schema_version']}")
    if not case["target"].get("container"):
        raise ValueError(f"{path}: target.container is required")
    fatal_keywords = case.get("detection", {}).get("fatal_keywords", [])
    if not fatal_keywords:
        raise ValueError(f"{path}: detection.fatal_keywords is required")
    if case["protocol"] == "SBI":
        method = case["target"].get("method")
        if method not in {"GET", "POST", "PUT"}:
            raise ValueError(f"{path}: only GET/POST/PUT SBI issue cases are supported")
        if not case["transport"].get("sender_container"):
            raise ValueError(f"{path}: transport.sender_container is required")
        if method == "GET" and "query" not in case:
            raise ValueError(f"{path}: query is required for SBI issue cases")
        if method in {"POST", "PUT"} and "query" not in case and "body" not in case:
            raise ValueError(f"{path}: body or query is required for SBI {method} issue cases")
    elif case["protocol"] == "NAS_NGAP_SBI":
        sequence = case.get("sequence", {})
        if case["transport"].get("kind") != "ueransim_cli":
            raise ValueError(f"{path}: NAS_NGAP_SBI requires transport.kind=ueransim_cli")
        if not case["transport"].get("ue_container") or not case["transport"].get("ue_node"):
            raise ValueError(f"{path}: transport.ue_container and transport.ue_node are required")
        if sequence.get("iterations", 0) < 1:
            raise ValueError(f"{path}: sequence.iterations must be positive")
        if not sequence.get("deregister_command"):
            raise ValueError(f"{path}: sequence.deregister_command is required")
    elif case["protocol"] == "PFCP":
        if case["transport"].get("kind") != "pfcp_udp":
            raise ValueError(f"{path}: PFCP requires transport.kind=pfcp_udp")
        for field in ["sender_container", "target_host", "target_port"]:
            if not case["transport"].get(field):
                raise ValueError(f"{path}: transport.{field} is required")
        mutation = case.get("mutation", {})
        if mutation.get("pfcp_message") != "SessionModificationRequest":
            raise ValueError(f"{path}: only PFCP SessionModificationRequest is supported")
        if mutation.get("group_ie") != "CreateFAR":
            raise ValueError(f"{path}: only CreateFAR mutation is supported")
    else:
        raise ValueError(f"{path}: unsupported protocol={case['protocol']}")
    return case


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to decode JSON: {text}") from exc


def inspect_container(container: str) -> dict:
    result = run(
        [
            "docker",
            "inspect",
            container,
            "--format",
            "{{json .}}",
        ],
        check=False,
    )
    if result.returncode != 0:
        return {
            "container": container,
            "exists": False,
            "inspect_error": (result.stderr or result.stdout).strip(),
        }
    inspected = safe_json(result.stdout.strip())
    state = inspected.get("State", {})
    return {
        "container": container,
        "exists": True,
        "status": state.get("Status"),
        "running": state.get("Running"),
        "paused": state.get("Paused"),
        "restarting": state.get("Restarting"),
        "oom_killed": state.get("OOMKilled"),
        "dead": state.get("Dead"),
        "pid": state.get("Pid"),
        "exit_code": state.get("ExitCode"),
        "error": state.get("Error"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "restart_count": inspected.get("RestartCount", 0),
        "health": (state.get("Health") or {}).get("Status"),
    }


def current_network_name(container: str) -> str | None:
    result = run(
        [
            "docker",
            "inspect",
            container,
            "--format",
            "{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}",
        ],
        check=False,
    )
    value = ", ".join(result.stdout.split())
    return value or None


def component_log_path(component: str) -> Path:
    if component == "nrf":
        return NRF_LOG_PATH
    if component == "amf":
        return AMF_LOG_PATH
    if component == "smf":
        return SMF_LOG_PATH
    if component == "upf":
        return UPF_LOG_PATH
    raise ValueError(f"unsupported log component: {component}")


def log_lines(component: str) -> list[str]:
    path = component_log_path(component)
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def summarize_lines(lines: list[str], *, limit: int = 12, width: int = 240) -> list[str]:
    summary: list[str] = []
    for line in lines[-limit:]:
        summary.append(line if len(line) <= width else f"{line[: width - 3]}...")
    return summary


def keyword_hits(lines: list[str], keywords: list[str]) -> list[str]:
    lowered = [keyword.lower() for keyword in keywords]
    hits: list[str] = []
    for line in lines:
        text = line.lower()
        if any(keyword in text for keyword in lowered):
            hits.append(line)
    return hits


def core_ready() -> subprocess.CompletedProcess[str]:
    return run(["./scripts/env/check_core_ready.sh"], check=False)


def restore_baseline() -> subprocess.CompletedProcess[str]:
    return run(["./scripts/env/restore_baseline.sh"], check=False)


def request_url(case: dict) -> str:
    target = case["target"]
    transport = case["transport"]
    return (
        f"{transport.get('scheme', 'http')}://{target['host']}:{target['port']}{target['path']}"
    )


def request_summary(case: dict) -> dict:
    if case["protocol"] != "SBI":
        if case["protocol"] == "PFCP":
            mutation = case["mutation"]
            summary = {
                "kind": case["transport"].get("kind"),
                "sender_container": case["transport"].get("sender_container"),
                "source_port": case["transport"].get("source_port"),
                "target": f"{case['transport'].get('target_host')}:{case['transport'].get('target_port')}",
                "pfcp_message": mutation.get("pfcp_message"),
            }
            if mutation.get("pfcp_message") == "SessionModificationRequest":
                summary.update(
                    {
                        "group_ie": mutation.get("group_ie"),
                        "far_id": mutation.get("far_id"),
                        "apply_action": mutation.get("apply_action"),
                    }
                )
            elif mutation.get("pfcp_message") == "SessionEstablishmentRequest":
                summary.update(
                    {
                        "attack": mutation.get("attack"),
                        "pdr_count": mutation.get("pdr_count"),
                        "qer_id_base": mutation.get("qer_id_base"),
                        "teid_base": mutation.get("teid_base"),
                        "dnn": mutation.get("dnn"),
                    }
                )
            return summary
        sequence = case.get("sequence", {})
        return {
            "kind": case["transport"].get("kind"),
            "ue_container": case["transport"].get("ue_container"),
            "ue_node": case["transport"].get("ue_node"),
            "iterations": sequence.get("iterations"),
            "deregister_command": sequence.get("deregister_command"),
            "registration_timeout_seconds": sequence.get("registration_timeout_seconds"),
        }
    query = case.get("query", {})
    body = case.get("body")
    body_keys = list(body) if isinstance(body, dict) else []
    return {
        "method": case["target"]["method"],
        "url": request_url(case),
        "query_string": urlencode(query) if query else "",
        "query_keys": list(query),
        "body_keys": body_keys,
        "body_length": len(json.dumps(body, separators=(",", ":"))) if body is not None else 0,
        "requester_features_length": len(query.get("requester-features", "")),
    }


def send_request(case: dict) -> dict:
    sender = case["transport"]["sender_container"]
    method = case["target"]["method"]
    cmd = [
        "docker",
        "exec",
        sender,
        "curl",
        "-sS",
        "--http2-prior-knowledge",
        "-o",
        CURL_BODY_PATH,
        "-w",
        f"{CURL_MARKER}%{{http_code}}",
        "-X",
        method,
        request_url(case),
    ]
    if method == "GET":
        cmd.insert(8, "-G")
    for key, value in case.get("query", {}).items():
        cmd.extend(["--data-urlencode", f"{key}={value}"])
    if "body" in case:
        body_text = json.dumps(case["body"], separators=(",", ":"))
        for key, value in case.get("headers", {"Content-Type": "application/json"}).items():
            cmd.extend(["-H", f"{key}: {value}"])
        cmd.extend(["--data-binary", body_text])
    proc = run(cmd, check=False)
    body = run(["docker", "exec", sender, "cat", CURL_BODY_PATH], check=False)
    run(["docker", "exec", sender, "rm", "-f", CURL_BODY_PATH], check=False)
    http_status = None
    marker_index = proc.stdout.rfind(CURL_MARKER)
    if marker_index != -1:
        http_status = proc.stdout[marker_index + len(CURL_MARKER) :].strip() or None
    return {
        "command": " ".join(cmd[3:8]) + " ...",
        "curl_exit_code": proc.returncode,
        "curl_stdout": proc.stdout.strip(),
        "curl_stderr": proc.stderr.strip(),
        "http_status": int(http_status) if http_status and http_status.isdigit() else None,
        "response_body_excerpt": body.stdout[:500].strip(),
        "response_body_length": len(body.stdout),
    }


def ueransim_down() -> subprocess.CompletedProcess[str]:
    return run(["./scripts/env/run_ueransim_smoke.sh", "down"], check=False)


def ueransim_run() -> subprocess.CompletedProcess[str]:
    return run(["./scripts/env/run_ueransim_smoke.sh", "run"], check=False)


def nr_cli(case: dict, command: str) -> subprocess.CompletedProcess[str]:
    ue_container = case["transport"]["ue_container"]
    ue_node = case["transport"]["ue_node"]
    return run(
        [
            "docker",
            "exec",
            ue_container,
            "sh",
            "-lc",
            f"cd /UERANSIM/build && ./nr-cli {ue_node} --exec {json.dumps(command)}",
        ],
        check=False,
    )


def ue_logs(case: dict, *, tail: int = 400) -> str:
    return run(
        ["docker", "logs", "--tail", str(tail), case["transport"]["ue_container"]],
        check=False,
    ).stdout


def wait_for_ue_registered(case: dict, timeout: int) -> tuple[bool, list[dict]]:
    observations: list[dict] = []
    for _ in range(timeout):
        status = nr_cli(case, "status")
        output = (status.stdout + status.stderr).strip()
        registered = (
            status.returncode == 0
            and "rm-state: RM-REGISTERED" in output
            and "mm-state: MM-REGISTERED" in output
        )
        observations.append(
            {
                "returncode": status.returncode,
                "registered": registered,
                "status_excerpt": summarize_lines(output.splitlines(), limit=12),
            }
        )
        if registered:
            return True, observations[-5:]
        time.sleep(1)
    return False, observations[-5:]


def classify_result(
    *,
    request: dict,
    before: dict,
    after: dict,
    fatal_hits: list[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    restart_delta = (after.get("restart_count") or 0) - (before.get("restart_count") or 0)
    running_after = after.get("running") is True and after.get("status") == "running"
    if restart_delta > 0:
        reasons.append(f"restart_count increased by {restart_delta}")
    if after.get("exists") and not running_after:
        reasons.append(f"container status became {after.get('status')}")
    if fatal_hits:
        reasons.append(f"fatal keyword hits={len(fatal_hits)}")
    if reasons:
        return "VULNERABLE_CRASH", reasons

    status = request.get("http_status")
    if request.get("curl_exit_code") == 0 and status is not None and status >= 400 and running_after:
        return "SAFE_REJECT", [f"HTTP {status} returned while target stayed alive"]
    if request.get("curl_exit_code") == 0 and status is not None and running_after:
        return "NOT_REPRODUCED", [f"HTTP {status} returned without crash indicators"]
    if request.get("curl_exit_code") != 0 and running_after:
        return "INFRA_FAIL", ["request transport failed without crash indicators"]
    return "INFRA_FAIL", ["unable to classify request outcome"]


def live_result(case: dict) -> dict:
    if case["protocol"] == "NAS_NGAP_SBI":
        return live_ueransim_dereg_rereg_result(case)
    if case["protocol"] == "PFCP":
        return live_pfcp_session_modification_result(case)

    if core_ready().returncode != 0:
        return {
            "classification": "INFRA_FAIL",
            "result": "FAIL",
            "error": "baseline is not healthy before live execution",
            "baseline_ready_before_live": False,
        }

    before_lines = log_lines(case["component"])
    before_state = inspect_container(case["target"]["container"])
    request = send_request(case)
    time.sleep(2)
    after_state = inspect_container(case["target"]["container"])
    after_lines = log_lines(case["component"])
    new_lines = after_lines[len(before_lines) :]
    fatal_hits = keyword_hits(new_lines, case["detection"]["fatal_keywords"])
    classification, reasons = classify_result(
        request=request,
        before=before_state,
        after=after_state,
        fatal_hits=fatal_hits,
    )
    log_delta = {
        "new_line_count": len(new_lines),
        "fatal_keyword_hits": summarize_lines(fatal_hits, limit=8),
        "tail_excerpt": summarize_lines(new_lines),
    }
    return {
        "classification": classification,
        "result": "PASS" if classification != "INFRA_FAIL" else "FAIL",
        "baseline_ready_before_live": True,
        "request": request,
        "target_before": before_state,
        "target_after": after_state,
        "restart_count_delta": (after_state.get("restart_count") or 0)
        - (before_state.get("restart_count") or 0),
        "log_delta": log_delta,
        f"{case['component']}_log_delta": log_delta,
        "reasons": reasons,
    }


def classify_sequence_result(
    *,
    before: dict,
    after: dict,
    fatal_hits: list[str],
    observations: list[dict],
    required_hits: dict[str, bool],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    restart_delta = (after.get("restart_count") or 0) - (before.get("restart_count") or 0)
    running_after = after.get("running") is True and after.get("status") == "running"
    if restart_delta > 0:
        reasons.append(f"restart_count increased by {restart_delta}")
    if after.get("exists") and not running_after:
        reasons.append(f"container status became {after.get('status')}")
    if fatal_hits:
        reasons.append(f"fatal keyword hits={len(fatal_hits)}")
    if reasons:
        return "VULNERABLE_CRASH", reasons

    failed_iterations = [item for item in observations if not item.get("registered_after")]
    if failed_iterations:
        return "INFRA_FAIL", [f"{len(failed_iterations)} iteration(s) did not re-register"]
    if all(required_hits.values()) and running_after:
        return "NOT_REPRODUCED", ["deregistration/re-registration sequence completed without AMF crash"]
    missing = [name for name, observed in required_hits.items() if not observed]
    return "INFRA_FAIL", [f"missing required observations: {', '.join(missing)}"]


def live_ueransim_dereg_rereg_result(case: dict) -> dict:
    if core_ready().returncode != 0:
        return {
            "classification": "INFRA_FAIL",
            "result": "FAIL",
            "error": "baseline is not healthy before live execution",
            "baseline_ready_before_live": False,
        }

    sequence = case["sequence"]
    setup = ueransim_run()
    if setup.returncode != 0:
        return {
            "classification": "INFRA_FAIL",
            "result": "FAIL",
            "baseline_ready_before_live": True,
            "setup": {
                "returncode": setup.returncode,
                "stdout": summarize_lines((setup.stdout + setup.stderr).splitlines()),
            },
            "error": "UERANSIM smoke setup failed",
        }

    initial_registered, initial_status = wait_for_ue_registered(
        case, int(sequence.get("registration_timeout_seconds", 35))
    )
    if not initial_registered:
        return {
            "classification": "INFRA_FAIL",
            "result": "FAIL",
            "baseline_ready_before_live": True,
            "setup": {"returncode": setup.returncode},
            "initial_status": initial_status,
            "error": "UERANSIM UE did not reach registered state before sequence",
        }

    before_lines = log_lines(case["component"])
    before_state = inspect_container(case["target"]["container"])
    observations: list[dict] = []
    for index in range(int(sequence["iterations"])):
        dereg = nr_cli(case, sequence["deregister_command"])
        registered, status_tail = wait_for_ue_registered(
            case, int(sequence.get("registration_timeout_seconds", 35))
        )
        observations.append(
            {
                "iteration": index + 1,
                "deregister_returncode": dereg.returncode,
                "deregister_stdout": summarize_lines((dereg.stdout + dereg.stderr).splitlines()),
                "registered_after": registered,
                "status_tail": status_tail,
            }
        )
        time.sleep(float(sequence.get("settle_seconds", 2)))

    after_state = inspect_container(case["target"]["container"])
    after_lines = log_lines(case["component"])
    new_lines = after_lines[len(before_lines) :]
    fatal_hits = keyword_hits(new_lines, case["detection"]["fatal_keywords"])
    required_hits = {
        required: any(required in line for line in new_lines)
        for required in case.get("detection", {}).get("required_observations", [])
    }
    classification, reasons = classify_sequence_result(
        before=before_state,
        after=after_state,
        fatal_hits=fatal_hits,
        observations=observations,
        required_hits=required_hits,
    )
    return {
        "classification": classification,
        "result": "PASS" if classification != "INFRA_FAIL" else "FAIL",
        "baseline_ready_before_live": True,
        "setup": {
            "returncode": setup.returncode,
            "stdout": summarize_lines((setup.stdout + setup.stderr).splitlines()),
        },
        "target_before": before_state,
        "target_after": after_state,
        "restart_count_delta": (after_state.get("restart_count") or 0)
        - (before_state.get("restart_count") or 0),
        "sequence_observations": observations,
        "required_observations": required_hits,
        "amf_log_delta": {
            "new_line_count": len(new_lines),
            "fatal_keyword_hits": summarize_lines(fatal_hits, limit=8),
            "tail_excerpt": summarize_lines(new_lines),
        },
        "ue_log_tail": summarize_lines(ue_logs(case).splitlines(), limit=20),
        "reasons": reasons,
    }


def pfcp_ie(ie_type: int, payload: bytes) -> bytes:
    return struct.pack("!HH", ie_type, len(payload)) + payload


def pfcp_group_ie(ie_type: int, children: list[bytes]) -> bytes:
    return pfcp_ie(ie_type, b"".join(children))


def build_pfcp_create_far_session_modification(*, seid: int, sequence: int, far_id: int, apply_action: int) -> bytes:
    # IE type IDs from 3GPP TS 29.244: Create FAR=3, Apply Action=44, FAR ID=108.
    create_far = pfcp_group_ie(
        3,
        [
            pfcp_ie(108, struct.pack("!I", far_id)),
            pfcp_ie(44, struct.pack("!B", apply_action)),
        ],
    )
    payload = create_far
    header_payload_len = 8 + 4 + len(payload)
    # PFCP v1 with S flag, message type 52 = Session Modification Request.
    return (
        struct.pack("!BBH", 0x21, 52, header_payload_len)
        + struct.pack("!Q", seid)
        + sequence.to_bytes(3, "big")
        + b"\x00"
        + payload
    )


def pfcp_ipv4(address: str) -> bytes:
    return socket.inet_aton(address)


def parse_pfcp_response(response_hex: str) -> dict:
    if not response_hex:
        return {"received": False}
    data = bytes.fromhex(response_hex)
    if len(data) < 16:
        return {"received": True, "malformed": True, "length": len(data)}
    flags, msg_type, length = struct.unpack("!BBH", data[:4])
    offset = 16 if flags & 0x01 else 8
    parsed = {
        "received": True,
        "flags": flags,
        "message_type": msg_type,
        "length": length,
        "seid": struct.unpack("!Q", data[4:12])[0] if flags & 0x01 else None,
        "sequence": int.from_bytes(data[12:15] if flags & 0x01 else data[4:7], "big"),
        "cause": None,
        "offending_ie": None,
    }
    while offset + 4 <= len(data):
        ie_type, ie_len = struct.unpack("!HH", data[offset : offset + 4])
        value = data[offset + 4 : offset + 4 + ie_len]
        if len(value) != ie_len:
            break
        if ie_type == 19 and ie_len >= 1:
            parsed["cause"] = value[0]
        elif ie_type == 40 and ie_len >= 2:
            parsed["offending_ie"] = int.from_bytes(value[:2], "big")
        offset += 4 + ie_len
    return parsed


def latest_upf_fseid() -> dict | None:
    pattern = re.compile(
        r"UE F-SEID\[UP:0x([0-9a-fA-F]+) CP:0x([0-9a-fA-F]+)\].*IPv4\[([^\]]*)\]"
    )
    for line in reversed(log_lines("upf")):
        match = pattern.search(line)
        if match:
            return {
                "up_seid": int(match.group(1), 16),
                "cp_seid": int(match.group(2), 16),
                "ue_ipv4": match.group(3),
                "log_line": line,
            }
    return None


def send_pfcp_from_container(case: dict, payload: bytes, timeout: int) -> dict:
    transport = case["transport"]
    if transport.get("source_port"):
        code = r"""
import random
import socket
import struct
import sys


def checksum(data):
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for index in range(0, len(data), 2):
        total += (data[index] << 8) + data[index + 1]
    while total > 0xFFFF:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


payload = bytes.fromhex(sys.argv[1])
host = sys.argv[2]
dst_port = int(sys.argv[3])
src_port = int(sys.argv[4])

dst_ip = socket.gethostbyname(host)
route_probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
route_probe.connect((dst_ip, dst_port))
src_ip = route_probe.getsockname()[0]
route_probe.close()

udp_length = 8 + len(payload)
udp_header = struct.pack("!HHHH", src_port, dst_port, udp_length, 0)
total_length = 20 + udp_length
packet_id = random.randrange(0, 0x10000)
ip_header_without_checksum = struct.pack(
    "!BBHHHBBH4s4s",
    0x45,
    0,
    total_length,
    packet_id,
    0,
    64,
    socket.IPPROTO_UDP,
    0,
    socket.inet_aton(src_ip),
    socket.inet_aton(dst_ip),
)
ip_header = struct.pack(
    "!BBHHHBBH4s4s",
    0x45,
    0,
    total_length,
    packet_id,
    0,
    64,
    socket.IPPROTO_UDP,
    checksum(ip_header_without_checksum),
    socket.inet_aton(src_ip),
    socket.inet_aton(dst_ip),
)

packet = ip_header + udp_header + payload
sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
sock.sendto(packet, (dst_ip, dst_port))
print("RAW_SEND=%s:%s>%s:%s" % (src_ip, src_port, dst_ip, dst_port))
print("RESPONSE_HEX=")
print("RESPONSE_FROM=")
"""
        return run(
            [
                "docker",
                "exec",
                transport["sender_container"],
                "python3",
                "-c",
                code,
                payload.hex(),
                transport["target_host"],
                str(transport["target_port"]),
                str(transport["source_port"]),
            ],
            check=False,
        )
    code = r"""
import binascii
import socket
import sys

payload = bytes.fromhex(sys.argv[1])
host = sys.argv[2]
port = int(sys.argv[3])
timeout = float(sys.argv[4])

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(timeout)
sock.sendto(payload, (host, port))
try:
    data, addr = sock.recvfrom(4096)
    print("RESPONSE_HEX=" + data.hex())
    print("RESPONSE_FROM=%s:%s" % addr)
except socket.timeout:
    print("RESPONSE_HEX=")
    print("RESPONSE_FROM=")
"""
    return run(
        [
            "docker",
            "exec",
            transport["sender_container"],
            "python3",
            "-c",
            code,
            payload.hex(),
            transport["target_host"],
            str(transport["target_port"]),
            str(timeout),
        ],
        check=False,
    )


def live_pfcp_session_modification_result(case: dict) -> dict:
    if core_ready().returncode != 0:
        return {
            "classification": "INFRA_FAIL",
            "result": "FAIL",
            "error": "baseline is not healthy before live execution",
            "baseline_ready_before_live": False,
        }

    mutation = case["mutation"]
    setup: subprocess.CompletedProcess[str] | None = None
    fseid = None
    if mutation["pfcp_message"] == "SessionModificationRequest":
        setup = ueransim_run()
        if setup.returncode != 0:
            return {
                "classification": "INFRA_FAIL",
                "result": "FAIL",
                "baseline_ready_before_live": True,
                "setup": {
                    "returncode": setup.returncode,
                    "stdout": summarize_lines((setup.stdout + setup.stderr).splitlines()),
                },
                "error": "UERANSIM smoke setup failed",
            }

        fseid = latest_upf_fseid()
        if not fseid:
            return {
                "classification": "INFRA_FAIL",
                "result": "FAIL",
                "baseline_ready_before_live": True,
                "setup": {"returncode": setup.returncode},
                "error": "failed to extract UPF F-SEID from logs after PDU session setup",
            }

    before_upf_lines = log_lines("upf")
    before_smf_lines = log_lines("smf")
    before_state = inspect_container(case["target"]["container"])
    sequence_number = int(time.time()) & 0xFFFFFF
    payload = build_pfcp_create_far_session_modification(
        seid=fseid["up_seid"],
        sequence=sequence_number,
        far_id=int(mutation["far_id"]),
        apply_action=int(mutation["apply_action"]),
    )
    pfcp_request = {
        "message_type": "SessionModificationRequest",
        "sequence": sequence_number,
        "payload_hex": payload.hex(),
        "payload_length": len(payload),
        "far_id": int(mutation["far_id"]),
        "apply_action": int(mutation["apply_action"]),
    }
    sent = send_pfcp_from_container(
        case,
        payload,
        int(case.get("sequence", {}).get("response_timeout_seconds", 5)),
    )
    time.sleep(2)
    after_state = inspect_container(case["target"]["container"])
    after_upf_lines = log_lines("upf")
    after_smf_lines = log_lines("smf")
    upf_delta = after_upf_lines[len(before_upf_lines) :]
    smf_delta = after_smf_lines[len(before_smf_lines) :]
    fatal_hits = keyword_hits(upf_delta + smf_delta, case["detection"]["fatal_keywords"])
    error_hits = keyword_hits(upf_delta + smf_delta, case["detection"].get("pfcp_error_keywords", []))
    response_hex = ""
    response_from = ""
    for line in sent.stdout.splitlines():
        if line.startswith("RESPONSE_HEX="):
            response_hex = line.split("=", 1)[1].strip()
        elif line.startswith("RESPONSE_FROM="):
            response_from = line.split("=", 1)[1].strip()
    response = parse_pfcp_response(response_hex)
    classification, reasons = classify_pfcp_result(
        before=before_state,
        after=after_state,
        fatal_hits=fatal_hits,
        error_hits=error_hits,
        response=response,
    )
    return {
        "classification": classification,
        "result": "PASS" if classification != "INFRA_FAIL" else "FAIL",
        "baseline_ready_before_live": True,
        "setup": (
            {
                "returncode": setup.returncode,
                "stdout": summarize_lines((setup.stdout + setup.stderr).splitlines()),
            }
            if setup is not None
            else {"returncode": 0, "stdout": ["baseline_only: no UE setup required"]}
        ),
        "target_before": before_state,
        "target_after": after_state,
        "restart_count_delta": (after_state.get("restart_count") or 0)
        - (before_state.get("restart_count") or 0),
        "pfcp_session": fseid,
        "pfcp_request": pfcp_request,
        "pfcp_send": {
            "returncode": sent.returncode,
            "stdout": summarize_lines((sent.stdout + sent.stderr).splitlines()),
            "response_from": response_from,
        },
        "pfcp_response": response,
        "upf_log_delta": {
            "new_line_count": len(upf_delta),
            "pfcp_error_hits": summarize_lines(error_hits, limit=8),
            "fatal_keyword_hits": summarize_lines(fatal_hits, limit=8),
            "tail_excerpt": summarize_lines(upf_delta),
        },
        "smf_log_delta": {
            "new_line_count": len(smf_delta),
            "tail_excerpt": summarize_lines(smf_delta, limit=8),
        },
        "reasons": reasons,
    }


def classify_pfcp_result(
    *,
    before: dict,
    after: dict,
    fatal_hits: list[str],
    error_hits: list[str],
    response: dict,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    restart_delta = (after.get("restart_count") or 0) - (before.get("restart_count") or 0)
    running_after = after.get("running") is True and after.get("status") == "running"
    if restart_delta > 0:
        reasons.append(f"restart_count increased by {restart_delta}")
    if after.get("exists") and not running_after:
        reasons.append(f"container status became {after.get('status')}")
    if fatal_hits:
        reasons.append(f"fatal keyword hits={len(fatal_hits)}")
    if reasons:
        return "VULNERABLE_CRASH", reasons

    cause = response.get("cause")
    if response.get("received") and cause == 1 and running_after:
        return "ACCEPTED_OR_FIXED_BEHAVIOR", ["PFCP Session Modification accepted by UPF"]
    if response.get("received") and cause and cause != 1 and running_after:
        out = [f"PFCP response cause={cause}"]
        if error_hits:
            out.append(f"PFCP error log hits={len(error_hits)}")
        return "PFCP_ERROR_NO_IMPACT", out
    if error_hits and running_after:
        return "PFCP_ERROR_NO_IMPACT", [f"PFCP error log hits={len(error_hits)}"]
    if response.get("received") is False and running_after:
        return "NOT_REPRODUCED", ["no PFCP response and no crash/error indicators"]
    return "INFRA_FAIL", ["unable to classify PFCP testcase outcome"]


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    case = load_case(args.case)
    generated_at = datetime.now(timezone.utc).isoformat()
    target_container = case["target"]["container"]
    result: dict = {
        "schema_version": 1,
        "generated_at": generated_at,
        "mode": "live" if args.live else "dry-run",
        "case_id": case["id"],
        "issue": case.get("issue"),
        "fix": case.get("fix"),
        "component": case["component"],
        "protocol": case["protocol"],
        "open5gs_image": run(
            ["docker", "inspect", "nrf", "--format", "{{.Config.Image}}"], check=False
        ).stdout.strip(),
        "docker_network": current_network_name(target_container),
        "request_summary": request_summary(case),
    }

    if not args.live:
        result.update(
            {
                "classification": "DRY_RUN",
                "result": "DRY-RUN",
                "safety": "no live SBI request sent; use --live to execute against Docker Open5GS",
                "target_before": inspect_container(target_container),
                "baseline_ready_now": core_ready().returncode == 0,
            }
        )
        write_json(args.output, result)
        print("[DRY-RUN] Open5GS issue testcase validated without sending traffic")
        print(args.output)
        return 0

    live = None
    restore = None
    try:
        live = live_result(case)
        result.update(live)
    finally:
        restore = restore_baseline()
        ready = core_ready()
        result["baseline_restore"] = {
            "restore_exit_code": restore.returncode,
            "restore_stdout": summarize_lines((restore.stdout + restore.stderr).splitlines()),
            "core_ready_exit_code": ready.returncode,
            "core_ready_stdout": summarize_lines((ready.stdout + ready.stderr).splitlines(), limit=4),
            "restored": restore.returncode == 0 and ready.returncode == 0,
        }

    write_json(args.output, result)
    print(f"[{result['classification']}] Open5GS issue testcase")
    print(args.output)
    restore_ok = result["baseline_restore"]["restored"]
    if result["classification"] == "INFRA_FAIL" or not restore_ok:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

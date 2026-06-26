#!/usr/bin/env python3
"""Replay a GTP-U downlink packet against the current isolated UE session."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from encode_gtpu import build_ethernet, build_ipv4, write_pcap


CU_UP = "srsran_cu_up"
UPF = "upf"
UE = "srsue_5g_zmq"
SOURCE_INNER_IP = "198.18.0.1"


def run(cmd: list[str], *, input_text: str | None = None, check: bool = True) -> str:
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        input=input_text,
        capture_output=True,
    ).stdout


def combined_logs(container: str) -> str:
    result = subprocess.run(
        ["docker", "logs", container],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.stdout


def require_running(container: str) -> None:
    running = run(["docker", "inspect", "-f", "{{.State.Running}}", container], check=False).strip()
    if running != "true":
        raise RuntimeError(f"required container is not running: {container}")


def current_session() -> dict:
    cu_up_logs = combined_logs(CU_UP)
    rx_matches = re.findall(
        r"DL teid=(0x[0-9a-fA-F]+): GTPU NGU Rx configured.*local_teid=(0x[0-9a-fA-F]+)",
        cu_up_logs,
    )
    tx_matches = re.findall(
        r"UL teid=(0x[0-9a-fA-F]+): GTPU NGU Tx configured.*"
        r"peer_teid=(0x[0-9a-fA-F]+) peer_addr=([0-9.]+) peer_port=(\d+)",
        cu_up_logs,
    )
    if not rx_matches or not tx_matches:
        raise RuntimeError("could not find an active NG-U tunnel in CU-UP logs")
    downlink_teid = rx_matches[-1][1]
    configured_at = cu_up_logs.rfind(f"GTPU NGU Rx configured. node=ngu local_teid={downlink_teid}")
    removed_at = cu_up_logs.rfind(f"Tunnel removed. teid={downlink_teid}")
    if removed_at > configured_at:
        raise RuntimeError(f"the most recent NG-U tunnel {downlink_teid} has already been removed")

    ue_addr = run(
        ["docker", "exec", UE, "sh", "-lc", "ip -4 -o addr show tun_srsue | awk '{print $4}'"]
    ).strip()
    if not ue_addr:
        raise RuntimeError("could not find the current UE tunnel address")
    ue_ip = str(ipaddress.ip_interface(ue_addr).ip)

    peer_teid, configured_peer_teid, configured_upf, peer_port = tx_matches[-1]
    cu_up_addresses = run(
        ["docker", "exec", CU_UP, "sh", "-lc", "ip -4 -o addr show scope global | awk '{print $4}'"]
    ).splitlines()
    upf_addresses = run(
        ["docker", "exec", UPF, "sh", "-lc", "ip -4 -o addr show scope global | awk '{print $4}'"]
    ).splitlines()
    upf_endpoint = str(ipaddress.ip_address(configured_upf))
    if not any(str(ipaddress.ip_interface(value).ip) == upf_endpoint for value in upf_addresses):
        raise RuntimeError("configured NG-U peer address is not present in the UPF namespace")
    cu_up_endpoint = next(
        (
            str(interface.ip)
            for value in cu_up_addresses
            if ipaddress.ip_address(upf_endpoint) in (interface := ipaddress.ip_interface(value)).network
        ),
        None,
    )
    if cu_up_endpoint is None:
        raise RuntimeError("could not find the CU-UP endpoint on the active NG-U network")
    if peer_teid != configured_peer_teid:
        raise RuntimeError("current CU-UP tunnel log does not match the UPF network endpoint")
    if not ipaddress.ip_address(cu_up_endpoint).is_private or not ipaddress.ip_address(upf_endpoint).is_private:
        raise RuntimeError("live replay is restricted to private local endpoints")

    return {
        "cu_up_endpoint": cu_up_endpoint,
        "upf_endpoint": upf_endpoint,
        "upf_port": int(peer_port),
        "downlink_teid": downlink_teid,
        "uplink_teid": peer_teid,
        "ue_ip": ue_ip,
        "qfi": 1,
    }


def checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_gtpu_payload(session: dict) -> bytes:
    src = ipaddress.IPv4Address(SOURCE_INNER_IP).packed
    dst = ipaddress.IPv4Address(session["ue_ip"]).packed
    body = b"STAGE5C4-LIVE-GTPU"
    icmp_header = struct.pack("!BBHHH", 0, 0, 0, 0x5C04, 1)
    icmp = struct.pack("!BBHHH", 0, 0, checksum(icmp_header + body), 0x5C04, 1) + body
    ip_header = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, 20 + len(icmp), 0x5C04, 0, 64, 1, 0, src, dst
    )
    ip_header = ip_header[:10] + struct.pack("!H", checksum(ip_header)) + ip_header[12:]
    inner = ip_header + icmp
    teid = int(session["downlink_teid"], 0)
    gtpu = struct.pack("!BBHI", 0x34, 0xFF, 8 + len(inner), teid)
    return gtpu + b"\0\0\0\x85\x01\x00" + bytes([session["qfi"]]) + b"\0" + inner


def send_from_upf(session: dict, payload: bytes) -> None:
    sender = r"""
import socket
import sys

config = __import__("json").loads(sys.stdin.read())
gtpu = bytes.fromhex(config["payload_hex"])
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(gtpu, (config["cu_up_endpoint"], 2152))
print(len(gtpu))
"""
    config = {"cu_up_endpoint": session["cu_up_endpoint"], "payload_hex": payload.hex()}
    run(["docker", "exec", "-i", UPF, "python3", "-c", sender], input_text=json.dumps(config))


def verify_l2(session: dict, payload: bytes) -> dict:
    udp = struct.pack("!HHHH", 2152, 2152, 8 + len(payload), 0) + payload
    outer = build_ipv4(
        {
            "src": session["upf_endpoint"],
            "dst": session["cu_up_endpoint"],
            "ttl": 64,
            "identification": "0x5c04",
        },
        17,
        udp,
    )
    packet = build_ethernet(
        {"src": "02:00:00:00:00:03", "dst": "02:00:00:00:00:05"},
        outer,
    )
    with tempfile.TemporaryDirectory(prefix="stage5c4-gtpu-l2-") as directory:
        pcap = Path(directory) / "generated.pcap"
        write_pcap(pcap, [packet])
        recognized = run(
            [
                "tshark",
                "-r",
                str(pcap),
                "-Y",
                f"gtp && gtp.teid == {int(session['downlink_teid'], 0)}",
                "-T",
                "fields",
                "-e",
                "gtp.teid",
            ],
            check=False,
        )
        malformed = run(
            [
                "tshark",
                "-r",
                str(pcap),
                "-Y",
                "_ws.malformed",
                "-T",
                "fields",
                "-e",
                "frame.number",
            ],
            check=False,
        )
    teids = [line for line in recognized.splitlines() if line]
    malformed_frames = [line for line in malformed.splitlines() if line]
    return {
        "protocol_and_teid_recognized": bool(teids),
        "malformed_frames": malformed_frames,
        "passed": bool(teids) and not malformed_frames,
    }


def wait_for_evidence(cu_up_before: int, ue_before: int, session: dict) -> tuple[dict, dict]:
    teid = session["downlink_teid"].lower()
    evidence = {"l3_peer_recognition": False, "l4_state_advance": False, "ue_received": False}
    for _ in range(30):
        cu_up_lines = combined_logs(CU_UP).splitlines()[cu_up_before:]
        ue_lines = combined_logs(UE).splitlines()[ue_before:]
        cu_up_new = "\n".join(cu_up_lines)
        ue_new = "\n".join(ue_lines)
        evidence["l3_peer_recognition"] = f"dl teid={teid}: rx sdu" in cu_up_new.lower()
        evidence["l4_state_advance"] = (
            evidence["l3_peer_recognition"]
            and "PDCP" in cu_up_new
            and "DL: TX PDU" in cu_up_new
            and "TX PDU" in cu_up_new
        )
        evidence["ue_received"] = "RX PDU" in ue_new
        if all(evidence.values()):
            break
        time.sleep(0.2)
    peer_receive_log = [
        line for line in cu_up_lines if f"dl teid={teid}: rx sdu" in line.lower()
    ]
    state_log = [
        line for line in cu_up_lines if "PDCP" in line or "DL: TX PDU" in line or "TX PDU" in line
    ][-12:]
    ue_receive_log = [line for line in ue_lines if "RX PDU" in line][-12:]
    return evidence, {
        "peer_receive_log": peer_receive_log,
        "state_advance_log": state_log,
        "ue_receive_log": ue_receive_log,
        "response_message": "CU-UP PDCP/F1-U transmit and UE RX PDU" if evidence["ue_received"] else None,
    }


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="send to the current local isolated session")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("json/replay_results/live_gtpu_result.json"),
        help="structured result path",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    for container in (CU_UP, UPF, UE):
        require_running(container)
    session = current_session()
    payload = build_gtpu_payload(session)
    l2 = verify_l2(session, payload)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if args.live else "dry-run",
        "protocol": "GTP-U",
        "case_id": "gtpu_generated_current_session_downlink",
        "generated_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "generated_payload_length": len(payload),
        "session": session,
        "levels": {"L1": True, "L2": l2["passed"], "L3": False, "L4": False},
        "checks": {"l2_tshark": l2},
    }
    if not args.live:
        result["checks"]["safety"] = "PASS: no packet sent; use --live only in the local isolated environment"
        write_result(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    run(["./scripts/env/check_core_ready.sh"])
    cu_up_before = len(combined_logs(CU_UP).splitlines())
    ue_before = len(combined_logs(UE).splitlines())
    result["send_time"] = datetime.now(timezone.utc).isoformat()
    send_from_upf(session, payload)
    evidence, trace = wait_for_evidence(cu_up_before, ue_before, session)
    run(["./scripts/env/check_core_ready.sh"])
    result["checks"].update(evidence)
    result["evidence"] = trace
    result["levels"]["L3"] = evidence["l3_peer_recognition"]
    result["levels"]["L4"] = evidence["l4_state_advance"] and evidence["ue_received"]
    result["result"] = "PASS" if all(result["levels"].values()) else "FAIL"
    write_result(args.output, result)
    print(f"[{result['result']}] GTP-U live replay {session['upf_endpoint']} -> {session['cu_up_endpoint']}")
    print(args.output)
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

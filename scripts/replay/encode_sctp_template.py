#!/usr/bin/env python3
"""Encode an extracted ASN.1 APER template as Ethernet/IPv4/SCTP DATA pcap."""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

from encode_gtpu import build_ethernet, build_ipv4, parse_int, write_pcap


def crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for octet in data:
        crc ^= octet
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def load_case(path: Path) -> dict:
    case = load_json(path)
    if case.get("schema_version") != 1:
        raise ValueError(f"{path}: unsupported schema_version")
    if case.get("protocol") not in {"F1AP", "E1AP", "XnAP", "NGAP"}:
        raise ValueError(f"{path}: unsupported SCTP application protocol")
    if not isinstance(case.get("template"), str):
        raise ValueError(f"{path}: template must be a path string")
    return case


def resolve_template(case: dict, case_path: Path | None = None) -> tuple[Path, dict]:
    template_path = Path(case["template"])
    if not template_path.is_absolute():
        root = Path.cwd()
        candidate = root / template_path
        if not candidate.exists() and case_path is not None:
            candidate = case_path.parent / template_path
        template_path = candidate
    return template_path, load_json(template_path)


def generate_control_payload(case: dict, template: dict) -> tuple[bytes, dict | None]:
    source = bytes.fromhex(template["payload"]["hex"])
    mutation = case.get("mutation")
    if mutation is None:
        return source, None
    if case["protocol"] not in {"F1AP", "E1AP"}:
        raise ValueError(f"{case['protocol']}: structured APER mutation is not supported")

    field = mutation["field"]
    value = mutation["value"]
    structured_ies = case.get("structured_ies", {})
    if field not in structured_ies:
        raise ValueError(f"mutation field {field} is missing from structured_ies")
    completed = subprocess.run(
        [
            str(Path(__file__).with_name("run_control_aper_mutator.sh")),
            case["protocol"],
            template["message"],
            source.hex(),
            field,
            str(value),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    json_lines = [line for line in completed.stdout.splitlines() if line.startswith("{")]
    if not json_lines:
        raise ValueError("APER mutator did not return structured output")
    metadata = json.loads(json_lines[-1])
    if metadata["before"] != structured_ies[field]:
        raise ValueError(
            f"{field}: structured source value {structured_ies[field]} does not match "
            f"decoded APER value {metadata['before']}"
        )
    if metadata["after"] != value:
        raise ValueError(f"{field}: APER mutation did not produce requested value {value}")
    payload = bytes.fromhex(metadata["payload_hex"])
    if payload == source:
        raise ValueError(f"{field}: APER payload did not change after mutation")
    return payload, metadata


def build_sctp_data(template: dict, payload: bytes | None = None) -> bytes:
    transport = template["transport"]
    source_payload = bytes.fromhex(template["payload"]["hex"])
    expected_length = parse_int(template["payload"]["length"], "payload.length", 0xFFFF_FFFF)
    if len(source_payload) != expected_length:
        raise ValueError(
            f"payload length mismatch: JSON={expected_length}, hex={len(source_payload)}"
        )
    if payload is None:
        payload = source_payload

    tsn = parse_int(transport.get("tsn", 0), "transport.tsn", 0xFFFF_FFFF)
    stream_id = parse_int(transport.get("stream_id", 0), "transport.stream_id", 0xFFFF)
    stream_sequence = parse_int(
        transport.get("stream_sequence", 0), "transport.stream_sequence", 0xFFFF
    )
    ppid = parse_int(transport["ppid"], "transport.ppid", 0xFFFF_FFFF)
    chunk_length = 16 + len(payload)
    chunk = struct.pack("!BBHIHHI", 0, 3, chunk_length, tsn, stream_id, stream_sequence, ppid)
    chunk += payload
    chunk += b"\x00" * ((-len(chunk)) % 4)
    return chunk


def encode_packet(
    case: dict, case_path: Path | None = None, payload: bytes | None = None
) -> bytes:
    _, template = resolve_template(case, case_path)
    direction = template["direction"]
    transport = template["transport"]
    if payload is None:
        payload, _ = generate_control_payload(case, template)
    chunk = build_sctp_data(template, payload)

    src_port = parse_int(transport["src_port"], "transport.src_port", 0xFFFF)
    dst_port = parse_int(transport["dst_port"], "transport.dst_port", 0xFFFF)
    verification_tag = parse_int(
        case.get("sctp", {}).get("verification_tag", "0x13579bdf"),
        "sctp.verification_tag",
        0xFFFF_FFFF,
    )
    common = struct.pack("!HHII", src_port, dst_port, verification_tag, 0)
    checksum = crc32c(common + chunk)
    sctp = common[:8] + struct.pack("<I", checksum) + chunk

    ipv4_config = {
        "src": direction["src_ip"],
        "dst": direction["dst_ip"],
        "ttl": case.get("ipv4", {}).get("ttl", 64),
        "identification": case.get("ipv4", {}).get("identification", "0x5c30"),
    }
    ip_packet = build_ipv4(ipv4_config, 132, sctp)
    ethernet = case.get(
        "ethernet",
        {"src": "02:00:00:00:00:04", "dst": "02:00:00:00:00:06"},
    )
    return build_ethernet(ethernet, ip_packet)


def extract_sctp_data_payload(packet: bytes) -> bytes:
    if len(packet) < 62:
        raise ValueError("encoded packet is shorter than Ethernet/IPv4/SCTP DATA headers")
    ip_header_length = (packet[14] & 0x0F) * 4
    chunk_offset = 14 + ip_header_length + 12
    if packet[chunk_offset] != 0:
        raise ValueError("first SCTP chunk is not DATA")
    chunk_length = struct.unpack("!H", packet[chunk_offset + 2 : chunk_offset + 4])[0]
    return packet[chunk_offset + 16 : chunk_offset + chunk_length]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="replay testcase JSON")
    parser.add_argument("-o", "--output", type=Path, required=True, help="output pcap path")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    case = load_case(args.case)
    _, template = resolve_template(case, args.case)
    payload, _ = generate_control_payload(case, template)
    packet = encode_packet(case, args.case, payload)
    if extract_sctp_data_payload(packet) != payload:
        raise ValueError("encoded SCTP payload is not reversible to the generated APER payload")
    write_pcap(args.output, [packet])
    print(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

#!/usr/bin/env python3
"""Encode a deterministic Ethernet/IPv4/UDP/GTP-U/IPv4/ICMP packet to pcap."""

from __future__ import annotations

import argparse
import ipaddress
import json
import struct
import sys
from pathlib import Path


def checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def parse_int(value: int | str, field: str, maximum: int) -> int:
    try:
        parsed = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer or integer string") from exc
    if not 0 <= parsed <= maximum:
        raise ValueError(f"{field} must be between 0 and {maximum}")
    return parsed


def mac_bytes(value: str) -> bytes:
    parts = value.split(":")
    if len(parts) != 6:
        raise ValueError(f"invalid MAC address: {value}")
    try:
        return bytes(int(part, 16) for part in parts)
    except ValueError as exc:
        raise ValueError(f"invalid MAC address: {value}") from exc


def ipv4_bytes(value: str) -> bytes:
    try:
        return ipaddress.IPv4Address(value).packed
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"invalid IPv4 address: {value}") from exc


def build_icmp_echo(config: dict) -> bytes:
    icmp_type = parse_int(config.get("type", 8), "icmp_echo.type", 255)
    code = parse_int(config.get("code", 0), "icmp_echo.code", 255)
    identifier = parse_int(config.get("identifier", 1), "icmp_echo.identifier", 0xFFFF)
    sequence = parse_int(config.get("sequence", 1), "icmp_echo.sequence", 0xFFFF)
    payload = config.get("payload", "5G O-RAN replay test")
    if not isinstance(payload, str):
        raise ValueError("icmp_echo.payload must be a string")

    header = struct.pack("!BBHHH", icmp_type, code, 0, identifier, sequence)
    packet = header + payload.encode("utf-8")
    return struct.pack("!BBHHH", icmp_type, code, checksum(packet), identifier, sequence) + payload.encode(
        "utf-8"
    )


def build_ipv4(config: dict, protocol: int, payload: bytes) -> bytes:
    src = ipv4_bytes(config["src"])
    dst = ipv4_bytes(config["dst"])
    ttl = parse_int(config.get("ttl", 64), "ipv4.ttl", 255)
    identification = parse_int(config.get("identification", 0), "ipv4.identification", 0xFFFF)
    total_length = 20 + len(payload)

    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        identification,
        0,
        ttl,
        protocol,
        0,
        src,
        dst,
    )
    header = header[:10] + struct.pack("!H", checksum(header)) + header[12:]
    return header + payload


def build_gtpu(config: dict, payload: bytes) -> bytes:
    flags = parse_int(config.get("flags", "0x30"), "gtpu.flags", 0xFF)
    message_type = parse_int(config.get("message_type", "0xff"), "gtpu.message_type", 0xFF)
    teid = parse_int(config["teid"], "gtpu.teid", 0xFFFFFFFF)
    return struct.pack("!BBHI", flags, message_type, len(payload), teid) + payload


def build_udp(config: dict, src_ip: str, dst_ip: str, payload: bytes) -> bytes:
    src_port = parse_int(config.get("src_port", 2152), "udp.src_port", 0xFFFF)
    dst_port = parse_int(config.get("dst_port", 2152), "udp.dst_port", 0xFFFF)
    length = 8 + len(payload)
    header = struct.pack("!HHHH", src_port, dst_port, length, 0)
    pseudo_header = ipv4_bytes(src_ip) + ipv4_bytes(dst_ip) + struct.pack("!BBH", 0, 17, length)
    udp_checksum = checksum(pseudo_header + header + payload)
    if udp_checksum == 0:
        udp_checksum = 0xFFFF
    return struct.pack("!HHHH", src_port, dst_port, length, udp_checksum) + payload


def build_ethernet(config: dict, payload: bytes) -> bytes:
    ethertype = parse_int(config.get("ethertype", "0x0800"), "ethernet.ethertype", 0xFFFF)
    return mac_bytes(config["dst"]) + mac_bytes(config["src"]) + struct.pack("!H", ethertype) + payload


def encode_packet(case: dict) -> bytes:
    packet = case.get("packet")
    if not isinstance(packet, dict):
        raise ValueError("case.packet must be an object")

    inner_payload = build_icmp_echo(packet["icmp_echo"])
    inner_ip = build_ipv4(packet["inner_ipv4"], 1, inner_payload)
    gtpu = build_gtpu(packet["gtpu"], inner_ip)
    outer_ipv4 = packet["outer_ipv4"]
    udp = build_udp(packet["udp"], outer_ipv4["src"], outer_ipv4["dst"], gtpu)
    outer_ip = build_ipv4(outer_ipv4, 17, udp)
    return build_ethernet(packet["ethernet"], outer_ip)


def write_pcap(path: Path, packets: list[bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for index, packet in enumerate(packets):
            handle.write(struct.pack("<IIII", index, 0, len(packet), len(packet)))
            handle.write(packet)


def load_case(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if value.get("schema_version") != 1:
        raise ValueError(f"{path}: unsupported schema_version")
    if value.get("protocol") != "GTP-U":
        raise ValueError(f"{path}: encode_gtpu.py only supports protocol GTP-U")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="replay testcase JSON")
    parser.add_argument("-o", "--output", type=Path, required=True, help="output pcap path")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    case = load_case(args.case)
    write_pcap(args.output, [encode_packet(case)])
    print(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

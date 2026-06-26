#!/usr/bin/env python3
"""Extract traceable ASN.1 AP and current GTP-U payload templates from a flow capture."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path


TARGETS = {
    "F1AP": ["UEContextSetupRequest", "UEContextModificationRequest", "UEContextReleaseCommand"],
    "E1AP": ["BearerContextSetupRequest", "BearerContextModificationRequest", "BearerContextReleaseCommand"],
    "NGAP": [
        "InitialUEMessage",
        "PDUSessionResourceSetupRequest",
        "UEContextReleaseRequest",
        "UEContextReleaseCommand",
    ],
}


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, text=True, capture_output=True).stdout


def tshark_rows(pcap: Path) -> list[dict[str, str]]:
    fields = [
        "frame.number",
        "frame.time_epoch",
        "ip.src",
        "ip.dst",
        "sctp.srcport",
        "sctp.dstport",
        "sctp.data_sid",
        "sctp.data_ssn",
        "sctp.data_tsn",
        "sctp.data_payload_proto_id",
        "f1ap.procedureCode",
        "e1ap.procedureCode",
        "ngap.procedureCode",
        "_ws.col.Info",
    ]
    cmd = [
        "tshark",
        "-r",
        str(pcap),
        "-Y",
        "f1ap || e1ap || ngap",
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
    output = run(cmd)
    return list(csv.DictReader(output.splitlines(), delimiter="\t"))


def protocol(row: dict[str, str]) -> str:
    for name in ("F1AP", "E1AP", "NGAP"):
        if row.get(f"{name.lower()}.procedureCode"):
            return name
    return "UNKNOWN"


def clean_message(info: str) -> str:
    for part in (value.strip() for value in info.split(",")):
        if not part or part.startswith(("SACK", "DATA ", "HEARTBEAT", "INIT")):
            continue
        return re.sub(r"\s+\(.*\)$", "", part)
    return info


def recursive_find(value: object, key: str) -> object | None:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = recursive_find(child, key)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = recursive_find(child, key)
            if found is not None:
                return found
    return None


def raw_value(pcap: Path, frame: int, raw_key: str) -> list:
    packet = json.loads(run(["tshark", "-r", str(pcap), "-Y", f"frame.number == {frame}", "-T", "jsonraw"]))
    raw = recursive_find(packet, raw_key)
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], str):
        raise ValueError(f"could not find {raw_key} for frame {frame}")
    return raw


def raw_payload(pcap: Path, frame: int, raw_key: str) -> str:
    return raw_value(pcap, frame, raw_key)[0]


def full_gtpu_payload(pcap: Path, frame: int) -> str:
    frame_raw = raw_value(pcap, frame, "frame_raw")
    udp_raw = raw_value(pcap, frame, "udp_raw")
    udp_length_raw = raw_value(pcap, frame, "udp.length_raw")
    if len(udp_raw) < 2 or not isinstance(udp_raw[1], int):
        raise ValueError(f"could not determine UDP range for frame {frame}")
    frame_bytes = bytes.fromhex(frame_raw[0])
    udp_offset = udp_raw[1]
    udp_length = int(udp_length_raw[0], 16)
    return frame_bytes[udp_offset + 8 : udp_offset + udp_length].hex()


def stable(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def extract_control(args: argparse.Namespace) -> tuple[list[dict], list[str]]:
    normalized = {record["frame"]: record for record in json.loads(args.control.read_text(encoding="utf-8"))}
    extracted: list[dict] = []
    found: set[tuple[str, str]] = set()
    for row in tshark_rows(args.sctp_pcap):
        proto = protocol(row)
        message = next(
            (target for target in TARGETS.get(proto, []) if target in row["_ws.col.Info"]),
            clean_message(row["_ws.col.Info"]),
        )
        target = (proto, message)
        if message not in TARGETS.get(proto, []) or target in found:
            continue
        frame = int(row["frame.number"])
        payload_hex = raw_payload(args.sctp_pcap, frame, f"{proto.lower()}_raw")
        record = normalized.get(frame, {})
        template = {
            "schema_version": 1,
            "id": f"{slug(proto)}_{slug(message)}",
            "protocol": proto,
            "message": message,
            "procedure_code": int(row[f"{proto.lower()}.procedureCode"]),
            "direction": {"src_ip": row["ip.src"], "dst_ip": row["ip.dst"]},
            "transport": {
                "type": "SCTP",
                "src_port": int(row["sctp.srcport"]),
                "dst_port": int(row["sctp.dstport"]),
                "stream_id": row["sctp.data_sid"],
                "stream_sequence": row["sctp.data_ssn"],
                "tsn": row["sctp.data_tsn"],
                "ppid": int(row["sctp.data_payload_proto_id"]),
            },
            "payload": {"encoding": "ASN.1 APER", "hex": payload_hex, "length": len(payload_hex) // 2},
            "key_ies": record.get("ies", {}),
            "source": {
                "capture_run": args.run_id,
                "pcap": stable(args.sctp_pcap),
                "frame": frame,
                "time_epoch": row["frame.time_epoch"],
            },
        }
        write_json(args.output_dir / "control" / f"{template['id']}.json", template)
        extracted.append(template)
        found.add(target)
    missing = [
        f"{proto}:{message}"
        for proto, messages in TARGETS.items()
        for message in messages
        if (proto, message) not in found
    ]
    return extracted, missing


def extract_gtpu(args: argparse.Namespace) -> list[dict]:
    records = json.loads(args.gtpu.read_text(encoding="utf-8"))
    extracted: list[dict] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for record in records:
        key = (record["outer_ip"]["src"], record["outer_ip"]["dst"], record["gtp"]["teid"])
        if key in seen:
            continue
        frame = record["frame"]
        payload_hex = full_gtpu_payload(args.gtpu_pcap, frame)
        extracted.append(
            {
                "outer_ip": record["outer_ip"],
                "udp": record["udp"],
                "gtp": record["gtp"],
                "inner_ip": record["inner_ip"],
                "inner_ipv6": record["inner_ipv6"],
                "payload": {"encoding": "GTP-U", "hex": payload_hex, "length": len(payload_hex) // 2},
                "source": {
                    "capture_run": args.run_id,
                    "pcap": stable(args.gtpu_pcap),
                    "frame": frame,
                    "time_epoch": record["time_epoch"],
                },
            }
        )
        seen.add(key)
    write_json(args.output_dir / "gtpu" / "current_endpoints_teids.json", extracted)
    return extracted


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sctp-pcap", type=Path, required=True)
    parser.add_argument("--gtpu-pcap", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--gtpu", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    control, missing = extract_control(args)
    gtpu = extract_gtpu(args)
    manifest = {
        "schema_version": 1,
        "run_id": args.run_id,
        "control_templates": [template["id"] for template in control],
        "missing_control_targets": missing,
        "gtpu_tunnels": len(gtpu),
    }
    write_json(args.output_dir / "manifest.json", manifest)
    print(args.output_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except subprocess.CalledProcessError as exc:
        print(exc.stderr, file=sys.stderr)
        raise SystemExit(exc.returncode) from exc

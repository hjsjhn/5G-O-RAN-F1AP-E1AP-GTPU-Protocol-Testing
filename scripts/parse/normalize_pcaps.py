#!/usr/bin/env python3
"""Normalize captured O-RAN/5G pcaps into compact JSON records."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


CONTROL_BASE_FIELDS = [
    "frame.number",
    "frame.time_epoch",
    "frame.time_relative",
    "_ws.col.Protocol",
    "_ws.col.Info",
    "ip.src",
    "ip.dst",
    "sctp.srcport",
    "sctp.dstport",
    "f1ap.procedureCode",
    "ngap.procedureCode",
    "e1ap.procedureCode",
]

CONTROL_OPTIONAL_FIELDS = [
    "f1ap.C_RNTI",
    "f1ap.gNB_CU_UE_F1AP_ID",
    "f1ap.gNB_DU_UE_F1AP_ID",
    "f1ap.transportLayerAddress",
    "f1ap.transportLayerAddressIPv4",
    "f1ap.TransportLayerAddress",
    "ngap.AMF_UE_NGAP_ID",
    "ngap.RAN_UE_NGAP_ID",
    "ngap.pDUSessionID",
    "ngap.PDUSessionType",
    "ngap.transportLayerAddress",
    "ngap.TransportLayerAddressIPv4",
    "e1ap.gNB_CU_CP_UE_E1AP_ID",
    "e1ap.gNB_CU_UP_UE_E1AP_ID",
    "e1ap.dRB_ID",
    "e1ap.qoS_Flow_Identifier",
    "e1ap.transportLayerAddress",
    "e1ap.TransportLayerAddressIPv4",
]

GTPU_BASE_FIELDS = [
    "frame.number",
    "frame.time_epoch",
    "frame.time_relative",
    "_ws.col.Protocol",
    "_ws.col.Info",
    "ip.src",
    "ip.dst",
    "udp.srcport",
    "udp.dstport",
    "gtp.teid",
    "gtp.message",
    "gtp.seq_number",
]

GTPU_OPTIONAL_FIELDS = [
    "gtp.ext_hdr.next",
    "gtp.ext_hdr.length",
    "gtp.ext_hdr.ran_cont",
    "gtp.ext_hdr.pdu_ses_con.pdu_type",
    "gtp.ext_hdr.pdu_ses_con.qos_flow_id",
    "nrup.pdu_type",
    "nrup.seq_num",
    "nrup.desrd_buff_sz_data_radio_bearer",
    "nrup.desrd_data_rate",
    "icmp.type",
    "icmp.code",
    "icmp.seq",
    "ipv6.src",
    "ipv6.dst",
]


F1AP_PROC = {
    "1": "F1Setup",
    "5": "UEContextSetup",
    "7": "UEContextModification",
    "11": "InitialULRRCMessageTransfer",
    "12": "ULRRCMessageTransfer",
    "13": "DLRRCMessageTransfer",
    "26": "F1Removal",
}

E1AP_PROC = {
    "8": "BearerContextSetup",
    "9": "BearerContextModification",
}


def run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return proc.stdout


def supported_tshark_fields() -> set[str]:
    output = run(["tshark", "-G", "fields"])
    fields: set[str] = set()
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0] == "F":
            fields.add(parts[2])
    return fields


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
        "occurrence=a",
        "-E",
        "aggregator=,",
    ]
    for field in fields:
        cmd.extend(["-e", field])
    output = run(cmd)
    if not output.strip():
        return []
    reader = csv.DictReader(output.splitlines(), delimiter="\t")
    return [dict(row) for row in reader]


def first_nonempty(row: dict[str, str], fields: Iterable[str]) -> str:
    for field in fields:
        value = row.get(field, "")
        if value:
            return value
    return ""


def split_values(value: str) -> list[str]:
    return [part for part in value.split(",") if part]


def as_int(value: str) -> int | None:
    if not value:
        return None
    first = split_values(value)[0]
    try:
        return int(first, 0)
    except ValueError:
        return None


def as_float(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(split_values(value)[0])
    except ValueError:
        return None


def protocol_from_row(row: dict[str, str]) -> str:
    proto = row.get("_ws.col.Protocol", "")
    if "F1AP" in proto:
        return "F1AP"
    if "NGAP" in proto or "NAS-5GS" in proto:
        return "NGAP"
    if "E1AP" in proto:
        return "E1AP"
    for prefix, name in (("f1ap.", "F1AP"), ("ngap.", "NGAP"), ("e1ap.", "E1AP")):
        if any(key.startswith(prefix) and value for key, value in row.items()):
            return name
    return proto or "UNKNOWN"


def clean_info_message(info: str) -> str | None:
    if not info:
        return None
    cleaned = re.sub(r"^(SACK|HEARTBEAT|INIT|DATA)\s*\([^)]*\)\s*,\s*", "", info)
    parts = [part.strip() for part in cleaned.split(",")]
    for part in parts:
        if not part or part.startswith(("SACK", "HEARTBEAT", "INIT", "DATA ")):
            continue
        part = re.sub(r"\s+\(.*\)$", "", part)
        return part
    return parts[-1] if parts else None


def control_procedure(row: dict[str, str], protocol: str) -> tuple[int | None, str | None]:
    field = {
        "F1AP": "f1ap.procedureCode",
        "NGAP": "ngap.procedureCode",
        "E1AP": "e1ap.procedureCode",
    }.get(protocol)
    code = as_int(row.get(field, "")) if field else None
    info_name = clean_info_message(row.get("_ws.col.Info", ""))
    if protocol == "F1AP" and code is not None:
        return code, info_name or F1AP_PROC.get(str(code))
    if protocol == "E1AP" and code is not None:
        return code, info_name or E1AP_PROC.get(str(code))
    return code, info_name


def compact_ies(row: dict[str, str], prefix: str) -> dict[str, str | list[str]]:
    values: dict[str, str | list[str]] = {}
    for field, value in row.items():
        if not field.startswith(prefix) or not value:
            continue
        short = field[len(prefix) :]
        parts = split_values(value)
        values[short] = parts if len(parts) > 1 else value
    return values


def normalize_control(pcap: Path, fields: list[str]) -> list[dict]:
    rows = tshark_rows(pcap, "f1ap || ngap || e1ap", fields)
    records: list[dict] = []
    for row in rows:
        protocol = protocol_from_row(row)
        code, name = control_procedure(row, protocol)
        src_ips = split_values(row.get("ip.src", ""))
        dst_ips = split_values(row.get("ip.dst", ""))
        prefix = {"F1AP": "f1ap.", "NGAP": "ngap.", "E1AP": "e1ap."}.get(protocol, "")
        records.append(
            {
                "frame": as_int(row.get("frame.number", "")),
                "time_epoch": as_float(row.get("frame.time_epoch", "")),
                "time_relative": as_float(row.get("frame.time_relative", "")),
                "protocol": protocol,
                "protocol_stack": row.get("_ws.col.Protocol", ""),
                "info": row.get("_ws.col.Info", ""),
                "ip": {"src": src_ips[0] if src_ips else None, "dst": dst_ips[0] if dst_ips else None},
                "sctp": {
                    "srcport": as_int(row.get("sctp.srcport", "")),
                    "dstport": as_int(row.get("sctp.dstport", "")),
                },
                "procedure": {"code": code, "name": name},
                "ies": compact_ies(row, prefix),
            }
        )
    return records


def normalize_gtpu(pcap: Path, fields: list[str]) -> list[dict]:
    rows = tshark_rows(pcap, "gtp", fields)
    records: list[dict] = []
    for row in rows:
        src_ips = split_values(row.get("ip.src", ""))
        dst_ips = split_values(row.get("ip.dst", ""))
        records.append(
            {
                "frame": as_int(row.get("frame.number", "")),
                "time_epoch": as_float(row.get("frame.time_epoch", "")),
                "time_relative": as_float(row.get("frame.time_relative", "")),
                "protocol": "GTP-U",
                "protocol_stack": row.get("_ws.col.Protocol", ""),
                "info": row.get("_ws.col.Info", ""),
                "outer_ip": {
                    "src": src_ips[0] if src_ips else None,
                    "dst": dst_ips[0] if dst_ips else None,
                },
                "inner_ip": {
                    "src": src_ips[1] if len(src_ips) > 1 else None,
                    "dst": dst_ips[1] if len(dst_ips) > 1 else None,
                },
                "inner_ipv6": {
                    "src": first_nonempty(row, ["ipv6.src"]) or None,
                    "dst": first_nonempty(row, ["ipv6.dst"]) or None,
                },
                "udp": {
                    "srcport": as_int(row.get("udp.srcport", "")),
                    "dstport": as_int(row.get("udp.dstport", "")),
                },
                "gtp": {
                    "teid": first_nonempty(row, ["gtp.teid"]) or None,
                    "message_type": first_nonempty(row, ["gtp.message"]) or None,
                    "sequence_number": first_nonempty(row, ["gtp.seq_number"]) or None,
                    "extension_next": first_nonempty(row, ["gtp.ext_hdr.next"]) or None,
                    "extension_length": as_int(first_nonempty(row, ["gtp.ext_hdr.length"])),
                    "ran_container": first_nonempty(row, ["gtp.ext_hdr.ran_cont"]) or None,
                    "pdu_session_container_type": as_int(first_nonempty(row, ["gtp.ext_hdr.pdu_ses_con.pdu_type"])),
                    "qfi": as_int(first_nonempty(row, ["gtp.ext_hdr.pdu_ses_con.qos_flow_id"])),
                },
                "nrup": {
                    "pdu_type": as_int(row.get("nrup.pdu_type", "")),
                    "sequence_number": as_int(row.get("nrup.seq_num", "")),
                    "desired_buffer_size": as_int(row.get("nrup.desrd_buff_sz_data_radio_bearer", "")),
                    "desired_data_rate": as_int(row.get("nrup.desrd_data_rate", "")),
                },
                "inner_icmp": {
                    "type": as_int(row.get("icmp.type", "")),
                    "code": as_int(row.get("icmp.code", "")),
                    "sequence": as_int(row.get("icmp.seq", "")),
                },
            }
        )
    return records


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summarize(control: list[dict], gtpu: list[dict], args: argparse.Namespace) -> dict:
    control_by_protocol = Counter(record["protocol"] for record in control)
    control_by_procedure = Counter(
        f"{record['protocol']}:{record['procedure']['code']}:{record['procedure']['name']}"
        for record in control
    )
    gtpu_by_teid = Counter(record["gtp"]["teid"] or "unknown" for record in gtpu)
    gtpu_by_outer_flow = Counter(
        f"{record['outer_ip']['src']}->{record['outer_ip']['dst']}" for record in gtpu
    )
    gtpu_inner_icmp = sum(1 for record in gtpu if record["inner_icmp"]["type"] is not None)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pcaps": {
            "sctp": str(args.sctp_pcap) if args.sctp_pcap else None,
            "gtpu": str(args.gtpu_pcap) if args.gtpu_pcap else None,
        },
        "counts": {
            "control_packets": len(control),
            "gtpu_packets": len(gtpu),
            "control_by_protocol": dict(sorted(control_by_protocol.items())),
            "control_by_procedure": dict(sorted(control_by_procedure.items())),
            "gtpu_by_teid": dict(sorted(gtpu_by_teid.items())),
            "gtpu_by_outer_flow": dict(sorted(gtpu_by_outer_flow.items())),
            "gtpu_inner_icmp_packets": gtpu_inner_icmp,
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sctp-pcap", type=Path, help="full-frame SCTP pcap")
    parser.add_argument("--gtpu-pcap", type=Path, help="GTP-U UDP/2152 pcap")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("json/normalized"),
        help="directory for normalized JSON output",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="output filename prefix; defaults to the capture directory name",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.sctp_pcap and not args.gtpu_pcap:
        raise SystemExit("at least one of --sctp-pcap or --gtpu-pcap is required")

    available = supported_tshark_fields()
    control_fields = CONTROL_BASE_FIELDS + [field for field in CONTROL_OPTIONAL_FIELDS if field in available]
    gtpu_fields = GTPU_BASE_FIELDS + [field for field in GTPU_OPTIONAL_FIELDS if field in available]

    control = normalize_control(args.sctp_pcap, control_fields) if args.sctp_pcap else []
    gtpu = normalize_gtpu(args.gtpu_pcap, gtpu_fields) if args.gtpu_pcap else []

    prefix = args.prefix
    if not prefix:
        pcap = args.sctp_pcap or args.gtpu_pcap
        prefix = pcap.parent.name if pcap else "capture"

    outputs = {
        "control": args.output_dir / f"{prefix}_control_plane_packets.json",
        "gtpu": args.output_dir / f"{prefix}_gtpu_packets.json",
        "summary": args.output_dir / f"{prefix}_summary.json",
    }
    write_json(outputs["control"], control)
    write_json(outputs["gtpu"], gtpu)
    write_json(outputs["summary"], summarize(control, gtpu, args))

    for path in outputs.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

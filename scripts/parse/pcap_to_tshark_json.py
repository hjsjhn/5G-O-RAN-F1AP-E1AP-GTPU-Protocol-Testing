#!/usr/bin/env python3
"""Convert pcap files to raw tshark JSON artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_tshark_json(pcap: Path) -> list[dict]:
    cmd = ["tshark", "-r", str(pcap), "-T", "json"]
    proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return json.loads(proc.stdout)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def convert_one(pcap: Path, output_dir: Path, prefix: str | None) -> Path:
    if not pcap.is_file():
        raise FileNotFoundError(f"pcap not found: {pcap}")

    packets = run_tshark_json(pcap)
    name = f"{prefix}_{pcap.stem}" if prefix else pcap.stem
    out_path = output_dir / f"{name}.tshark.json"
    write_json(out_path, packets)

    meta_path = output_dir / f"{name}.tshark.meta.json"
    write_json(
        meta_path,
        {
            "source_pcap": str(pcap),
            "output_json": str(out_path),
            "packet_count": len(packets),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "command": ["tshark", "-r", str(pcap), "-T", "json"],
        },
    )
    return out_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcaps", nargs="+", type=Path, help="pcap files to convert")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("json/tshark_raw"),
        help="directory for raw tshark JSON output",
    )
    parser.add_argument("--prefix", help="optional output filename prefix")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    for pcap in args.pcaps:
        out_path = convert_one(pcap, args.output_dir, args.prefix)
        print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

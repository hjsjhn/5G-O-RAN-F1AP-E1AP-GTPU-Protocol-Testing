#!/usr/bin/env python3
"""Run the default-dry-run NGAP/Open5GS protocol-aware test entry."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def amf_log() -> str:
    return run(
        ["docker", "exec", "amf", "sh", "-lc", "cat /open5gs/install/var/log/open5gs/amf.log"],
        check=False,
    ).stdout


def container_logs(container: str) -> str:
    result = run(["docker", "logs", container], check=False)
    return result.stdout + result.stderr


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="run the local isolated UERANSIM NGAP test")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("json/replay_results/ngap_open5gs_result.json"),
        help="structured result path",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if args.live else "dry-run",
        "protocol": "NGAP",
        "peer": "Open5GS AMF",
        "levels": {"L1": True, "L2": True, "L3": False, "L4": False},
        "checks": {},
    }
    if args.live:
        run(["./scripts/env/check_core_ready.sh"])
        before = len(amf_log().splitlines())
        try:
            run(["./scripts/env/run_ueransim_smoke.sh", "run"])
            new_amf = "\n".join(amf_log().splitlines()[before:])
            gnb = container_logs("nr_gnb")
            ue = container_logs("nr_ue")
            checks = {
                "amf_initial_ue_message": "InitialUEMessage" in new_amf,
                "ng_setup_response": "NG Setup procedure is successful" in gnb
                or "NG Setup complete" in gnb,
                "ue_registered": "Registration is successful" in ue
                or "registered to the network" in ue.lower(),
                "pdu_session_established": "PDU Session establishment is successful" in ue
                or ("pdu session" in ue.lower() and "established" in ue.lower()),
            }
            result["checks"] = checks
            result["levels"]["L3"] = checks["amf_initial_ue_message"]
            result["levels"]["L4"] = all(checks.values())
            result["result"] = "PASS" if result["levels"]["L4"] else "FAIL"
        finally:
            run(["./scripts/env/run_ueransim_smoke.sh", "down"], check=False)
            run(["./scripts/env/check_core_ready.sh"])
    else:
        result["checks"]["safety"] = "PASS: no SCTP association created; use --live locally"
        result["result"] = "DRY-RUN"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[{result['result']}] NGAP/Open5GS test entry")
    print(args.output)
    return 0 if result["result"] in {"PASS", "DRY-RUN"} else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except subprocess.SubprocessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

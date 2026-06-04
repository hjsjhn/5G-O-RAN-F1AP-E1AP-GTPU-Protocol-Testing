#!/usr/bin/env python3
"""Run the default-dry-run NGAP/Open5GS protocol-aware test entry."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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
        "--case",
        type=Path,
        default=Path("tests/replay/ngap_cases/ueransim_smoke.json"),
        help="explicit NGAP smoke or mutation testcase JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("json/replay_results/ngap_open5gs_result.json"),
        help="structured result path",
    )
    return parser.parse_args(argv)


def load_case(path: Path) -> dict:
    case = json.loads(path.read_text(encoding="utf-8"))
    if case.get("schema_version") != 1 or case.get("protocol") != "NGAP":
        raise ValueError(f"{path}: unsupported NGAP testcase")
    if case.get("kind") not in {"smoke", "mutation"}:
        raise ValueError(f"{path}: kind must be smoke or mutation")
    if case["kind"] == "mutation":
        mutation = case.get("mutation", {})
        if mutation.get("field") != "tracking_area_code" or not isinstance(
            mutation.get("value"), int
        ):
            raise ValueError(f"{path}: only integer tracking_area_code mutation is supported")
    return case


def configured_tac() -> str:
    result = run(
        [
            "docker",
            "exec",
            "nr_gnb",
            "sh",
            "-lc",
            "sed -n \"s/^[[:space:]]*tac:[[:space:]]*//p\" /UERANSIM/config/ueransim-gnb.yaml",
        ],
        check=False,
    )
    value = result.stdout.strip().strip("'\"")
    return value.split()[0] if value else ""


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    case = load_case(args.case)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if args.live else "dry-run",
        "protocol": "NGAP",
        "peer": "Open5GS AMF",
        "case_id": case["id"],
        "case_kind": case["kind"],
        "classification": (
            "ordinary_ueransim_smoke_not_replay"
            if case["kind"] == "smoke"
            else "protocol_aware_configuration_mutation_not_payload_replay"
        ),
        "replay_levels": {"L1": False, "L2": False, "L3": False, "L4": False},
        "mutation": case.get("mutation"),
        "checks": {},
    }
    if args.live:
        run(["./scripts/env/check_core_ready.sh"])
        before = len(amf_log().splitlines())
        try:
            if case["kind"] == "smoke":
                run(["./scripts/env/run_ueransim_smoke.sh", "run"])
            else:
                env = os.environ.copy()
                env["UERANSIM_TAC_OVERRIDE"] = str(case["mutation"]["value"])
                subprocess.run(
                    ["./scripts/env/run_ueransim_smoke.sh", "gnb"],
                    check=True,
                    text=True,
                    capture_output=True,
                    env=env,
                )
                time.sleep(8)
            new_amf = "\n".join(amf_log().splitlines()[before:])
            gnb = container_logs("nr_gnb")
            ue = container_logs("nr_ue")
            ng_setup_success = "NG Setup procedure is successful" in gnb or "NG Setup complete" in gnb
            if case["kind"] == "smoke":
                checks = {
                    "amf_initial_ue_message": "InitialUEMessage" in new_amf,
                    "ng_setup_response": ng_setup_success,
                    "ue_registered": "Registration is successful" in ue
                    or "registered to the network" in ue.lower(),
                    "pdu_session_established": "PDU Session establishment is successful" in ue
                    or ("pdu session" in ue.lower() and "established" in ue.lower()),
                }
            else:
                expected = case["expect"]
                checks = {
                    "explicit_mutation_input_accepted": True,
                    "configured_tac": configured_tac() == expected["configured_tac"],
                    "ng_setup_success_matches_expectation": ng_setup_success
                    == expected["ng_setup_success"],
                    "amf_or_gnb_observed_test": bool(new_amf.strip() or gnb.strip()),
                }
            result["checks"] = checks
            result["observations"] = {
                "configured_tac": configured_tac(),
                "ng_setup_success": ng_setup_success,
                "amf_new_log_lines": len(new_amf.splitlines()),
            }
            result["result"] = "PASS" if all(checks.values()) else "FAIL"
        finally:
            down = run(["./scripts/env/run_ueransim_smoke.sh", "down"], check=False)
            if down.returncode != 0:
                raise RuntimeError("failed to remove UERANSIM testcase containers")
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
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

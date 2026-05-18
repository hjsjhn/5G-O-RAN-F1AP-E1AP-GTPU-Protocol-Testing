# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

5G O-RAN protocol stack analysis and testing — a course project that captures, parses, re-encodes, replays, and validates control-plane and user-plane protocol messages between 5G RAN components. The primary interfaces are F1 (CU↔DU), E1 (CU-CP↔CU-UP), Xn (gNB↔gNB), and GTP-U, with cross-layer analysis involving NG (RAN↔Core).

**Languages**: Python (scripts, parsing, encoding, testing), C (optional — srsRAN internals), Shell (env control, capture), Wireshark/tshark (dissection).

## Course Requirements

Three mandatory deliverables:
1. **Structured JSON parsing** of E1AP/F1AP/XnAP/GTP-U packets covering common IEs
2. **Reversible encoding**: re-encode ≥5 control message types + GTP-U from JSON → pcap, verifiable by Wireshark and peer components
3. **Two complete UE flow tests**: e.g. Registration + PDU Session Establishment, Registration + Deregistration — with state-machine progression confirmed via component logs

**Bonus**: real phone access (bonus 1), auto-generated test cases accepted by network components (bonus 2).

**Technical stack**: C, Python, Wireshark.

## Planned Architecture

```
docker/           → Docker Compose for CU-CP, CU-UP, DU, Open5GS core, UE
scripts/
  env/            → start/stop/reset/check the environment
  capture/        → tcpdump-based capture on Docker bridges or containers
  parse/          → tshark JSON → normalized JSON (per-protocol: F1AP, E1AP, XnAP, GTP-U)
  encode/         → JSON/template → binary → pcap (GTP-U via Scapy, control-plane via template replay)
  replay/         → inject packets back into running components
  validate/       → tshark decode check, component log analysis, flow-state verification, report generation
json/
  tshark_raw/     → raw tshark -T json output
  normalized/     → cleaned, schema-validated per-packet JSON
  templates/      → message templates for re-encoding
captures/
  raw/            → original pcaps with metadata per run
  generated/      → pcaps produced by the encode scripts
reports/          → flow timelines, testcase results, final report
tests/           → pytest unit/integration tests
```

## Tech Stack

- **RAN**: srsRAN Project / OCUDU in CU-DU split mode (Docker)
- **Core**: Open5GS
- **UE**: srsUE over ZMQ (phase 1), real phone + SDR (optional phase 2)
- **Capture**: tcpdump inside containers or on Docker bridge interfaces
- **Parsing**: tshark `-T json` → Python normalization scripts
- **Encoding**: Scapy for GTP-U; template-based byte replacement for F1AP/E1AP (extract raw payload from real pcap, patch selected fields)
- **Replay**: tcpreplay or Scapy send on Docker network
- **Validation**: tshark decode check + component log grep + state assertion

## Key Commands (once implemented)

```bash
# Environment
docker compose -f docker/compose/docker-compose.yml -f docker/compose/docker-compose.split.yml up -d
docker compose -f docker/compose/docker-compose.yml -f docker/compose/docker-compose.split.yml down

# Capture
sudo tcpdump -i any sctp -w captures/raw/run_XXX/sctp.pcap
sudo tcpdump -i any udp port 2152 -w captures/raw/run_XXX/gtpu.pcap

# Parse
python scripts/parse/pcap_to_tshark_json.py captures/raw/run_XXX/sctp.pcap -o json/tshark_raw/
python scripts/parse/normalize_f1ap.py json/tshark_raw/run_XXX_sctp.json -o json/normalized/
python scripts/parse/normalize_gtpu.py json/tshark_raw/run_XXX_gtpu.json -o json/normalized/

# Encode
python scripts/encode/encode_gtpu.py json/templates/gtpu_gpdu.json -o captures/generated/
python scripts/encode/encode_f1ap_template.py json/templates/f1ap_ue_context_setup.json -o captures/generated/

# Validate
python scripts/validate/validate_wireshark_decode.py captures/generated/testcase_XXX.pcap
python scripts/validate/generate_report.py reports/

# Test
pytest tests/
```

## Protocol Priority

1. **F1AP** — highest priority; most naturally present in CU/DU split
2. **GTP-U** — structurally simple; good first encoding target
3. **NGAP** — cross-layer analysis support
4. **E1AP** — may not be exposed as capturable SCTP in current srsRAN Docker split; fallback to theoretical analysis if unresolvable
5. **XnAP** — requires multi-gNB or handover; not committed for phase 1

## Encoding Strategy

Start simple, escalate only as needed:
- **GTP-U**: Scapy or hand-crafted binary
- **F1AP/E1AP control messages**: template replay (extract raw bytes from real pcap, patch select fields like UE IDs, TEIDs)
- Full ASN.1 encoder is explicitly out of scope for phase 1

## Network Layout (Docker)

```
ran_net  10.53.1.0/24  → AMF .2, CU-CP .4, CU-UP .5, DU .6
f1u_net  172.18.10.0/24 → CU-UP .2, DU .3
```

Config files (cu_cp.yml, cu_up.yml, du.yml, Open5GS amf.yaml/upf.yaml) must have consistent IP references to these addresses.

## Risks and Fallbacks

- **E1AP not capturable**: document in report, focus on F1AP+GTP-U+NGAP
- **XnAP needs multi-gNB**: deferred; use existing XnAP pcaps if available
- **Control-plane re-encoding too hard**: fall back to template replay with minimal field patching
- **srsUE 5G limitations**: no handover support; affects Xn/Handover testing

## Implementation Plan Reference

See `IMPLEMENTATION.md` for the full phased plan (phases 0–10, weekly schedule, per-phase deliverables, and agent execution instructions).

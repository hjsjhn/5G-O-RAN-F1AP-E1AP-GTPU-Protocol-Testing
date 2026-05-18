# 5G O-RAN F1AP/E1AP/GTPU Protocol Testing

5G O-RAN protocol stack parsing, re-encoding, replay and testing — focusing on F1AP, E1AP, XnAP, and GTP-U.

## Project Goal

Capture and parse control-plane (F1AP, E1AP, XnAP) and user-plane (GTP-U) protocol messages between 5G RAN components, then build reversible encoding and automated replay testing.

## Architecture

```
srsRAN/OCUDU (CU-CP / CU-UP / DU) + Open5GS Core + srsUE
```

All components run in Docker Compose with CU-DU split mode.

## Directory Structure

```
docker/          Docker Compose configs and component YAML files
scripts/
  env/           Environment start/stop/reset
  capture/       tcpdump-based packet capture
  parse/         pcap → tshark JSON → normalized JSON
  encode/        JSON/template → binary → pcap
  replay/        Inject packets into running components
  validate/      Wireshark decode check, log analysis, report generation
json/
  tshark_raw/    Raw tshark -T json output
  normalized/    Cleaned per-packet JSON
  templates/     Message templates for re-encoding
captures/        Raw, processed, and generated pcap files
reports/         Test case results and final report
tests/           pytest tests
```

## Quick Start

```bash
# Start environment
docker compose -f docker/compose/docker-compose.yml \
               -f docker/compose/docker-compose.split.yml up -d

# Capture packets
sudo tcpdump -i any sctp -w captures/raw/sctp.pcap
sudo tcpdump -i any udp port 2152 -w captures/raw/gtpu.pcap

# Parse
python scripts/parse/pcap_to_tshark_json.py captures/raw/sctp.pcap -o json/tshark_raw/
python scripts/parse/normalize_f1ap.py json/tshark_raw/sctp.json -o json/normalized/

# Encode
python scripts/encode/encode_gtpu.py json/templates/gtpu_gpdu.json -o captures/generated/

# Validate
python scripts/validate/validate_wireshark_decode.py captures/generated/test.pcap

# Run tests
pytest tests/
```

## Protocols

| Interface | Protocol | Stack |
|-----------|----------|-------|
| F1-C (CU↔DU) | F1AP | F1AP/SCTP/IP |
| F1-U (CU-UP↔DU) | GTP-U | GTP-U/UDP/IP |
| E1 (CU-CP↔CU-UP) | E1AP | E1AP/SCTP/IP |
| Xn (gNB↔gNB) | XnAP | XnAP/SCTP/IP |
| NG-C (RAN↔Core) | NGAP | NGAP/SCTP/IP |
| NG-U (RAN↔Core) | GTP-U | GTP-U/UDP/IP |

## Requirements

- Docker & Docker Compose
- Python 3.10+
- tshark / Wireshark
- tcpdump
- Scapy (`pip install scapy`)

## License

Course project — not licensed for redistribution.

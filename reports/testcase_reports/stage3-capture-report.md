# Stage 3 Capture Report: Interface Capture and Protocol Identification

Date: 2026-05-22

## Conclusion

Stage 3 is complete.

The environment can capture and identify full network-frame traffic for:

- SCTP control plane: F1AP, NGAP, E1AP
- UDP/2152 user plane: F1-U GTP-U and N3 GTP-U

The validated capture path is in-container tcpdump on the target RAN containers, automated by:

```bash
./scripts/capture/capture_traffic.sh run captures/raw/<run_name>
```

## Validated Capture Run

Latest validation artifact:

```text
captures/raw/run_capture_ping_20260522_110820/
  ran_sctp_full.pcap
  gtpu_full.pcap
```

Protocol hierarchy from `ran_sctp_full.pcap`:

```text
sll frames:218
  ip frames:218
    sctp frames:218
      f1ap frames:25
      ngap frames:13
      e1ap frames:4
```

Protocol hierarchy from `gtpu_full.pcap`:

```text
sll frames:12
  ip frames:12
    udp frames:12
      gtp frames:12
        ip frames:6
          icmp frames:6
```

## What Was Captured

SCTP control-plane pcap:

- F1AP over CU-CP <-> DU
- NGAP over CU-CP <-> AMF
- E1AP over CU-CP <-> CU-UP
- Full IP/SCTP headers are present, not only srsRAN exported-pdu records.

GTP-U user-plane pcap:

- F1-U: `172.18.10.3 -> 172.18.10.2`, UDP/2152, GTP-U T-PDU
- N3: `10.53.1.5 -> 10.53.1.3`, UDP/2152, GTP-U T-PDU
- The generated UE ping traffic appears as inner ICMP from `10.45.0.16 -> 8.8.8.8` inside N3 GTP-U.

## Why GTP-U Packet Count Is Small

The 12 UDP/2152 frames are expected for the current test workload.

- The script sends 5 ICMP echo requests from the UE via `tun_srsue`.
- The UE received 0 replies from `8.8.8.8`, so there are no corresponding downlink reply packets.
- Registration and PDU Session setup naturally produce only a small number of F1-U/N3 packets.

This is sufficient for Stage 3 because the goal is to prove capture and protocol identification, not throughput or Internet reachability.

## OrbStack Finding

Sidecar capture containers are unreliable under OrbStack for this topology. A sidecar tcpdump container attached to the same Docker network can produce empty 24-byte pcap files.

The working method is target-container capture:

- `srsran_cu_cp`: `tcpdump -i any -s 0 -U -w /tmp/ran_sctp_full.pcap sctp`
- `srsran_cu_up`: `tcpdump -i any -s 0 -U -w /tmp/gtpu_full.pcap 'udp port 2152'`

This method has been automated in `scripts/capture/capture_traffic.sh`.

## Verification Commands

```bash
RUN=captures/raw/run_capture_ping_20260522_110820

tshark -r "$RUN/ran_sctp_full.pcap" -q -z io,phs
tshark -r "$RUN/gtpu_full.pcap" -q -z io,phs

tshark -r "$RUN/ran_sctp_full.pcap" -Y 'f1ap || ngap || e1ap'
tshark -r "$RUN/gtpu_full.pcap" -Y 'udp.port == 2152 || gtp'
```

## Stage Boundary

Completed:

- Capture process is automated.
- Full-frame SCTP and GTP-U pcaps are produced.
- F1AP, NGAP, E1AP, F1-U GTP-U, and N3 GTP-U are identifiable with tshark/Wireshark.

Not part of Stage 3:

- Sustained user-plane throughput.
- Successful public Internet ping replies.
- JSON extraction and IE normalization. These belong to Stage 4.

## Next Step

Proceed to Stage 4: parse pcap to JSON and extract protocol information elements.

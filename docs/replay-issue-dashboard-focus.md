# Replay / Issue / Dashboard Focus

> Branch: `feature/replay-issue-dashboard`
> Date: 2026-05-30

This branch owns the final demonstration path that does not depend on F1 or N2 handover being fully successful.

The concrete gated execution order is documented in:

```text
docs/replay-execution-plan.md
```

## Primary Goal

Build a reproducible workflow that takes captured or constructed protocol messages, normalizes them into JSON/templates, encodes them back into recognizable packets, runs automated UE-flow test cases, and presents the result in a dashboard.

## In Scope

1. Protocol JSON and templates
   - Reuse existing normalized JSON output under `json/normalized/`.
   - Define stable message templates for replay/encoding tests.
   - Cover at least NGAP, F1AP, E1AP, GTP-U, and XnAP offline parse/construct examples.

2. Encoding and packet generation
   - Implement JSON/template to packet or pcap generation.
   - Generated packets must be recognized by tshark/Wireshark.
   - Complete at least five F1AP/E1AP control-message encodings plus GTP-U.
   - Keep XnAP in the offline parse/construct scope agreed in Stage 4.5.
   - Prioritize correctness of protocol identity, key IEs, TEID/session fields, and procedure names over full live-network injection at first.

3. Protocol-aware peer validation
   - Validate F1AP and E1AP testcases against peer components through valid SCTP associations or controlled scenarios.
   - Validate GTP-U through UDP/2152 live replay using current endpoints and TEIDs.
   - Use NGAP peer validation for Open5GS issue-driven tests.
   - XnAP is the only protocol explicitly exempted from live replay.

4. Automated complete-flow tests
   - Turn the existing baseline UE smoke flow into repeatable test cases.
   - Keep default behavior compatible with the current baseline environment.
   - Produce machine-readable outputs for dashboard and reports.

5. Open5GS issue-driven tests
   - Target the pinned Open5GS digest and observed container version.
   - Select Open5GS v2.7.6-era issues that can be mapped to malformed, replayed, or mutated protocol messages.
   - For each issue candidate, record: issue summary, affected component, packet/message trigger idea, expected behavior, observed behavior, and reproducibility status.

6. Dashboard
   - Build a local frontend for final demonstration.
   - Left side: parsed signaling tree / JSON / selected IE details.
   - Right side: live or replayed logs, testcase output, and pass/fail status.
   - The dashboard should consume generated artifacts rather than requiring manual copy-paste.

7. Reports
   - Produce testcase reports for replay, issue reproduction, and dashboard demo flow.
   - Keep raw pcap, raw tshark JSON, and logs out of git.

## Out of Scope

- Do not block this branch on F1 handover or N2 handover success.
- Do not change the default baseline compose topology.
- Do not make `feature/replay-issue-dashboard` depend on branch-specific handover overlays.
- Do not require live XnAP handover traffic. XnAP is offline parse/construct only.

## Engineering Constraints

- Public scripts must keep their default behavior unless a new scenario argument is explicitly passed.
- New generated artifacts should be small, deterministic, and safe to commit.
- Large or raw runtime outputs belong under ignored capture/log locations.
- Any Docker Compose or network change must be opt-in and documented.
- Tests should be runnable from scripts, not from a manual checklist.

## Milestones

### 5C.1 Replay Data Model

- [x] Define replay testcase directory layout.
- [x] Define message template schema.
- [x] Add initial GTP-U uplink/downlink testcase templates.
- [x] Generate and validate recognizable GTP-U pcaps.

### 5C.2 Fresh Flows and Template Extraction

- [ ] Automate registration + PDU session and registration + deregistration flows.
- [ ] Extract traceable F1AP/E1AP/NGAP ASN.1 payload templates.
- [ ] Extract current GTP-U endpoints, TEIDs, extension headers, and payloads.

### 5C.3 Multi-Protocol Encoding and Wireshark Validation

- [ ] Encode at least five F1AP/E1AP control message types plus GTP-U.
- [ ] Add XnAP offline parse/construct examples.
- [ ] Run automatic round-trip and tshark validation.

### 5C.4 Protocol-Aware Peer Validation

- [ ] Validate F1AP and E1AP through controlled SCTP scenarios.
- [ ] Validate GTP-U through live UDP/2152 replay.
- [ ] Validate NGAP against Open5GS for issue-driven tests.
- [ ] Record XnAP live-replay exemption from Stage 4.5.

### 5C.5 Complete UE Flow Tests

- [ ] Complete registration + PDU session testcase.
- [ ] Complete registration + deregistration/release testcase.
- [ ] Export state-machine logs and structured PASS/FAIL results.

### 5C.6 Issue Reproduction

- [ ] Pick 2-3 Open5GS v2.7.6 issue candidates.
- [ ] Implement mutation/replay testcase prototypes.
- [ ] Document whether each one is reproduced, not reproduced, or bounded.

### 5C.7 Dashboard Demo

- [ ] Build the frontend around real parser/test outputs.
- [ ] Provide a one-command local demo path.

## Success Criteria

- A fresh clone can run the baseline environment and replay/test scripts without manual repair.
- E1AP/F1AP/XnAP/GTP-U have the required structured JSON coverage.
- At least five control-message types plus GTP-U can be encoded and recognized by tshark/Wireshark.
- The selected five F1AP/E1AP control messages and GTP-U reach peer-recognition validation; XnAP alone keeps the agreed live-replay exemption.
- At least two complete UE-flow automated testcases produce structured results.
- At least one Open5GS issue-driven testcase is demonstrated or clearly bounded with evidence.
- Dashboard shows parsed signaling and testcase/log output from real project artifacts.

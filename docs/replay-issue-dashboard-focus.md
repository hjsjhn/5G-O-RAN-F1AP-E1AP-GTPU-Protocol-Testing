# Replay / Issue / Dashboard Focus

> Branch: `feature/replay-issue-dashboard`
> Date: 2026-05-30

This branch owns the final demonstration path that does not depend on F1 or N2 handover being fully successful.

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
   - Prioritize correctness of protocol identity, key IEs, TEID/session fields, and procedure names over full live-network injection at first.

3. Automated complete-flow tests
   - Turn the existing baseline UE smoke flow into repeatable test cases.
   - Keep default behavior compatible with the current baseline environment.
   - Produce machine-readable outputs for dashboard and reports.

4. Open5GS issue-driven tests
   - Target the pinned Open5GS digest and observed container version.
   - Select Open5GS v2.7.6-era issues that can be mapped to malformed, replayed, or mutated protocol messages.
   - For each issue candidate, record: issue summary, affected component, packet/message trigger idea, expected behavior, observed behavior, and reproducibility status.

5. Dashboard
   - Build a local frontend for final demonstration.
   - Left side: parsed signaling tree / JSON / selected IE details.
   - Right side: live or replayed logs, testcase output, and pass/fail status.
   - The dashboard should consume generated artifacts rather than requiring manual copy-paste.

6. Reports
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

## Suggested Milestones

### 5C.1 Replay Data Model

- [x] Define replay testcase directory layout.
- [x] Define message template schema.
- [x] Add initial GTP-U uplink/downlink testcase templates.

### 5C.2 Encoder Prototype

- [x] Generate recognizable GTP-U pcap messages.
- [x] Verify GTP-U generated outputs with tshark.
- [ ] Extend the encoder/validator framework to control-plane protocol classes.

### 5C.3 Automated Flow Tests

- Wrap baseline UE registration and PDU session smoke flow as testcases.
- Export structured result JSON.

### 5C.4 Issue Reproduction

- Pick 2-3 Open5GS v2.7.6 issue candidates.
- Implement mutation/replay testcase prototypes.
- Document whether each one is reproduced, partially reproduced, or only analyzed.

### 5C.5 Dashboard Demo

- Build the frontend around real parser/test outputs.
- Provide a one-command local demo path.

## Success Criteria

- A fresh clone can run the baseline environment and replay/test scripts without manual repair.
- Generated/replayed artifacts are recognized by tshark/Wireshark.
- At least two complete UE-flow automated testcases produce structured results.
- At least one Open5GS issue-driven testcase is demonstrated or clearly bounded with evidence.
- Dashboard shows parsed signaling and testcase/log output from real project artifacts.

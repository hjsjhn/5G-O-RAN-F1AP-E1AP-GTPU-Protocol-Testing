# Stage 5C.2 Traceable Templates

These small templates were extracted by `scripts/flows/extract_templates.py` from
successful automated flow runs. Raw pcaps and logs are intentionally not
committed.

- Control source run: `registration_release_20260604_151613`
- GTP-U source run: `registration_pdu_session_20260604_151300`
- Each control template includes the ASN.1 APER payload, SCTP metadata, source
  frame, direction, procedure code, and normalized key IEs.
- `gtpu/current_endpoints_teids.json` includes the current F1-U and N3 payloads,
  endpoints, TEIDs, extension metadata, and source frames.

These are legal captured payload templates for Stage 5C.3 offline construction.
Their presence does not by itself claim replay success.

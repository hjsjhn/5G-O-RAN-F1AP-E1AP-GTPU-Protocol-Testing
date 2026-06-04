# Stage 5C.3 Constructed Templates

`xnap/` contains offline-only XnAP Handover Request and Handover Request
Acknowledge APER templates constructed with the srsRAN generated ASN.1 encoder.

Verify that the committed payloads still match a fresh encoder run:

```bash
./scripts/replay/check_xnap_template_generation.sh
```

These templates satisfy offline parse/construct and Wireshark validation. XnAP
is explicitly exempt from live replay; the templates do not claim L3 or L4.

# Stage 5C.3 Constructed Templates

`xnap/` contains offline-only XnAP Handover Request and Handover Request
Acknowledge APER templates constructed with the srsRAN generated ASN.1 encoder.

Verify that the committed payloads still match a fresh encoder run:

```bash
./scripts/replay/check_xnap_template_generation.sh
```

The check refuses unpinned inputs. Prepare the ignored source checkout and
builder image exactly as follows:

```bash
git -C docker/srsran-src checkout 4bf1543936d062686d64c10724d2f27a9854f065
docker pull pavonis/srs-gnb-dev@sha256:820ba5ed9056ba8f913ef6b749bf24cd72127ceadf040d60fbc56193368bb344
```

The same pinned source and image are used by the F1AP/E1AP APER mutation
encoder. The scripts fail before encoding if the local source commit differs.

These templates satisfy offline parse/construct and Wireshark validation. XnAP
is explicitly exempt from live replay; the templates do not claim L3 or L4.

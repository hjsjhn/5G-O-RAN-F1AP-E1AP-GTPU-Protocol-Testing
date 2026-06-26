# AGENTS.md

This repository is developed by multiple agents and people in parallel. Treat `main` as the stable baseline branch.

## Shared Instructions

Read [docs/collaboration.md](docs/collaboration.md) before changing Docker Compose files, network addresses, shell scripts, parser schemas, replay tools, or reports.

Before changing project scope, phase plans, protocol coverage, or acceptance criteria, read:

- `5G-ORAN 协议解析和测试 - 课程project.pdf`
- `IMPLEMENTATION.md`

Treat `IMPLEMENTATION.md` as the canonical full project plan. A branch-specific plan may refine it but must not silently narrow the course requirements.

## Baseline Safety

- Keep the existing baseline runnable by default: `docker/compose/docker-compose.yml` + `docker/compose/docker-compose.split.yml`.
- Do not turn the baseline into an F1/N2 handover-only environment.
- Add new handover behavior through overlay compose files, scenario configs, or opt-in script arguments.
- Public scripts must keep their current default behavior unless the user explicitly asks to change it.

## Parallel Branches

Use these task branches for parallel work:

- `feature/f1-handover`: F1/intra-CU handover experiments.
- `feature/n2-handover`: N2/AMF-mediated handover experiments.
- `feature/replay-issue-dashboard`: encoding/replay, Open5GS issue reproduction, frontend dashboard.

Branch isolation is for development only. Final usage should be scenario/overlay based after merge to `main`.

## Data and Artifacts

Do not commit raw pcaps, raw tshark JSON, logs, `.env`, local cloned third-party repos, or local AI logs.

Commit these when useful:

- scripts and configs
- normalized JSON examples
- reports
- frontend/dashboard code
- small generated artifacts required for tests

## Scope Notes

- Open5GS is pinned by digest in `docker/compose/docker-compose.yml`; keep it pinned unless the team explicitly decides to update the test target.
- XnAP is offline parse/construct only. Do not spend time trying to make the current baseline produce full XnAP handover traffic unless explicitly requested.
- Complete UE flow tests do not require handover; do not block replay/issue/dashboard work on F1/N2 handover progress.

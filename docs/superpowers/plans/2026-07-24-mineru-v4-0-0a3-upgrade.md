# MinerU v4.0.0a3 Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the FileX MinerU sidecar from `4.0.0a2` to the official `4.0.0a3` pre-release while preserving the v4 runner contract and proving the image works end to end.

**Architecture:** Keep FileX's local Hybrid pipeline compatibility runner and `mineru[medium]` extra unchanged; update the pinned dependency and repository contracts/docs, rebuild the sidecar image, then validate runtime package/version, v4 CLI compatibility, health, and a real PDF parse. No application feature behavior or runtime tuning changes are included.

**Tech Stack:** Docker Compose, Python 3.13 sidecar, MinerU 4 local pipeline, pytest, shell update tooling.

## Global Constraints

- Keep `mineru[medium]` and pin exactly `4.0.0a3`.
- Do not change MinerU runtime tuning or unrelated application features.
- Preserve the FileX v4 compatibility runner and its output layout.
- Follow the repository's four-layer upgrade verification: container, sidecar files, CLI contract, and real PDF parse.
- Record the release as a pre-release upgrade and retain production smoke-test follow-up until a real deployed PDF is verified.

### Task 1: Update dependency and repository contracts

**Files:**
- Modify: `docker/mineru-sidecar/requirements.txt`
- Modify: `backend/tests/test_mineru_gpu_runtime_contract.py`
- Modify: `README.md`
- Modify: `scripts/update_minerU.sh`
- Modify: `specs/_project/mineru-auto-update.md`

- [ ] Change every current `4.0.0a2` example/pin that describes the active v4 runtime to `4.0.0a3`; keep historical test fixtures unchanged unless they assert the active pin.
- [ ] Add a regression assertion that the active sidecar pin is exactly `mineru[medium]==4.0.0a3`.
- [ ] Keep the v4 runner import and command contract assertions intact.

### Task 2: Add upgrade record

**Files:**
- Create: `specs/150-mineru-sidecar-upgrade-a3/spec.md`
- Create: `specs/150-mineru-sidecar-upgrade-a3/plan.md`
- Create: `specs/150-mineru-sidecar-upgrade-a3/tasks.md`

- [ ] Record official release date, pre-release status, official release/compare links, scope, non-goals, risks, and four-layer acceptance commands.
- [ ] Record that no official parsing-accuracy or OCR benchmark uplift is claimed for a3; the practical focus is download, doclib, startup, lifecycle, and diagnostics reliability.

### Task 3: Run tests and rebuild the local sidecar

**Files:**
- No source changes.

- [ ] Run the MinerU contract/update-tool tests and `git diff --check`.
- [ ] Run the project-provided local MinerU build/update path.
- [ ] Verify `pip show mineru`, `/health`, sidecar files, `mineru --help`, `mineru parse --help`, and the compatibility runner help inside the rebuilt container.

### Task 4: Verify a real parse and hand off deployment gate

**Files:**
- Modify: `specs/150-mineru-sidecar-upgrade-a3/tasks.md`
- Modify: `specs/150-mineru-sidecar-upgrade-a3/spec.md`

- [ ] Run a real PDF through the available local sidecar path and confirm MinerU output is produced without CLI errors or fallback.
- [ ] Record exact command results and distinguish local verification from the still-required production Bamboo/real-document acceptance.

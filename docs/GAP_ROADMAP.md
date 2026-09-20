# Remaining Meaningful Gaps vs Grok Bot

**Updated:** 2026-09-19  
**CLAIMABLE_SCORE:** see `compliance_score.py` (live)  
**Doctrine:** `/opt/otacon/keep-bots/DOCTRINE.md`

## Framing (agreed)

OtaconsKeep is **not** trying to clone Firecracker / commercial cloud / SCIM / native mobile parity.

Browser status (honest):

> Architecture / L4 / fixture-L5 / auth-boundary honesty: **proven**.  
> **L5-prod Gate B PASS** — 51 authed @ 90.2%, recovery 100%, HIR 2.1%; baseline frozen.  
> L5-04 live login takeover **PASS** · L5-06 WebDAV hash upload/download **PASS**.  
> Preferred auth: **human VNC takeover** — bot never sees secrets (`gate_a_human_seed.py`).  
> **L6 endurance RUNNING** (`ENDURANCE/`, 12h job).

| Level | Status |
|---|---|
| BROW-L3 / L4 | **PASS** |
| BROW-L5_FIXTURE_GATE | **PASS** |
| BROW-L5 (prod) | **PASS** (Gate A–E; baseline frozen 2026-09-19) |
| BROW-L6 | **IN PROGRESS** — 12h live SaaS endurance |

### Metric doctrine

| Metric | Role |
|---|---|
| DISCOVERY SUCCESS RATE | Non-blocked task success (context only) |
| AUTH BOUNDARY ACCURACY | Correct blocks + 0 false completion/bypass |
| **AUTHENTICATED TASK SUCCESS RATE** | **Critical L5 denominator** |
| RECOVERY RATE | Fault/expiry recovery |
| HIR | unexpected_human_rescue / tasks (≤10% L5) |

### Campaign Gates A–E

| Gate | Command |
|---|---|
| **A** Seed 4–6 services | `python3 api/gate_a_human_seed.py` → noVNC `:6080` → login → `touch …/HUMAN_DONE` |
| **B** ≥30 authed tasks | `python3 api/l5_prod_gate.py` |
| **C** L5-06 hash upload/download | `L5_ONLY_CLASSES=upload L5_ONLY_IDS=upload_nextcloud L5_MERGE_PREV=1 python3 api/l5_prod_gate.py` |
| **D** L5-04 takeover/resume | `python3 api/gate_d_takeover.py` (or cookie-wipe → Gate-A seed restore) |
| **E** Freeze baseline | `python3 api/freeze_l5_baseline.py` when `gate_pass` |
| **L6** Endurance | `ENDURE_HOURS=12 ENDURE_TICK_SEC=60 python3 api/endurance_harness.py` |

Password JSON is **opt-in only** (`L5_ALLOW_PASSWORD_SEED=1`). Prefer human seed.

Live registry: `config/live_services.json`.

## Worth closing (autonomy)

| Gap | Status | Evidence / next |
|---|---|---|
| Auth boundary / false-completion honesty | **Proven** | 0 false completions / 0 unauthorized |
| L5-prod authenticated breadth | **PASS** | 51 authed @ 90.2%; baseline frozen |
| L5-04 live MFA/login takeover | **PASS** | `GATE_D_L504.json` — auth wall → human seed restore → resume |
| L5-06 hash upload/download | **PASS** | Nextcloud WebDAV PUT→GET sha256 match |
| L6 endurance (not feature sprint) | **IN PROGRESS** | `ENDURANCE/` 12h job `endure_*` |

## Not worth cloning (platform)

Firecracker · xAI cloud host · billing · public template marketplace · SCIM · enterprise provisioning · native iOS/Android for parity · X-specific integration

## Commands

```bash
# Teach-by-demo
python3 /opt/otacon/keep-bots/api/ci6_teach_by_demo_test.py

# Open web breadth (set OPEN_WEB_LIMIT=20 when expanding TASKS)
python3 /opt/otacon/keep-bots/api/open_web_suite.py

# LLM chaos
CHAOS_TRIALS=10 python3 /opt/otacon/keep-bots/api/chaos_multiagent.py

# Endurance (12h)
ENDURE_HOURS=12 ENDURE_TICK_SEC=60 python3 /opt/otacon/keep-bots/api/endurance_harness.py

# Gate A — human session seed (VNC :5901; bot never sees secrets)
python3 /opt/otacon/keep-bots/api/gate_a_human_seed.py
# after login: touch /mnt/data/keep-desk/workspace/status/L5_PROD/HUMAN_DONE

# Gate B — L5-prod (authenticated denominator)
python3 /opt/otacon/keep-bots/api/l5_prod_gate.py

# Gate E — freeze baseline (only if gate_pass)
python3 /opt/otacon/keep-bots/api/freeze_l5_baseline.py

python3 /opt/otacon/keep-bots/api/compliance_score.py
```

## Architecture target (closed loop)

```
HUMAN DEMONSTRATION
        ↓
AUTOMATIC WORKFLOW INFERENCE   ← CI-6 teach_by_demo.py
        ↓
Skill (generalized inputs)
        ↓
Sandbox replay / validate
        ↓
Schedule / Routine
        ↓
Unattended run + policy gates
```

# Keep Desk Engineering Doctrine — Requirement → Evidence → PASS

**Status:** ACTIVE  
**Applies to:** Keep Desk / Keep Bots Grok-parity program  
**Host:** OtaconsKeep 192.168.50.219 (local-only)

## Definition of Done (non-negotiable)

| Claim | Accepted? |
|---|---|
| Code exists / PR merged | **NO** |
| Unit test green | **NO** |
| API returns 200 | **NO** |
| UI exists | **NO** |
| LLM says success | **NO** |
| **Black-box acceptance + objective evidence + required reliability + regression inclusion** | **YES → matrix PASS** |

`IMPLEMENTED ≠ PASS`

## V-model inside sprints

```
Stakeholder Need → System Requirement → Architecture/Interface
        → Implementation → Component → Integration → System → Operational Validation
        → Evidence attached to compliance row
```

Each sprint requirement enters with **verification method already defined** (TEST / ANALYSIS / INSPECTION / DEMONSTRATION). Grok-parity claims: **TEST dominates**.

## Backlog hierarchy

```
EPIC → Capability → System Requirement → Verification Requirement → Test Case → Objective Evidence
```

## Scoring (authoritative)

```
RAW_SCORE      = unweighted PASS rate among tested rows
WEIGHTED_SCORE = Σ(criticality × status_credit) / Σ(criticality)
  status_credit: PASS=1.0 PARTIAL=0.5 FAIL=0 NOT_TESTED=0
CRITICAL_GATE  = all parity-critical IDs are PASS
CLAIMABLE_SCORE = WEIGHTED_SCORE if CRITICAL_GATE else "blocked"
```

### Criticality

| Class | Weight |
|---|---|
| Mission Critical | 5 |
| High | 3 |
| Medium | 2 |
| Low | 1 |

### Parity-critical veto (must be PASS to claim ≥85%)

`C-06`, `C-07`, `C-08`, `D-05`, `E-02`, `F-02`, `F-03`, `F-06`

`C-10` (teach-by-demo) is **not** required for 85% Keep-mission parity; required for 90–95% Grok feature parity.

### Reliability thresholds

| Category | Min reliability |
|---|---|
| Read-only | ≥95% |
| Skill execution | ≥90% |
| Agent handoff | ≥90% |
| Browser workflow | ≥90% |
| Recovery | ≥90% |
| Approval enforcement | **100%** |
| Destructive-action prevention | **100%** |

## Suites

| Suite | When | Contents |
|---|---|---|
| **L0 Smoke** | every commit | APIs, schemas, tool reachability (`validate.py`) |
| **L1 Integration** | every merge | tasks, queues, delegation, policy, skills |
| **L2 System/Parity** | nightly / RC | black-box Grok-parity scenarios |

## 85% release gate

ALL of:

1. `WEIGHTED_SCORE >= 85%`
2. `CRITICAL_GATE == PASS`
3. No Mission-Critical FAIL
4. No Mission-Critical NOT_TESTED
5. ≥90% reliability on core autonomy suite
6. 100% approval-policy enforcement
7. 24h autonomous soak green
8. Regression green
9. Every PASS has evidence (paths + hashes)

## Commands

```bash
python3 /opt/otacon/keep-bots/api/compliance_score.py
python3 /opt/otacon/keep-bots/api/run_suite.py --level L0
python3 /opt/otacon/keep-bots/api/run_suite.py --level L1
python3 /opt/otacon/keep-bots/api/run_suite.py --level L2
```

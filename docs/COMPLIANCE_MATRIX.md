# Keep Desk — Compliance / Benchmark Matrix

Authoritative scorer: `python3 api/compliance_score.py`  
Reference Keep scored **2026-09-19** (OtaconsKeep production stack).

## Headline numbers

| Metric | Value |
|---|---|
| RAW_SCORE | **87.3%** |
| WEIGHTED_SCORE | **91.6%** (239.0 / 261.0) |
| CRITICAL_GATE | **PASS** |
| CLAIMABLE_SCORE | **91.6** |
| RELEASE_85_GATE | **True** |

### Outcome counts

| PASS | PARTIAL | FAIL | NOT_TESTED |
|---|---|---|---|
| 69 | 5 | 5 | 10 |

### Critical gaps

None (critical gate PASS).

---

## Category rollup (reference)

| Category | Score | n |
|---|---|---|
| browser_l5_prod | 100.0% | 10 |
| computer_fs_term | 100.0% | 10 |
| computer_use | 97.1% | 10 |
| multi_agent | 93.5% | 7 |
| local_keep | 92.9% | 4 |
| browser_worker | 90.0% | 15 |
| identity | 88.9% | 6 |
| approval_recovery | 88.9% | 7 |
| skills_routines | 82.7% | 8 |
| client_ecosystem | 33.3% | 5 |

**Read this carefully:** `client_ecosystem` is low because native mobile clients and broad marketplace connectors are **not** Keep Desk’s center of gravity. That drags “feel like Grok on your phone” more than it drags “local operator deck.”

---

## Browser evidence (summary)

| Level | Status |
|---|---|
| BROW-L3 / L4 | PASS |
| L5-prod Gate | PASS — 51 authed @ 90.2%, HIR 2.1% |
| L6 endurance | In progress on reference Keep |

---

## How to re-score

```bash
cd keep-desk
python3 api/compliance_score.py
```

Do not hand-edit claimable scores in README without re-running the scorer.

---

## Interpreting “91.6%” vs “~75% Grok feel”

| Phrase | Meaning |
|---|---|
| **91.6% claimable** | Weighted pass rate on **our** requirements matrix with critical gate PASS. |
| **~75% day-to-day Grok feel** | Operator estimate including frontier model quality, mobile apps, connector breadth, desktop GUI agent. |

Both are intentional. Marketing should not collapse them into one fake number.

---

## Known FAIL / PARTIAL themes

Examples (see scorer output for IDs):

- Full **desktop GUI** computer-use (not browser-only) — FAIL  
- Some **connector listeners** — NOT_TESTED / PARTIAL  
- True **parallel multi-bot** heavy concurrency — PARTIAL  
- **Client ecosystem** (native apps) — weak by design  

For product honesty vs Grok / OpenAI Pilot, see [COMPARISON.md](./COMPARISON.md).

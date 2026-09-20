# Keep Desk

**Local multi-agent work deck** — named AI teammates that share one always-on computer, run jobs in the background, browse the real web, write files, and brief you like an operator — **on your hardware, with your Ollama model, for free.**

Designed by **Antonio G. Garcia** ([Otaconskeep](https://github.com/Otaconskeep)).

| | |
|---|---|
| **Live UI (reference Keep)** | `http://192.168.50.219:5765/` |
| **Claimable parity score** | **91.6%** (weighted systems-test matrix; critical gate PASS) |
| **License** | Use / fork freely for homelab & research (see Doctrine) |
| **Demo** | [`demo/keep_soda_demo.mp4`](./demo/keep_soda_demo.mp4) · [shots](./demo/shots/) |

---

## Why it exists

Cloud “AI teammates” (Grok Bot, OpenAI Operator / ChatGPT computer-use agents) are exciting — and they also mean:

- your work lives on someone else’s computer  
- your browsing and files sit behind a vendor account  
- you pay subscription + usage, forever  
- you can’t inspect the agent loop when it carts the wrong product  

**Keep Desk** is OtaconsKeep’s answer: a **local Grok Bot–class control plane** that runs on a home GPU box (reference: RTX 3090 + Ollama `gpt-oss:20b`). Same *idea* — persistent bots, shared desk, browser computer-use, skills, routines, approvals — without the cloud landlord.

It’s also **fun**. You open a cinematic Command Deck, transmit an order, watch LIVE browser snow turn into real pages, and get a mission report with a Why dossier. When it fails, it fails *honestly* (hollow / off-brief) instead of smiling “Complete” over coffee when you asked for soda.

---

## What you get

- **Named fleet** — ENGINEER / QA / RESEARCHER / PM (extendable), auto-routed from natural language  
- **Shared desk** — one filesystem + shell + persistent Chromium for all bots (`/desk`)  
- **Jobs & pipelines** — multipart briefs split into stages with **namespaced** research folders  
- **Command Deck UI** — briefing-first home, codec bar, LIVE pane, Why / Batch popups  
- **Approvals** — destructive desk actions pause for you  
- **Skills & routines** — teachable workflows + cron-like schedules  
- **Local brain only** — refuses cloud LLM endpoints by design  

---

## Quick start

```bash
git clone https://github.com/Otaconskeep/keep-desk.git
cd keep-desk
cp .env.example .env
# Edit LOCAL_OLLAMA_URL / LOCAL_MODEL if needed
docker compose up -d --build
```

Open **http://127.0.0.1:5765/**

Full install: **[INSTALL.md](./INSTALL.md)**  
Comparisons: **[docs/COMPARISON.md](./docs/COMPARISON.md)**  
FAQ: **[docs/FAQ.md](./docs/FAQ.md)**  
Benchmarks: **[docs/COMPLIANCE_MATRIX.md](./docs/COMPLIANCE_MATRIX.md)**

---

## Demo (soda mission)

A clean end-to-end run — Google soda images → pick winner → YouTube synopsis → Ogden, UT store — with Command Deck screenshots and a ~23 MB slideshow video:

- Video: [`demo/keep_soda_demo.mp4`](./demo/keep_soda_demo.mp4)  
- Stills: [`demo/shots/`](./demo/shots/)  
- Artifacts: [`demo/research/`](./demo/research/)  

---

## Honest limitations (read this)

Keep Desk is **~75% of day-to-day Grok Bot feel**, and **~91.6% claimable** on the *requirements we defined and tested*. That is **not** “we are Grok.”

| Ahead / strong | Behind / missing |
|---|---|
| Local-only brain, no cloud bill | No Firecracker / vendor cloud VM |
| Named multi-agent ops UI + briefing | No native iOS/Android apps (by choice) |
| Browser L5-prod gate evidence | Full desktop GUI agent (C-09 **FAIL**) |
| Shared always-on desk on your NAS/GPU | True parallel bots still **PARTIAL** |
| Approvals + REX doctrine for prod Keep | Broad connector marketplace (Slack/GitHub listeners) **PARTIAL / NOT_TESTED** |
| Off-brief detection (won’t celebrate wrong cart) | Smaller local models write thinner prose than frontier cloud |

Full honesty table: [docs/COMPARISON.md](./docs/COMPARISON.md).

---

## Architecture (one glance)

```
Operator → Command Deck (:5765)
              ↓
         keep-bots-api  →  jobs / bots / briefing / approvals
              ↓
       keep-bots-worker →  Ollama (local) + tools
              ↓
   keep-desk-browser (:5766) + /desk volume (files, memory, screenshots)
```

Production Keep writes (media, HA, Arr) still go through **REX + Hermes** — bots are workers, not a security boundary.

---

## Benchmarks (systems-test)

Authoritative scorer: `python3 api/compliance_score.py`

| Metric | Value (2026-09-19 reference Keep) |
|---|---|
| RAW | 87.3% |
| WEIGHTED | **91.6%** |
| CRITICAL_GATE | **PASS** |
| CLAIMABLE | **91.6** |
| PASS / PARTIAL / FAIL / NOT_TESTED | 69 / 5 / 5 / 10 |

Browser: BROW-L3/L4 PASS · L5-prod Gate PASS (51 authed @ 90.2%, HIR 2.1%) · L6 endurance in progress.

---

## Related OtaconsKeep projects

- [Otaconskeep site](https://github.com/Otaconskeep/otaconskeep-site)  
- [KeepRoute](https://github.com/Otaconskeep/KeepRoute) — mission orchestration  
- [otacons-ai-ecosystem](https://github.com/Otaconskeep/otacons-ai-ecosystem) — Lite install  

---

## Doctrine

Bots share one desk — **not** isolation. You are the principal. Have fun, break things on purpose, and keep production mutations on REX.

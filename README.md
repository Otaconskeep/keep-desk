# Keep Desk

**Local multi-agent Command Deck** — named AI teammates, shared desk, browser computer-use, Ollama-only brain.

Designed by **Antonio G. Garcia** ([Otaconskeep](https://github.com/Otaconskeep)).

| | |
|---|---|
| **Public page** | https://otaconskeep.github.io/keepdesk/ |
| **YouTube Short** | https://www.youtube.com/shorts/2DsgEbgGDYI |
| **Install** | **Supporter vault** (Buy Me a Coffee) — not public |
| **Claimable score** | **91.6%** (critical gate PASS) |
| **Visibility** | **Private repository** |

---

## Demo

**YouTube Short:** [Keep Desk demo](https://www.youtube.com/shorts/2DsgEbgGDYI) — LIVE pages, handoffs, Done + Why.

Longer soda-mission cut + stills: [`demo/`](./demo/) on this repo (supporters).

---

## Access

This repo is **private**. Install instructions unlock on the public Keep Desk page after you support the project:

1. Buy Me a Coffee → https://www.buymeacoffee.com/otaconskeep  
2. Put your Discord handle in the BMC note  
3. Antonio issues access name / password / PIN  
4. Unlock **Install Vault** at https://otaconskeep.github.io/keepdesk/#vault  
5. Request GitHub invite if clone 404s (Discord + access name)

**Premium seats** also unlock the Keep Desk vault (same license table).

---

## Quick install (supporters with repo access)

```bash
git clone https://github.com/Otaconskeep/keep-desk.git
cd keep-desk
cp .env.example .env
# Edit LOCAL_OLLAMA_URL / LOCAL_MODEL
ollama pull gpt-oss:20b
docker compose up -d --build
# http://127.0.0.1:5765/
```

Full guide: [INSTALL.md](./INSTALL.md) · Comparison: [docs/COMPARISON.md](./docs/COMPARISON.md) · FAQ: [docs/FAQ.md](./docs/FAQ.md)

---

## Why it exists

Cloud “AI teammates” (Grok Bot, OpenAI Operator / Pilot) are exciting — and they also mean your work lives on someone else’s computer. Keep Desk is the homelab answer: same genre, your hardware, honest failure modes.

---

## Honest limitations

Browser-first (not full desktop GUI). Local model quality ≠ frontier cloud. Bots are workers — gate money and public posts. See docs/COMPARISON.md.

---

## Doctrine

Bots share one desk — not isolation. You are the principal.

# Keep Desk FAQ

## What is Keep Desk?

A **local multi-agent work deck**: named AI bots share one computer (files, shell, Chromium), take jobs from a Command Deck UI, and brief you like an operator. The brain is **Ollama on your hardware** — no required cloud LLM.

## Is it free?

**Software:** yes — clone and run.  
**Cost to you:** electricity, disk, and optional GPU. No xAI/OpenAI subscription required for the core loop.

## How is this like Grok Bot?

Same genre: persistent teammates, computer use, skills/routines, background work. Different landlord: **your** machine and model. See [COMPARISON.md](./COMPARISON.md).

## How is this like OpenAI Operator / Pilot?

Same genre: goal-directed browser agent with approvals and long-running tasks. Keep’s browser runs in **your** Docker stack, not OpenAI’s cloud VM.

## What model should I use?

Anything Ollama serves that can tool-call reasonably. Reference Keep uses **`gpt-oss:20b`** on an RTX 3090. Larger/stronger local models plan better; smaller ones are faster but thinner.

## Does it call OpenAI or xAI behind the scenes?

**No.** The stack is built to **refuse cloud LLM endpoints**. Point `LOCAL_OLLAMA_URL` at local Ollama only.

## Ports?

Default: **5765** Command Deck / API, **5766** browser service. Override in `.env`.

## Where do files go?

Under the **desk volume** (`/desk` in containers): bot memory, screenshots, scratch, and `workspace/research/<pipeline_id>/` for mission artifacts.

## What is a pipeline / batch?

A multipart brief (e.g. images → pick → YouTube → store) is split into **stages**. Each pipeline gets a **namespaced research folder** so soda research cannot leak coffee criteria into Why.

## What is “hollow” or “off-brief”?

Honesty modes:

- **Hollow / Incomplete** — work did not finish; UI should not fake a victory briefing.  
- **Off-brief** — result doesn’t match the mission (wrong product family, etc.); refuse to celebrate / cart.

## Can it buy things with my credit card?

Treat purchase flows as **dangerous**. Research and shortlist are in scope; **production spending** should go through human approval and, on OtaconsKeep, **REX** — not raw bot autonomy.

## Can multiple bots run at once?

Fleet routing is real; **heavy parallel browser** concurrency is still **partial**. Prefer one intense computer-use job at a time on modest hardware.

## Does it control my whole desktop?

**No.** Claimable computer-use is **browser-first**. Full desktop GUI agent is a known **FAIL** in the compliance matrix.

## Can I use Obsidian?

Yes — mount a vault into `/desk` and brief bots with the path. Keep does not replace Obsidian Sync.

## Is the LIVE pane always a real screenshot?

When a job is actively browsing, LIVE should reflect the browser service. When idle, Keep uses an honest **park** state — not a fake “LIVE on example.com” lie.

## What does 91.6% mean?

**Claimable weighted score** from `api/compliance_score.py` on the requirements matrix (critical gate PASS). It is **not** “91.6% of Grok’s product.” Day-to-day feel is closer to **~75%** once you count model quality, mobile, and connectors. Details: [COMPLIANCE_MATRIX.md](./COMPLIANCE_MATRIX.md).

## Where is the demo?

[`demo/keep_soda_demo.mp4`](../demo/keep_soda_demo.mp4) and [`demo/shots/`](../demo/shots/) — clean soda mission (images → pick → YouTube → Ogden store), no poisoned coffee cart.

## How do I install?

See [INSTALL.md](./INSTALL.md).

## Is this production-ready?

For **homelab / research / operator briefing**: yes, with eyes open.  
For **unguarded production mutations** (money, deletes, public posts): **no** — keep approvals and external gates.

## Who built this?

**Antonio G. Garcia** — [Otaconskeep](https://github.com/Otaconskeep). Part of the OtaconsKeep local AI ecosystem.

## License / reuse?

Fork for homelab and research. Don’t paste production secrets into public forks. Attribution appreciated.

## Something broken?

1. `docker compose logs` on api, worker, browser  
2. Confirm Ollama tags + URL from inside the container network  
3. Check desk volume permissions  
4. Open an issue on [Otaconskeep/keep-desk](https://github.com/Otaconskeep/keep-desk) with logs (redact secrets)

# Keep Desk / Keep Bots — Local Grok Bot on OtaconsKeep

**Host:** OtaconsKeep `192.168.50.219` (RTX 3090)  
**Status:** Local-only parity build (2026-09-19)  
**Brain:** Host GPU router → Ollama `gpt-oss:20b` — **NO** xAI / Claude / OpenAI cloud APIs  
**Doctrine:** Bots are workers, not a security boundary. Xof remains principal. Production Keep writes still go through REX + Hermes.

## Non-negotiable: local silicon only

Keep Desk refuses cloud LLM endpoints. Inference is pinned to:

```
LOCAL_OLLAMA_URL=http://host.docker.internal:11434/v1
LOCAL_MODEL=gpt-oss:20b
```

## What this is

A local analogue of xAI **Grok Bot**: named persistent AI teammates that share one always-on computer (filesystem + terminal + persistent Chromium), run jobs in the background, hand work to each other, learn reusable skills, schedule routines, and pause for approval before sensitive actions — all on OtaconsKeep hardware.

## Mapping: Grok Bot → Keep Desk

| Grok Bot | Keep Desk |
|---|---|
| Persistent named Bots | `bots` registry (`engineer`, `qa`, `researcher`, `pm`, …) |
| Shared cloud computer | **Desk** container + `/mnt/data/keep-desk` volume (all bots share it) |
| Browser / apps | Phase 1: HTTP fetch + files; Phase 2: Playwright sidecar; GUI via Win11 lab share (optional) |
| Background execution | `keep-bots-worker` loop (survives client disconnect) |
| Multi-agent handoffs | `handoffs` + per-bot inboxes under `/desk/inbox/<bot_id>/` |
| Group coordination | Shared thread jobs + PM bot watching open work |
| Teachable skills | `/desk/skills/<skill_id>/SKILL.md` + registry |
| Scheduled routines | `routines` (cron-like; max 50 per bot) |
| Memory / context | `/desk/memory/<bot_id>/` + job history in state DB |
| Approval boundaries | Sensitive tools → `pending_approval`; Discord `/approvals` optional later |
| X integration | Out of scope for MVP (can add via Omniroute tools later) |

## What OtaconsKeep already owns (do not duplicate)

- Persona roster, Codec, companion presence → executor
- REX approval plane for **production** media/infra → `rex_proposals` + Hermes
- Omniroute model gateway → `:20128`
- Discord Otacon bot → ears/mouth for Keep agents

Keep Desk adds the missing Grok Bot differentiator: **a first-class shared computer that workers can drive**.

## Trust model (important)

Same warning as xAI: bots on one Keep Desk share files, shell history, and (later) browser sessions. Do **not** treat bot A vs bot B as isolation.

Sensitive classes always require approval:

- Destructive shell / deletes
- Anything outside `/desk`
- External publish / purchase / email send
- Docker / HA / Arr / Seerr / production Keep mutations (those stay REX-gated forever)

## Runtime

| Service | Role | Port |
|---|---|---|
| `keep-desk` | Shared computer (bash, python, git, curl) | — |
| `keep-bots-api` | Control plane + Ops UI | `5765` |
| `keep-bots-worker` | Background job runner | — |

UI: `http://192.168.50.219:5765/`

## Phases

1. **MVP (now):** bots, jobs, handoffs, desk FS + sandboxed shell, Omniroute brain, approvals, seed 4 bots, Ops UI  
2. **Browser:** Playwright sidecar bound to desk profile  
3. **Routines + skill capture:** cron runner + “save this workflow as skill”  
4. **Keep bridge:** optional job → REX draft only (never direct Hermes execute)  
5. **Win11 desk lane:** optional GUI automation via existing `otacon-win11-lab` shared folder (not required for MVP)

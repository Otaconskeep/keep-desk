# Keep Desk vs Grok Bot vs OpenAI Pilot / Operator

Honest product comparison for operators choosing a **computer-use teammate**.  
Keep Desk is **local and free to run** (hardware + electricity). Grok Bot and OpenAI’s computer-use agents are **cloud products** with different strengths.

**Disclaimer:** Feature sets move fast. This write-up reflects OtaconsKeep’s reference Keep (Sep 2026) and public product positioning for Grok / OpenAI at that time — not a legal claim against xAI or OpenAI.

---

## One-sentence each

| Product | Pitch |
|---|---|
| **Keep Desk** | Homelab multi-agent Command Deck: named bots, shared desk, local Ollama, browser computer-use, jobs/pipelines, operator briefing UI. |
| **Grok Bot** (xAI) | Cloud AI teammates with persistent personality, tools, and computer/browser use inside xAI’s product surface — polished consumer/pro UX. |
| **OpenAI Operator / ChatGPT computer use** (“Pilot”-class agents) | Cloud agents that drive a remote browser/desktop to complete tasks for you inside OpenAI’s account & safety stack. |

*(Naming note: OpenAI has shipped and previewed computer-use under several product names. Here “Pilot” means that class of OpenAI remote-computer agents, not a specific SKU forever.)*

---

## Philosophy

| | Keep Desk | Grok Bot | OpenAI Pilot / Operator |
|---|---|---|---|
| **Where the computer lives** | Your box / LAN | xAI cloud | OpenAI cloud |
| **Where the brain lives** | Your Ollama model | xAI frontier models | OpenAI frontier models |
| **Cost model** | Hardware + power | Subscription / product access | Subscription + usage |
| **Data default** | Stays on disk you control | Vendor tenancy | Vendor tenancy |
| **UI metaphor** | Operator briefing / Command Deck | Chat + bot teammates | Chat + remote session |
| **Security doctrine** | Bots are workers; REX gates prod writes | Vendor policies + account | Vendor policies + account |
| **Fun factor** | High if you like self-hosting & cinema UI | High if you want zero ops | High if you want “it just works” |

Keep Desk exists because **“teammate that uses a computer”** should not require surrendering the computer.

---

## Capability matrix (honest)

Legend: **Y** = solid · **P** = partial / DIY · **N** = no / not the point · **?** = vendor-dependent / changing

| Capability | Keep Desk | Grok Bot | OpenAI Pilot |
|---|---|---|---|
| Named persistent bots | Y | Y | P (custom GPTs / agents vary) |
| Shared long-lived filesystem | Y (`/desk`) | P / product-specific | P (session / workspace) |
| Real browser computer-use | Y (Chromium service) | Y | Y |
| Full desktop GUI agent (arbitrary apps) | **N** (FAIL C-09) | P / ? | P / ? |
| Local-only LLM | **Y** (enforced) | N | N |
| Offline / air-gap friendly | P (needs local model + no CDN deps) | N | N |
| Multi-step jobs + pipeline stages | Y | Y | Y |
| Operator approvals for risky tools | Y | Y / ? | Y / safety layer |
| Cron / routines | Y | Y / ? | P |
| Skills / teachable workflows | Y | Y | Y |
| Mobile-native apps | N (by choice) | Y / ? | Y (ChatGPT apps) |
| Marketplace connectors (Slack, GH…) | P | Y / ? | Y / ? |
| Parallel multi-bot concurrency | P | ? | ? |
| Inspectable agent loop / logs | Y (you own logs) | P | P |
| Cart / purchase automation | P (research OK; prod $ via REX) | ? | ? |
| Open source self-host | **Y** (this repo) | N | N |
| Frontier model quality out of box | P (depends on your GPU model) | **Y** | **Y** |
| Zero-ops install | P (Docker + Ollama) | **Y** | **Y** |

---

## Where Keep Desk is stronger

1. **Sovereignty** — prompts, screenshots, research MD, and desk files never need to leave your LAN.  
2. **Cost ceiling** — no per-token surprise after the GPU is paid for.  
3. **Operator UX** — briefing-first deck, LIVE browser, Why dossier, batch matrix — built for “mission control,” not only chat bubbles.  
4. **Failure honesty** — hollow / Incomplete / off-brief paths so a soda mission cannot silently become a coffee cart win.  
5. **Integration with your stack** — REX, vault mounts, Arr/media, home automation — because the desk *is* your machine.  
6. **Fun & ownership** — you can break it, score it (`compliance_score.py`), and ship demos from real runs.

---

## Where Grok Bot / OpenAI win

1. **Model quality** — frontier cloud models still beat a 20B local for long prose, tool planning, and messy sites.  
2. **Polish & onboarding** — account, app, done. No Docker, no Ollama, no port fights.  
3. **Mobile & always-with-you** — phone apps and vendor sync.  
4. **Managed safety / abuse** — enterprise-grade policy engines (whether you love them or not).  
5. **Scale of connectors** — first-party integrations Keep has not cloned.  
6. **Desktop breadth** — Keep’s computer-use is **browser-first**; full Windows/macOS app driving is not claimed.

---

## “Grok Bot parity” — what we actually mean

OtaconsKeep tracks a **systems-test matrix** (not vibes):

| Metric | Reference Keep |
|---|---|
| RAW | 87.3% |
| WEIGHTED / CLAIMABLE | **91.6%** |
| CRITICAL_GATE | PASS |

Marketing shorthand “~75% of day-to-day Grok feel” is the **operator experience** estimate (model quality + mobile + connectors + desktop).  
**91.6% claimable** is the **scored requirements** we wrote and can evidence (browser L5-prod gate, jobs, bots, desk, approvals, etc.).

Both numbers can be true. Do not confuse them.

Known **FAIL** rows (examples): full desktop GUI agent (C-09), some connector listeners **NOT_TESTED**, true parallel bots **PARTIAL**. See [COMPLIANCE_MATRIX.md](./COMPLIANCE_MATRIX.md).

---

## Similarity to Grok Bot (the fun part)

If you like Grok Bot because:

- bots have **names and jobs**  
- they can **use a computer** while you do something else  
- you can **teach skills** and schedule routines  
- the vibe is **teammate**, not autocomplete  

…Keep Desk is the same *genre*: persistent agents on a shared machine.

Differences you will feel in five minutes:

- Keep’s UI is a **Command Deck / briefing**, not a clone of Grok’s chat chrome  
- The brain is **whatever you run in Ollama**  
- When LIVE is idle, you see an honest **park** state — not a fake “browsing” spinner  
- Research pipelines write under **`workspace/research/<pipe_id>/`** so missions don’t poison each other  

---

## Similarity to OpenAI Pilot / Operator

If you like Operator because:

- the agent **drives a browser** toward a goal  
- you can **approve** sensitive steps  
- long tasks run **while you walk away**  

…Keep Desk overlaps hard on browser computer-use + approvals + jobs.

Differences:

- Session computer is **yours** (Chromium in Docker), not OpenAI’s remote VM  
- No ChatGPT account required  
- Weaker at “figure out any website with frontier vision/planning” unless your local model is strong  
- Stronger at **homelab continuity** (files persist on `/desk` across reboots if you volume them)

---

## Limitations (do not skip)

1. **Not a cloud frontier model** — expect shorter, more brittle plans on hard sites unless you run a strong local model.  
2. **Browser ≠ desktop** — Excel/Photoshop/native apps are out of scope for claimable PASS.  
3. **Not production-safe by itself** — treat bots as untrusted workers; gate money, deletes, and public posts.  
4. **Concurrency** — fleet is real; true simultaneous heavy browsers is still partial.  
5. **CAPTCHA / anti-bot walls** — same as every computer-use agent; sometimes you must take over.  
6. **Legal / ToS** — automating third-party sites is your responsibility.  
7. **No official mobile app** — use a browser or reverse proxy if you need remote access (VPN recommended).  
8. **Docs & APIs evolve** — pin a commit for production; this is living software.

---

## Who should pick what?

| You want… | Pick |
|---|---|
| Zero ops, best model, phone app | Grok Bot or OpenAI |
| Data on your NAS, free local, cinematic ops UI | **Keep Desk** |
| Enterprise SSO + vendor compliance paperwork | OpenAI / xAI (vendor) |
| Homelab fun + REX/Hermes ecosystem | **Keep Desk** |
| “Buy this SKU on Amazon while I sleep” with max success rate | Cloud agent + human approval (model quality matters) |
| Teachable local research pipelines you can diff in git | **Keep Desk** |

---

## Bottom line

Keep Desk is **not** “Grok but stolen.” It is **Grok/Operator-shaped infrastructure you can own**: free to run, local, fun, and honest about the gaps. Use cloud bots when you want the frontier brain. Use Keep when you want the **desk** to be yours.

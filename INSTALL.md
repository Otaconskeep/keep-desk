# Install Keep Desk

This guide gets a **self-hosted Keep Desk** running with Docker Compose: API, worker, browser computer-use service, and the Command Deck UI.

**Requirements**

| Item | Recommendation |
|---|---|
| OS | Linux (x86_64). Tested on Proxmox / Debian-family hosts |
| Docker | Docker Engine 24+ with Compose v2 |
| RAM | 16 GB+ host RAM (32 GB+ comfortable with browser + model) |
| GPU | Optional but strongly recommended for local Ollama (e.g. RTX 3090) |
| Disk | ≥20 GB free for images, desk volume, and screenshots |
| Ollama | Reachable from containers (`LOCAL_OLLAMA_URL`) with a chat model pulled |

You do **not** need an OpenAI, xAI, or Anthropic API key. Keep Desk is local-brain only.

---

## 1. Clone

```bash
git clone https://github.com/Otaconskeep/keep-desk.git
cd keep-desk
```

---

## 2. Environment

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Ollama reachable from Docker network
LOCAL_OLLAMA_URL=http://172.17.0.1:11434
LOCAL_MODEL=gpt-oss:20b

# Optional: bind ports if 5765/5766 collide
KEEP_API_PORT=5765
KEEP_BROWSER_PORT=5766
```

**Ollama tips**

```bash
# On the host
ollama pull gpt-oss:20b   # or your preferred local model
curl -s http://127.0.0.1:11434/api/tags | head
```

If containers cannot reach host Ollama:

- Linux: use `http://172.17.0.1:11434` or `host.docker.internal` (with `extra_hosts`)
- Or run Ollama in Compose on the same network and point `LOCAL_OLLAMA_URL` at that service

The API **rejects** cloud LLM base URLs by design. Do not point `LOCAL_OLLAMA_URL` at OpenAI/xAI.

---

## 3. Start

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f keep-bots-api
```

Expected services (names may match compose file):

- `keep-bots-api` — Command Deck + REST API (`:5765`)
- `keep-bots-worker` — job runner / tool loop
- `keep-desk-browser` — Chromium computer-use (`:5766`)

Open:

- **Command Deck:** http://127.0.0.1:5765/
- **Browser park / debug:** http://127.0.0.1:5766/ (if exposed)

---

## 4. First mission (smoke test)

1. Open the Command Deck.  
2. Transmit a short order, e.g.  
   `Research the latest AI news briefly and write a 5-bullet summary to /desk/scratch/ai_news.md`  
3. Confirm a job appears, LIVE / status updates, and a file lands under the desk volume.  
4. Open **Why** after completion — you should see a short dossier, not a hollow parking screen if work finished.

**Browser smoke**

```
Open example.com, take a screenshot, then park.
```

You should see the LIVE pane leave the parking overlay when navigation succeeds.

---

## 5. Persistent desk data

Compose mounts a volume (or bind) for `/desk` — files, bot memory, screenshots, research workspaces.

Back up that volume if you care about bot memory and research artifacts.

Default layout (inside the volume / container):

```
/desk/
  bots/<BOT>/memory.md
  screenshots/
  workspace/research/<pipe_id>/   # pipeline-namespaced artifacts
  scratch/
```

---

## 6. Optional: Obsidian / vault

To give bots a vault (Obsidian-style markdown):

1. Bind-mount your vault into the desk volume (e.g. `/desk/vault`).  
2. Tell bots in brief or memory where the vault lives.  
3. Prefer **read + write markdown** over cloud sync plugins inside Chromium.

Keep Desk does **not** replace Obsidian Sync; it is a local filesystem agent.

---

## 7. Production / OtaconsKeep reference Keep

The live reference Keep (`192.168.50.219:5765`) is wired into the wider Otacons ecosystem:

- REX for production mutations  
- Hermes for ops  
- Host Ollama + GPU  

For a **portable fork**, the compose file in this repo is enough. Do not copy production secrets, REX tokens, or private vaults into a public clone.

---

## 8. Upgrading

```bash
git pull
docker compose up -d --build
```

Re-score compliance (optional):

```bash
docker compose exec keep-bots-api python3 /app/api/compliance_score.py
# or run on host against checked-out tree
python3 api/compliance_score.py
```

---

## 9. Troubleshooting

| Symptom | Check |
|---|---|
| UI loads, jobs stuck | `docker compose logs keep-bots-worker` · Ollama reachable? |
| “cloud LLM refused” | `LOCAL_OLLAMA_URL` must be local Ollama, not api.openai.com |
| LIVE stuck on park | Browser container up? `/park` healthy? Network DNS from browser container? |
| Empty Why / hollow | Job Incomplete or off-brief — open Batch / research folder for that `pipe_id` |
| Port in use | Change `KEEP_API_PORT` / `KEEP_BROWSER_PORT` in `.env` |
| OOM / slow | Smaller model, less concurrent browser tabs, more host RAM |

---

## 10. Uninstall

```bash
docker compose down
# optional: remove desk volume
docker volume ls | grep keep
docker volume rm <volume_name>
```

---

## Next

- [README](./README.md) — product overview  
- [FAQ](./docs/FAQ.md) — common questions  
- [COMPARISON](./docs/COMPARISON.md) — vs Grok Bot & OpenAI Pilot / Operator  
- [COMPLIANCE_MATRIX](./docs/COMPLIANCE_MATRIX.md) — scorecard  

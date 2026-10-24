# Running evaluations on the BRACU research PC

The lab PC (i7-14700K, RTX 4080 Super 16 GB, 64 GB RAM, 1 TB SSD) is available on **Saturday and
Monday, 1:00 am to 1:00 pm**. It removes the main limit of this project: Groq's free tier allows
about 200K tokens per model per day, and one patch episode costs 25-35K. A local model server has
no such limit, so we can run every task 3+ times on several models, which the paper needs.

**What it is for**
1. **Agent evaluations**: open models served locally by Ollama, through the same harness as before.
2. **The LLM judge (V4)**: gpt-oss-20b runs locally, so re-judging every solution costs nothing.
3. **Optional, later**: small GRPO fine-tuning runs (QLoRA on a 4-8B model fits in 16 GB).

## Step 0: find these things out first

Ask the lab admin, or check on your first visit:

| Question | Why it matters |
|---|---|
| Which **OS**: Windows 11 or Ubuntu? | The setup steps differ (below). |
| Do we get **admin / sudo** rights? | Installing Docker, WSL2 and Ollama needs them. If not, ask the admin to install them from the list below. |
| How do we **connect remotely**: SSH, RDP, AnyDesk, Chrome Remote Desktop? Is a VPN needed? | SSH is best for long jobs. With a remote desktop, the job must keep running after you disconnect. |
| Do **files stay** between sessions, on our own user account? | Models are about 25 GB, so downloading them every session would waste hours. |
| Can it **download** from ollama.com, Docker Hub, ghcr.io and GitHub? About 40 GB the first time. | A university firewall or proxy might block some of these. |
| Can a job **run unattended** (no auto-logout, sleep or reboot during the window)? | A batch runs for hours. |
| Is the PC **shared** with other users? | Never leave API keys or GitHub logins on a shared PC (see "Safety"). |
| What does "**offline access**" mean: physically in the lab? | Then you can also start jobs in person. |

## Step 1: one-time setup (about 2 hours, mostly downloads)

### If it runs Windows 11
1. Install **Git for Windows**, **uv** (`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`),
   **WSL2** (`wsl --install`, then reboot) and **Docker Desktop** (WSL2 backend).
2. Install **Ollama for Windows** from ollama.com. Then set these user environment variables and
   restart Ollama:
   - `OLLAMA_CONTEXT_LENGTH=32768` (patch episodes are long; the default context is too short)
   - `OLLAMA_KEEP_ALIVE=-1` (keep the model loaded between requests)
   - `OLLAMA_MODELS=D:\ollama` only if C: is short of space
3. Run the repo's shell scripts from **Git Bash**, as on your laptop.

### If it runs Ubuntu
1. Install Git, Docker Engine (and add yourself to the `docker` group), and uv.
2. Install Ollama with the official script from ollama.com. Set the same `OLLAMA_*` variables with
   `sudo systemctl edit ollama` (an `[Service]` section with `Environment=` lines), then
   `sudo systemctl restart ollama`.

### Both
```bash
git clone https://github.com/zariffromlatif/secops-mcp-rlvr-gym.git
cd secops-mcp-rlvr-gym
uv sync --extra mcp
ollama pull gpt-oss:20b
ollama pull qwen3:14b
ollama cp gpt-oss:20b local/gpt-oss-20b
ollama cp qwen3:14b local/qwen3-14b
```
Check the current model tags on ollama.com/library before pulling; newer versions may exist.
The `ollama cp` aliases matter: run folders are named after the model, and Windows doesn't allow
the `:` in `gpt-oss:20b` in folder names.

**Which models fit in 16 GB of VRAM**
- `gpt-oss-20b`: about 13 GB, fits fully. It is also the judge model.
- `qwen3-14b` (4-bit): about 9 GB plus context, fits fully.
- Bigger models (27-32B dense) don't fit and partly run on the CPU, which is much slower. A
  mixture-of-experts model like `qwen3:30b-a3b` is an exception worth trying: only a small part
  of it runs per token, so it stays usable with the 64 GB of system RAM.

**Check it works**
```bash
ollama run local/gpt-oss-20b "Say hi"
ollama ps
```
`ollama ps` must show **100% GPU**. If it shows a CPU share, the model or context is too big.

## Step 2: each lab session

```bash
cd secops-mcp-rlvr-gym
git pull
MODELS="local/gpt-oss-20b local/qwen3-14b" REPEATS=3 DEADLINE=12:15 bash scripts/local_batch.sh
```
- `scripts/local_batch.sh` runs both environments for each model, 3 attempts per task, and starts
  no new run after `DEADLINE`, so it finishes before the window closes at 1 pm.
- Then it re-scores every solution with V1-V4, using the local gpt-oss-20b as the judge.
- Progress is in `.tmp/local/log.txt`. Results land in `results/audit/local_verdicts.csv` and
  `results/evals/`.
- The first session should start with a short run (`REPEATS=1`, one model) to measure how long an
  episode takes. Then plan the next sessions from that number.

**Getting results back to your laptop**: push them to a branch, then sign out of GitHub on the lab
PC:
```bash
git checkout -b results-$(date +%F)
git add results/
git commit -m "Local eval results $(date +%F)"
git push -u origin HEAD
```

## Safety on a shared PC
- No Groq or Gemini keys are needed here: the local server needs none (the scripts use a dummy
  key, `LOCAL_API_KEY=local`). Don't copy `.env` to this PC.
- Sign in to GitHub only to push, and sign out at the end of the session (on Windows: Credential
  Manager, remove the `git:https://github.com` entry).
- Ollama listens only on this PC (`127.0.0.1:11434`) by default. Leave it that way.

## For the paper
- Local models are different checkpoints from the Groq ones. Report them as separate models
  (for example "gpt-oss-20b, Ollama, MXFP4"), with the serving settings: context length,
  temperature, number of attempts.
- Use **one judge setup for all solutions**. When the local judge is in place, re-judge the Groq
  solutions with it too, so V4 means the same thing everywhere.

# Lab runbook: running everything on the BRACU PC

Follow the parts in order. Every step gives the command to copy, what you should see, and what to
do if you don't. Part 1 happens once; on later visits start at Part 2.

| Part | What | Time | Needs |
|---|---|---|---|
| 1 | One-time setup | about 1 hour, mostly downloads | admin rights to install software |
| 2 | Two live rollouts (unblocks the v0.3.0 Hub release) | 20-30 minutes | Ollama, Docker |
| 3 | The training run (V3 vs V2) | many hours; runs unattended | the GPU free of Ollama |
| 4 | Send the results back | 5 minutes | your GitHub login |
| 5 | Judges, red team and contamination probe | a few hours | Ollama, Docker; not while training |

**Where to type commands.** On Windows, use **Git Bash** (Start menu, "Git Bash"), not PowerShell or
cmd: every command below is written for it. On Ubuntu, any terminal. Copy one block at a time.

**Two rules that prevent most problems:**
1. Always start Python commands with `uv run --no-sync`. Plain `uv run` or `uv sync` removes the
   training packages; if that happens, repeat step 1.5.
2. Never commit or share the file `~/.secops-gym-heldout-secret` (Part 3 creates it).

---

## Part 1: one-time setup

### 1.1 Check the GPU

```bash
nvidia-smi
```

You should see a table that names **NVIDIA GeForce RTX 4080 SUPER** and shows a "CUDA Version".
If the command is not found, the NVIDIA driver is missing: ask the lab admin to install the latest
NVIDIA driver, then reopen Git Bash.

### 1.2 Install the tools

Skip any you already have. Check what you have with `git --version`, `uv --version` and `docker info`.

**Windows**
- **Git for Windows** (this also gives you Git Bash): https://git-scm.com/download/win
- **uv**: in PowerShell, run
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`,
  then close and reopen Git Bash.
- **Docker Desktop**: https://www.docker.com/products/docker-desktop/ . It needs WSL2 or Hyper-V.
  If the installer refuses or Docker never starts, skip it and use step 1.6b instead.

**Ubuntu**
- `sudo apt install -y git`
- uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then open a new terminal.
- Docker Engine: https://docs.docker.com/engine/install/ubuntu/ , then
  `sudo usermod -aG docker $USER` and log out and back in.

### 1.3 Get the code, on the right branch

```bash
cd ~
git clone https://github.com/zariffromlatif/secops-mcp-rlvr-gym.git
cd secops-mcp-rlvr-gym
git checkout ccr-cfcbcb20-dpk9k3
ls train/campaign.py
```

The last line must print `train/campaign.py`. **The training code is on the branch
`ccr-cfcbcb20-dpk9k3`, not on `main`.** If git asks you to sign in, sign in with your GitHub account
in the browser window it opens.

### 1.4 Install the project

```bash
uv sync --extra mcp
```

You should see uv resolve and install packages, ending without an error.

### 1.5 Install PyTorch with CUDA, and the training packages

**Windows only, first:** open https://pytorch.org/get-started/locally/ and choose
*Stable · Windows · Pip · Python · the newest CUDA*. It shows a command like
`pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu128`. Run it like
this, with `uv pip install`, only `torch`, and the `cu...` part copied from the website:

```bash
uv pip install torch --index-url https://download.pytorch.org/whl/cu128
```

(On Windows, plain `pip install torch` gives a CPU-only build. On Ubuntu, skip this; the next command
brings a CUDA build.)

**Both:**

```bash
uv pip install -r train/requirements.txt
```

If only `bitsandbytes` fails to install, ignore it: it is needed only for 4-bit loading, which the
default run does not use. Install the rest with
`uv pip install "trl>=1.17,<2" "peft>=0.17" "transformers>=4.56.2" "datasets>=4.7" "accelerate>=1.11"`.

**Check:**

```bash
uv run --no-sync python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

You should see a version, then **`True`**, then **`NVIDIA GeForce RTX 4080 SUPER`**. If it prints
`False` or fails, you have a CPU build: repeat the Windows command above with `--reinstall` added
after `install`.

### 1.6 Something to score answers with

**a) With Docker (preferred).** Start Docker Desktop (wait for "Engine running"), then:

```bash
docker compose -f runtime/docker-compose.yml up -d --wait
```

You should see `Container runtime-db-1 Healthy`.

**b) Without Docker.** Install PostgreSQL 16 from https://www.postgresql.org/download/ and remember
the password you choose for the `postgres` user. Create a database named `gym` (in pgAdmin:
Databases, Create, Database, name `gym`). Then, **every time you open Git Bash**, run this line with
your password:

```bash
export DATABASE_URL="postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/gym"
```

Without Docker the scorer runs in "local" mode, which is not isolated; the report says so.

### 1.7 Check the scorer, before any model is involved

```bash
uv run --no-sync python -m train.grpo --dry-run
```

(Without Docker, add `--sandbox local`.) The first time takes several minutes: it builds the scoring
sandbox image once. You should see a table of 17 tasks in which every **gold** column reads
`1.00/1.00/1.00`, ending in `34 samples scored`. If any gold value is not `1.00/1.00/1.00`, stop
and send me the output.

Setup is done.

---

## Part 2: two live rollouts (for the v0.3.0 Hub release)

These run one task of each environment with a real model, through the same code the Hub will run.
They need Ollama set up as in [bracu-pc.md](bracu-pc.md), Step 1 (including
`OLLAMA_CONTEXT_LENGTH=32768`), and Docker. Skip this part if either is missing.

```bash
cd ~/secops-mcp-rlvr-gym
ollama run local/gpt-oss-20b "Say hi"
LOCAL_LLM=http://host.docker.internal:11434/v1 sh scripts/run_eval.sh patches local/gpt-oss-20b -n 1 --no-push
LOCAL_LLM=http://host.docker.internal:11434/v1 sh scripts/run_eval.sh workflows local/gpt-oss-20b -n 1 --no-push
```

The first line must answer. Each rollout should end with a results summary (a reward between 0 and
1), not an error. Whether the model solves the task does not matter: this checks that a live agent
runs end to end. The output lands in `.tmp/evals/`. If either fails, copy its last 40 lines and send
them to me.

---

## Part 3: the training run

### 3.1 Before each start

```bash
cd ~/secops-mcp-rlvr-gym
git pull
```

(Do not run `uv sync` after pulling; see the two rules at the top.)

**Free the GPU.** Ollama keeps its model in GPU memory and leaves too little for training.
- Windows: right-click the Ollama icon in the taskbar's notification area, then **Quit Ollama**.
- Ubuntu: `sudo systemctl stop ollama`

Then check:

```bash
nvidia-smi
```

The "Memory-Usage" column should be under about 1,000 MiB, with no `ollama` process listed.

**With Docker:** make sure Docker Desktop is running, then
`docker compose -f runtime/docker-compose.yml up -d --wait`.
**Without Docker:** run your `export DATABASE_URL=...` line from step 1.6b.

**Keep the PC awake.** On Windows: Settings, System, Power, set Screen and Sleep to *Never*. You may
close a Remote Desktop window, but do not sign out: signing out stops the run.

### 3.2 Start it

```bash
uv run --no-sync python -m train.campaign --steps 400 --evaluate-at 100 200
```

This one command does everything, in order:

1. **Checks** that PyTorch sees the GPU and that it is free, then that the scorer marks every gold
   fix as solved (about 1 minute).
2. **Makes tasks:** 9 held-out tasks from a secret seed (saved in `~/.secops-gym-heldout-secret`)
   and 9 extra training tasks, and validates them (about 5 minutes).
3. **Measures the base model** on all tasks, 4 answers each. The first time, it downloads the model
   (about 3 GB).
4. **Trains V3 and V2 in turns**, 25 steps at a time, so both always have about the same number of
   steps.
5. **At 100, 200 and 400 steps**, evaluates both trained models and rewrites
   `results/train/README.md`. At each of these points you already have a complete comparison.

**What to watch:** lines that start with a time, like `[14:02:11]`. After every 25 steps it prints
`pace: N s per step ...; about H h of training left`. The full log is `results/train/campaign.log`.
`nvidia-smi` in a second Git Bash window shows the GPU working.

**How long:** the pace line tells you. As a rough guide, 60-90 seconds per step makes 400 steps for
both runs 13-20 hours, plus the evaluations. Leaving it overnight is fine.

### 3.3 If it stops

Whatever the reason (you pressed Ctrl+C, the PC restarted, an error you fixed), **run the same
command again**. It skips everything already done and continues from the last checkpoint, losing at
most 25 steps. Use the **same command every time**. You may raise `--steps` or add milestones to
`--evaluate-at` later; don't change the other options.

To stop by a set time instead, add `--deadline 23:30` (24-hour clock). It then saves and stops before
that time.

### 3.4 If you see an error

| The message says | Do this |
|---|---|
| `PyTorch cannot see a CUDA GPU` | Step 1.5: install the CUDA build of PyTorch. |
| `only N GB of GPU memory free` | Quit Ollama (3.1), check `nvidia-smi` for other programs, start again. |
| `no working scorer` | Start Docker Desktop and run the `docker compose` line (1.6a), or set `DATABASE_URL` (1.6b). |
| `CUDA out of memory` while training | Add `--batch 2 --grad-accum 16` (same 32 answers per step, less memory) and keep them on every later run. |
| `No module named 'trl'` (or `peft`, `transformers`) | You ran `uv sync` or plain `uv run`: repeat step 1.5. |
| `this campaign uses <model>; start a new one with another --out` | You changed `--model`. Go back to the old one, or add `--out results/train-<name>` for a new campaign. |
| Anything else | Send me the last 40 lines of `results/train/campaign.log`. |

---

## Part 4: send the results back

At the end of a visit, even if training is not finished:

```bash
cd ~/secops-mcp-rlvr-gym
git add results/train
git commit -m "Lab training results $(date +%F)"
git push
```

If the push is rejected because the branch moved, run `git pull --rebase`, then `git push` again.

- Model weights (`checkpoint-*`, `final/`) are not added; they stay on the lab PC, which is what the
  next visit continues from.
- `samples.jsonl` files can reach tens of MB; that is fine.
- **Keep the secret:** open `~/.secops-gym-heldout-secret` and copy its one line into a private note.
  Without it, nobody, you included, can rebuild the held-out tasks.
- On a shared PC, sign out of GitHub afterwards: Control Panel, Credential Manager, Windows
  Credentials, remove `git:https://github.com`.

Then tell me it's pushed.

---

## Part 5: judges, red team and contamination probe (optional, after training)

These use the local model through Ollama, so run them when training is not running.

**Start Ollama** (open the app; on Ubuntu `sudo systemctl start ollama`), then:

```bash
cd ~/secops-mcp-rlvr-gym
ollama run local/gpt-oss-20b "Say hi"
export LOCAL_API_KEY=local
```

**5.1 The LLM judges (V4, V5) on all 122 known-answer solutions.** This takes a few hours. Answers
are cached, so an interrupted run continues where it stopped.

```bash
uv run --no-sync python -m audit.verify results/audit/corpus.jsonl --out results/audit/corpus_verdicts.csv --sandbox warm \
  --judge-model local/gpt-oss-20b --judge-base-url http://localhost:11434/v1 --judge-key-var LOCAL_API_KEY \
  --v5-model local/gpt-oss-20b --v5-base-url http://localhost:11434/v1 --v5-key-var LOCAL_API_KEY
uv run --no-sync python -m audit.analyze results/audit/corpus_verdicts.csv --known results/audit/corpus.jsonl --out results/audit/corpus_report.md
```

Without Docker, use `--sandbox local`. V5 needs Docker to run the code; without Docker, leave out the
three `--v5-...` options.

**5.2 The red team:** the model tries to get every task scored as solved without fixing it.

```bash
uv run --no-sync python -m audit.hacker --all --model local/gpt-oss-20b --base-url http://localhost:11434/v1 --key-var LOCAL_API_KEY --attempts 5 --sandbox warm
```

Results land in `results/hacker/`. An attempt that scored as solved is a hole in the scorer, so tell
me straight away.

**5.3 The contamination probe** (a few minutes):

```bash
uv run --no-sync python -m audit.contamination --model local/gpt-oss-20b --base-url http://localhost:11434/v1 --key-var LOCAL_API_KEY --out results/audit/contamination-gpt-oss-20b.json
```

**Send these back:**

```bash
git add results
git commit -m "Lab audit runs $(date +%F)"
git push
```

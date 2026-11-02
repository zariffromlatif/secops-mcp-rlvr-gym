# Lab runbook in PowerShell

The same steps as [lab-runbook.md](lab-runbook.md), for Windows PowerShell instead of Git Bash. The
runbook explains each step and what to do when something goes wrong; this page is only the commands,
in order. Lines starting with `#` are comments. Run one block at a time.

Always start Python commands with `uv run --no-sync`, and never commit or share
`$HOME\.secops-gym-heldout-secret`.

## Part 1: one-time setup

```powershell
# 1.1 The GPU: the table must name NVIDIA GeForce RTX 4080 SUPER
nvidia-smi

# 1.2 Tools: check what you have, install only what is missing
git --version
uv --version
docker info
winget install --id Git.Git -e --source winget
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Docker Desktop needs WSL2 or Hyper-V; if it will not install or start, skip it and use 1.6b
winget install --id Docker.DockerDesktop -e --source winget
# Python output and files in UTF-8 (once)
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
# Now close PowerShell and open a new window, so it finds git and uv
```

```powershell
# 1.3 The code, on the branch that has the training code (must print True)
Set-Location $HOME
git clone https://github.com/zariffromlatif/secops-mcp-rlvr-gym.git
Set-Location $HOME\secops-mcp-rlvr-gym
git checkout ccr-cfcbcb20-dpk9k3
Test-Path train\campaign.py
# Your name and email for the commits in Part 4 (this repository only)
git config user.name "Your Name"
git config user.email "you@example.com"
```

```powershell
# 1.4 The project
uv sync --extra mcp

# 1.5 PyTorch with CUDA (copy the cu... part from https://pytorch.org/get-started/locally/), then the training packages
uv pip install torch --index-url https://download.pytorch.org/whl/cu128
uv pip install -r train/requirements.txt
# Only if bitsandbytes alone failed above:
uv pip install "trl>=1.17,<2" "peft>=0.17" "transformers>=4.56.2" "datasets>=4.7" "accelerate>=1.11"
# Must print a version, True, NVIDIA GeForce RTX 4080 SUPER
uv run --no-sync python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# Only if it printed False: reinstall the CUDA build
uv pip install --reinstall torch --index-url https://download.pytorch.org/whl/cu128
```

```powershell
# 1.6a With Docker: start Docker Desktop, wait for the engine, start the database (Container runtime-db-1 Healthy)
Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
do { Start-Sleep 5; docker info *> $null } until ($LASTEXITCODE -eq 0)
docker compose -f runtime/docker-compose.yml up -d --wait
```

```powershell
# 1.6b Without Docker: PostgreSQL 16 (choose a password without @ : / # in the installer), a database named gym
winget install --id PostgreSQL.PostgreSQL.16 -e --source winget --interactive
& "$env:ProgramFiles\PostgreSQL\16\bin\createdb.exe" -U postgres gym
# Put your password in both lines; the first remembers it for new windows
[Environment]::SetEnvironmentVariable("DATABASE_URL", 'postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/gym', "User")
$env:DATABASE_URL = 'postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/gym'
```

```powershell
# 1.7 The scorer, before any model: every gold column 1.00/1.00/1.00, ending in "34 samples scored"
uv run --no-sync python -m train.grpo --dry-run
# Without Docker instead:
uv run --no-sync python -m train.grpo --dry-run --sandbox local
```

```powershell
# 1.8 Ollama and the local model (Parts 2 and 5 only)
winget install --id Ollama.Ollama -e --source winget
[Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "32768", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "-1", "User")
$env:OLLAMA_CONTEXT_LENGTH = "32768"
$env:OLLAMA_KEEP_ALIVE = "-1"
# Restart Ollama so it reads them
Get-Process -Name "ollama*" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
do { Start-Sleep 2; try { $up = (Invoke-RestMethod http://localhost:11434/api/version).version } catch { $up = $null } } until ($up)
# The model (about 13 GB), under the name the scripts use; ollama ps must show 100% GPU
ollama pull gpt-oss:20b
ollama cp gpt-oss:20b local/gpt-oss-20b
ollama run local/gpt-oss-20b "Say hi"
ollama ps
```

## Part 2: two live rollouts (needs Docker and Ollama)

```powershell
# Once: the Linux devbox the evaluations run in
Set-Location $HOME\secops-mcp-rlvr-gym
$bash = "$env:ProgramFiles\Git\bin\bash.exe"
& $bash scripts/devbox.sh uv sync --extra mcp --extra envs
```

```powershell
# Each time: copy the tasks into the environments ("synced environments"), then one rollout of each
Set-Location $HOME\secops-mcp-rlvr-gym
$bash = "$env:ProgramFiles\Git\bin\bash.exe"
& $bash scripts/devbox.sh uv run --no-sync python scripts/sync_envs.py
ollama run local/gpt-oss-20b "Say hi"
$env:LOCAL_LLM = "http://host.docker.internal:11434/v1"
& $bash scripts/run_eval.sh patches local/gpt-oss-20b -n 1 --no-push
& $bash scripts/run_eval.sh workflows local/gpt-oss-20b -n 1 --no-push
Remove-Item Env:LOCAL_LLM
# The output is in .tmp\evals
Get-ChildItem .tmp\evals
```

## Part 3: the training run

```powershell
# 3.1 Before each start
Set-Location $HOME\secops-mcp-rlvr-gym
git pull
# Free the GPU: quit Ollama, then Memory-Usage must be under about 1,000 MiB
Get-Process -Name "ollama*" -ErrorAction SilentlyContinue | Stop-Process -Force
nvidia-smi
# With Docker:
Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
do { Start-Sleep 5; docker info *> $null } until ($LASTEXITCODE -eq 0)
docker compose -f runtime/docker-compose.yml up -d --wait
# Without Docker, only if you did not save DATABASE_URL in 1.6b:
$env:DATABASE_URL = 'postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/gym'
# Keep the PC awake on mains power (do not sign out while it runs)
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 0
```

```powershell
# 3.2 Start it; after any stop, run exactly the same command again
uv run --no-sync python -m train.campaign --steps 400 --evaluate-at 100 200
# Or, to save and stop before a set time:
uv run --no-sync python -m train.campaign --steps 400 --evaluate-at 100 200 --deadline 23:30
# Only after "CUDA out of memory": add these two options, and keep them on every later run
uv run --no-sync python -m train.campaign --steps 400 --evaluate-at 100 200 --batch 2 --grad-accum 16
```

```powershell
# In a second PowerShell window, to watch it
Set-Location $HOME\secops-mcp-rlvr-gym
Get-Content results\train\campaign.log -Tail 20 -Wait
nvidia-smi -l 10
# The last 40 lines, to send when something goes wrong
Get-Content results\train\campaign.log -Tail 40
```

## Part 4: send the results back

```powershell
Set-Location $HOME\secops-mcp-rlvr-gym
git add results/train
git commit -m "Lab training results $(Get-Date -Format yyyy-MM-dd)"
git push
# Only if the push was rejected because the branch moved:
git pull --rebase
git push
# Copy this one line into a private note (never commit it)
Get-Content $HOME\.secops-gym-heldout-secret
# On a shared PC, sign out of GitHub afterwards
cmdkey /delete:git:https://github.com
```

## Part 5: judges, red team and contamination probe (not while training)

```powershell
Set-Location $HOME\secops-mcp-rlvr-gym
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
do { Start-Sleep 2; try { $up = (Invoke-RestMethod http://localhost:11434/api/version).version } catch { $up = $null } } until ($up)
ollama run local/gpt-oss-20b "Say hi"
$env:LOCAL_API_KEY = "local"
# With Docker:
docker compose -f runtime/docker-compose.yml up -d --wait
```

```powershell
# 5.1 The LLM judges (V4, V5) on all 122 known-answer solutions (a few hours; an interrupted run continues)
uv run --no-sync python -m audit.verify results/audit/corpus.jsonl --out results/audit/corpus_verdicts.csv --sandbox warm --judge-model local/gpt-oss-20b --judge-base-url http://localhost:11434/v1 --judge-key-var LOCAL_API_KEY --v5-model local/gpt-oss-20b --v5-base-url http://localhost:11434/v1 --v5-key-var LOCAL_API_KEY
# Without Docker instead (no V5):
uv run --no-sync python -m audit.verify results/audit/corpus.jsonl --out results/audit/corpus_verdicts.csv --sandbox local --judge-model local/gpt-oss-20b --judge-base-url http://localhost:11434/v1 --judge-key-var LOCAL_API_KEY
uv run --no-sync python -m audit.analyze results/audit/corpus_verdicts.csv --known results/audit/corpus.jsonl --out results/audit/corpus_report.md
```

```powershell
# 5.2 The red team (results in results\hacker; an attempt scored as solved is a hole: report it)
uv run --no-sync python -m audit.hacker --all --model local/gpt-oss-20b --base-url http://localhost:11434/v1 --key-var LOCAL_API_KEY --attempts 5 --sandbox warm
# Without Docker: the same with --sandbox local
uv run --no-sync python -m audit.hacker --all --model local/gpt-oss-20b --base-url http://localhost:11434/v1 --key-var LOCAL_API_KEY --attempts 5 --sandbox local
```

```powershell
# 5.3 The contamination probe (a few minutes)
uv run --no-sync python -m audit.contamination --model local/gpt-oss-20b --base-url http://localhost:11434/v1 --key-var LOCAL_API_KEY --out results/audit/contamination-gpt-oss-20b.json
```

```powershell
# Send these back
git add results
git commit -m "Lab audit runs $(Get-Date -Format yyyy-MM-dd)"
git push
```

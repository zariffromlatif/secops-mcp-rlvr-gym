# Lab runbook in PowerShell, without admin rights

Every command for the BRAC lab PC, first to last, for Windows PowerShell on an account **without
admin rights**, so without Docker. [lab-runbook.md](lab-runbook.md) explains each step and what to do
when something goes wrong. Lines starting with `#` are comments; run one block at a time.

What changes without Docker:

| | Without Docker |
|---|---|
| Scoring | "local" mode: a PostgreSQL you run yourself (from its zip, no installer) and the tests in the same Python process as the answer. The campaign picks it on its own. |
| Training (Part 3) | runs as usual |
| Two live rollouts (old Part 2) | **not on this PC**: they need Docker. Do them on a machine where you have admin rights, or skip them. |
| Red team, V5 judge | **not on this PC**: they need the isolated sandbox |
| Afterwards (Part 6) | every training answer is scored again in the isolated sandbox on a machine with Docker, so a reward earned by a trick that works only in local mode would show up |

Local mode runs the model's answers as you, on this PC, without a sandbox. A 1.5B model writing a
FastAPI file is very unlikely to do harm, but train under an account that holds nothing you would
mind losing, and sign out of GitHub after pushing (Part 4).

Two rules: always start Python commands with `uv run --no-sync`, and never commit or share
`$HOME\.secops-gym-heldout-secret`.

## Part 1: one-time setup

```powershell
# 1.1 The GPU: the table must name NVIDIA GeForce RTX 4080 SUPER
nvidia-smi

# 1.2 Tools: check what you have
git --version
uv --version
ollama --version
# uv (installs for your account only)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Git, only if git --version failed (for your account only; if winget refuses, run the installer
# from https://git-scm.com/download/win and choose "Only for me")
winget install --id Git.Git -e --source winget --scope user
# Python output and files in UTF-8
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
# 1.4 The project, then PyTorch with CUDA (copy the cu... part from https://pytorch.org/get-started/locally/)
uv sync --extra mcp
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
# 1.5 PostgreSQL without admin rights: the official zip (about 330 MB), run as you
Set-Location $HOME
curl.exe -L -o pg16.zip https://get.enterprisedb.com/postgresql/postgresql-16.15-1-windows-x64-binaries.zip
tar -xf pg16.zip pgsql/bin pgsql/lib pgsql/share "pgsql/pgAdmin 4/python/vcruntime140.dll" "pgsql/pgAdmin 4/python/vcruntime140_1.dll"
Remove-Item pg16.zip
# The Visual C++ runtime it needs, if Windows lacks it
if (-not (Test-Path "$env:WINDIR\System32\vcruntime140_1.dll")) { Copy-Item "$HOME\pgsql\pgAdmin 4\python\vcruntime140*.dll" "$HOME\pgsql\bin\" }
# A database cluster in your home folder, with a random password, on port 5433 (localhost only).
# --no-locale sorts text byte by byte, exactly like the database the scorer was validated on.
$pgpw = -join ((48..57) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
Set-Content "$HOME\pgpass.tmp" $pgpw -NoNewline -Encoding ascii
& "$HOME\pgsql\bin\initdb.exe" -D "$HOME\pgdata" -U postgres -E UTF8 --no-locale --auth=scram-sha-256 --pwfile="$HOME\pgpass.tmp"
Remove-Item "$HOME\pgpass.tmp"
Add-Content "$HOME\pgdata\postgresql.conf" "port = 5433"
# Start it in the background, wait until it answers, create the database gym
Start-Process -WindowStyle Hidden -FilePath "$HOME\pgsql\bin\pg_ctl.exe" -ArgumentList "-D `"$HOME\pgdata`" -l `"$HOME\pgdata\server.log`" start"
do { Start-Sleep 2; & "$HOME\pgsql\bin\pg_isready.exe" -h localhost -p 5433 *> $null } until ($LASTEXITCODE -eq 0)
$env:PGPASSWORD = $pgpw
& "$HOME\pgsql\bin\createdb.exe" -h localhost -p 5433 -U postgres gym
# Tell the project where it is (remembered for new windows too)
$url = "postgresql+psycopg://postgres:$pgpw@localhost:5433/gym"
[Environment]::SetEnvironmentVariable("DATABASE_URL", $url, "User")
$env:DATABASE_URL = $url
```

```powershell
# 1.6 The scorer, before any model: every gold column 1.00/1.00/1.00, ending in "34 samples scored"
Set-Location $HOME\secops-mcp-rlvr-gym
uv run --no-sync python -m train.grpo --dry-run --sandbox local
```

```powershell
# 1.7 Ollama and the local model (for Part 5 only; skip what is already there)
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

## Part 2: the two live rollouts

They need Docker, so not on this PC. Skip this part.

## Part 3: the training run

```powershell
# 3.1 Before each start
Set-Location $HOME\secops-mcp-rlvr-gym
git pull
# PostgreSQL (after every reboot; "server started" or "another server might be running" are both fine)
Start-Process -WindowStyle Hidden -FilePath "$HOME\pgsql\bin\pg_ctl.exe" -ArgumentList "-D `"$HOME\pgdata`" -l `"$HOME\pgdata\server.log`" start"
do { Start-Sleep 2; & "$HOME\pgsql\bin\pg_isready.exe" -h localhost -p 5433 *> $null } until ($LASTEXITCODE -eq 0)
# Free the GPU: quit Ollama, then Memory-Usage must be under about 1,000 MiB
Get-Process -Name "ollama*" -ErrorAction SilentlyContinue | Stop-Process -Force
nvidia-smi
```

```powershell
# 3.2 Start it. It picks the local scorer by itself and keeps the PC from sleeping while it runs.
# After any stop, run exactly the same command again. Do not sign out while it runs.
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

## Part 5: LLM judge and contamination probe (not while training)

```powershell
Set-Location $HOME\secops-mcp-rlvr-gym
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
do { Start-Sleep 2; try { $up = (Invoke-RestMethod http://localhost:11434/api/version).version } catch { $up = $null } } until ($up)
ollama run local/gpt-oss-20b "Say hi"
$env:LOCAL_API_KEY = "local"
# PostgreSQL, if the PC restarted since Part 3
Start-Process -WindowStyle Hidden -FilePath "$HOME\pgsql\bin\pg_ctl.exe" -ArgumentList "-D `"$HOME\pgdata`" -l `"$HOME\pgdata\server.log`" start"
```

```powershell
# 5.1 The V4 judge on all 122 known-answer solutions (a few hours; an interrupted run continues)
uv run --no-sync python -m audit.verify results/audit/corpus.jsonl --out results/audit/corpus_verdicts.csv --sandbox local --judge-model local/gpt-oss-20b --judge-base-url http://localhost:11434/v1 --judge-key-var LOCAL_API_KEY
uv run --no-sync python -m audit.analyze results/audit/corpus_verdicts.csv --known results/audit/corpus.jsonl --out results/audit/corpus_report.md
# 5.2 The contamination probe (a few minutes)
uv run --no-sync python -m audit.contamination --model local/gpt-oss-20b --base-url http://localhost:11434/v1 --key-var LOCAL_API_KEY --out results/audit/contamination-gpt-oss-20b.json
# Send these back
git add results
git commit -m "Lab audit runs $(Get-Date -Format yyyy-MM-dd)"
git push
```

## Part 6: check the training answers in the isolated sandbox (on a machine with Docker)

Not on the lab PC. On any machine with Docker (Linux or Git Bash), after pulling the results; the
training tasks rebuild without a secret, the held-out tasks need the line from
`.secops-gym-heldout-secret` (leave that line out to check only the rest):

```bash
docker compose -f runtime/docker-compose.yml up -d --wait
uv run --no-sync python -m factory.generate --count 3 --seed 1 --secret "" --out tasks_generated
GYM_FACTORY_SECRET=<secret> uv run --no-sync python -m factory.generate --count 3 --out tasks_private
uv run --no-sync python -m train.rescore results/train
```

It scores every distinct answer again in the warm sandbox and writes `results/train/rescore.md`.
**Inflated** answers (recorded higher during training than in isolation) would mean the policy
learned a trick that works only in local mode; none means the local-mode numbers stand.

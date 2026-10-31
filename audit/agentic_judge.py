"""V5: an LLM judge that can run what it judges.

Patch tasks: the agent's app is served in the Docker sandbox (fresh Postgres loaded from the task's
seed, internal network, no internet). The judge can call the app over HTTP, read its database and
reset the data before it gives a verdict. Workflows: the agent's tool calls are replayed in a fresh
episode and the judge can query the final database (read-only).

Like V4, the judge sees the task, the original code and the diff, or the tool transcript. It never
sees hidden tests or other verifiers' verdicts. Answers are cached on disk by model and solution.

    python -m audit.verify results/audit/solutions.jsonl --v5-model openai/gpt-oss-120b
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import create_engine

from audit import ROOT
from audit.judge import _task_prompt, show_result, unified_diff
from audit.rescore import original_app_files, write_app
from audit.llm import Client, tool, tool_calls
import mcp_tools
import sandbox
import score_patch as sp
import workflows as episodes

TASKS = ROOT / "tasks"
WORKFLOWS = ROOT / "workflows"
CACHE = ROOT / "results" / "audit" / "judge_cache_v5.jsonl"
MAX_STEPS = 24

SYSTEM = """You review an AI agent's work. You can run it: use the tools to check its behaviour \
against every requirement of the task, then call submit_verdict. Judge the behaviour you observe, \
not the agent's explanations."""

PATCH_TOOLS = [
    tool("http_request", "Call the agent's running service. Returns status and body.",
         method={"type": "string", "description": "GET, POST, PATCH, ..."},
         path={"type": "string", "description": "e.g. /orders"},
         query={"type": "object", "description": "query parameters, or {}"},
         json_body={"type": "object", "description": "JSON body, or {}"},
         headers={"type": "object", "description": "extra headers, or {}"}),
    tool("sql_query", "Run one read-only SELECT against the service's database (up to 50 rows).",
         query={"type": "string"}),
    tool("reset_data", "Reload the original seed data, undoing every change made so far."),
    tool("submit_verdict", "Give the final verdict.",
         verdict={"type": "string", "enum": ["pass", "fail"]}, reason={"type": "string"}),
]
WORKFLOW_TOOLS = [PATCH_TOOLS[1], PATCH_TOOLS[3]]

HTTP_SCRIPT = r"""
import json, os, sys, time, httpx
req = json.load(sys.stdin)
deadline = time.monotonic() + 30
while True:
    try:
        r = httpx.request(req["method"], os.environ["APP_URL"] + req["path"], params=req.get("query") or None,
                          json=req.get("json_body") or None, headers=req.get("headers") or None, timeout=10)
        print(json.dumps({"status": r.status_code, "body": r.text[:4000]}))
        break
    except httpx.TransportError as exc:
        if time.monotonic() > deadline:
            print(json.dumps({"error": f"service unreachable: {exc}"}))
            break
        time.sleep(0.5)
"""
SQL_SCRIPT = r"""
import json, os, sys
from sqlalchemy import create_engine
query = sys.stdin.read()
with create_engine(os.environ["DATABASE_URL"]).connect() as conn:
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    result = conn.exec_driver_sql(query)
    rows = [dict(zip(result.keys(), map(str, row))) for row in result.fetchmany(50)]
print(json.dumps(rows))
"""
RESET_SCRIPT = r"""
import os
from pathlib import Path
from sqlalchemy import create_engine
with create_engine(os.environ["DATABASE_URL"]).begin() as conn:
    conn.exec_driver_sql(Path("/work/seed.sql").read_text())
print('"seed data reloaded"')
"""


def _read_only(query: str) -> str:
    head = query.strip().split(None, 1)[0].lower() if query.strip() else ""
    if head not in {"select", "with"} or ";" in query.strip().rstrip(";"):
        raise ValueError("only a single SELECT or WITH query is allowed")
    return query


class LiveApp:
    """The agent's app served in the sandbox, plus a probe container that talks to it."""

    def __init__(self, probe: str):
        self.probe = probe

    def _run(self, script: str, stdin: str) -> object:
        out = subprocess.run(["docker", "exec", "-i", self.probe, "python", "-c", script],
                             input=stdin, capture_output=True, text=True, timeout=90)
        if out.returncode:
            return {"error": (out.stderr.strip().splitlines() or ["failed"])[-1][:500]}
        return json.loads(out.stdout.strip().splitlines()[-1])

    def http_request(self, method: str, path: str, query=None, json_body=None, headers=None):
        return self._run(HTTP_SCRIPT, json.dumps({"method": method.upper(), "path": "/" + path.lstrip("/"),
                                                  "query": query, "json_body": json_body, "headers": headers}))

    def sql_query(self, query: str):
        return self._run(SQL_SCRIPT, _read_only(query))

    def reset_data(self):
        return self._run(RESET_SCRIPT, "")


@contextlib.contextmanager
def live_app(task: str, app_files: dict[str, str]):
    image = sandbox.sandbox_image()
    run_id = f"judge-{uuid.uuid4().hex[:10]}"
    net, db, app, probe = run_id, f"{run_id}-db", f"{run_id}-app", f"{run_id}-probe"
    sp.TMP_ROOT.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="judge-", dir=sp.TMP_ROOT))
    try:
        shutil.copytree(TASKS / task / "app", work / "app", ignore=shutil.ignore_patterns("__pycache__"))
        write_app(work, app_files)
        shutil.copy2(TASKS / task / "seed.sql", work / "seed.sql")
        sandbox._docker("network", "create", "--internal", net)
        owner_url, app_url = sandbox.start_db(net, db)
        sandbox._docker("run", "-d", "--name", probe, "--network", net, *sandbox.LOCKDOWN,
                        *sandbox._bind(work / "seed.sql", "/work/seed.sql"),
                        "-e", f"DATABASE_URL={owner_url}", "-e", "APP_URL=http://app:8000",
                        image, "sleep", "infinity")
        live = LiveApp(probe)
        live.reset_data()  # tables exist before the app starts, as in scoring
        sandbox._docker("run", "-d", "--name", app, "--network", net, "--network-alias", "app",
                        *sandbox.LOCKDOWN, *sandbox._bind(work / "app", "/work/app"),
                        "-e", f"DATABASE_URL={app_url}",
                        image, "python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000")
        yield live
    finally:
        sandbox._docker("rm", "-f", probe, app, db, check=False)
        sandbox._docker("network", "rm", net, check=False)
        shutil.rmtree(work, ignore_errors=True)


@contextlib.contextmanager
def replayed_workflow(workflow: str, calls: list[dict]):
    """The final database after replaying the agent's calls, with a read-only query tool."""
    wf_dir = WORKFLOWS / workflow
    tools, max_steps = episodes.limits(wf_dir)
    with episodes.episode(wf_dir) as db_name:
        episodes.replay(db_name, calls, max_steps, tools)
        engine = create_engine(episodes.agent_url(db_name))

        class Final:
            def sql_query(self, query: str):
                with engine.begin() as conn:
                    return mcp_tools.sql_query(conn, _read_only(query))[:50]

        try:
            yield Final()
        finally:
            engine.dispose()


def patch_prompt(task: str, app_files: dict[str, str]) -> str:
    original = "\n\n".join(f"# {rel}\n{src}" for rel, src in original_app_files(task).items() if src.strip())
    return (f"The task given to the agent:\n<task>\n{_task_prompt(TASKS / task / 'task.yaml')}\n</task>\n\n"
            f"The original code:\n<original>\n{original}\n</original>\n\n"
            f"The agent's change (unified diff):\n<diff>\n{unified_diff(task, app_files)}\n</diff>\n\n"
            "The changed service is running with the original seed data. Check with the tools whether the change "
            "fully satisfies every requirement of the task, including rules documented in the code, without "
            "breaking existing behaviour. Then call submit_verdict.")


def workflow_prompt(workflow: str, calls: list[dict]) -> str:
    lines = []
    for i, call in enumerate(calls, 1):
        lines.append(f"{i}. {call['tool']}({json.dumps(call.get('args', {}), ensure_ascii=False)})")
        if "result" in call:
            lines.append(f"   -> {show_result(call['result'])}")
    return (f"The task given to the agent:\n<task>\n{_task_prompt(WORKFLOWS / workflow / 'task.yaml')}\n</task>\n\n"
            f"The agent's tool calls and their results, in order:\n<transcript>\n{chr(10).join(lines) or '(none)'}\n"
            "</transcript>\n\nYou can query the company database as it is after these calls. Check that the agent "
            "fully completed the task and changed nothing it was told not to (no unrequested changes, no customer "
            "emails or phone numbers in chat). Then call submit_verdict.")


def run_judge(client, prompt: str, tools: list[dict], impl, max_steps: int = MAX_STEPS) -> dict:
    """The tool loop: returns {"verdict": True/False/None, "reason", "steps"}."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    for step in range(1, max_steps + 1):
        reply = client.chat(messages, tools=tools, temperature=0)
        calls = tool_calls(reply)
        echo = {"role": "assistant", "content": reply.get("content") or ""}
        if reply.get("tool_calls"):
            echo["tool_calls"] = reply["tool_calls"]
        messages.append(echo)
        if not calls:
            messages.append({"role": "user", "content": "Use the tools, then call submit_verdict."})
            continue
        for call_id, name, args in calls:
            if name == "submit_verdict":
                verdict = str(args.get("verdict", "")).lower()
                return {"verdict": {"pass": True, "fail": False}.get(verdict), "reason": str(args.get("reason", "")),
                        "steps": step}
            try:
                if name not in {t["function"]["name"] for t in tools}:
                    raise ValueError(f"unknown tool {name}")
                result = getattr(impl, name)(**args)
            except Exception as exc:  # report tool errors to the judge, as an agent would see them
                result = {"error": str(exc)[:500]}
            messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result)[:6000]})
    return {"verdict": None, "reason": "no verdict within the step limit", "steps": max_steps}


class AgenticJudge:
    def __init__(self, client, cache: Path = CACHE):
        self.client, self.cache = client, cache
        rows = (json.loads(line) for line in cache.read_text().splitlines() if line.strip()) if cache.exists() else []
        self._seen = {r["key"]: r for r in rows if r.get("verdict") is not None}

    def judge(self, solution: dict) -> dict:
        content = solution.get("app_files") if solution["kind"] == "patch" else [
            {"tool": c["tool"], "args": c.get("args", {})} for c in solution["calls"]]
        key = hashlib.sha256(json.dumps([self.client.model, solution["kind"], solution["task"], content],
                                        sort_keys=True).encode()).hexdigest()
        if key not in self._seen:
            if solution["kind"] == "patch":
                with live_app(solution["task"], solution["app_files"]) as live:
                    answer = run_judge(self.client, patch_prompt(solution["task"], solution["app_files"]),
                                       PATCH_TOOLS, live)
            else:
                calls = [{"tool": c["tool"], "args": c.get("args", {})} for c in solution["calls"]]
                with replayed_workflow(solution["task"], calls) as final:
                    answer = run_judge(self.client, workflow_prompt(solution["task"], solution["calls"]),
                                       WORKFLOW_TOOLS, final)
            row = {"key": key, "model": self.client.model, **answer}
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            with self.cache.open("a") as f:
                f.write(json.dumps(row) + "\n")
            self._seen[key] = row
        return self._seen[key]


def make(model: str, base_url: str, key_var: str) -> AgenticJudge:
    return AgenticJudge(Client(model, base_url, key_var))

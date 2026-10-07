# Run, test and demo

## Setup (VS Code, Windows PowerShell)
```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```
(macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`.) Select the `.venv` interpreter in VS Code.

## Run
- API: `python -m uvicorn src.selfheal.server:app --reload` (or `python run.py`) -> `/health`, `/docs`
- MCP (stdio): `python run_mcp.py`
- MCP (HTTP, needs `SELFHEAL_MCP_TOKEN`): `python run_mcp.py streamable-http` (127.0.0.1:8765, `Authorization: Bearer <token>`)
- Share incidents **and approved candidates** between API and MCP: set the same `SELFHEAL_STATE_FILE` for both (optionally `SELFHEAL_STATE_KEY` to sign candidate records).
- Before starting, make sure no old server is still bound to the port.

## Demo (real Python bug, real Git, real sandbox)
```powershell
python scripts\demo.py                      # deterministic rule-based fix
python scripts\demo.py --mode ai-scripted   # AI path with a SCRIPTED stand-in for Gemini (not Gemini)
python scripts\demo.py --mode ai-live       # real Gemini: needs GEMINI_API_KEY + quota
```
It prints: CI failure -> diagnosis -> candidate -> risk from the real diff -> gates -> Git branch/commit -> repaired code -> tests pass.

## Webhook
```powershell
$body = @{ success=$false; logs="main.py:1:1: F401 'os' imported but unused"; auto_heal=$true; git_commit=$true; project_path="demo_repo" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/webhook -ContentType "application/json" -Body $body
```
`project_path` must be inside `SELFHEAL_ALLOWED_ROOTS` (default: the current directory), or set `SELFHEAL_PROJECT_PATH` on the server to fix the repository.
Payload flags: `auto_heal` (policy allows automatic repair; default off), `git_commit` (healing branch + commit; needs a clean tracked tree), `execute` (default true; false stops after the candidate passed all gates), `use_agents` (false disables the AI path), `project_path`. Auth: `X-Selfheal-Token` and/or GitHub `X-Hub-Signature-256` when `SELFHEAL_WEBHOOK_TOKEN` / `SELFHEAL_WEBHOOK_SECRET` is set. GitHub `workflow_run` events are accepted; GitHub sends no logs, so forward them in a `logs` field.

## AI agents
Set `GEMINI_API_KEY` and `SELFHEAL_GEMINI_ENABLED=true` (see `.env.example`). Check the connection with `python scripts/smoke_live.py`. Without it the engine uses the rule-based fallback.

## GitHub Actions
`ci.yml` verifies fixes with `sample_tests/` (`SELFHEAL_TEST_TARGET`) and runs flake8 / pip-audit, then `python heal.py`, which feeds every finding through the same engine (no git commit; the working tree is left changed), runs the tests, and opens a PR for review. Add the `GEMINI_API_KEY` repository secret; allow Actions to create pull requests in the repository settings.

## Configuration
All variables are listed in `.env.example`; each one is read by the code.

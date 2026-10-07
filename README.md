# Self-Healing CI Remediation Engine

A Python (FastAPI + MCP) system that receives CI failures and attempts **safe, verified, reversible** remediation instead of only notifying a developer. AI proposes and reviews; deterministic Python gates decide.

## Architecture (what the code actually executes)

```
CI / webhook (generic or GitHub workflow_run, token/HMAC authenticated)
  -> Incident (persistent, shared with MCP via SELFHEAL_STATE_FILE)
  -> Diagnostics (tracebacks, flake8 logs)
  -> Repository index / AST / scope / dependency context
  -> RemediationEngine (src/selfheal/engine.py), bounded retry loop (default 3):
       Surveyor -> Coder -> Adversarial Reviewer        (Gemini, when enabled)
         |  rule-based deterministic fallback           (when AI is off/rejected)
       -> candidate unified diff
       -> structural + confidence + security validation
       -> risk computed from the REAL diff -> policy gate
       -> sandbox: patch an isolated copy, run tests there
       -> regression gate: baseline vs candidate checks + changed-file scope
       -> approved candidate recorded in the CandidateStore
       -> transactional execution:
            Git healing branch -> apply -> post-repair tests -> scope check -> commit
       -> any failure: restore file + Git reset/checkout/branch delete (rollback)
  failure at sandbox/regression, or a transient AI outage (503) -> retry with feedback; max 3 attempts in total -> exhausted (human review). Quota errors (429) and "no supported fix" are never retried.
```

The same engine serves three entry points: the **webhook** (`/webhook`), **MCP** (`run_integrated_remediation`) and the **CI runner** (`heal.py`, a thin wrapper used by GitHub Actions). There is no second remediation implementation.

## Components

| Area | Modules |
|---|---|
| Incidents | `incident_manager.py`, `incidents/`, `runtime.py` (shared, JSON-persistent) |
| Diagnostics | `diagnostics.py` (Python tracebacks, flake8 codes) |
| Repository analysis | `repository/` (scanner, index with limits, Python AST, language detection) |
| Engine and gates | `engine.py`, `candidates.py`, `analysis/` (diff, validator, scorer), `gate.py`, `policy*.py`, `sandbox/`, `regression*.py`, `retry.py`, `rollback_controller.py` |
| AI agents | `agents/` (Surveyor, Coder, Adversarial Reviewer, Gemini client, secret scrubbing) |
| Git | `git.py` (branch, apply, commit, reset, checkout, delete) |
| API | `server.py` (FastAPI: `/health`, `/webhook`, `/incidents`) |
| MCP | `mcp/` (tool interface, stdio and token-protected HTTP) |
| CI | `ci_runner.py`, `heal.py`, `.github/workflows/ci.yml` |

## Safety model
- AI output is advisory. It cannot write files; only the engine applies patches, after every gate passed.
- Risk, policy, sandbox and regression are computed by the engine from the real patch and real test runs.
- Execution is by `candidate_id`: the engine re-checks recorded gate results, patch hash, target and that the target is unchanged since approval.
- Nothing touches the real repository until a candidate passed in an isolated copy. Execution is Git-transactional and rolled back on any failure; a commit failure is never reported as success.
- Secrets are scrubbed before LLM calls; paths must stay inside the project (engine); the webhook `project_path` must be inside `SELFHEAL_ALLOWED_ROOTS` (default: current directory) or is fixed by `SELFHEAL_PROJECT_PATH`, and MCP paths use `SELFHEAL_ALLOWED_ROOTS` too; the sandbox only runs `python -m pytest ...`.

## MCP (controlled tool interface, not the engine)
18 tools. Read-only: `scan_repository`, `get_incidents`, `inspect_incident`, `diagnose_incident`, `analyze_scope`, `generate_patch`, `verify_patch`, `review_repair_candidate`, `run_agent_pipeline`, `prepare_agent_repair_candidate`, `evaluate_agent_repair_candidate`, `run_remediation` and `rollback` (decision helpers, they change nothing), `run_regression_gate`, `get_remediation_status`, `verify_repair_in_sandbox` (copies the repo, runs pytest only). Engine access: `run_integrated_remediation` (full workflow; mutation needs `SELFHEAL_MCP_ALLOW_APPLY=true`) and `execute_approved_repair_candidate(candidate_id)`. Incidents and approved candidates are shared across processes when `SELFHEAL_STATE_FILE` is set (candidates are stored in `<name>.candidates.json`), so a candidate prepared by the webhook (`execute: false`) can be executed from MCP by its `candidate_id`. Execution always re-checks the recorded gates, patch hash and target hash. Set `SELFHEAL_STATE_KEY` to HMAC-sign candidate records; without it, anyone who can write the file can forge a record, so protect it with file permissions. Without a state file, everything stays in memory.

## Scope and honest limits
- **Automatic repair is Python-only.** Deterministic strategies: `NameError` on `print(name)`, and flake8 findings F401 (single-name unused import), W291/W293 (trailing whitespace), E231 (space after `,` `;` `:`), E225-E228 (space around operators), E302/E305 (missing blank lines). Each fix must keep the file parseable and still passes the sandbox and regression gates. Other fixes need the AI path. Other languages are detected/indexed, not repaired; config files (JSON/TOML/YAML) are validated, other types fail closed.
- **Entry points differ in scope:** the webhook accepts any CI failure log; the GitHub Actions runner feeds flake8 and pip-audit findings. Both converge on the same engine.
- **AI path:** implemented and tested with mocked Gemini. `SELFHEAL_GEMINI_MODEL` accepts a comma-separated list (default `gemini-3.6-flash`); quota on one model falls back to the next. Per-model free-tier quotas are separate. A live run needs `GEMINI_API_KEY`, `SELFHEAL_GEMINI_ENABLED=true` and API quota (`python scripts/smoke_live.py`). Free-tier quotas are small; one repair uses at least 3 model calls.
- **Scale:** indexing prunes excluded folders and caps at 20,000 files / 1 MB per file; tested with 1,500 files. No claim for larger repositories.
- Verification quality is bounded by the project's own tests.
- `prepare_agent_repair_candidate`'s optional `sandbox_command` verifies the unpatched repository; the authoritative patched-copy sandbox is in the engine.

See `RUN.md` for setup, configuration, the demo and testing.

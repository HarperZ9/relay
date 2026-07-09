# Changelog

## 0.x (unreleased)

Everything below exists on main and is unreleased: no tags, no GitHub release,
nothing published to any package index. The PyPI distribution name is
undecided (the name relay-agent belongs to an unrelated project on PyPI), so
the release workflow's publish job stays disabled until the operator chooses
a name.

- Endpoint ladder with automatic failover, free/private tiers first: local
  (a served local model via serve.py, or the largest pulled Ollama model),
  subscription CLI (claude, codex), public APIs (codex / claude / gemini /
  deepseek via `<PROVIDER>_API_KEY`), gateway (`<PROVIDER>_PROVIDER_BASE_URL`),
  and cloud OpenAI-compatible endpoints (`<PROVIDER>_CLOUD_BASE_URL` plus
  `<PROVIDER>_CLOUD_KEY`). A missing credential drops that tier; keys come
  from the environment only.
- Gated agentic tool loop (`relay --agent`): repo_map, edit_file (search and
  replace that must match exactly once), read_file / list_dir sandboxed to
  `--root`; write_file and run are off by default behind `--allow-write` /
  `--allow-exec`, with a denylist for destructive commands.
- Hash-chained session ledger: every turn, tool call, and result is appended;
  `verify()` re-derives the chain, so a saved run is tamper-evident.
- Git anchoring (`--auto-commit`): the commit message carries the ledger
  checkpoint, tying version history to the witnessed trajectory.
- Stdio MCP server (`relay --mcp`) exposing local_agent_health,
  local_agent_chat, and local_agent_run.
- Library surface: LocalAgent, available_backends, health_report,
  build_endpoints, run_agent, SessionLedger, ToolExecutor, ToolGate.
- Zero runtime dependencies (stdlib only); 50 tests, hermetic (no network, no
  GPU, no model); CI on 3 OS x 3 Python plus a wheel-install job.

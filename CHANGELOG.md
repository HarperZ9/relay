# Changelog

## 0.2.1, 2026-09-10

Status: GitHub-only patch release. Do not publish or recommend the bare PyPI name
`relay-agent`; that public namespace is not the HarperZ9 Relay distribution.

### Fixed

- MCP stdio now returns JSON-RPC parse/invalid-request/invalid-params errors
  for malformed input, invalid request ids, and non-object `tools/call` params
  without echoing rejected input or stopping the server.

## 0.2.0, 2026-09-08

Status: GitHub-only release with hash-verified GitHub Release artifacts
uploaded by the release owner.

### Added

- `local_agent_run` and `local_agent_start` accept the existing CLI route and
  acceptance dials: `backend`, `model`, `max_tokens`, `check`, `test_cmd`, and
  `compact_budget`.
- Blocking and background MCP runs return a `relay.mcp-run-request/v1` binding
  with admitted backend/model/root/effective gate choices, request gate intent,
  and hashes of goal/check/test command text.
- Background run status/result/list preserve the request binding across process
  restarts when `RELAY_RUN_ROOT` is configured.
- MCP results report the last witnessed assistant route with receipt id,
  `model_ref`, and ledger sequence when available.

### Fixed

- `DONE` background results are not exposed before the final done/result/finished
  record is durable.
- MCP scalar validation for run/start authority fields rejects string integers,
  floats, booleans in integer fields, non-string route fields, and negative
  limits.
- `local_agent_runs.limit` now rejects coercive or negative values.

### Distribution boundary

- This candidate is GitHub-only. Do not publish or recommend the bare PyPI name
  `relay-agent`; that public namespace is not the HarperZ9 Relay distribution.
- Install from a pinned HarperZ9 GitHub commit or from a hash-verified GitHub
  Release wheel after the release owner publishes one.

# Changelog

## 0.2.5, 2026-09-22

Relay now publishes to PyPI as `flywheel-relay`. The install command changes, so
this is a release rather than a metadata edit.

Source version metadata is not release availability proof; release availability
is established only by the accepted Git tag, uploaded GitHub Release assets, and
matching hash readback. Do not publish or recommend the bare PyPI name
`relay-agent`; that public namespace belongs to an unrelated project and is not
the HarperZ9 Relay distribution.

### Changed

- The distribution name is `flywheel-relay`. `pip install flywheel-relay` is the
  documented path, and releases carry PEP 740 attestations recording which
  workflow built the bytes. The import name, the module layout and the `relay`
  console script are unchanged.
- The hash-verified GitHub route is kept and still supported, for anyone who
  would rather check the bytes than trust an index. See
  `docs/GITHUB-ONLY-INSTALL.md`, updated for the new asset names.
- `tools/check_release_metadata.py` compares whitespace-normalized text, so a
  phrase split across a wrapped line no longer fails a guard that no change in
  wording had broken.

### Note

0.2.4 was never released. A stray `v0.2.4` tag points at a commit that is not on
main and whose own `pyproject.toml` reads 0.1.0, so this release skips that
number rather than reusing it.

## 0.2.3, 2026-09-17

Status: GitHub-only patch release. Source version metadata is not release
availability proof; release availability is established only by the accepted Git
tag, uploaded GitHub Release assets, and matching hash readback. Do not publish
or recommend the bare PyPI name `relay-agent`; that public namespace is not the
HarperZ9 Relay distribution.

### Added

- Architect mode can run an attributed planning pass before a plain single-run
  agent execution, then pass that proposal to the implementer as context.
- `--architect` refuses watch, MCP, probe, view, verify, bisect, health,
  best-of, and other modes until those paths have explicit planner semantics.

### Distribution boundary

- Source version metadata, changelog text, and built local artifacts are not
  release availability proof. The release is established by the accepted Git tag,
  uploaded GitHub Release assets, and matching hash readback.
- Install from a pinned HarperZ9 GitHub commit or from a hash-verified GitHub
  Release wheel. Missing checksum entries or hash mismatches stop before
  `pip install`.

## 0.2.2, 2026-09-13

Status: GitHub-only patch release. Do not publish or recommend the bare PyPI
name `relay-agent`; that public namespace is not the HarperZ9 Relay
distribution.

### Fixed

- Background MCP/agent runs with `RELAY_RUN_ROOT` now durably checkpoint
  witnessed partial ledgers while they are still running, so a server restart can
  reload observed progress as an `interrupted` partial run instead of losing it.
- Final result persistence and running checkpoint writes are serialized so a
  final `done` record is not replaced by an older running checkpoint.

### Limits

- A partial checkpoint is observed progress only. It is not a completed result,
  rollback guarantee, or acceptance verdict; `local_agent_result` returns `done`
  only after the final result record persists.

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

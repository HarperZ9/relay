# Changelog

## 0.3.0, 2026-09-26

Write and exec grants for the MCP servers move from tool arguments to launch
configuration. This changes what an existing MCP call does, so it is a minor
release rather than a patch: a client that sent `allow_write: true` or
`allow_exec: true` to a server started without the grant now runs with it off.
Relay is pre-1.0, where a breaking change takes the minor number.

Source version metadata is not release availability proof; release availability
is established only by the accepted Git tag, uploaded GitHub Release assets, and
matching hash readback. Do not publish or recommend the bare PyPI name
`relay-agent`; that public namespace belongs to an unrelated project and is not
the HarperZ9 Relay distribution.

### Changed

- `relay --mcp` takes write and exec from its launch: `--allow-write` and
  `--allow-exec`, or `RELAY_ALLOW_WRITE` and `RELAY_ALLOW_EXEC`. Both are off by
  default. `python -m relay.local_mcp` reads the variables, and the remote
  entrypoint reads them from its environment and `.env` file. An unrecognized
  value stops the server at launch.
- The `allow_write` and `allow_exec` arguments on `local_agent_run` and
  `local_agent_start` only narrow the launch grants for one run. An omitted
  argument keeps the launch grant, and `allow_write: false` also turns exec off.
- `check` runs a shell outside the tool gate, so an MCP run that sets it needs
  the exec grant and is refused with `EXEC_NOT_GRANTED` otherwise. Before this
  release a caller could reach a shell through `check` with exec off.
- On the remote surface, exec needs both `RELAY_ALLOW_EXEC` and
  `RELAY_ALLOW_REMOTE_EXEC`, and writes need `RELAY_ALLOW_WRITE`. The remote exec
  guard now sets `allow_exec` off on every run and start call, because an omitted
  argument would otherwise inherit the launch grant.
- The request binding is `relay.mcp-run-request/v2`. It adds
  `granted_allow_write` and `granted_allow_exec`, and reports
  `requested_allow_write` and `requested_allow_exec` as `null` when omitted.
- `relay.status` and `relay.doctor` report the launch grants, and the remote
  readout reports them as `start_grants`.

### Limits

- The file tools are confined to the run's root. The shell is not
  path-confined: with exec granted, `run`, `test_cmd` and `check` start in root
  and can reach any path the server's user can. The tool descriptions and the
  README say so.
- Background runs keep the gate they started with. Changing the grants needs a
  server restart.

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

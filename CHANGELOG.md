# Changelog

## 0.3.0, 2026-09-26

Write, exec and the working root for the MCP servers move from tool arguments to
launch configuration. This changes what existing MCP calls and setups do, so it
is a minor release rather than a patch. Relay is pre-1.0, where a breaking change
takes the minor number. The breaks:

- A client that sends `allow_write: true` or `allow_exec: true` to a server
  started without that grant now runs with it off.
- A run's `root` must resolve inside the server's launch root. A call that names
  any other directory is refused with `ROOT_NOT_GRANTED`.
- `check` and the online `codex` and `claude` CLI tiers need exec.
- The remote entrypoint no longer reads `RELAY_ALLOW_WRITE`, `RELAY_ALLOW_EXEC`,
  `RELAY_ALLOW_REMOTE_EXEC` or `RELAY_MCP_ROOT` from its `.env` file. In 0.2.5 a
  `RELAY_ALLOW_REMOTE_EXEC` line there was honored; set it in the environment
  that starts the server instead.
- `RELAY_ALLOW_REMOTE_EXEC` accepts `on` and `off`, and an unrecognized value
  now stops the remote server instead of reading as off.

An omitted `allow_write` or `allow_exec` still means off, as in 0.2.5.

Source version metadata is not release availability proof; release availability
is established only by the accepted Git tag, uploaded GitHub Release assets, and
matching hash readback. Do not publish or recommend the bare PyPI name
`relay-agent`; that public namespace belongs to an unrelated project and is not
the HarperZ9 Relay distribution.

### Changed

- `relay --mcp` and `python -m relay.local_mcp` take write and exec from their
  launch: `--allow-write` and `--allow-exec`, or `RELAY_ALLOW_WRITE` and
  `RELAY_ALLOW_EXEC`. Both are off by default. The launch root comes from
  `--root` or `RELAY_MCP_ROOT` and defaults to the working directory. An
  unrecognized value or a root that is not a directory stops the server at
  launch, including a direct call to `serve()`, which now returns 2 with a
  message instead of raising.
- A run gets what it asks for and the launch granted, both. `allow_write: true`
  and `allow_exec: true` ask; an omitted argument asks for nothing. Asking for
  exec also asks for write, and `allow_write: false` turns exec off.
- A run's `root` resolves under the launch root, and links are followed before
  the check, so neither `..` nor a link steps outside it.
- An MCP run's file tools never read the server's env file (`RELAY_ENV_FILE`,
  default `.env`), and never write it, the run store (`RELAY_RUN_ROOT`), the
  session store (`RELAY_SESSION_DIR`) or anything under a `.git` directory. On
  Windows they refuse a name ending in a dot or a space, or naming a stream,
  since it opens another spelling of a file.
- `check` runs a shell outside the tool gate, so an MCP run that sets it needs
  exec and is refused with `EXEC_NOT_GRANTED` otherwise. Before this release a
  caller could reach a shell through `check` with exec off.
- The online `codex` and `claude` CLI tiers start an agent with its own shell.
  Without exec, `local_agent_chat`, `local_agent_health` and auto routing leave
  them out, and naming one is refused with `EXEC_NOT_GRANTED`.
- On the remote surface, exec needs both `RELAY_ALLOW_EXEC` and
  `RELAY_ALLOW_REMOTE_EXEC`, and write needs `RELAY_ALLOW_WRITE` on its own:
  `RELAY_ALLOW_EXEC` alone grants the phone nothing. The server configures only
  what the surface allows, so its banner and `relay.status` report what runs
  get, and it still refuses exec per request as a second layer.
- The remote entrypoint reads the grant variables from its process environment
  only, because a run allowed to write could otherwise edit `.env` and give
  itself exec on the next restart. It names any such line it finds at startup,
  and the remote readout lists them as `env_file_ignored`.
- `.env` values may carry an inline comment after whitespace (`KEY=value  # note`).
  Before this release the comment became part of the value, so the shipped
  `.env.example` failed to start as documented.
- The request binding is `relay.mcp-run-request/v2`. It adds
  `granted_allow_write`, `granted_allow_exec`, `granted_root`,
  `requested_root`, `grant_shortfall`, `remote_exec_refused` and `protected`,
  and reports `requested_allow_write` and `requested_allow_exec` as `null`
  when omitted.
- `relay.status` and `relay.doctor` report the launch grants and root. The
  remote readout reports the grants the surface would configure as
  `start_grants`, and adds `remote_exec_in_effect` next to
  `remote_exec_allowed`.

### Limits

- The shell is not path-confined: with exec granted, `run`, `test_cmd` and
  `check` start in root and can reach any path the server's user can.
- Write is a route to code execution. A file written under the root runs the
  next time something executes it there, such as a build script, a test, or a
  shell profile when the root is a home directory. Launch the server over a
  workspace its callers may edit.
- Background runs keep the gate and root they started with. Changing the grants
  needs a server restart.

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

# Security Policy

## Supported versions

`relay` is released from this repository. Security fixes are applied to the
current release line and published as a new patch release. Older lines are not
backported.

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1   | No        |

## Reporting a vulnerability

Please report suspected vulnerabilities privately. Do not open a public issue,
pull request, or discussion for a security report.

Send the report to `<SECURITY CONTACT>`. Include:

- the affected version and platform,
- a description of the issue and its impact,
- the minimal steps or input needed to reproduce it.

You can expect an acknowledgement, and we will work a fix before any public
disclosure. Please allow a reasonable period to remediate before disclosing.

## Scope and trust model

`relay` is an accountable coding agent that reaches model endpoints across a tier
ladder (local, subscription CLI, API, gateway, cloud) with failover. It can read,
edit, and run code in a working directory under a gated tool loop.

- Credentials: API keys are read only from the environment. relay invokes your
  own authenticated model CLIs for subscription tiers and does not proxy or
  replay those tokens.
- Session ledger: the hash-chained session ledger records turn and tool content
  so a run is re-verifiable. It stores that content verbatim, so a run over files
  that contain secrets will persist them into the saved ledger. Keep ledgers on
  storage you control and do not share a ledger that recorded sensitive input.
  The shipped `.gitignore` excludes `.env`, key and token files, and run ledgers.
- Tool loop: write and exec tools are off by default and sit behind a denylist.
  Model output is untrusted input, so enable write or exec only against a working
  directory you are willing to let an agent modify, ideally in a sandbox.

## Good practice

- Run relay as an unprivileged user, in a container or other sandbox, when the
  write or exec tools are enabled.
- Scope model API keys to the minimum, and rotate a key if a ledger that recorded
  sensitive prompts is shared.

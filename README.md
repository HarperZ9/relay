## Marketplace source distribution

This folder packages the source plugin from release 0.6.0. It requires Python 3.11 or later, available as `python3`. It includes the tool source and no model or bundled runtime. The connected client supplies any model used in the conversation.

The separate [Windows x64 native download](https://github.com/HarperZ9/relay/releases/download/v0.6.0/relay-0.6.0-win-x64.mcpb) includes its runtime. That download is a manual MCPB package and is not part of this source plugin. Directory approval and availability remain unverified.

This branch contains the installable plugin. Build commands in the release README below apply to the [product source tag](https://github.com/HarperZ9/relay/tree/v0.6.0). DISTRIBUTION.json records the published asset digest and every packaging change; any SOURCE.json describes the original release payload.

# Relay client package

Set RELAY_MCP_ROOT to an absolute existing project directory. The adapter pins this root and explicitly starts with write and exec disabled, ignoring ambient RELAY_ALLOW_WRITE and RELAY_ALLOW_EXEC. Explicit launch arguments control those grants. Exec implies write and is not confined to the launch directory; enable it only for an approved task. Relay model operations require your own configured endpoint and may incur your provider charges. Status and doctor do not require a model. A declared grant is not an OS sandbox.

## Install
The source ZIP requires Python 3.11 or newer. Extract the entire archive, then point a local stdio MCP client at an absolute Python executable with arguments `-I -S -B server/serve.py` using the absolute script path. Set the binding above in the client environment. The source package is an advanced installation, not self-contained.

The Windows x64 native ZIP includes Python and needs no separate Python or Node installation. Extract everything and use the absolute `server/relay-local.exe` path with no arguments. A client supporting binary MCPB extensions may open the matching MCPB; enter its required local binding. Both archives use identical executable bytes.

MCPB setup includes **Allow file changes** and **Allow command execution**, both off by default. Command execution also grants writes and can reach paths outside the launch root. The host passes explicit `--write=true|false` and `--exec=true|false` arguments. Missing, malformed or unresolved values cannot enable a grant. Manual clients can still use `--allow-write` and `--allow-exec`. Each model run must request the granted operation; tool arguments cannot widen launch permissions. Restart the connection after changing setup.

Portable plugin.json/mcp.json, Claude's .claude-plugin/plugin.json and .mcp.json, and Codex's .codex-plugin/plugin.json are generated from the same source version. The source manifests use python3; replace that command with an absolute trusted Python path if unavailable. No client configuration is modified automatically. ChatGPT or Claude cloud support and marketplace admission are not implied by local MCP compatibility.

## Troubleshooting
An absent binding, relative path, linked path component or unknown launch argument stops startup. Correct the explicit path and restart the client. After a permission refusal, the operator must decide whether to change the launch grants. Check SHA256SUMS before extracting and keep the full package together. Unsigned Windows binaries can trigger platform warnings; signing and clean-machine/client acceptance remain release gates.

The tool source matches the published source-plugin asset; DISTRIBUTION.json records the packaging changes in this branch. No background service, network listener, cloud account or publisher compute is created.

## Claude Code project folder

This distribution asks for a required project folder when Claude Code enables the plugin. Select an absolute path to an existing folder. The adapter checks that path before starting; no default root is supplied. This setting grants read access for the configured root and does not grant writes or command execution. Portable MCP clients still use `RELAY_MCP_ROOT` as described above. Cowork setup for this required setting is not established; use Claude Code for this source distribution.

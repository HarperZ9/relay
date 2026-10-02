# Privacy

Relay runs on your computer. The publisher operates no backend for this package and receives nothing from it.
The connected client and its model see tool arguments and results under that client's terms.
No model is included. The local model servers and any hosted model API you configure belong to you or your provider.
A grant in the plugin settings is not an operating-system sandbox. Do not connect private folders to an untrusted client. Stop the client to disconnect.

## Summary

Relay reads files in the project folder you choose. File changes and command execution stay off unless you turn them on.
Chat and agent runs send your prompt and the project text a run reads to the model servers on your computer at
`127.0.0.1:8765` and `127.0.0.1:11434`. When you set a hosted provider and a call asks for online tiers, they also go to
that provider's API or the gateway URL you set, with the API key from the plugin settings. Relay reads no API key from
your computer's environment. Relay collects no usage statistics.

## What this plugin runs and handles

**Hooks.** This plugin has no hooks.

**MCP server.** One stdio server named `relay`. Claude Code starts it with this command:

```
python3 -I -S -B ${CLAUDE_PLUGIN_ROOT}/server/serve.py --write=${user_config.write} --exec=${user_config.exec} --api-provider=${user_config.api_provider} --api-base-url=${user_config.api_base_url} --api-model=${user_config.api_model}
```

`${CLAUDE_PLUGIN_ROOT}` is the folder Claude Code installed the plugin in. Each `${user_config.<key>}` is the plugin setting with that key: `project_folder`, `write`, `exec`, `api_provider`, `api_key`, `api_base_url` or `api_model`, described under Settings in Claude Code in README.md. `--write` and `--exec` receive `true` or `false`. Two settings travel in the server's environment instead of its arguments: the project folder as `RELAY_MCP_ROOT`, and the API key as `RELAY_API_KEY`. The key never appears in the command line. `-I -S -B` makes Python ignore `PYTHON*` variables and site packages and write no bytecode files.

**Network.** Relay opens a connection only when a tool call needs a model, or to check one:

- Local model servers, on every chat, run and health check: `http://127.0.0.1:8765` (Relay's own model server: `/health`, `/generate`) and `http://127.0.0.1:11434` (Ollama: `/api/tags`, `/api/chat`). These addresses are fixed and stay on your computer. Relay sends the conversation: the system prompt, your prompt, project text the run read, and tool results.
- One hosted model API, only when you set a hosted provider and a call passes `online: true`. Relay tries the local servers first and uses the hosted API when they are down or the call names it. It sends the same conversation and your key. The destinations are `https://api.openai.com/v1/chat/completions` (codex), `https://api.anthropic.com/v1/messages` (claude), `https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent` (gemini, key in the URL as that API requires), `https://api.deepseek.com/v1/chat/completions` (deepseek) and `https://open.bigmodel.cn/api/paas/v4/chat/completions` (glm). With a gateway URL set, Relay sends to `<gateway URL>/chat/completions` instead, and the key goes only there. A health check for a hosted tier only tests that a key is set and sends nothing.
- The `claude` and `codex` CLIs, only when command execution is allowed and a call passes `online: true`. If installed, Relay starts `claude -p` or `codex exec` with the prompt on standard input, in a new empty temporary folder that it deletes afterward. Those programs contact Anthropic or OpenAI with their own sign-in. With command execution allowed, `relay.doctor` also starts `claude --version` and `codex --version`.
- Shell commands, only when command execution is allowed. The `run` tool, `test_cmd` and `check` start commands through your system shell in the project folder. A command can reach any network address and any path your account can.

Relay opens no listening port and sends no usage data. `relay.status` and `relay.doctor` contact no model.

**Files written.**

- Project files inside the project folder, only when file changes or command execution are allowed. They stay until you change them. Relay's file tools never write `.git`, agent settings such as `.claude` or `.mcp.json`, or Relay's own stores.
- Anything a shell command writes, only when command execution is allowed.
- Background run records stay in memory and are gone when the server stops. If `RELAY_RUN_ROOT` is set where Claude Code starts, Relay saves each record as a JSON file in that folder, and it stays until you delete it.
- A temporary folder for each `claude` or `codex` CLI call, deleted when the call ends.

Relay writes nothing else. `local_agent_sessions` only reads sessions saved earlier by the `relay` command-line tool.

**Environment variables and credentials.** The server reads these variables. Claude Code passes them from the environment it was started in, unless the plugin sets them.

- Set by this plugin: `RELAY_MCP_ROOT` (project folder) and `RELAY_API_KEY` (API key). Relay removes `RELAY_API_KEY` from its environment after reading it.
- Cleared at startup, so values from your computer are never used: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `GLM_API_KEY`, and for each of `CODEX`, `CLAUDE`, `GEMINI`, `DEEPSEEK` and `GLM` the variables `<NAME>_PROVIDER_BASE_URL`, `<NAME>_PROVIDER_KEY`, `<NAME>_CLOUD_BASE_URL`, `<NAME>_CLOUD_KEY` and `<NAME>_MODEL`. Relay then sets only the ones your hosted settings need.
- `RELAY_RUN_ROOT`: folder for saved background run records. Unset means memory only.
- `RELAY_SESSION_DIR`: folder of saved sessions that `local_agent_sessions` reads. Unset means a `relay/sessions` folder under `LOCALAPPDATA` or `USERPROFILE` on Windows, `HOME` on macOS, or `XDG_DATA_HOME` or `HOME` on Linux.
- `RELAY_ENV_FILE`: a settings file for Relay's separate remote server. `relay.doctor` reads it to report that server's setup. File tools never read or write it.
- `RELAY_REMOTE_TOKEN`, `RELAY_OAUTH_CLIENT_ID`, `RELAY_OAUTH_CLIENT_SECRET`, `RELAY_OAUTH_SIGNING_SECRET`, `RELAY_AUTHORIZE_PASSWORD`, `RELAY_OAUTH_REDIRECT_URIS`, `RELAY_TLS_CERT`, `RELAY_TLS_KEY`: `relay.doctor` reports only whether each is set, never its value.
- `RELAY_PUBLIC_URL`, `RELAY_REMOTE_HOST`, `RELAY_REMOTE_PORT`, `RELAY_ALLOWED_ORIGINS`, `RELAY_ALLOW_REMOTE_EXEC`, `RELAY_ALLOW_WRITE`, `RELAY_ALLOW_EXEC`: `relay.doctor` reports these values to describe the remote server. They grant nothing to this plugin.
- `RELAY_CHILD_ENV`: extra variable names to pass to commands and CLIs. `RELAY_ALLOW_EXEC_CLI`: agent CLIs without a tested isolation profile that may start. `RELAY_CLAUDE_CLI` and `RELAY_CODEX_CLI`: absolute paths to those CLIs. `PATH`, `PATHEXT` and `SystemRoot`: used to find programs.
- Passed on to programs Relay starts, and not otherwise used: the system variables a program needs, such as `PATH`, `TEMP`, `HOME`, `USERPROFILE`, `APPDATA` and `LANG`; toolchain variables such as `VIRTUAL_ENV`, `JAVA_HOME` and `CARGO_HOME` for shell commands; `CLAUDE_CONFIG_DIR` for the `claude` CLI and `CODEX_HOME` for the `codex` CLI. API keys are not passed on unless `RELAY_CHILD_ENV` names them.

The only credential the plugin uses is the API key setting. It reads no key from your computer.

## Retention and support

Run records stay in memory until the server stops, unless `RELAY_RUN_ROOT` names a folder, where they stay until you
delete them. File changes stay in your project until you change them. Your hosted model provider's privacy policy covers
what you send to it. Support and security reports: https://github.com/HarperZ9/relay/issues

# relay

**A zero-dependency, accountable coding agent that runs on any model endpoint.**
Local models when you're offline, your subscription or API when you need more,
automatic failover across all of them — and every run is a re-verifiable,
git-anchored trajectory. Stdlib only.

```
pip install git+https://github.com/HarperZ9/relay.git

relay --health --online                    # which model tiers are live?
relay "explain this function" --file app.py
relay --agent "fix the off-by-one in paginate()" --root . --allow-write --auto-commit
relay --mcp                                # serve the agent to any MCP client
```

## Reaches every endpoint (with your own credentials)

One ladder, tried in order, failing over on exhaustion or error — free/private
tiers first so you only spend metered tokens when you have to:

| Tier | Reached by |
|---|---|
| **local** | a served 14B/32B (`serve.py`) → Ollama (largest pulled model) |
| **plan / max** | the official CLI (`claude`, `codex`) using your subscription auth |
| **api** | `codex` / `claude` / `gemini` / `deepseek` public APIs + `<PROVIDER>_API_KEY` |
| **provider** | a gateway (OpenRouter, ...) via `<PROVIDER>_PROVIDER_BASE_URL` |
| **cloud** | a cloud OpenAI-compatible endpoint via `<PROVIDER>_CLOUD_BASE_URL` + `_CLOUD_KEY` |

Legitimate by construction: keys come from the environment, subscriptions from
your own authenticated CLI, gateways from a base URL you set. Nothing is forged,
no cover identity is minted, no session token is harvested, no billing is evaded.
A missing credential just drops that tier from the ladder.

## An actual coding agent, not a chat box

`--agent` runs a gated tool loop the model drives:

- **`repo_map`** — a compact code outline (Python via `ast`; JS/TS/Go/Rust/Java/
  C#/Swift/PHP/Ruby via patterns) so the model finds the right file.
- **`edit_file`** — precise search/replace where the target must match exactly
  once, so an ambiguous edit is refused, not guessed.
- **`read_file` / `list_dir`** — sandboxed to `--root`.
- **`write_file` / `run`** — off by default; enabled with `--allow-write` /
  `--allow-exec`, and a denylist blocks destructive commands even then.

## The wedge: a provable run

Every turn, tool call, and result is appended to a **hash-chained session
ledger**. A saved run is tamper-evident: reload it and `verify()` re-derives the
chain. With `--auto-commit`, the git commit message carries the ledger
checkpoint, so your version history points back at the exact witnessed trajectory
that produced the change. Each model turn also carries a content-addressed
receipt. No other coding agent gives you a run you can *prove*, not just read.

## Use from an agent (MCP)

`relay --mcp` is a zero-dep stdio MCP server exposing `local_agent_health`,
`local_agent_chat`, and `local_agent_run`. Point Claude Code (or any MCP client)
at it to use relay as a fallback tier — e.g. keep working on local models when a
hosted quota runs out.

## Library

```python
from relay import LocalAgent, available_backends, build_endpoints, run_agent

agent = LocalAgent(backends=available_backends() + build_endpoints())  # local + online
print(agent.send("hi")["content"][0]["text"])
```

## License

MIT. See [LICENSE](LICENSE).

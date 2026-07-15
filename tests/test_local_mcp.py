"""Falsifiers for the harness MCP server (agent-consumable over JSON-RPC).

Load-bearing: (1) initialize names the local-agent server; (2) tools/list
advertises health/chat/run; (3) the health tool returns the real tier report;
(4) a chat with no live backend is a typed error, not a crash; (5) unknown
method/tool are typed; (6) the serve loop round-trips JSON-RPC.
"""
import io
import json

from relay.local_mcp import handle, serve


def _req(method, rid=1, params=None):
    r = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        r["id"] = rid
    if params is not None:
        r["params"] = params
    return r


def test_initialize_and_tools_list():
    assert handle(_req("initialize"))["result"]["serverInfo"]["name"] == "local-agent"
    tools = {t["name"] for t in handle(_req("tools/list"))["result"]["tools"]}
    assert tools == {"local_agent_health", "local_agent_chat", "local_agent_run"}


def test_run_tool_description_does_not_overclaim_exec_sandbox():
    # The MCP description an auto-consuming client trusts must not claim a blanket
    # root sandbox that the run/exec tool does not honor (exec only sets cwd).
    from relay.local_mcp import TOOLS
    run_tool = next(t for t in TOOLS if t["name"] == "local_agent_run")
    desc = run_tool["description"]
    assert "tools sandboxed to root" not in desc
    assert "cwd" in desc.lower() or "not path-confined" in desc.lower()


def test_health_tool_returns_tier_report():
    resp = handle(_req("tools/call", params={"name": "local_agent_health", "arguments": {}}))
    report = json.loads(resp["result"]["content"][0]["text"])
    assert "tiers" in report and {t["backend"] for t in report["tiers"]} >= {"serve", "ollama"}


def test_chat_with_no_backend_is_typed_error(monkeypatch):
    # force every backend unhealthy: point at dead local ports and no online
    import relay.local_mcp as m
    from relay.local_agent import ServeBackend

    def dead(*a, **k):
        return [ServeBackend(base_url="http://127.0.0.1:1"),
                ServeBackend(base_url="http://127.0.0.1:2")]
    monkeypatch.setattr(m, "available_backends", dead)
    resp = handle(_req("tools/call", params={"name": "local_agent_chat",
                                             "arguments": {"prompt": "hi"}}))
    assert resp["result"]["isError"] is True


def test_unknown_tool_and_method_are_typed():
    assert handle(_req("tools/call", params={"name": "nope", "arguments": {}}))["result"]["isError"]
    assert handle(_req("bogus"))["error"]["code"] == -32601


def test_serve_loop_roundtrips():
    stdin = io.StringIO(json.dumps(_req("initialize")) + "\n")
    out = io.StringIO()
    serve(stdin=stdin, stdout=out)
    assert json.loads(out.getvalue())["result"]["serverInfo"]["name"] == "local-agent"

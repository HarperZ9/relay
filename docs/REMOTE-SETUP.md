# Driving relay from your phone and PC

relay's agent can run on your PC and be driven remotely — from **Flywheel on your
PC** and from the **Claude app on your phone** — the way Codex and Claude Code
connect to their phone apps. This guide sets both up.

The code is done: `relay.remote_mcp` serves the agent over Streamable-HTTP MCP
(`/mcp`) with OAuth 2.1 and TLS. What's left is your network and a few values.

---

## PC (Flywheel) — already works, no setup

The relay agent on PC is Flywheel's **Chat → Agent mode**:

1. Confirm relay is installed: `python -c "import relay; print(relay.__file__)"`.
2. Open the Flywheel desktop app (its local gateway starts with it).
3. Open **Chat**, turn **Agent mode ON**, pick a workspace root and a model
   endpoint, and run. That is the same gated, witnessed tool loop relay packages
   (writes/execs are one-use grants, every run keeps its receipt).

Optional: on the **Lanes** view, find `relay` and click **Probe now** to confirm
`relay.status` / `relay.doctor` answer (the lane is live). The desktop is not an
MCP client, so it does not consume the `/mcp` endpoint — that endpoint is the
server your **phone** connects to.

---

## Mobile (Claude app) — one-time setup

### Check the blockers first

- **Plan:** any Claude plan works (Free allows one custom connector). A new
  connector **cannot be added from the phone app** — you add it once on
  **claude.ai (web) or Claude Desktop**, then it appears on your phone.
- **CGNAT (the make-or-break check).** Claude needs your PC reachable over a
  **public IPv4** address. Compare your router's WAN IP against
  `curl https://api.ipify.org`. If the WAN IP is inside `100.64.0.0/10`, or does
  not match ipify, your ISP is carrier-grade-NATing you and **no port-forward can
  work** — ask your ISP for a public/static IP. (IPv6 is not a reliable fallback;
  Claude connectors are IPv4-only. A relay/VPS ingress is the only other option,
  which is out of scope here.)
- **Cert:** the phone path needs a **publicly-valid CA cert** (Let's Encrypt).
  Self-signed is rejected.

### 1. A public name and cert (your network)

- **Static LAN IP** for the PC (DHCP reservation on the router).
- **DDNS name:** create one at DuckDNS / No-IP / Cloudflare and install its
  updater on a Windows Scheduled Task so it self-heals on IP changes.
- **Port-forward** external TCP **443** → the PC's LAN IP + `RELAY_REMOTE_PORT`
  (and **80** during cert issuance if using HTTP-01). Open the port in Windows
  Firewall.
- **TLS cert** with [win-acme](https://www.win-acme.com) (run elevated):
  - HTTP-01 (needs port 80): `wacs.exe --target manual --host <ddns-name> --validation selfhosting --store pemfiles --pemfilespath C:\certs`
  - DNS-01 (Cloudflare domain, no port 80): `wacs.exe --target manual --host <name> --validation cloudflare --cloudflareapitoken <token> --store pemfiles --pemfilespath C:\certs`
  - Point `RELAY_TLS_CERT` / `RELAY_TLS_KEY` at the actual PEM filenames win-acme
    writes to `C:\certs`. win-acme installs its own 90-day renewal task; the
    launcher below restarts relay so the renewed cert is picked up.

### 2. Configure and run relay (the code)

1. Copy `.env.example` to `.env` and fill every value (generate secrets with
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`). Set
   `RELAY_PUBLIC_URL` to your `https://<ddns-name>` origin and
   `RELAY_REMOTE_HOST=0.0.0.0`.
2. Start it: `powershell -ExecutionPolicy Bypass -File scripts\serve_remote.ps1`.
3. **From mobile data (not home wifi)**, verify it is reachable:
   `python scripts/check_remote.py https://<ddns-name>` — it must PASS (valid
   cert, metadata, `/mcp` answering) before you touch the connector dialog.

### 3. Add the connector (on claude.ai web or Claude Desktop)

1. **Settings → Connectors → Add custom connector.**
2. **Name:** `relay`. **URL:** `https://<ddns-name>/mcp` (the MCP endpoint itself,
   the final non-redirecting URL — not a `.well-known` URL).
3. **Advanced settings:** **Client ID** = your `RELAY_OAUTH_CLIENT_ID`,
   **Client Secret** = your `RELAY_OAUTH_CLIENT_SECRET`. Add.
4. Complete the OAuth consent: a browser prompt (HTTP Basic) appears — enter **any
   username** and your **`RELAY_AUTHORIZE_PASSWORD`**. Claude redirects back and
   the connector shows connected.

### 4. Use it on the phone

Open the Claude app → in a chat tap **+ → Connectors → toggle `relay` on**. Ask
Claude to use the relay tools (`local_agent_run`, `local_agent_chat`,
`relay.status`, …). Writes are opt-in per run; remote exec is **off** unless you
set `RELAY_ALLOW_REMOTE_EXEC=true` on the PC (relay's shell is not confined to the
workspace root — enable it only deliberately).

---

## Values that must match

| Claude connector dialog | your `.env` on the PC |
|---|---|
| URL | `RELAY_PUBLIC_URL` + `/mcp` |
| Client ID | `RELAY_OAUTH_CLIENT_ID` |
| Client Secret | `RELAY_OAUTH_CLIENT_SECRET` |
| consent password | `RELAY_AUTHORIZE_PASSWORD` |

`RELAY_OAUTH_REDIRECT_URIS` must include `https://claude.ai/api/mcp/auth_callback`
(and `https://claude.com/api/mcp/auth_callback`) — the `.env.example` default
already lists both.

## Known limitations

- **Access tokens do not refresh yet.** A phone session ends at the access-token
  lifetime and you re-do the consent. Refresh-token support is the next increment.
- **Cert renewal needs a process restart** — the launcher's restart loop handles
  it; a hard kill loses that.
- **CGNAT has no no-VPS fix** for the Claude path — a public IP from your ISP is
  the only in-scope answer.

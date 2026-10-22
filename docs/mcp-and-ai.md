# Outline + MCP (Claude, Cursor, Codex)

Outline ships its own MCP server. There is nothing extra to deploy: enable it
once and point Claude at `https://notes.example.com/mcp`. Community MCP
servers for Outline exist but the official one has replaced them (the most
popular, mmmeff/outline-mcp-server, is archived for that reason).

## Enable

Outline > Settings > Workspace > **AI** > enable MCP. The same page has an
optional "guidance" field: write a sentence about how your knowledge base is
organised; clients receive it as instructions. Self-hosted support arrived in
v1.6.0; v1.11 (October 2026) follows the latest MCP spec and exposes Skills.

## Getting through Cloudflare Access

Browsers carry an Access cookie; MCP clients do not. Three working patterns:

### 1. Claude Code (simplest)

Create a **Service Token** (Zero Trust > Access controls > Service
credentials) and add a policy to the Outline self-hosted application:
action **Service Auth**, include *Service Token* = that token. The
`cloudflared` connector accepts it because Access still issues a JWT for
service-token requests. Then an Outline **API key** (Settings > API) for
Outline's own auth:

```bash
claude mcp add --transport http outline https://notes.example.com/mcp \
  --header "CF-Access-Client-Id: <id>.access" \
  --header "CF-Access-Client-Secret: <secret>" \
  --header "Authorization: Bearer <outline-api-key>"
```

Scope the API key to what you need (read-only for a research assistant).

### 2. Claude.ai / Claude Desktop connectors: Cloudflare MCP portal

Zero Trust > Access controls > AI controls > **MCP servers**: add
`https://notes.example.com/mcp`, then create a **portal**
(`https://mcp.example.com/mcp`). Claude connects to the portal with OAuth
handled by Cloudflare (Google login again, same policy). For the hop from
the portal to Outline, set the server's auth to *bearer* with the Outline API
key, and on the Outline Access application add a **Service Auth** policy with
selector **Linked App Token** = the portal's SaaS app. Verify the first call
in Zero Trust > Logs > Access; this is the one piece this repo could not
test offline.

### 3. Over Tailscale, no Cloudflare

If the Mac mini is on your tailnet you could expose Outline on the Tailscale
IP only and talk to `/mcp` directly. The playbook deliberately publishes no
host ports in tunnel mode; adding a Tailscale-only port is a one-line change
to the Outline compose template (`100.x.y.z:3000:3000`) if you want it.

## Other MCP servers worth knowing

- **Cloudflare**: `https://mcp.cloudflare.com/mcp` (official, OAuth) manages
  DNS, Access and tunnels from Claude. Useful for the one-time setup and for
  reading Access logs.
- **Authentik**: no official server. Community: Samik081/mcp-authentik,
  cdmx-in/authentik-mcp. Only relevant in `auth_mode: authentik`.

## Hygiene

- An MCP client can read and edit everything the key can. Use a dedicated
  API key per client and revoke it when the client goes away.
- Keep Outline's MCP behind Access. Never add a Bypass policy for `/mcp`.
- Outline records MCP searches and edits in document history, so review
  history after letting an agent loose on a collection.

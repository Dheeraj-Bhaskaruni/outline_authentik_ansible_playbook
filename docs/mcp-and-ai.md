# Outline + MCP (Claude Code, Claude Desktop, Cursor, Codex)

Outline ships its own MCP server at `https://notes.example.com/mcp`
(Streamable HTTP; OAuth or API key). Community servers are archived in its
favour. Enable it once: Settings > Workspace > **AI** > MCP, and write a
sentence of guidance about how your knowledge base is organised.

## From the tailnet (default)

```bash
claude mcp add --transport http outline https://notes.example.com/mcp \
  --header "Authorization: Bearer <outline api key>"
```

Or omit the header and let Claude Code run Outline's OAuth flow in your
browser (Google login through Access, then Outline's consent screen).

## From elsewhere (Cloudflare)

Add the service-token headers of a token allowed by the `/mcp` path app
(`docs/cloudflare-security.md` Part D):

```bash
claude mcp add --transport http outline https://notes.example.com/mcp \
  --header "CF-Access-Client-Id: <id>.access" \
  --header "CF-Access-Client-Secret: <secret>" \
  --header "Authorization: Bearer <outline api key>"
```

claude.ai's connector UI supports custom headers only in a limited beta; for
it, Cloudflare's **MCP server portal** (Zero Trust > AI controls) fronts
Outline's `/mcp` with Cloudflare-handled OAuth. Not set up by this repo.

## Other MCP servers worth knowing

- Cloudflare's own `https://mcp.cloudflare.com/mcp` manages DNS, Access and
  tunnels from Claude; handy for the one-time setup and for reading logs.

## Hygiene

An MCP client can read and edit everything its key can. One key per client,
scoped and expiring; keep `/mcp` behind Access and the tailnet.

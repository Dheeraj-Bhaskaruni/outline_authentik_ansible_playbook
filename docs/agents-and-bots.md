# Agents and bots writing to the knowledge base

Outline has a complete REST API, an OAuth provider, webhooks and a built-in
MCP server. This repo adds the plumbing so your Proxmox VMs, cloud agents and
Claude can use them safely.

## Identity: one key per machine

Outline API keys belong to a user; there are no service accounts.

- Start with keys on your own account, one per machine or agent, named
  `agent/<name>/<yyyy-mm>`, **scoped** (e.g. `documents.create`,
  `documents.update`, `documents.info`, `documents.search`) and with an
  **expiry**. Settings > API & Apps.
- For a clean history ("written by planner-bot"), create a bot Google account,
  allow it in both Access applications, log in once over the private path,
  create its key there, and give it Editor rights only on the collections it
  needs.
- Revoke a key the moment the machine goes away. Agents on ephemeral
  Tailscale keys disappear from the tailnet by themselves.

## Reaching Outline

| From | Path | Headers |
| --- | --- | --- |
| Tailnet or home LAN | `https://notes.example.com` directly | `Authorization: Bearer <key>` |
| Anywhere else | through Cloudflare, path app `/api/*` | + `CF-Access-Client-Id`, `CF-Access-Client-Secret` (service token) |

Outline's own rate limiter is on (1000 requests/minute per IP by default,
`outline_rate_limiter_*`). Raise the multiplier if a batch job hits 429.

## Idempotent writes

The API has no upsert. The clients in `examples/clients/` derive the document
id as a UUIDv5 of `(client name, title)`, call `documents.info`, then
`documents.update` or `documents.create` with that `id`. Re-running a job
updates the same page instead of creating duplicates.

```bash
export OUTLINE_URL=https://notes.example.com OUTLINE_API_KEY=ol_api_...
examples/clients/kb_client.py collections
examples/clients/kb_client.py put --collection <id> --title "Nightly report" < report.md
examples/clients/kb_client.py search "report"
```

`kb-put.sh` is the same thing in Bash + curl for hosts without Python.

## Claude as the chatbot

Claude Code, Claude Desktop and claude.ai can read and edit the knowledge base
through Outline's MCP server (`docs/mcp-and-ai.md`). That is the chatbot: ask
Claude, it searches and cites your documents, and writes summaries back when
you ask. No LLM runs on the Mac mini.

## Event-driven bots (webhooks)

Outline > Settings > Webhooks: subscribe to events (`documents.publish`,
`comments.create`, ...) with URL `http://automation:8080/outline` and note the
signing secret. Set `automation_enabled: true` and `outline_webhook_secret`
and deploy. The consumer (`files/automation/webhook_consumer.py`):

- is reachable only inside the Outline Compose network (no host port);
- verifies `Outline-Signature` (HMAC-SHA256 over `t.body`) and rejects
  replays older than 5 minutes;
- logs each event and calls `handle(event)`: put your logic there, or have it
  forward to an agent on a Proxmox VM over the tailnet.

Example bot: on `comments.create` containing `@bot`, fetch the document, ask
Claude through the API, post the answer as a reply with `comments.create`.

## Hygiene

- Scope keys down; one key per client; expiry on every key.
- Never add a Cloudflare Bypass policy for `/api` or `/oauth`.
- Outline records API and MCP edits in document history; review it after
  letting a new agent loose on a collection.

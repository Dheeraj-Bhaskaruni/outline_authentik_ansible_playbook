# Personal knowledge platform: Outline, safely on your own domain

Ansible deploys [Outline](https://www.getoutline.com) (wiki, notes, knowledge
base) on a small Linux box such as a 2014 Mac mini, and gives it three doors:

| Who | Door | Identity |
| --- | --- | --- |
| You, from anywhere | Cloudflare Tunnel + Cloudflare Access | Google login (any IdP Cloudflare supports) |
| Your machines, your phone | the same hostname over Tailscale or the home LAN | Tailscale identity + Outline API key / OAuth |
| Hosted clients without Tailscale | Cloudflare, path app `/api/*` | Cloudflare service token + Outline API key |

Nothing listens on the Internet. Cloudflare down: the private path still works.
Claude and other agents read and write through Outline's built-in MCP server
and REST API. The Android app signs in over the private path.

Guides: [Cloudflare + cPanel](docs/cloudflare-security.md) ·
[Private path (Tailscale/LAN)](docs/private-path.md) ·
[Backups and restore](docs/backup-restore.md) ·
[Agents and bots](docs/agents-and-bots.md) · [MCP](docs/mcp-and-ai.md) ·
[Mac mini host](docs/mac-mini-host.md)

## Architecture

```
 Internet (humans)                       Your machines
 browser / PWA ----> Cloudflare Access ----> cloudflared --+        Tailscale / LAN
                     (Google, MFA, 404 for unknown hosts)   |      +-- dnsmasq (split DNS)
                                                            v      v
                                                        outline:3000 <--- Caddy :443 (LE cert, bound to
                                                            |             tailnet + LAN addresses only)
                                       PostgreSQL 16 | Redis (noeviction) | uploads
                                       restic -> R2 + USB | UFW | optional webhook consumer
```

Each tier is a tagged task file (`tasks/*.yml`); the `apps` list in
`group_vars/all.yml` drives tunnel ingress, Caddy and DNS, so another service
is one Compose directory plus one list entry.

## Security model

- **No public host ports.** `cloudflared` rejects any request without a valid
  Access token for that hostname; unknown hostnames get 404.
- **Private path binds only** to the Tailscale (`100.64.0.0/10`) and RFC1918
  addresses you configure; dnsmasq answers only the app hostnames.
- PostgreSQL, Redis, the webhook consumer never publish ports.
- Outline's rate limiter is on; Redis uses `noeviction` so job queues survive.
- Secrets live in Ansible Vault; rendered files are `0600`/`0400`; rendering
  suppresses logs and diffs.
- Deployment rejects placeholder or reused secrets, HTTP URLs when published,
  floating image tags in production, public bind addresses, weak backup
  passwords and incomplete Cloudflare settings.
- Nightly encrypted backups to two places with a documented restore drill.

## Deploy

1. Host: Debian 13 + Docker 28 + Tailscale (`docs/mac-mini-host.md`).
2. Cloudflare one-time setup (`docs/cloudflare-security.md` Parts A–B) and
   Tailscale split DNS/ACL (`docs/private-path.md`).
3. `cp examples/production.yml production.yml`, `cp examples/secrets.yml
   secrets.yml`, fill both, `ansible-vault encrypt secrets.yml`.
4. Edit `inventory.ini` with the host's tailnet address and user.
5. Run:

   ```bash
   uv venv .venv && uv pip install --python .venv/bin/python ansible-core pyyaml
   .venv/bin/python tests/validate_security.py
   .venv/bin/ansible-playbook site.yml -e @production.yml -e @secrets.yml --ask-vault-pass --check --diff
   .venv/bin/ansible-playbook site.yml -e @production.yml -e @secrets.yml --ask-vault-pass
   ```

   `--tags backup`, `--tags edge` etc. touch one tier.
6. Open the site, sign in with Google, enable MCP under Settings > AI.

## Using it

- **Dashboard**: `https://<team>.cloudflareaccess.com` (Cloudflare App Launcher).
- **Claude**: `claude mcp add --transport http outline https://notes.example.com/mcp --header "Authorization: Bearer <key>"`.
- **Agents**: `examples/clients/kb_client.py put --collection <id> --title "..." < file.md`
  (idempotent; one scoped API key per machine).
- **Bots**: Outline webhooks into the optional consumer (`automation_enabled`).
- **Phone**: Tailscale + Outline PWA, or the Inkharbor Android app.

## Verification

```bash
.venv/bin/python tests/validate_security.py   # 41 scenarios, renders every tier
.venv/bin/python tests/test_webhook_consumer.py
```

CI (`.github/workflows/ci.yml`) runs the same plus syntax checks on every push.
Live acceptance checks are listed at the end of each guide.

## Layout

| Path | Purpose |
| --- | --- |
| `site.yml`, `restore.yml` | Entry points |
| `tasks/*.yml` | Tiers: validate, docker, outline, edge, firewall, backup, start |
| `group_vars/all.yml` | All variables, documented, with the `apps` list |
| `templates/` | Compose files, env, Caddyfile, dnsmasq, cloudflared, backup units |
| `files/` | Caddy and dnsmasq Dockerfiles, webhook consumer |
| `examples/` | `production.yml`, `secrets.yml`, agent clients |
| `tests/` | Offline security checks and unit tests |
| `docs/` | Runbooks |

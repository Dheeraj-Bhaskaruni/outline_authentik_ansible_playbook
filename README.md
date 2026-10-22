# Outline on your own domain, behind Cloudflare Access

Deploys Outline (wiki/notes) as Docker Compose stacks on a Debian/Ubuntu box
such as a 2014 Mac mini, publishes it on your domain through an
Access-protected Cloudflare Tunnel, and signs you in with Google (or any
identity provider Cloudflare supports). Cloudflare's App Launcher becomes
your dashboard. Outline's built-in MCP server works with Claude.

Guides: [Cloudflare + cPanel runbook](docs/cloudflare-security.md) ·
[Mac mini host](docs/mac-mini-host.md) · [MCP and AI clients](docs/mcp-and-ai.md)

## Modes

| | `auth_mode: cloudflare` (recommended) | `auth_mode: authentik` |
| --- | --- | --- |
| Login | Google via Cloudflare Access, once | Access, then Authentik |
| Containers | Outline, PostgreSQL, Redis, cloudflared | + Authentik server/worker, PostgreSQL, Caddy |
| RAM | under 1.5 GB | about 3 GB |
| Extra secrets | Access OIDC client secret | Authentik keys, OIDC client, DNS API token |
| Use when | personal or small-team notes | you need your own IdP for many apps |

Lab mode (`cloudflare_tunnel_enabled: false`) binds the apps to `127.0.0.1`
only, for testing over SSH port-forwarding or Tailscale.

## Security model

- **No host ports in tunnel mode.** An outbound `cloudflared` connector carries
  traffic and rejects every request without a valid Cloudflare Access token
  for that hostname. Unknown hostnames return 404. Bots see Cloudflare's
  login page, never your server.
- PostgreSQL, Redis and MailHog never publish host ports.
- Optional UFW firewall: deny inbound except SSH from a range you choose.
- Credential files are root-owned (`0600`) or owned by the connector's uid
  (`0400`); secret rendering suppresses logs and diffs.
- Deployment rejects sample credentials, reused secrets, weak key formats,
  HTTP URLs in production, floating image tags, and incomplete Cloudflare
  settings (missing AUD tag, team name, credentials, OIDC client).
- SSH host key checking is enabled; verify the server fingerprint first.

## Prerequisites

Install Ansible on the control machine (`uv venv .venv && uv pip install
ansible-core pyyaml`). On the target install Docker Engine 28+ and the
Compose plugin from Docker's repository; see the Mac mini guide for a full
host setup. Update `inventory.ini` with the host and SSH user. Shared cPanel
hosting cannot run Docker; the domain, website and email stay on cPanel.

## Configure and deploy

1. Follow Parts A and B of the runbook: move DNS to Cloudflare, add Google as
   a login method, create the self-hosted Access application (AUD tag), the
   SaaS/OIDC application (client ID and secret), the tunnel and its DNS CNAME.
2. Copy `examples/production.yml` to `production.yml` and fill in URLs, team
   name, AUD tag, client ID, SMTP and tested image digests.
3. Copy `examples/secrets.yml` to `secrets.yml`: three `openssl rand -hex 32`
   values, the tunnel credentials JSON, the OIDC client secret. Encrypt with
   `ansible-vault encrypt secrets.yml`.
4. Deploy:

   ```bash
   ansible-playbook site.yml --syntax-check
   ansible-playbook site.yml -e @production.yml -e @secrets.yml --ask-vault-pass
   ```

5. Open `https://notes.example.com`, sign in with Google, and your workspace
   is created. Enable MCP under Settings > AI if you want Claude to use it.

Access authorises who may reach the app; Outline roles decide what they can
do. On an existing installation keep the current keys and database password;
changing `POSTGRES_PASSWORD` does not rotate the password inside a volume.

## Verification

```bash
.venv/bin/python tests/validate_security.py
```

Renders the real templates for lab, production, Authentik and Cloudflare-login
modes and verifies: rejection of unsafe inputs (31 scenarios), loopback-only
or no host ports, no database publishing, Access enforcement on every tunnel
hostname with a 404 catch-all, credential file modes, OIDC wiring and HTTPS
settings. It does not run Docker or touch Cloudflare. Then do the runbook's
live acceptance checks.

## Layout

| Path | Purpose |
| --- | --- |
| `site.yml` | Playbook: validation, rendering, firewall, Compose stacks |
| `group_vars/all.yml` | Defaults and documented variables |
| `templates/*-docker-compose.yml.j2` | Outline, Authentik and edge stacks |
| `templates/cloudflared-*.j2`, `templates/Caddyfile.j2` | Edge configuration |
| `files/caddy/Dockerfile` | Caddy with the Cloudflare DNS module (Authentik mode) |
| `examples/` | Copy to `production.yml` / `secrets.yml` (gitignored) |
| `tests/validate_security.py` | Offline safety checks |

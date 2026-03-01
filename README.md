# Outline + Authentik Ansible Deployment

This Ansible project deploys Outline and Authentik using Docker Compose with reusable templates.

## What it sets up

- Docker + Docker Compose plugin (Debian/Ubuntu)
- Authentik stack in `/opt/selfhosted/authentik` (default)
- Outline stack in `/opt/selfhosted/outline` (default)
- OIDC env wiring from Outline to Authentik

## 1) Edit variables

Edit:

- `group_vars/all.yml`

Required values to change:

- `outline_secret_key`
- `outline_utils_secret`
- `authentik_secret_key`
- `outline_oidc_client_id`
- `outline_oidc_client_secret`
- `outline_url`
- `authentik_external_url`

## 2) Generate strong secrets (example)

```bash
openssl rand -hex 32
```

Use separate values for each secret variable.

## 3) Run playbook

```bash
cd /home/dheera/ansible
ansible-playbook site.yml
```

## 4) Post-deploy Authentik steps (one-time)

1. Open Authentik admin: `http://<host>:9000/if/admin/`
2. Create OAuth2/OpenID provider + application for Outline
3. Set app slug equal to `outline_oidc_slug` (default `outline`)
4. Set Redirect URI:
   - `http://<host>:3000/auth/oidc.callback`
5. Copy Client ID/Client Secret into `group_vars/all.yml`
6. Re-run:

```bash
ansible-playbook site.yml
```

## 5) User requirements

For Outline login to work, Authentik users must have:

- Valid email address

Outline rejects users without email in OIDC claims.

## Re-deploy/update

Re-run `ansible-playbook site.yml` after changing variables.

## Notes

- This is HTTP-only lab config by default.
- For production, add reverse proxy + TLS and tighten secrets/backups.

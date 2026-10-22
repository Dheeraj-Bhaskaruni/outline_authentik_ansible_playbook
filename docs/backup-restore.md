# Backups and restore

Nightly, `outline-backup.timer` runs `/opt/selfhosted/backup/backup.sh`:

1. `pg_dump -Fc` of the Outline database into `backup/dumps/outline.dump`.
2. `restic backup` of `/opt/selfhosted` (configs, dump) and the uploads
   volume to **every** repository in `backup_repositories`, initialising a
   repository on first use.
3. `restic forget --prune` with the keep policy (14 daily, 8 weekly, 12
   monthly by default); `restic check --read-data-subset=5%` on Sundays.
4. Pings `backup_healthcheck_url` (`/start`, success, `/fail`) so a backup
   that never ran is noticed, not just one that failed.

Two copies are the default: Cloudflare R2 (off-site) and a USB disk on the
mini (fast restores). Backblaze B2 is a drop-in third entry.

## Setup

- **R2**: Cloudflare dashboard > R2 > create bucket `knowledge-backup` > R2
  API token with *Object Read & Write* on that bucket. Repository
  `s3:https://<account-id>.r2.cloudflarestorage.com/knowledge-backup`, keys
  into `backup_r2_access_key` / `backup_r2_secret_key` (secrets.yml).
- **USB**: format ext4, mount persistently at `/mnt/backup`
  (`/etc/fstab` with `nofail`). Repository `/mnt/backup/restic`.
- `backup_restic_password`: `openssl rand -hex 32`. **Store it in your
  password manager.** Without it the backups are unreadable.
- healthchecks.io: create a check with a 1-day period and 2-hour grace; paste
  the ping URL into `backup_healthcheck_url`.
- `backup_enabled: true`, deploy, then run once by hand:

  ```bash
  sudo systemctl start outline-backup.service && journalctl -u outline-backup -n 50
  sudo bash -c 'set -a; . /opt/selfhosted/backup/r2.env; restic snapshots'
  ```

## The other half of a backup

`SECRET_KEY` encrypts fields inside the database. The vaulted `secrets.yml`
and `production.yml` on your Mac are therefore part of the backup. Keep a
copy of both (and the vault password) in your password manager or an
encrypted USB stick.

## Restore

Drill this once on a Proxmox VM before you need it. On the target host run
the normal playbook first (fresh, empty Outline), then:

```bash
ansible-playbook restore.yml -e @production.yml -e @secrets.yml --ask-vault-pass \
  -e restore_repository=r2 -e restore_snapshot=latest -e restore_confirm=yes
```

It stops Outline, restores the snapshot to a scratch directory, syncs the
uploads into the volume, `pg_restore --clean --if-exists` into the running
PostgreSQL, starts Outline and waits for `/_health`. Compare document counts
(`kb_client.py search ""` or the UI) with the source.

## PostgreSQL major upgrades

Stay on 16 until you do this deliberately: deploy a new host or compose
project with the new image, restore the dump into it, switch. Image 18 moved
PGDATA, so an in-place image swap on the existing volume does not work.

# Mac mini (Late 2014) as the server

A 2014 Mac mini (Macmini7,1: dual-core Haswell i5, 8 GB soldered RAM, 256 GB
PCIe SSD, gigabit Ethernet) is a fine host for this stack. Its macOS line
ended with Monterey, which no longer receives security updates, and Docker
Desktop needs a newer macOS anyway. Run Linux on it.

## Budget

| Component | Typical RSS |
| --- | --- |
| Outline | 300–500 MB |
| PostgreSQL 16 | 50–150 MB |
| Redis | 10–30 MB |
| cloudflared | 20–40 MB |
| Caddy + dnsmasq (private path) | 40–80 MB |
| Debian + Docker | 300–500 MB |
| **Total** | **under 1.5 GB** |

8 GB leaves plenty of room; the dual-core CPU is the limit, and it is enough
for a personal wiki plus a few agents writing to it.

## Install Debian 13

1. Download the Debian 13 amd64 netinst ISO and write it to a USB stick with
   `dd` or balenaEtcher (not unetbootin).
2. Connect Ethernet, a keyboard and a display for the install only.
3. Power on holding **Option**, choose the USB stick ("EFI Boot").
4. Install with the whole disk (guided, ext4, no separate /home needed), a
   plain user plus sudo, **SSH server** selected, no desktop environment.
   Hostname e.g. `mini`.
5. Wi-Fi is a Broadcom BCM4360 that needs the proprietary `wl` driver; do not
   bother. Ethernet (BCM57766, `tg3`) works out of the box.
6. First boot, then over SSH:

   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo apt install -y unattended-upgrades curl ca-certificates zram-tools
   sudo dpkg-reconfigure -plow unattended-upgrades
   ```

   `zram-tools` gives compressed swap in RAM, which is kinder to the SSD than
   a swap file and smooths out memory spikes.

7. Docker Engine from Docker's own repository (the Debian `docker.io` package
   is too old for the Docker 28+ requirement):
   <https://docs.docker.com/engine/install/debian/>. Install `docker-ce`,
   `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`,
   `docker-compose-plugin`.

8. Tailscale: SSH without opening a port, and the [private path](private-path.md):

   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --ssh --advertise-tags=tag:kb
   ```

   Then `firewall_ssh_source: 100.64.0.0/10` in `production.yml` restricts
   SSH to the tailnet.

9. USB backup disk (optional but recommended): format ext4, add to
   `/etc/fstab` with `nofail`, mounted at `/mnt/backup`.

## Headless behaviour

- **Power loss.** Intel Macs forget "start up automatically after power
  failure" under Linux. Add a systemd unit or `/etc/rc.local` line
  `setpci -s 0:1f.0 0xa4.b=0`, the long-standing trick for Intel minis, and
  test by pulling the plug.
- **No sleep.** `sudo systemctl mask sleep.target suspend.target
  hibernate.target hybrid-sleep.target`.
- **Firmware.** Update to the last Apple firmware (via the final macOS
  updater) before wiping, if you still can; it fixes EFI quirks.
- **Fan and dust.** The 2014 mini is quiet, but it throttles when dusty.
  Give it air.
- **Backups.** The SSD is the only disk. Back up PostgreSQL dumps,
  `/var/lib/docker/volumes`, `/opt/selfhosted` and the vault off-box
  (restic to a USB disk or cloud bucket). Test a restore.

## Inventory

```ini
[outline_host]
mini ansible_host=100.x.y.z ansible_user=you
```

Replace the default `localhost` entry. Verify the SSH host key fingerprint
the first time; `ansible.cfg` enforces host key checking.

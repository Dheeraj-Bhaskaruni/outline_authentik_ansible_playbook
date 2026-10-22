# Private path: your machines and your phone (Tailscale + home LAN)

The same `notes.example.com` resolves to the Mac mini's **Tailscale address**
on the tailnet and to its **LAN address** at home. Caddy terminates TLS there
with a real Let's Encrypt certificate (DNS-01 through a zone-scoped Cloudflare
token) and is bound **only** to those addresses. Nothing is public.

```
Proxmox VM / cloud agent / phone / laptop
        | DNS: notes.example.com ?  -> dnsmasq on the mini (split DNS)
        |      answer: 100.x.y.z on the tailnet, 192.168.x.y on the LAN
        v
   Caddy  :443 on 100.x.y.z and 192.168.x.y  (LE certificate)
        v
   outline:3000
```

Why: Outline is single-URL (OAuth redirects, cookies, API links). Machines
cannot carry a browser's Access cookie, and the Android app's token exchange
happens in the app. Giving the same hostname a private address solves both
and keeps working when Cloudflare is down.

## One-time setup

1. **Tailscale on the mini** (`docs/mac-mini-host.md`). Note its address:
   `tailscale ip -4`. Tag it in the admin console: `tag:kb`.
2. **Split DNS** in the Tailscale admin console > DNS > Nameservers > Add >
   *Custom* > the mini's tailnet IP, **Restrict to domain** `example.com`.
   Keep MagicDNS on. Clients then send only `*.example.com` queries to the
   mini, which answers `notes.example.com` itself and forwards the rest to
   `1.1.1.1`.
3. **ACL** (Access Controls), minimal example:

   ```json
   "tagOwners": { "tag:kb": ["autogroup:admin"], "tag:agent": ["autogroup:admin"] },
   "acls": [
     { "action": "accept", "src": ["autogroup:member"], "dst": ["tag:kb:443", "tag:kb:53"] },
     { "action": "accept", "src": ["tag:agent"], "dst": ["tag:kb:443", "tag:kb:53"] }
   ]
   ```

4. **Machines**: `tailscale up --accept-dns --auth-key tskey-auth-...`
   with an **ephemeral, pre-authorized** key tagged `tag:agent`, so a lost VM
   disappears from the tailnet by itself.
5. **Home LAN (optional)**: set `private_path_lan_ip` to the mini's Ethernet
   address and `private_path_lan_cidr` to your LAN. Point your router's DNS
   override for `notes.example.com` at the mini, or add a line to
   `/etc/hosts` on the laptop. Tailscale peers on the same LAN already talk
   directly, so this is mainly for debugging without Tailscale.
6. `production.yml`: `private_path_enabled: true`, `acme_email`, and the
   DNS token in `secrets.yml`. Deploy. The first run builds Caddy and
   dnsmasq images (a few minutes on the 2014 i5).

## What the playbook does

- Detects the Tailscale address, asserts it is in `100.64.0.0/10` and the LAN
  address is RFC1918.
- Caddy publishes `443` on exactly those addresses; dnsmasq runs with host
  networking, `bind-interfaces`, `listen-address` per address, `no-hosts`,
  an additional hosts file with one line per address, and `localise-queries`
  so each network gets its own answer.
- Docker starts after `tailscaled` (systemd drop-in) so the bound addresses
  exist at boot.
- UFW allows 443 and 53 from the tailnet and the LAN CIDR only.

## Verify

From a tailnet machine:

```bash
dig +short notes.example.com            # 100.x.y.z
curl -sI https://notes.example.com/api/auth.config | head -1   # HTTP/2 200
openssl s_client -connect notes.example.com:443 -servername notes.example.com </dev/null 2>/dev/null | grep issuer   # Let's Encrypt
```

From the LAN: `dig` returns `192.168.x.y`, same `curl` result. From outside:
the name resolves to Cloudflare and `curl -sI` gives `302` to Access.

On the mini: `ss -ltnp | grep -E ':443|:53'` shows only the bind addresses,
never `0.0.0.0`. From a LAN device that is not on the tailnet and not in
`private_path_lan_cidr`, `nmap` sees nothing.

## Phone

Install Tailscale, sign in, keep the VPN on. The Outline PWA works at once.
For the native app (Inkharbor, Android): Outline >= 1.11.0 and MCP enabled;
sign in from the app, finish the Google login in the browser, done.

## Claude Code and agents

```bash
claude mcp add --transport http outline https://notes.example.com/mcp \
  --header "Authorization: Bearer <outline api key>"
```

No Cloudflare headers needed on the tailnet. See `docs/agents-and-bots.md`.

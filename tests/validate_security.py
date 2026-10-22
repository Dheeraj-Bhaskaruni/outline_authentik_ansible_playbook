#!/usr/bin/env python3
"""Offline configuration checks; never contacts a deployment or starts Docker.

Runs tasks/validate.yml against good and bad inputs, renders every template
the tiers would render, and inspects the results for the security properties
documented in README.md.
"""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
TASK_FILES_WITH_TEMPLATES = ("outline", "edge", "backup")
SYSTEMD_DIR = "/etc/systemd/system"

TUNNEL_CREDENTIALS = {
    "AccountTag": "f" * 32,
    "TunnelSecret": "dGVzdC1zZWNyZXQtdGVzdC1zZWNyZXQtdGVzdC1zZWNyZXQ=",
    "TunnelID": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
}
TUNNEL = {
    "cloudflare_tunnel_enabled": True,
    "cloudflare_access_outline_aud": "1" * 64,
    "cloudflare_tunnel_credentials": json.dumps(TUNNEL_CREDENTIALS),
}
PRIVATE = {
    "private_path_enabled": True,
    "private_path_tailscale_ip": "100.101.102.103",
    "acme_email": "admin@example.test",
    "cloudflare_dns_api_token": "t" * 40,
}
LAN = {"private_path_lan_ip": "192.168.1.20", "private_path_lan_cidr": "192.168.1.0/24"}
BACKUP = {
    "backup_enabled": True,
    "backup_healthcheck_url": "https://hc-ping.com/0000",
    "backup_restic_password": "p" * 40,
    "backup_repositories": [
        {"name": "r2", "repository": "s3:https://acct.r2.cloudflarestorage.com/kb",
         "env": {"AWS_ACCESS_KEY_ID": "AKIA$TEST", "AWS_SECRET_ACCESS_KEY": "s3cr3t"}},
        {"name": "usb", "repository": "/mnt/backup/restic"},
    ],
}
AUTOMATION = {"automation_enabled": True, "outline_webhook_secret": "w" * 40}


def load_tasks(name):
    return yaml.safe_load((ROOT / "tasks" / f"{name}.yml").read_text())


def main():
    defaults = yaml.safe_load((ROOT / "group_vars/all.yml").read_text())
    values = {
        **defaults,
        "ansible_os_family": "Debian",
        "ansible_python_interpreter": sys.executable,
        "outline_url": "https://notes.example.test",
        "outline_secret_key": "a1" * 32,
        "outline_utils_secret": "b2" * 32,
        "outline_db_password": "d4" * 32,
        "outline_smtp_host": "mail.example.test",
        "outline_smtp_from_email": "notes@example.test",
        "outline_smtp_password": "test${UNSET_TEST_VARIABLE} # 'quote' \\ slash",
        "cloudflare_access_team_name": "example-team",
        "cloudflare_access_oidc_client_id": "c" * 32,
        "cloudflare_access_oidc_client_secret": "s" * 64,
        "production_mode": True,
        "mailhog_enabled": False,
    }
    for variable, repository in (
        ("outline_image", "docker.getoutline.com/outlinewiki/outline"),
        ("postgres_image", "postgres"),
        ("redis_image", "redis"),
        ("cloudflared_image", "cloudflare/cloudflared"),
        ("caddy_image", "caddy"),
        ("caddy_builder_image", "caddy"),
        ("alpine_image", "alpine"),
        ("python_image", "python"),
    ):
        # Synthetic digest validates configuration only; never pulled/run.
        values[variable] = repository + "@sha256:" + "a" * 64

    scenarios = [
        # name, overrides, should_reject
        ("explicit local lab", {"production_mode": False, "mailhog_enabled": True,
                                "outline_url": "http://127.0.0.1:3000"}, False),
        ("production without any edge (private deployment)", {}, False),
        ("tunnel only", TUNNEL, False),
        ("tunnel with path-scoped service-token apps",
         {**TUNNEL, "cloudflare_access_api_aud": "2" * 64, "cloudflare_access_mcp_aud": "3" * 64}, False),
        ("private path only (tailscale)", PRIVATE, False),
        ("private path tailscale + lan", {**PRIVATE, **LAN}, False),
        ("tunnel + private path + backups + automation", {**TUNNEL, **PRIVATE, **LAN, **BACKUP, **AUTOMATION}, False),
        ("tunnel with dict credentials", {**TUNNEL, "cloudflare_tunnel_credentials": TUNNEL_CREDENTIALS}, False),
        ("tunnel in lab mode still needs https", {**TUNNEL, "production_mode": False,
                                                   "outline_url": "http://notes.example.test"}, True),
        ("firewall with CIDR SSH source", {"firewall_enabled": True, "firewall_ssh_source": "100.64.0.0/10"}, False),
        ("firewall with tunnel and private path", {**TUNNEL, **PRIVATE, **LAN, "firewall_enabled": True}, False),
        # rejections
        ("placeholder secret", {"outline_secret_key": "CHANGE_ME"}, True),
        ("reused secrets", {"outline_utils_secret": values["outline_secret_key"]}, True),
        ("weak database password", {"outline_db_password": "outlinepass"}, True),
        ("public HTTP in production", {"outline_url": "http://notes.example.test"}, True),
        ("production inbox", {"mailhog_enabled": True}, True),
        ("floating image", {"outline_image": "outline:latest"}, True),
        ("floating connector image", {**TUNNEL, "cloudflared_image": "cloudflare/cloudflared:latest"}, True),
        ("floating private path images", {**PRIVATE, "alpine_image": "alpine:3.20"}, True),
        ("missing SMTP", {"outline_smtp_host": ""}, True),
        ("unsupported host", {"ansible_os_family": "Darwin"}, True),
        ("login without client id", {"cloudflare_access_oidc_client_id": ""}, True),
        ("login with placeholder secret", {"cloudflare_access_oidc_client_secret": "CHANGE_ME_" * 5}, True),
        ("login without team", {"cloudflare_access_team_name": ""}, True),
        ("tunnel without Access audience", {**TUNNEL, "cloudflare_access_outline_aud": ""}, True),
        ("tunnel with duplicate audiences", {**TUNNEL, "cloudflare_access_api_aud": "1" * 64}, True),
        ("tunnel without credentials", {k: v for k, v in TUNNEL.items() if k != "cloudflare_tunnel_credentials"}, True),
        ("tunnel with malformed credentials", {**TUNNEL, "cloudflare_tunnel_credentials": json.dumps({"TunnelID": "nope"})}, True),
        ("private path with public tailscale ip", {**PRIVATE, "private_path_tailscale_ip": "8.8.8.8"}, True),
        ("private path with public lan ip", {**PRIVATE, "private_path_lan_ip": "203.0.113.5"}, True),
        ("private path lan cidr without ip", {**PRIVATE, "private_path_lan_cidr": "192.168.1.0/24"}, True),
        ("private path without ACME email", {**PRIVATE, "acme_email": ""}, True),
        ("private path with placeholder DNS token", {**PRIVATE, "cloudflare_dns_api_token": "CHANGE_ME_CHANGE_ME_CHANGE_ME_CHANGE_ME"}, True),
        ("private path over HTTP", {**PRIVATE, "outline_url": "http://notes.example.test", "production_mode": False}, True),
        ("backup without repositories", {**BACKUP, "backup_repositories": []}, True),
        ("backup with weak password", {**BACKUP, "backup_restic_password": "short"}, True),
        ("backup with http repository", {**BACKUP, "backup_repositories": [{"name": "x", "repository": "s3:http://insecure/kb"}]}, True),
        ("backup with duplicate names", {**BACKUP, "backup_repositories": BACKUP["backup_repositories"] * 2}, True),
        ("automation without secret", {"automation_enabled": True}, True),
        ("firewall with bad SSH source", {"firewall_enabled": True, "firewall_ssh_source": "; rm -rf /"}, True),
        ("firewall with bad SSH port", {"firewall_enabled": True, "firewall_ssh_port": 70000}, True),
    ]

    validate_tasks = load_tasks("validate")
    render_tasks = []
    for name in TASK_FILES_WITH_TEMPLATES:
        render_tasks += [task for task in load_tasks(name) if "ansible.builtin.template" in task]
    for task in render_tasks:
        template = task["ansible.builtin.template"]
        src = template["src"]
        secret_bearing = ("compose" in src or src.endswith(".env.j2") or "credentials" in src)
        if secret_bearing:
            assert task.get("no_log") is True and task.get("diff") is False, task["name"]
            assert template["mode"] in ("0600", "0400"), task["name"]
        if "credentials" in src or "cloudflared-config" in src:
            assert template["mode"] == "0400" and template["owner"] == "65532", task["name"]

    with tempfile.TemporaryDirectory(prefix="ansible-security-") as directory:
        temp = Path(directory)
        plays = []
        rendered = {}
        for index, (name, overrides, should_reject) in enumerate(scenarios):
            case_vars = {**values, **overrides}
            tasks = [
                {"ansible.builtin.set_fact": {"configuration_rejected": False}},
                {"block": copy.deepcopy(validate_tasks),
                 "rescue": [{"ansible.builtin.set_fact": {"configuration_rejected": True}}]},
                {"name": "Check expected rejection: " + name,
                 "ansible.builtin.assert": {"that": ["configuration_rejected == " + str(should_reject)]}},
            ]
            if not should_reject:
                case = temp / str(index)
                for sub in ("outline", "edge/cloudflared", "edge/caddy", "edge/dnsmasq", "backup", "systemd"):
                    (case / sub).mkdir(parents=True)
                case_vars.update(stack_root=str(case), outline_dir=str(case / "outline"),
                                 edge_dir=str(case / "edge"), backup_dir=str(case / "backup"))
                for original in render_tasks:
                    task = copy.deepcopy(original)
                    options = task["ansible.builtin.template"]
                    options["src"] = str(ROOT / options["src"])
                    options["dest"] = options["dest"].replace(SYSTEMD_DIR, str(case / "systemd"))
                    # Tests run as the local user; ownership is checked above.
                    options.pop("owner", None)
                    options.pop("group", None)
                    task.pop("notify", None)
                    tasks.append(task)
                rendered[name] = (case, case_vars)
            plays.append({"name": name, "hosts": "localhost", "gather_facts": False,
                          "connection": "local", "vars": case_vars, "tasks": tasks})

        playbook = temp / "checks.yml"
        playbook.write_text(yaml.safe_dump(plays, sort_keys=False))
        env = {**os.environ, "ANSIBLE_HOME": str(temp / "ansible-home"),
               "ANSIBLE_LOCAL_TEMP": str(temp / "ansible-local"),
               "ANSIBLE_REMOTE_TEMP": str(temp / "ansible-remote"),
               "ANSIBLE_NOCOLOR": "1"}
        result = subprocess.run(
            [sys.executable, "-m", "ansible.cli.playbook", "-i", "localhost,", str(playbook)],
            cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if result.returncode:
            print(result.stdout)
            raise SystemExit(result.returncode)

        for name, (case, case_vars) in rendered.items():
            check_rendered(name, case, case_vars, values)

        print(f"PASS: {len(scenarios)} validation scenarios ({sum(1 for s in scenarios if s[2])} rejections); "
              "rendered lab, tunnel, private-path, backup and automation configurations; "
              "no public host ports, private binds only on tailnet/LAN addresses, Access enforced on "
              "every tunnel hostname with a 404 catch-all, Redis noeviction, secret-file permissions, "
              "OIDC wiring and HTTPS settings.")
        print("No Docker containers, remote hosts, DNS records or Cloudflare settings were changed.")


def check_rendered(name, case, case_vars, values):
    tunnel = bool(case_vars["cloudflare_tunnel_enabled"])
    private = bool(case_vars["private_path_enabled"])
    bind_ips = [ip for ip in (case_vars["private_path_tailscale_ip"], case_vars["private_path_lan_ip"]) if ip]
    attached = tunnel or private

    # --- Outline stack ----------------------------------------------------
    compose_path = case / "outline" / "docker-compose.yml"
    assert compose_path.stat().st_mode & 0o777 == 0o600
    compose = yaml.safe_load(compose_path.read_text())
    services = compose["services"]
    for service, config in services.items():
        for port in config.get("ports", []):
            assert port.startswith("127.0.0.1:"), (name, service, port)
        if service in ("postgres", "redis", "automation"):
            assert not config.get("ports"), (name, service)
        assert "/var/run/docker.sock" not in str(config.get("volumes", [])), (name, service)
    assert services["postgres"]["healthcheck"]["test"][1].startswith("pg_isready")
    assert services["outline"]["depends_on"]["postgres"] == {"condition": "service_healthy"}
    if attached:
        assert "ports" not in services["outline"], name
        assert "edge" in services["outline"]["networks"], name
        assert compose["networks"]["edge"] == {"external": True, "name": case_vars["edge_network"]}
    else:
        assert services["outline"]["ports"] == ["127.0.0.1:3000:3000"], name
        assert "networks" not in compose
    assert ("mailhog" in services) == case_vars["mailhog_enabled"]
    assert ("automation" in services) == bool(case_vars["automation_enabled"])
    if "automation" in services:
        assert services["automation"]["read_only"] is True
        assert (case / "outline" / "automation.env").stat().st_mode & 0o777 == 0o600

    redis_conf = (case / "outline" / "redis.conf").read_text()
    assert "maxmemory-policy noeviction" in redis_conf, "Bull queues need noeviction"

    env_path = case / "outline" / "docker.env"
    assert env_path.stat().st_mode & 0o777 == 0o600
    entries = dict(line.split("=", 1) for line in env_path.read_text().splitlines()
                   if line and not line.startswith("#"))
    assert entries["FORCE_HTTPS"] == str(case_vars["outline_url"].startswith("https:")).lower()
    assert json.loads(entries["SMTP_PASSWORD"]).replace("$$", "$") == values["outline_smtp_password"]
    assert json.loads(entries["APP_NAME"]) == case_vars["outline_app_name"]
    assert entries["RATE_LIMITER_ENABLED"] == "true"
    assert entries["OAUTH_DISABLE_DCR"] == "false"
    assert "OIDC_DISCOVERY_URL" not in entries  # Outline reads OIDC_ISSUER_URL only
    assert entries["OIDC_ISSUER_URL"] == "https://example-team.cloudflareaccess.com/cdn-cgi/access/sso/oidc/" + "c" * 32
    assert json.loads(entries["OIDC_CLIENT_SECRET"]) == "s" * 64
    assert json.loads(entries["OIDC_USERNAME_CLAIM"]) == "email"
    assert "authentik" not in env_path.read_text().lower()

    # --- Edge stack -------------------------------------------------------
    edge = case / "edge"
    assert (edge / "docker-compose.yml").exists() == attached, name
    if attached:
        assert (edge / "docker-compose.yml").stat().st_mode & 0o777 == 0o600
        edge_compose = yaml.safe_load((edge / "docker-compose.yml").read_text())
        for service, config in edge_compose["services"].items():
            assert "no-new-privileges:true" in config["security_opt"], (name, service)
            for port in config.get("ports", []):
                host_ip = port.rsplit(":", 2)[0]
                assert host_ip in bind_ips, (name, service, port, "port bound outside tailnet/LAN")
        assert ("cloudflared" in edge_compose["services"]) == tunnel
        assert ("caddy" in edge_compose["services"]) == private
        assert ("dnsmasq" in edge_compose["services"]) == private
        assert edge_compose["networks"]["edge"]["name"] == case_vars["edge_network"]

    assert (edge / "cloudflared" / "config.yml").exists() == tunnel, name
    if tunnel:
        assert edge_compose["services"]["cloudflared"]["read_only"] is True
        assert "ports" not in edge_compose["services"]["cloudflared"]
        credentials_path = edge / "cloudflared" / "credentials.json"
        assert credentials_path.stat().st_mode & 0o777 == 0o400
        assert json.loads(credentials_path.read_text()) == TUNNEL_CREDENTIALS
        config_path = edge / "cloudflared" / "config.yml"
        assert config_path.stat().st_mode & 0o777 == 0o400
        tunnel_config = yaml.safe_load(config_path.read_text())
        assert tunnel_config["tunnel"] == TUNNEL_CREDENTIALS["TunnelID"]
        assert tunnel_config["no-autoupdate"] is True
        ingress = tunnel_config["ingress"]
        assert ingress[-1] == {"service": "http_status:404"}, "catch-all must deny unknown hosts"
        expected_auds = [case_vars["cloudflare_access_outline_aud"]]
        for key in ("cloudflare_access_api_aud", "cloudflare_access_mcp_aud"):
            if case_vars.get(key):
                expected_auds.append(case_vars[key])
        hosts = {}
        for rule in ingress[:-1]:
            access = rule["originRequest"]["access"]
            assert access["required"] is True, rule
            assert access["teamName"] == case_vars["cloudflare_access_team_name"]
            assert rule["service"] == "http://outline:3000"
            assert all(isinstance(a, str) for a in access["audTag"])
            hosts[rule["hostname"]] = access["audTag"]
        assert hosts == {"notes.example.test": expected_auds}, (name, hosts)

    assert (edge / "Caddyfile").exists() == private, name
    assert (edge / "dnsmasq" / "dnsmasq.conf").exists() == private, name
    if private:
        caddy = edge_compose["services"]["caddy"]
        assert sorted(caddy["ports"]) == sorted(f"{ip}:443:443" for ip in bind_ips)
        assert caddy["environment"]["CLOUDFLARE_API_TOKEN"] == case_vars["cloudflare_dns_api_token"]
        dnsmasq = edge_compose["services"]["dnsmasq"]
        assert dnsmasq["network_mode"] == "host" and dnsmasq["read_only"] is True
        assert dnsmasq["cap_drop"] == ["ALL"]
        caddyfile = (edge / "Caddyfile").read_text()
        assert "admin off" in caddyfile
        assert "dns cloudflare {env.CLOUDFLARE_API_TOKEN}" in caddyfile
        assert case_vars["cloudflare_dns_api_token"] not in caddyfile
        assert "\nnotes.example.test {" in caddyfile
        assert "reverse_proxy outline:3000" in caddyfile
        dns_conf = (edge / "dnsmasq" / "dnsmasq.conf").read_text().splitlines()
        assert "bind-interfaces" in dns_conf and "localise-queries" in dns_conf and "no-hosts" in dns_conf
        assert "addn-hosts=/etc/dnsmasq.hosts" in dns_conf and "no-resolv" in dns_conf
        listens = [line.split("=", 1)[1] for line in dns_conf if line.startswith("listen-address=")]
        assert sorted(listens) == sorted(bind_ips), (name, listens)
        assert not any(line.startswith("host-record=") for line in dns_conf), "localise-queries ignores host-record"
        assert any(line.startswith("server=1.1.1.1") for line in dns_conf)
        hosts = [line.split() for line in (edge / "dnsmasq" / "dnsmasq.hosts").read_text().splitlines()
                 if line and not line.startswith("#")]
        assert sorted(hosts) == sorted([ip, "notes.example.test"] for ip in bind_ips), (name, hosts)
        assert "./dnsmasq/dnsmasq.hosts:/etc/dnsmasq.hosts:ro" in dnsmasq["volumes"]

    # --- Backups ----------------------------------------------------------
    backup_enabled = bool(case_vars["backup_enabled"])
    backup = case / "backup"
    assert (backup / "backup.sh").exists() == backup_enabled, name
    if backup_enabled:
        assert (backup / "backup.sh").stat().st_mode & 0o777 == 0o700
        script = (backup / "backup.sh").read_text()
        assert "pg_dump" in script and "restic backup" in script and "restic forget" in script
        assert "--keep-daily 14 --keep-weekly 8 --keep-monthly 12" in script
        assert "REPOS=(r2 usb)" in script, script.splitlines()[9]
        assert "hc-ping.com" in script
        for repo in case_vars["backup_repositories"]:
            env_file = backup / f"{repo['name']}.env"
            assert env_file.stat().st_mode & 0o777 == 0o600
            lines = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if line)
            assert json.loads(lines["RESTIC_REPOSITORY"]) == repo["repository"]
            assert json.loads(lines["RESTIC_PASSWORD"]) == case_vars["backup_restic_password"]
            for key, value in repo.get("env", {}).items():
                assert json.loads(lines[key]) == value
        service = (case / "systemd" / "outline-backup.service").read_text()
        assert f"ExecStart={backup}/backup.sh" in service
        timer = (case / "systemd" / "outline-backup.timer").read_text()
        assert "OnCalendar=*-*-* 03:30:00" in timer and "Persistent=true" in timer


if __name__ == "__main__":
    main()

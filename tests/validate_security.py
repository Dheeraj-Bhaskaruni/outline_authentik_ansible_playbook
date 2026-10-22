#!/usr/bin/env python3
"""Offline configuration checks; never contacts a deployment or starts Docker."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]

TUNNEL_CREDENTIALS = {
    "AccountTag": "f" * 32,
    "TunnelSecret": "dGVzdC1zZWNyZXQtdGVzdC1zZWNyZXQtdGVzdC1zZWNyZXQ=",
    "TunnelID": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
}

TUNNEL_VALUES = {
    "cloudflare_tunnel_enabled": True,
    "acme_email": "admin@example.test",
    "cloudflare_access_team_name": "example-team",
    "cloudflare_access_outline_aud": "1" * 64,
    "cloudflare_access_authentik_aud": "2" * 64,
    "cloudflare_tunnel_credentials": json.dumps(TUNNEL_CREDENTIALS),
    "cloudflare_dns_api_token": "t" * 40,
}

CLOUDFLARE_AUTH_VALUES = {
    **TUNNEL_VALUES,
    "auth_mode": "cloudflare",
    "cloudflare_access_oidc_client_id": "c" * 32,
    "cloudflare_access_oidc_client_secret": "s" * 64,
    # Not needed without Authentik:
    "cloudflare_dns_api_token": "CHANGE_ME",
    "acme_email": "",
    "cloudflare_access_authentik_aud": "",
}


def main():
    site = yaml.safe_load((ROOT / "site.yml").read_text())[0]
    defaults = yaml.safe_load((ROOT / "group_vars/all.yml").read_text())
    values = {
        **defaults,
        "ansible_os_family": "Debian",
        "ansible_python_interpreter": sys.executable,
        "outline_url": "https://notes.example.test",
        "authentik_external_url": "https://auth.example.test",
        "outline_secret_key": "a1" * 32,
        "outline_utils_secret": "b2" * 32,
        "authentik_secret_key": "c3" * 32,
        "outline_db_password": "d4" * 32,
        "authentik_db_password": "e5" * 32,
        "outline_oidc_client_id": "test-client",
        "outline_oidc_client_secret": "test-secret-" * 4,
        "outline_smtp_host": "mail.example.test",
        "outline_smtp_from_email": "notes@example.test",
        "outline_smtp_password": "test${UNSET_TEST_VARIABLE} # 'quote' \\ slash",
        "production_mode": True,
        "mailhog_enabled": False,
    }
    for variable, repository in (
        ("outline_image", "docker.getoutline.com/outlinewiki/outline"),
        ("authentik_image", "ghcr.io/goauthentik/server"),
        ("postgres_image", "postgres"),
        ("redis_image", "redis"),
        ("caddy_image", "caddy"),
        ("caddy_builder_image", "caddy"),
        ("cloudflared_image", "cloudflare/cloudflared"),
    ):
        # Synthetic digest validates configuration only; never pulled/run.
        values[variable] = repository + "@sha256:" + "a" * 64

    scenarios = [
        ("valid production", {}, False),
        ("placeholder secret", {"outline_secret_key": "CHANGE_ME"}, True),
        ("reused secrets", {"outline_utils_secret": values["outline_secret_key"]}, True),
        ("weak database password", {"outline_db_password": "outlinepass"}, True),
        ("public HTTP", {"outline_url": "http://notes.example.test"}, True),
        ("HTTP identity provider", {"authentik_external_url": "http://auth.example.test"}, True),
        ("production inbox", {"mailhog_enabled": True}, True),
        ("floating image", {"outline_image": "outline:latest"}, True),
        ("missing SMTP", {"outline_smtp_host": ""}, True),
        ("unsupported host", {"ansible_os_family": "Darwin"}, True),
        ("explicit local lab", {"production_mode": False, "mailhog_enabled": True,
                                "outline_url": "http://notes.example.test"}, False),
        # Cloudflare edge
        ("valid tunnel", TUNNEL_VALUES, False),
        ("tunnel with dict credentials", {**TUNNEL_VALUES,
                                          "cloudflare_tunnel_credentials": TUNNEL_CREDENTIALS}, False),
        ("tunnel without Access audience", {**TUNNEL_VALUES, "cloudflare_access_outline_aud": ""}, True),
        ("tunnel with shared Access audience",
         {**TUNNEL_VALUES, "cloudflare_access_authentik_aud": TUNNEL_VALUES["cloudflare_access_outline_aud"]}, True),
        ("tunnel without team", {**TUNNEL_VALUES, "cloudflare_access_team_name": ""}, True),
        ("tunnel without credentials", {k: v for k, v in TUNNEL_VALUES.items()
                                        if k != "cloudflare_tunnel_credentials"}, True),
        ("tunnel with malformed credentials",
         {**TUNNEL_VALUES, "cloudflare_tunnel_credentials": json.dumps({"TunnelID": "nope"})}, True),
        ("tunnel with placeholder DNS token",
         {**TUNNEL_VALUES, "cloudflare_dns_api_token": "CHANGE_ME_CHANGE_ME_CHANGE_ME_CHANGE_ME"}, True),
        ("tunnel without ACME email", {**TUNNEL_VALUES, "acme_email": ""}, True),
        ("tunnel on one hostname", {**TUNNEL_VALUES,
                                    "authentik_external_url": "https://notes.example.test"}, True),
        ("tunnel over HTTP lab", {**TUNNEL_VALUES, "production_mode": False,
                                  "outline_url": "http://notes.example.test"}, True),
        ("tunnel with floating connector image",
         {**TUNNEL_VALUES, "cloudflared_image": "cloudflare/cloudflared:latest"}, True),
        # Cloudflare Access as the identity provider (no Authentik)
        ("valid cloudflare login", CLOUDFLARE_AUTH_VALUES, False),
        ("cloudflare login without tunnel", {**CLOUDFLARE_AUTH_VALUES, "cloudflare_tunnel_enabled": False}, True),
        ("cloudflare login without client id", {**CLOUDFLARE_AUTH_VALUES,
                                                "cloudflare_access_oidc_client_id": ""}, True),
        ("cloudflare login with placeholder secret",
         {**CLOUDFLARE_AUTH_VALUES, "cloudflare_access_oidc_client_secret": "CHANGE_ME_" * 5}, True),
        ("cloudflare login ignores Authentik placeholders",
         {**CLOUDFLARE_AUTH_VALUES, "authentik_secret_key": "CHANGE_ME", "outline_oidc_client_id": "CHANGE_ME",
          "authentik_image": "ghcr.io/goauthentik/server:latest"}, False),
        ("unknown auth mode", {"auth_mode": "google"}, True),
        ("firewall with bad SSH source", {"firewall_enabled": True, "firewall_ssh_source": "; rm -rf /"}, True),
        ("firewall with CIDR SSH source", {"firewall_enabled": True, "firewall_ssh_source": "100.64.0.0/10"}, False),
    ]

    render_tasks = [task for task in site["tasks"] if "ansible.builtin.template" in task]
    for task in render_tasks:
        template = task["ansible.builtin.template"]
        src = template["src"]
        if "compose" in src or src.endswith(".env.j2") or "credentials" in src:
            assert task.get("no_log") is True and task.get("diff") is False, task["name"]
            if "credentials" in src:
                assert template["mode"] == "0400", task["name"]
            else:
                assert template["mode"] == "0600", task["name"]
                assert template["owner"] == template["group"] == "root", task["name"]

    with tempfile.TemporaryDirectory(prefix="ansible-security-") as directory:
        temp = Path(directory)
        plays = []
        rendered = {}
        for index, (name, overrides, should_reject) in enumerate(scenarios):
            case_vars = {**values, **overrides}
            tasks = [
                {"ansible.builtin.set_fact": {"configuration_rejected": False}},
                {"block": copy.deepcopy(site["pre_tasks"]),
                 "rescue": [{"ansible.builtin.set_fact": {"configuration_rejected": True}}]},
                {"name": "Check expected rejection: " + name,
                 "ansible.builtin.assert": {
                     "that": ["configuration_rejected == " + str(should_reject)]}},
            ]
            if not should_reject:
                case = temp / str(index)
                for stack in ("outline", "authentik", "edge/cloudflared", "edge/caddy"):
                    (case / stack).mkdir(parents=True)
                case_vars.update(stack_root=str(case), outline_dir=str(case / "outline"),
                                 authentik_dir=str(case / "authentik"), edge_dir=str(case / "edge"))
                for original in render_tasks:
                    task = copy.deepcopy(original)
                    options = task["ansible.builtin.template"]
                    options["src"] = str(ROOT / options["src"])
                    # Tests run as the local user; ownership is checked above.
                    options.pop("owner", None)
                    options.pop("group", None)
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
            tunnel = bool(case_vars["cloudflare_tunnel_enabled"])
            authentik = case_vars["auth_mode"] == "authentik"
            assert (case / "authentik" / "docker-compose.yml").exists() == authentik, name
            for stack in ("outline", "authentik") if authentik else ("outline",):
                config_path = case / stack / "docker-compose.yml"
                assert config_path.stat().st_mode & 0o777 == 0o600
                compose = yaml.safe_load(config_path.read_text())
                services = compose["services"]
                app = services["outline" if stack == "outline" else "authentik-server"]
                assert "ak_redis" not in services, "authentik 2025.10+ does not use Redis"
                for service, config in services.items():
                    for port in config.get("ports", []):
                        assert port.startswith("127.0.0.1:"), (name, service, port)
                    if service in ("postgres", "redis", "ak_postgres"):
                        assert not config.get("ports"), (name, service)
                    assert "/var/run/docker.sock" not in str(config.get("volumes", [])), (name, service)
                if tunnel:
                    # Tunnel mode: the apps are reachable only on the private edge network.
                    assert "ports" not in app, (name, stack)
                    assert "edge" in app["networks"], (name, stack)
                    assert compose["networks"]["edge"] == {"external": True,
                                                           "name": case_vars["edge_network"]}
                else:
                    assert app["ports"] == ["127.0.0.1:3000:3000" if stack == "outline"
                                            else "127.0.0.1:9000:9000"], (name, stack)
                    assert "networks" not in compose
                if stack == "outline":
                    assert ("mailhog" in services) == case_vars["mailhog_enabled"]
                    if "mailhog" in services:
                        assert services["mailhog"]["ports"] == ["127.0.0.1:8025:8025"]
            env_path = case / "outline" / "docker.env"
            assert env_path.stat().st_mode & 0o777 == 0o600
            entries = dict(line.split("=", 1) for line in env_path.read_text().splitlines()
                           if line and not line.startswith("#"))
            assert entries["FORCE_HTTPS"] == str(case_vars["outline_url"].startswith("https:")).lower()
            assert json.loads(entries["SMTP_PASSWORD"]).replace("$$", "$") == values["outline_smtp_password"]
            assert "OIDC_DISCOVERY_URL" not in entries  # Outline reads OIDC_ISSUER_URL only
            assert json.loads(entries["APP_NAME"]) == case_vars["outline_app_name"]
            if authentik:
                assert entries["OIDC_ISSUER_URL"] == case_vars["authentik_external_url"] + "/application/o/outline/"
                assert json.loads(entries["OIDC_USERNAME_CLAIM"]) == "preferred_username"
            else:
                assert entries["OIDC_ISSUER_URL"] == (
                    "https://example-team.cloudflareaccess.com/cdn-cgi/access/sso/oidc/" + "c" * 32)
                assert json.loads(entries["OIDC_CLIENT_ID"]) == "c" * 32
                assert json.loads(entries["OIDC_CLIENT_SECRET"]) == "s" * 64
                assert json.loads(entries["OIDC_USERNAME_CLAIM"]) == "email"
                assert "OIDC_LOGOUT_URI" not in entries
                assert "authentik" not in env_path.read_text().lower()

            edge = case / "edge"
            if not tunnel:
                assert not (edge / "docker-compose.yml").exists(), name
                continue
            assert (edge / "docker-compose.yml").stat().st_mode & 0o777 == 0o600
            edge_compose = yaml.safe_load((edge / "docker-compose.yml").read_text())
            for service in edge_compose["services"].values():
                assert "ports" not in service, (name, "edge publishes a port")
                assert "no-new-privileges:true" in service["security_opt"]
            assert edge_compose["services"]["cloudflared"]["read_only"] is True
            assert ("caddy" in edge_compose["services"]) == authentik, name
            assert (edge / "Caddyfile").exists() == authentik, name
            if authentik:
                assert sorted(edge_compose["services"]["caddy"]["networks"]["edge"]["aliases"]) == [
                    "auth.example.test", "notes.example.test"]
                assert edge_compose["services"]["caddy"]["environment"]["CLOUDFLARE_API_TOKEN"] == \
                    case_vars["cloudflare_dns_api_token"]

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
            hosts = {}
            for rule in ingress[:-1]:
                access = rule["originRequest"]["access"]
                assert access["required"] is True, rule
                assert access["teamName"] == case_vars["cloudflare_access_team_name"]
                if authentik:
                    assert rule["service"] == "https://caddy:443"
                    assert rule["originRequest"]["originServerName"] == rule["hostname"]
                else:
                    assert rule["service"] == "http://outline:3000"
                hosts[rule["hostname"]] = access["audTag"]
            expected_hosts = {"notes.example.test": [case_vars["cloudflare_access_outline_aud"]]}
            if authentik:
                expected_hosts["auth.example.test"] = [case_vars["cloudflare_access_authentik_aud"]]
            assert hosts == expected_hosts, (name, hosts)
            if not authentik:
                continue

            caddyfile = (edge / "Caddyfile").read_text()
            assert "admin off" in caddyfile
            assert "dns cloudflare {env.CLOUDFLARE_API_TOKEN}" in caddyfile
            assert case_vars["cloudflare_dns_api_token"] not in caddyfile
            assert "\nauth.example.test {" in caddyfile and "\nnotes.example.test {" in caddyfile
            assert "reverse_proxy authentik-server:9000" in caddyfile
            assert "reverse_proxy outline:3000" in caddyfile

        print(f"PASS: {len(scenarios)} validation scenarios; lab/production, Authentik and Cloudflare-login rendering; "
              "loopback-or-no host ports, no database/SMTP publishing, Access enforced on every tunnel "
              "hostname with a 404 catch-all, secret-file permissions, and HTTPS settings.")
        print("No Docker containers, remote hosts, DNS records or Cloudflare settings were changed.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Deploy a standalone Zitadel identity provider for EOS, using only Docker.

Generates secrets into ``.env``, brings up the docker/zitadel stack, then provisions the EOS
org, project, roles, apps, and service user via a one-shot container, and writes
``eos-instance.env`` with the credentials each EOS instance needs. With ``--issuer`` and
``--admin-pat`` it provisions an existing Zitadel instead of deploying one. Re-running is safe;
every step is idempotent.

Requires Docker and a system ``python3`` (standard library only, no EOS install).

    python3 deploy.py --url https://eos-auth.lab.internal --tls-mode internal
    python3 deploy.py --issuer https://auth.example.org --admin-pat <PAT>
"""

import argparse
import os
import secrets
import string
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from typing import NoReturn

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
ENV_PATH = SCRIPT_DIR / ".env"
ENV_EXAMPLE = SCRIPT_DIR / ".env.example"
OUT_PATH = SCRIPT_DIR / "eos-instance.env"
CA_PATH = SCRIPT_DIR / "caddy-root.crt"
BOOTSTRAP_MODULE = REPO_ROOT / "eos" / "auth" / "zitadel_bootstrap.py"
RUNNER = SCRIPT_DIR / "bootstrap.py"
PYTHON_IMAGE = "python:3.12-slim"


def _ok(message: str) -> None:
    print(f"  \033[32m✓\033[0m {message}")


def _fail(message: str) -> NoReturn:
    print(f"\033[31mError:\033[0m {message}", file=sys.stderr)
    raise SystemExit(1)


def _random_string(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _complex_password() -> str:
    """A password satisfying Zitadel's default complexity policy."""
    return _random_string(14) + "!1Aa"


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _update_env(path: Path, values: dict[str, str]) -> None:
    """Set KEY=value in the dotenv file, preserving comments and order; append any missing keys."""
    remaining = dict(values)
    lines = path.read_text().splitlines() if path.exists() else []
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
                continue
        out.append(line)
    out.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(out) + "\n")


def _docker(args: list[str], project: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "COMPOSE_PROJECT_NAME": project}
    return subprocess.run(["docker", *args], cwd=SCRIPT_DIR, env=env, check=check)


def _preflight() -> None:
    if subprocess.run(["docker", "info"], capture_output=True, check=False).returncode != 0:
        _fail("Docker is not available. Install Docker and ensure the daemon is running.")
    if not BOOTSTRAP_MODULE.exists():
        _fail(f"{BOOTSTRAP_MODULE} not found. Run this from inside a cloned EOS repository.")
    _ok("docker found")


def _prepare_env(args: argparse.Namespace) -> tuple[str, str]:
    """Create/fill .env and return the external issuer and the chosen compose project name."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text(ENV_EXAMPLE.read_text())
    current = _read_env(ENV_PATH)

    issuer = (args.url or current.get("EOS_AUTH_ISSUER") or "https://localhost").rstrip("/")
    origin = urlsplit(issuer)
    scheme = origin.scheme or "https"
    domain = origin.hostname or "localhost"
    external_port = str(origin.port or (443 if scheme == "https" else 80))
    tls_mode = args.tls_mode or current.get("ZITADEL_TLS_MODE") or ("none" if scheme == "http" else "internal")
    # The two published ports must never collide; without TLS nothing listens on the https one.
    http_port, https_port = (external_port, "8443") if tls_mode == "none" else ("80", external_port)

    _update_env(
        ENV_PATH,
        {
            "EOS_AUTH_ISSUER": issuer,
            "ZITADEL_TLS_MODE": tls_mode,
            # Reuse existing secrets; the masterkey in particular can never change once initialized.
            "ZITADEL_MASTERKEY": current.get("ZITADEL_MASTERKEY") or _random_string(32),
            "ZITADEL_DB_PASSWORD": current.get("ZITADEL_DB_PASSWORD") or _random_string(20),
            "ZITADEL_ADMIN_PASSWORD": current.get("ZITADEL_ADMIN_PASSWORD") or _complex_password(),
            # Derived from EOS_AUTH_ISSUER for the compose stack
            "ZITADEL_PUBLIC_SCHEME": scheme,
            "ZITADEL_DOMAIN": domain,
            "ZITADEL_EXTERNAL_PORT": external_port,
            "ZITADEL_EXTERNAL_SECURE": "true" if scheme == "https" else "false",
            "ZITADEL_HTTP_PORT": http_port,
            "ZITADEL_HTTPS_PORT": https_port,
            "ZITADEL_ACME_EMAIL": args.acme_email or current.get("ZITADEL_ACME_EMAIL") or "",
        },
    )
    _ok(f"wrote .env (TLS mode {tls_mode}, issuer {issuer})")
    return issuer, args.project_name


def _read_bootstrap_pat(project: str, timeout_s: int = 180) -> str:
    """Poll the shared volume until Zitadel has written the instance-admin bootstrap PAT."""
    volume = f"{project}_zitadel_bootstrap"
    cmd = ["docker", "run", "--rm", "-v", f"{volume}:/b:ro", "alpine", "cat", "/b/admin-sa.pat"]
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        token = result.stdout.strip()
        if result.returncode == 0 and token:
            return token
        time.sleep(2)
    _fail(f"timed out reading the bootstrap PAT from volume '{volume}' (check 'docker logs eos-zitadel')")


def _run_bootstrap(issuer: str, ui_url: str, admin_pat: str, base_url: str, network: str | None, relax: str) -> None:
    """Provision EOS objects from a one-shot python container that reaches Zitadel at base_url."""
    chown = ""
    if hasattr(os, "getuid"):
        chown = f" && chown {os.getuid()}:{os.getgid()} /out/eos-instance.env"
    inner = f"pip install -q --disable-pip-version-check httpx && python bootstrap.py{chown}"
    network_args = ["--network", network] if network else []
    cmd = [
        "docker",
        "run",
        "--rm",
        *network_args,
        "-e",
        f"RELAX_PASSWORD_POLICY={relax}",
        "-e",
        f"BOOTSTRAP_BASE_URL={base_url}",
        "-e",
        f"EOS_ISSUER={issuer}",
        "-e",
        f"EOS_UI_URL={ui_url}",
        "-e",
        f"ADMIN_PAT={admin_pat}",
        "-v",
        f"{BOOTSTRAP_MODULE}:/app/zitadel_bootstrap.py:ro",
        "-v",
        f"{RUNNER}:/app/bootstrap.py:ro",
        "-v",
        f"{SCRIPT_DIR}:/out",
        "-w",
        "/app",
        PYTHON_IMAGE,
        "sh",
        "-c",
        inner,
    ]
    if subprocess.run(cmd, check=False).returncode != 0:
        _fail("Zitadel bootstrap failed; fix the issue above and re-run (it resumes safely).")


def _export_internal_ca(project: str) -> None:
    """Save Caddy's internal root CA so EOS services and browsers can trust the self-signed issuer."""
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--profile",
            "auth",
            "exec",
            "-T",
            "zitadel-proxy",
            "cat",
            "/data/caddy/pki/authorities/local/root.crt",
        ],
        cwd=SCRIPT_DIR,
        env={**os.environ, "COMPOSE_PROJECT_NAME": project},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("  ! could not export the internal CA; grab it from zitadel-proxy:/data/caddy/...", file=sys.stderr)
        return
    CA_PATH.write_text(result.stdout)
    _ok(f"exported internal CA to {CA_PATH}")
    print("    Trust it on EOS hosts (EOS_AUTH_CA_BUNDLE), the web UI (NODE_EXTRA_CA_CERTS), and browsers.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy a standalone Zitadel identity provider for EOS.")
    parser.add_argument("--url", help="Public origin Zitadel is served on (default: https://localhost)")
    parser.add_argument(
        "--tls-mode",
        choices=["none", "internal", "custom", "acme"],
        help="Proxy TLS: none | internal (self-signed) | custom (mounted cert) | acme "
        "(default: internal, or none for an http --url)",
    )
    parser.add_argument("--acme-email", help="Contact email for ACME when --tls-mode acme")
    parser.add_argument(
        "--ui-url",
        default="http://localhost:3000",
        help="EOS web UI URL to register as the OIDC redirect target (default: http://localhost:3000)",
    )
    parser.add_argument("--project-name", default="eos-zitadel", help="Docker compose project name")
    parser.add_argument("--issuer", help="Provision an existing Zitadel at this URL instead of deploying one")
    parser.add_argument("--admin-pat", help="Instance-admin PAT for --issuer (skips the Docker deploy)")
    parser.add_argument("--relax-password-policy", action="store_true", help="Drop Zitadel password complexity rules")
    args = parser.parse_args()

    ui_url = args.ui_url.rstrip("/")
    _preflight()

    if args.admin_pat:
        if not args.issuer:
            _fail("--issuer is required with --admin-pat")
        issuer = args.issuer.rstrip("/")
        print(f"Provisioning EOS in existing Zitadel at {issuer}...")
        _run_bootstrap(issuer, ui_url, args.admin_pat, issuer, None, str(args.relax_password_policy).lower())
    else:
        print("Deploying standalone Zitadel for EOS\n")
        issuer, project = _prepare_env(args)
        relax = str(args.relax_password_policy).lower()
        print("\nStarting Zitadel...")
        _docker(["compose", "--profile", "auth", "up", "-d"], project)
        print("\nWaiting for Zitadel and provisioning EOS...")
        admin_pat = _read_bootstrap_pat(project)
        _ok("read bootstrap admin PAT")
        _run_bootstrap(issuer, ui_url, admin_pat, "http://zitadel-proxy:8080", f"{project}_default", relax)
        if _read_env(ENV_PATH).get("ZITADEL_TLS_MODE") == "internal":
            _export_internal_ca(project)

    print(f"\n\033[32mDone.\033[0m Credentials written to {OUT_PATH.name}:\n")
    print(OUT_PATH.read_text())
    print("Copy each block into the matching file on every EOS instance that uses this provider,")
    print("then create your account:  eos auth create-user <username> <email> --superuser")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#! /usr/bin/env python3

import ipaddress
import json
import re
import subprocess
from pathlib import Path
from typing import Any, List, Optional

from pydantic import BaseModel, validator
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi_versioning import VersionedFastAPI, version
from fastapi.staticfiles import StaticFiles
from loguru import logger

SERVICE_NAME = "tailscalemanager"
SETTINGS_PATH = Path("/var/lib/tailscale/settings.json")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
IGNORED_INTERFACE_PREFIXES = ("lo", "docker", "veth", "br-", "tailscale")


class Settings(BaseModel):
    hostname: Optional[str] = None
    advertise_routes: List[str] = []
    ssh: bool = False

    @validator("hostname")
    def validate_hostname(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        if not HOSTNAME_RE.match(value):
            raise ValueError("hostname must contain only letters, digits and dashes (max 63 chars)")
        return value

    @validator("advertise_routes", each_item=True)
    def validate_route(cls, value: str) -> str:
        try:
            return str(ipaddress.ip_network(value.strip(), strict=False))
        except ValueError as e:
            raise ValueError(f"invalid CIDR '{value}': {e}")


class Login(BaseModel):
    auth_key: Optional[str] = None

    @validator("auth_key")
    def validate_auth_key(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = value.strip()
        if not value.startswith("tskey-") or any(c.isspace() for c in value):
            raise ValueError("auth key must start with 'tskey-'")
        return value


app = FastAPI(
    title="TailscaleManager API",
    description="TailscaleManager is an extension to provide Tailscale connectivity to BlueOS",
)
logger.info("Starting TailscaleManager!")

# Background 'tailscale up' used for interactive login, kept so we don't spawn duplicates
login_process: Optional["subprocess.Popen[str]"] = None


def run_command(args: List[str], check: bool = True, timeout: Optional[float] = 15) -> "subprocess.CompletedProcess[str]":
    logger.debug(f"Running command: {redact(args)}")
    return subprocess.run(
        args,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def redact(args: List[str]) -> List[str]:
    return ["--auth-key=<redacted>" if arg.startswith("--auth-key=") else arg for arg in args]


def load_settings() -> Settings:
    try:
        return Settings(**json.loads(SETTINGS_PATH.read_text()))
    except Exception:
        return Settings()


def save_settings(settings: Settings) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(settings.json())


def tailscale_status() -> dict:
    output = run_command(["tailscale", "status", "--json"], check=False)
    try:
        return json.loads(output.stdout)
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, output.stderr or "tailscaled is not responding")


def set_ip_forwarding(enabled: bool) -> None:
    value = "1" if enabled else "0"
    run_command(["sysctl", "-w", f"net.ipv4.ip_forward={value}", f"net.ipv6.conf.all.forwarding={value}"], check=False)


def preference_flags(settings: Settings) -> List[str]:
    return [
        f"--hostname={settings.hostname or ''}",
        f"--advertise-routes={','.join(settings.advertise_routes)}",
        f"--ssh={str(settings.ssh).lower()}",
    ]


def summarize_peer(peer: dict) -> dict:
    return {
        "HostName": peer.get("HostName"),
        "DNSName": peer.get("DNSName"),
        "TailscaleIPs": peer.get("TailscaleIPs") or [],
        "OS": peer.get("OS"),
        "Online": peer.get("Online", False),
        "LastSeen": peer.get("LastSeen"),
        "PrimaryRoutes": peer.get("PrimaryRoutes") or [],
    }


@app.get("/status", status_code=status.HTTP_200_OK)
@version(1, 0)
def get_status() -> Any:
    data = tailscale_status()
    peers = sorted(
        (summarize_peer(peer) for peer in (data.get("Peer") or {}).values()),
        key=lambda peer: (not peer["Online"], (peer["HostName"] or "").lower()),
    )
    login_in_progress = login_process is not None and login_process.poll() is None
    return {
        "BackendState": data.get("BackendState"),
        # tailscaled keeps a stale AuthURL after logout, only show it while we're waiting on a login
        "AuthURL": data.get("AuthURL") if login_in_progress else "",
        "MagicDNSSuffix": data.get("MagicDNSSuffix"),
        "Health": data.get("Health") or [],
        "Self": summarize_peer(data["Self"]) if data.get("Self") else None,
        "Peers": peers,
        "LoginInProgress": login_in_progress,
    }


@app.post("/login", status_code=status.HTTP_200_OK)
@version(1, 0)
def login(body: Login) -> Any:
    global login_process
    settings = load_settings()
    args = ["tailscale", "up", "--reset", "--accept-dns=false", *preference_flags(settings)]

    if login_process is not None and login_process.poll() is None:
        login_process.terminate()
        login_process = None

    if body.auth_key:
        output = run_command([*args, f"--auth-key={body.auth_key}", "--timeout=30s"], check=False, timeout=45)
        if output.returncode != 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, output.stderr or output.stdout)
        return {"message": output.stdout or "Logged in"}

    # Interactive login blocks until approved; run it in the background and let
    # the UI pick up the AuthURL from /status
    logger.debug(f"Starting interactive login: {args}")
    login_process = subprocess.Popen(args, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"message": "Login started"}


@app.post("/logout", status_code=status.HTTP_200_OK)
@version(1, 0)
def logout() -> Any:
    global login_process
    if login_process is not None and login_process.poll() is None:
        login_process.terminate()
        login_process = None
    output = run_command(["tailscale", "logout"], check=False)
    if output.returncode != 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, output.stderr or output.stdout)
    return {"message": "Logged out"}


@app.get("/settings", status_code=status.HTTP_200_OK)
@version(1, 0)
def read_settings() -> Any:
    return load_settings()


@app.post("/settings", status_code=status.HTTP_200_OK)
@version(1, 0)
def write_settings(settings: Settings) -> Any:
    save_settings(settings)
    set_ip_forwarding(bool(settings.advertise_routes))
    if tailscale_status().get("BackendState") == "Running":
        output = run_command(["tailscale", "set", *preference_flags(settings)], check=False)
        if output.returncode != 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, output.stderr or output.stdout)
    return settings


@app.get("/subnets", status_code=status.HTTP_200_OK)
@version(1, 0)
def local_subnets() -> Any:
    output = run_command(["ip", "-j", "-4", "addr"], check=False)
    try:
        interfaces = json.loads(output.stdout)
    except json.JSONDecodeError:
        return []
    subnets = []
    for interface in interfaces:
        name = interface.get("ifname", "")
        if name.startswith(IGNORED_INTERFACE_PREFIXES):
            continue
        for addr in interface.get("addr_info", []):
            network = ipaddress.ip_network(f"{addr['local']}/{addr['prefixlen']}", strict=False)
            if network.prefixlen < 32 and not network.is_link_local:
                subnets.append({"interface": name, "subnet": str(network)})
    return subnets


app = VersionedFastAPI(app, version="1.0.0", prefix_format="/v{major}.{minor}", enable_latest=True)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    # Running uvicorn with log disabled so loguru can handle it
    uvicorn.run(app, host="0.0.0.0", port=9132, log_config=None)

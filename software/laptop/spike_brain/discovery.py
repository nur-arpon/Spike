"""Finding and pairing with the brain on the owner's Wi-Fi (PROTOCOL.md section 10, v1.2).

- The pairing token: SPIKE_TOKEN from .env when the owner set one, otherwise a random token
  the brain makes once and keeps in data/pairing_token.txt (git-ignored, this laptop only).
- The pairing link the app's QR scanner reads:
      spike://pair?host=<LAN IP>&port=<port>&token=<token>&name=<Spike>
  shown as a QR in the console (`python -m spike_brain --pair`) and saved as data/pairing_qr.png.
- An mDNS / DNS-SD advert `_spike._tcp` (python-zeroconf) while the brain listens on the LAN,
  so the app lists "Spike" by itself. The TXT record never contains the token.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlencode

from . import __version__

log = logging.getLogger("spike.lan")

SERVICE_TYPE = "_spike._tcp.local."
PROTOCOL_MINOR = "1.2"
TOKEN_FILE = "data/pairing_token.txt"
QR_FILE = "data/pairing_qr.png"


# ---------------------------------------------------------------- token
def load_or_create_token(path: Path) -> str:
    """The brain's own pairing token (made once, then reused so paired phones keep working)."""
    try:
        tok = path.read_text(encoding="utf-8").strip()
        if len(tok) >= 16:
            return tok
    except OSError:
        pass
    tok = secrets.token_urlsafe(24)                       # 32 URL-safe characters, 192 bits
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tok + "\n", encoding="utf-8")
    log.info("made a new pairing token (kept in %s)", path)
    return tok


def resolve_token(settings, lan: bool) -> str | None:
    """SPIKE_TOKEN from .env wins. On the LAN without one, the brain's own token file is used,
    so "listen on Wi-Fi" works without editing .env first. Loopback only: no token."""
    tok = settings.secret("SPIKE_TOKEN")
    if tok or not lan:
        return tok
    return load_or_create_token(settings.path(TOKEN_FILE))


# ---------------------------------------------------------------- addresses
def lan_ip() -> str | None:
    """The laptop's address on its main network (the one with the default route).
    A UDP "connect" sends nothing; it only asks Windows which interface it would use."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))                        # TEST-NET-1: never actually contacted
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") or ip == "0.0.0.0" else ip
    except OSError:
        return None
    finally:
        s.close()


def parse_tailscale_status(text: str) -> tuple[str | None, str | None]:
    """(100.x.y.z, MagicDNS name) of this laptop from `tailscale status --json`, or Nones
    when Tailscale is not running / not signed in."""
    try:
        st = json.loads(text)
    except (ValueError, TypeError):
        return None, None
    if not isinstance(st, dict) or st.get("BackendState") != "Running":
        return None, None
    me = st.get("Self") or {}
    ips = [ip for ip in (me.get("TailscaleIPs") or []) if isinstance(ip, str) and "." in ip]
    dns = me.get("DNSName")
    dns = dns.rstrip(".") if isinstance(dns, str) and dns.strip(".") else None
    return (ips[0] if ips else None), dns


def _tailscale_exe() -> str | None:
    exe = shutil.which("tailscale")
    if exe:
        return exe
    default = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale" / "tailscale.exe"
    return str(default) if default.exists() else None


def tailscale_addrs(timeout_s: float = 3.0) -> tuple[str | None, str | None]:
    """The laptop's Tailscale address and name, so the app can reach the brain from any
    network (the owner's own tailnet). Read-only: it only asks `tailscale status --json`;
    it never signs in, changes Tailscale or touches the firewall. Nones without Tailscale."""
    exe = _tailscale_exe()
    if not exe:
        return None, None
    try:
        r = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=timeout_s,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None, None
    return parse_tailscale_status(r.stdout) if r.returncode == 0 else (None, None)


def pairing_url(host: str, port: int, token: str | None, name: str = "Spike",
                ts: str | None = None, ts_name: str | None = None) -> str:
    """`ts` / `tsname`: the Tailscale address and MagicDNS name (PROTOCOL.md 10.7). The app tries
    `host` (home Wi-Fi) first, then these, with the same token."""
    q = {"host": host, "port": str(port)}
    if token:
        q["token"] = token
    if ts:
        q["ts"] = ts
    if ts_name:
        q["tsname"] = ts_name
    q["name"] = name
    return "spike://pair?" + urlencode(q)


def qr_console(url: str) -> str:
    """The pairing QR drawn with text blocks (for the console window)."""
    import qrcode
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    rows = qr.get_matrix()
    out = []
    for y in range(0, len(rows), 2):                       # two QR rows per text line
        top, bot = rows[y], rows[y + 1] if y + 1 < len(rows) else [False] * len(rows[y])
        out.append("".join(" " if (t and b) else ("▄" if t else ("▀" if b else "█"))
                           for t, b in zip(top, bot)))
    return "\n".join(out)


def save_qr_png(url: str, path: Path) -> Path:
    import qrcode
    img = qrcode.make(url, border=3, box_size=12)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))
    return path


# ---------------------------------------------------------------- mDNS advert
class Advertiser:
    """Announces `_spike._tcp` on the LAN (only on the main network's address, so the phone is
    not offered a VPN or virtual-adapter address) and follows the laptop to a new address."""

    def __init__(self, port: int, name: str = "Spike", token_required: bool = True,
                 check_every_s: float = 30.0):
        self.port = port
        self.name = name
        self.token_required = token_required
        self.check_every_s = check_every_s
        self.ip: str | None = None
        self._azc = None
        self._info = None
        self._task: asyncio.Task | None = None

    def _service_info(self, ip: str):
        from zeroconf import ServiceInfo
        host = socket.gethostname().split(".")[0] or "laptop"
        props = {"name": self.name, "v": "1", "pv": PROTOCOL_MINOR, "ver": __version__,
                 "token": "1" if self.token_required else "0", "host": host}
        return ServiceInfo(SERVICE_TYPE, f"{self.name} on {host}.{SERVICE_TYPE}",
                           addresses=[socket.inet_aton(ip)], port=self.port, properties=props,
                           server=f"{host.lower()}-spike.local.")

    async def start(self) -> bool:
        ip = lan_ip()
        if ip is None:
            log.warning("no network address found; Spike is not announced on Wi-Fi (the app can still "
                        "use a typed address or the QR)")
            self._task = asyncio.create_task(self._follow(), name="mdns-follow")
            return False
        await self._register(ip)
        self._task = asyncio.create_task(self._follow(), name="mdns-follow")
        return self._info is not None

    async def _register(self, ip: str) -> None:
        try:
            from zeroconf import IPVersion
            from zeroconf.asyncio import AsyncZeroconf
            if self._azc is None:
                self._azc = AsyncZeroconf(interfaces=[ip], ip_version=IPVersion.V4Only)
            info = self._service_info(ip)
            await self._azc.async_register_service(info, allow_name_change=True)
            self._info, self.ip = info, ip
            log.info("announced on Wi-Fi as '%s' (%s:%d, mDNS %s)", self.name, ip, self.port, SERVICE_TYPE)
        except Exception as e:  # noqa: BLE001 - discovery is a convenience, never fatal
            log.warning("could not announce Spike on Wi-Fi (%s); the QR and typed addresses still work", e)
            await self._close_zc()

    async def _follow(self) -> None:
        """Re-announce when the laptop's address changes (another Wi-Fi, a new DHCP lease)."""
        while True:
            await asyncio.sleep(self.check_every_s)
            ip = lan_ip()
            if ip and ip != self.ip:
                log.info("network address changed %s -> %s: announcing again", self.ip, ip)
                await self._unregister()
                await self._close_zc()
                await self._register(ip)

    async def _unregister(self) -> None:
        if self._azc is not None and self._info is not None:
            try:
                await asyncio.wait_for(self._azc.async_unregister_service(self._info), 3)
            except Exception:  # noqa: BLE001
                pass
        self._info = None

    async def _close_zc(self) -> None:
        if self._azc is not None:
            try:
                await asyncio.wait_for(self._azc.async_close(), 3)
            except Exception:  # noqa: BLE001
                pass
        self._azc = None

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await self._unregister()
        await self._close_zc()

"""The protocol server: the brain side of PROTOCOL.md.

Many clients at once (simulator, screen board, camera board, test tools),
hello handshake with optional pairing token, per-client ordered send queue,
app-level heartbeats, invalid-message rate limiting, and a same-machine
origin check so a random web page cannot drive Spike.
"""
from __future__ import annotations

import asyncio
import collections
import hmac
import ipaddress
import logging
import select
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from . import __version__
from . import protocol as P

log = logging.getLogger("spike.server")

OnMessage = Callable[["Client", dict], Awaitable[None]]
OnClient = Callable[["Client"], Awaitable[None]]

_LOCAL_ORIGINS = ("null", "file://")
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")


def origin_allowed(origin: str | None) -> bool:
    """Non-browser clients send no Origin. Browsers: only file:// or a local page."""
    if origin is None:
        return True
    o = origin.strip().lower()
    if o in _LOCAL_ORIGINS or o.startswith("file://"):
        return True
    for scheme in ("http://", "https://"):
        if o.startswith(scheme):
            host = o[len(scheme):].split("/")[0]
            host = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
            return host in _LOCAL_HOSTS
    return False


def is_loopback(host: str) -> bool:
    if host in ("localhost", ""):
        return host == "localhost"
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def port_in_use(port: int, hosts: tuple[str, ...] = ("127.0.0.1", "::1"), timeout: float = 0.25) -> bool:
    """Is another program listening on `port` on either loopback address?

    A successful bind proves nothing on Windows: it lets us bind 127.0.0.1:P
    right next to another program's wildcard [::]:P (even with
    SO_EXCLUSIVEADDRUSE, when that program used SO_REUSEADDR, as Python's
    http.server does). Browsers that resolve "localhost" to ::1 would then
    reach the other program. Only a connection attempt tells the truth.
    Both addresses are probed in parallel; a closed port on Windows answers
    slowly (it retries the RST), so no answer within `timeout` means free.
    """
    socks = []
    for h in hosts:
        try:
            s = socket.socket(socket.AF_INET6 if ":" in h else socket.AF_INET, socket.SOCK_STREAM)
        except OSError:
            continue                                   # no IPv6 on this machine
        s.setblocking(False)
        try:
            s.connect_ex((h, port))
        except OSError:
            s.close()
            continue
        socks.append(s)
    try:
        pending = list(socks)
        deadline = time.monotonic() + timeout
        while pending:
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            _, writable, failed = select.select([], pending, pending, left)
            for s in writable:
                if s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
                    return True                       # someone accepted the connection
            for s in set(writable) | set(failed):
                if s in pending:
                    pending.remove(s)
        return False
    finally:
        for s in socks:
            s.close()


def listen_socket(host: str, port: int) -> socket.socket:
    """A listening socket nobody else can share (SO_EXCLUSIVEADDRUSE on Windows)."""
    host = "127.0.0.1" if host == "localhost" else host
    s = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # POSIX: only skips TIME_WAIT
        s.bind((host, port))
        s.listen(128)
        s.setblocking(False)
        return s
    except OSError:
        s.close()
        raise


class PortBusy(OSError):
    """The protocol port (and, on loopback, the next few) belong to another program."""


@dataclass(eq=False)
class Client:
    """One connected robot board, simulator or tool."""
    conn_id: int
    ws: ServerConnection
    role: str = "tool"
    device_id: str = ""
    fw: str = ""
    caps: set[str] = field(default_factory=set)
    audio_rates: list[int] = field(default_factory=list)
    audio_format: str = ""          # v1.5: what a phone with cap `audio_out` gets (ogg_opus / pcm_s16le)
    phone_voice: bool = False       # v1.7: the phone voices its replies itself (text only, no synthesis here)
    ids: P.IdCounter = field(default_factory=P.IdCounter)
    last_seen: float = field(default_factory=time.monotonic)
    connected_at: float = field(default_factory=time.monotonic)
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    bad: collections.deque = field(default_factory=lambda: collections.deque(maxlen=21))

    def has(self, cap: str) -> bool:
        return cap in self.caps

    @property
    def label(self) -> str:
        return f"{self.role}#{self.conn_id}({self.device_id or '?'})"


class BrainServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, *, heartbeat_s: float = 5.0,
                 hello_timeout_s: float = 5.0, token: str | None = None,
                 max_message_bytes: int = 256 * 1024,
                 on_message: OnMessage | None = None, on_connect: OnClient | None = None,
                 on_disconnect: OnClient | None = None,
                 welcome: Callable[[Client], dict] | None = None, port_fallback: int = 10,
                 trust_loopback: bool = False):
        self.host, self.port = host, port
        self.requested_port = port
        # on loopback, try up to this many following ports if ours is taken;
        # a robot on Wi-Fi has the port in its firmware, so LAN mode never moves
        self.port_fallback = port_fallback if is_loopback(host) else 0
        self.heartbeat_s = heartbeat_s
        self.hello_timeout_s = hello_timeout_s
        self.token = token
        self.trust_loopback = trust_loopback     # v1.2: same-laptop clients need no token
        self.max_message_bytes = max_message_bytes
        self.on_message = on_message
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.welcome = welcome or (lambda c: {})
        self.clients: dict[int, Client] = {}
        self._next_conn = 0
        self._server = None
        self._hb_task: asyncio.Task | None = None
        if not is_loopback(host) and not token:
            raise ValueError("a pairing token (SPIKE_TOKEN in .env) is required when the "
                             f"server listens on a network address ({host})")

    # ------------------------------------------------------------------ life
    def _claim_port(self) -> socket.socket:
        """Bind our port exclusively, after checking nobody listens on it on
        127.0.0.1 or ::1. On loopback, move to the next free port if needed."""
        first = self.requested_port
        candidates = [first] if first == 0 else list(range(first, first + 1 + self.port_fallback))
        reasons = []
        for p in candidates:
            if p and port_in_use(p):
                reasons.append(f"{p} (another program is listening on it)")
                continue
            try:
                return listen_socket(self.host, p)
            except OSError as e:
                reasons.append(f"{p} ({e.strerror or e})")
        raise PortBusy(f"cannot use port {', '.join(reasons)}. Close the other program or start with "
                       f"--port <free port>.")

    async def start(self) -> None:
        sock = self._claim_port()
        self.port = sock.getsockname()[1]
        if self.requested_port and self.port != self.requested_port:
            log.warning("port %d is used by another program, so Spike is using port %d instead",
                        self.requested_port, self.port)
        self._server = await serve(self._handle, sock=sock,
                                   max_size=self.max_message_bytes,
                                   ping_interval=self.heartbeat_s * 2, ping_timeout=self.heartbeat_s * 4,
                                   compression=None)
        self._hb_task = asyncio.create_task(self._heartbeat(), name="heartbeat")
        shown = "127.0.0.1" if self.host == "localhost" else self.host
        log.info("protocol server listening on ws://%s:%d/", shown, self.port)

    @property
    def local_url(self) -> str:
        """The URL a simulator on this laptop should use. Always 127.0.0.1, never
        "localhost" (a browser may resolve that to ::1, where another program may listen)."""
        return f"ws://127.0.0.1:{self.port}"

    async def stop(self) -> None:
        if self._hb_task:
            self._hb_task.cancel()
        for c in list(self.clients.values()):
            try:
                await c.ws.close(P.CLOSE_GOING_AWAY, "brain shutting down")
            except Exception:  # noqa: BLE001 - already gone is fine
                pass
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # ------------------------------------------------------------------ sending
    def send(self, client: Client, type_: str, re: int | None = None, **fields: Any) -> int:
        """Queue a message for one client; returns its id. Never blocks."""
        msg_id = client.ids.next()
        client.queue.put_nowait(P.encode(P.make(type_, msg_id, re=re, **fields)))
        return msg_id

    def broadcast(self, type_: str, cap: str | None = None, **fields: Any) -> int:
        """Send to every client (with `cap`, if given). Returns how many got it."""
        n = 0
        for c in list(self.clients.values()):
            if cap is None or c.has(cap):
                self.send(c, type_, **fields)
                n += 1
        return n

    def with_cap(self, cap: str) -> list[Client]:
        return [c for c in self.clients.values() if c.has(cap)]

    def has_cap(self, cap: str) -> bool:
        return any(c.has(cap) for c in self.clients.values())

    async def drain(self, timeout: float = 2.0) -> None:
        """Wait until every client's send queue is empty (tests, shutdown)."""
        end = time.monotonic() + timeout
        while any(not c.queue.empty() for c in self.clients.values()) and time.monotonic() < end:
            await asyncio.sleep(0.01)

    async def _writer(self, client: Client) -> None:
        try:
            while True:
                text = await client.queue.get()
                await client.ws.send(text)
        except (ConnectionClosed, asyncio.CancelledError):
            pass

    # ------------------------------------------------------------------ receiving
    async def _handle(self, ws: ServerConnection) -> None:
        origin = ws.request.headers.get("Origin") if ws.request else None
        if not origin_allowed(origin):
            log.warning("refused a connection from web origin %r", origin)
            await ws.close(P.CLOSE_AUTH, "origin not allowed")
            return
        self._next_conn += 1
        client = Client(conn_id=self._next_conn, ws=ws)
        if not await self._hello(client):
            return
        self.clients[client.conn_id] = client
        writer = asyncio.create_task(self._writer(client), name=f"writer-{client.conn_id}")
        log.info("connected: %s caps=%s", client.label, sorted(client.caps))
        try:
            if self.on_connect:
                await self.on_connect(client)
            async for raw in ws:
                client.last_seen = time.monotonic()
                await self._on_raw(client, raw)
        except ConnectionClosed:
            pass
        finally:
            self.clients.pop(client.conn_id, None)
            writer.cancel()
            log.info("disconnected: %s", client.label)
            if self.on_disconnect:
                try:
                    await self.on_disconnect(client)
                except Exception:  # noqa: BLE001
                    log.exception("on_disconnect failed")

    async def _hello(self, client: Client) -> bool:
        ws = client.ws
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=self.hello_timeout_s)
        except asyncio.TimeoutError:
            await ws.close(P.CLOSE_HELLO_TIMEOUT, "hello timeout")
            return False
        except ConnectionClosed:
            return False
        try:
            msg = P.decode(raw)
            if msg["type"] != "hello":
                raise P.ProtocolError("not_ready", "send hello first")
            P.validate(msg, "to_brain")
        except P.ProtocolError as e:
            await self._send_now(client, "error", re=_msg_id(raw), code=e.code, message=e.message)
            code = P.CLOSE_VERSION if e.code == "version_mismatch" else P.CLOSE_HELLO_TIMEOUT
            await ws.close(code, e.message[:100])
            return False
        # v1.2: a client on this laptop (the simulator, or a phone through `adb reverse`) needs no
        # token even when the brain also listens on the LAN: it could read the token file anyway.
        if self.token and not (self.trust_loopback and _peer_is_loopback(ws)) \
                and not hmac.compare_digest(str(msg.get("token", "")), self.token):
            await self._send_now(client, "error", re=msg.get("id"), code="auth", message="bad or missing token")
            await ws.close(P.CLOSE_AUTH, "bad token")
            return False
        client.role = msg["role"]
        client.device_id = msg["device_id"]
        client.fw = msg["fw"]
        client.caps = {c for c in msg["caps"] if isinstance(c, str)}
        ao = msg.get("audio_out") or {}
        client.audio_rates = [int(r) for r in ao.get("rates", []) if isinstance(r, (int, float))]
        if "audio_out" in client.caps:             # v1.5 (PROTOCOL.md 10.8): a phone that plays Spike's voice
            from .speech.stream_audio import choose_format
            fmts = ao.get("formats")
            client.audio_format = choose_format([f for f in fmts if isinstance(f, str)] if isinstance(fmts, list) else None)
            client.phone_voice = ao.get("voice") == "phone"      # v1.7 (PROTOCOL.md 10.10), also `voice_source`
        fields = {"server": "spike-brain", "version": __version__, "session": f"{client.conn_id:04x}",
                  "heartbeat_s": self.heartbeat_s}
        fields.update(self.welcome(client))
        fields.setdefault("mode", "dog")
        await self._send_now(client, "hello", re=msg.get("id"), **fields)
        return True

    async def _send_now(self, client: Client, type_: str, re: int | None = None, **fields: Any) -> None:
        try:
            await client.ws.send(P.encode(P.make(type_, client.ids.next(), re=re, **fields)))
        except ConnectionClosed:
            pass

    async def _on_raw(self, client: Client, raw: str | bytes) -> None:
        if isinstance(raw, (bytes, bytearray)):
            return                                  # v1: binary frames are ignored
        try:
            msg = P.decode(raw)
            P.validate(msg, "from_app" if client.role == "app" else "to_brain")
        except P.ProtocolError as e:
            self.send(client, "error", re=_msg_id(raw), code=e.code, message=e.message)
            now = time.monotonic()
            client.bad.append(now)
            if len(client.bad) > 20 and now - client.bad[0] < 10:
                log.warning("closing %s: too many invalid messages", client.label)
                await client.ws.close(P.CLOSE_ABUSE, "too many invalid messages")
            return
        t = msg["type"]
        if t == "ping":
            self.send(client, "pong", re=msg.get("id"))
            return
        if t in ("pong", "hello"):
            return
        if t == "error":
            log.warning("%s reported error %s: %s", client.label, msg.get("code"), msg.get("message"))
            return
        if self.on_message:
            try:
                await self.on_message(client, msg)
            except Exception:  # noqa: BLE001 - one bad handler must not kill the link
                log.exception("handler failed for %s from %s", t, client.label)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_s)
            now = time.monotonic()
            for c in list(self.clients.values()):
                if now - c.last_seen > 3 * self.heartbeat_s:
                    log.warning("%s silent for %.0f s, closing", c.label, now - c.last_seen)
                    asyncio.create_task(c.ws.close(P.CLOSE_NORMAL, "heartbeat timeout"))
                    continue
                self.send(c, "ping")


def _peer_is_loopback(ws: Any) -> bool:
    """Is the other end of this connection a program on this laptop?"""
    try:
        host = ws.remote_address[0]
    except (AttributeError, IndexError, TypeError):
        return False
    host = str(host)
    if host.startswith("::ffff:"):                 # IPv4-mapped IPv6
        host = host[7:]
    return is_loopback(host)


def _msg_id(raw: Any) -> int | None:
    """Best-effort id of a message we could not accept (for the error's `re`)."""
    try:
        import json
        m = json.loads(raw)
        i = m.get("id") if isinstance(m, dict) else None
        return i if isinstance(i, int) else None
    except Exception:  # noqa: BLE001
        return None

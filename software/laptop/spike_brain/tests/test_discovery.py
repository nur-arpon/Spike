"""Pairing token, pairing link / QR, and the mDNS advert (discovery.py, PROTOCOL.md 10.7)."""
import socket
from urllib.parse import parse_qs, urlparse

from spike_brain import discovery as D
from spike_brain.server import BrainServer


def test_token_is_made_once_and_kept(tmp_path):
    p = tmp_path / "data" / "pairing_token.txt"
    a = D.load_or_create_token(p)
    b = D.load_or_create_token(p)
    assert a == b and len(a) >= 32 and p.exists()


def test_env_token_wins_and_loopback_needs_none(settings, tmp_path):
    assert D.resolve_token(settings, lan=False) is None
    s = settings.override({})
    s.env["SPIKE_TOKEN"] = "a-real-long-owner-token-123"
    assert D.resolve_token(s, lan=True) == "a-real-long-owner-token-123"


def test_lan_mode_without_env_token_uses_token_file(settings, tmp_path):
    s = settings.override({})
    s.root = tmp_path                                  # data/ goes to the temp folder
    tok = D.resolve_token(s, lan=True)
    assert tok and (tmp_path / D.TOKEN_FILE).read_text().strip() == tok


def test_pairing_url_matches_the_app_parser_format():
    url = D.pairing_url("192.168.1.20", 8765, "abc_DEF-123", "Spike")
    u = urlparse(url)
    q = parse_qs(u.query)
    assert u.scheme == "spike" and u.netloc == "pair"
    assert q == {"host": ["192.168.1.20"], "port": ["8765"], "token": ["abc_DEF-123"], "name": ["Spike"]}
    assert "token" not in D.pairing_url("10.0.0.2", 8765, None)


def test_qr_console_and_png(tmp_path):
    url = D.pairing_url("192.168.1.20", 8765, "x" * 32)
    text = D.qr_console(url)
    lines = text.splitlines()
    assert len(lines) > 10 and len({len(ln) for ln in lines}) == 1
    png = D.save_qr_png(url, tmp_path / "qr.png")
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_lan_ip_is_not_loopback():
    ip = D.lan_ip()
    assert ip is None or not ip.startswith("127.")
    if ip:
        socket.inet_aton(ip)


def test_service_info_never_carries_the_token():
    adv = D.Advertiser(8765, name="Spike", token_required=True)
    info = adv._service_info("192.168.1.20")
    props = {k.decode(): (v.decode() if v else v) for k, v in info.properties.items()}
    assert info.type == D.SERVICE_TYPE and info.port == 8765
    assert props["name"] == "Spike" and props["token"] == "1" and props["v"] == "1" and props["pv"] == "1.2"
    assert all("secret" not in str(v) for v in props.values())
    assert socket.inet_ntoa(info.addresses[0]) == "192.168.1.20"


async def test_loopback_client_trusted_only_when_enabled():
    import json
    from websockets.asyncio.client import connect
    hello = {"v": 1, "type": "hello", "id": 1, "role": "simulator", "device_id": "s", "fw": "1", "caps": []}
    srv = BrainServer("127.0.0.1", 0, token="s3cret", trust_loopback=True)
    await srv.start()
    try:
        async with connect(f"ws://127.0.0.1:{srv.port}/") as ws:
            await ws.send(json.dumps(hello))                      # no token, same laptop
            assert json.loads(await ws.recv())["type"] == "hello"
    finally:
        await srv.stop()


def test_pairing_url_carries_the_tailscale_address_when_known():
    url = D.pairing_url("192.168.1.20", 8765, "tok", "Spike", ts="100.101.102.103", ts_name="laptop.tail1234.ts.net")
    q = parse_qs(urlparse(url).query)
    assert q["host"] == ["192.168.1.20"] and q["ts"] == ["100.101.102.103"]
    assert q["tsname"] == ["laptop.tail1234.ts.net"] and q["token"] == ["tok"]
    assert "ts" not in parse_qs(urlparse(D.pairing_url("192.168.1.20", 8765, "tok")).query)


def test_parse_tailscale_status():
    import json
    running = {"BackendState": "Running",
               "Self": {"TailscaleIPs": ["100.64.1.2", "fd7a:115c:a1e0::1"], "DNSName": "laptop.tail1234.ts.net."}}
    assert D.parse_tailscale_status(json.dumps(running)) == ("100.64.1.2", "laptop.tail1234.ts.net")
    stopped = dict(running, BackendState="Stopped")
    assert D.parse_tailscale_status(json.dumps(stopped)) == (None, None)       # signed out / off
    assert D.parse_tailscale_status("not json") == (None, None)
    assert D.parse_tailscale_status(json.dumps({"BackendState": "Running", "Self": {}})) == (None, None)


def test_tailscale_addrs_without_tailscale_is_quiet(monkeypatch):
    monkeypatch.setattr(D, "_tailscale_exe", lambda: None)
    assert D.tailscale_addrs() == (None, None)


def test_tailscale_addrs_only_reads_status(monkeypatch):
    import subprocess
    calls = []

    class R:
        returncode, stdout = 0, '{"BackendState":"Running","Self":{"TailscaleIPs":["100.1.2.3"],"DNSName":"pc.ts.net."}}'

    monkeypatch.setattr(D, "_tailscale_exe", lambda: "tailscale")
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append(args) or R())
    assert D.tailscale_addrs() == ("100.1.2.3", "pc.ts.net")
    assert calls == [["tailscale", "status", "--json"]]                          # read-only, nothing else


def test_app_stream_end_silence_is_clamped_and_reset():
    from types import SimpleNamespace
    from spike_brain.brain import Brain
    got = []
    b = Brain.__new__(Brain)
    b.listener = SimpleNamespace(set_end_silence=got.append)
    b.s = SimpleNamespace(vad=SimpleNamespace(end_silence_ms=450))
    b.end_silence_client, b._end_silence_ms = None, None
    phone, robot = object(), object()
    b._stream_end_silence(phone, 3000)
    b._stream_end_silence(phone, 3000)                  # unchanged: not sent again
    b._stream_end_silence(phone, 99999)
    b._stream_end_silence(robot, None)                  # another stream without it: no effect
    b._stream_end_silence(phone, None)                  # the app stopped asking: the brain's own
    assert got == [3000, 6000, 450]
    b._stream_end_silence(phone, 10)
    assert got[-1] == 1500
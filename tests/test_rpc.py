import threading
import time

import pytest

from cairn import rpc, schema


def _server_thread(sock_path, handler):
    stop = threading.Event()

    def run():
        rpc.serve(sock_path, handler, stop)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    for _ in range(50):
        if sock_path.exists():
            break
        time.sleep(0.01)
    return t, stop


def test_roundtrip_ok(tmp_project):
    sock = tmp_project / ".cairn" / "sock"

    def handler(req: schema.Req) -> schema.Resp:
        return schema.Resp(ok=True, payload=b"pong-" + req.payload)

    t, stop = _server_thread(sock, handler)
    try:
        resp = rpc.call(sock, schema.Req(type="ping", payload=b"hi"))
        assert resp.ok and resp.payload == b"pong-hi"
    finally:
        stop.set()
        try:
            rpc.call(sock, schema.Req(type="__quit__"))
        except Exception:
            pass
        t.join(timeout=1.0)


def test_error_handler(tmp_project):
    sock = tmp_project / ".cairn" / "sock"

    def handler(req):
        raise RuntimeError("boom")

    t, stop = _server_thread(sock, handler)
    try:
        resp = rpc.call(sock, schema.Req(type="x"))
        assert not resp.ok
        assert "boom" in resp.error
    finally:
        stop.set()
        try:
            rpc.call(sock, schema.Req(type="__quit__"))
        except Exception:
            pass
        t.join(timeout=1.0)


def test_client_refused_when_no_server(tmp_project):
    with pytest.raises(ConnectionError):
        rpc.call(tmp_project / "nope.sock", schema.Req(type="x"), timeout=0.1)

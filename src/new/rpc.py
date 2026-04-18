import os
import socket
import struct
import threading
from pathlib import Path
from typing import Callable

from . import schema


_HDR = struct.Struct(">I")


def _send(sock: socket.socket, data: bytes) -> None:
    sock.sendall(_HDR.pack(len(data)) + data)


def _recv(sock: socket.socket) -> bytes:
    hdr = _recv_n(sock, 4)
    (n,) = _HDR.unpack(hdr)
    return _recv_n(sock, n)


def _recv_n(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed")
        buf += chunk
    return bytes(buf)


def serve(sock_path: Path, handler: Callable[[schema.Req], schema.Resp],
          stop: threading.Event) -> None:
    sock_path = Path(sock_path)
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    if sock_path.exists():
        sock_path.unlink()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    os.chmod(sock_path, 0o600)
    srv.listen(64)
    srv.settimeout(0.25)

    try:
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                try:
                    data = _recv(conn)
                    req = schema.decode(data, schema.Req)
                    if req.type == "__quit__":
                        _send(conn, schema.encode(schema.Resp(ok=True)))
                        break
                    try:
                        resp = handler(req)
                    except Exception as e:
                        resp = schema.Resp(ok=False, error=str(e))
                    _send(conn, schema.encode(resp))
                except Exception:
                    pass
    finally:
        srv.close()
        try:
            sock_path.unlink()
        except FileNotFoundError:
            pass


def call(sock_path: Path, req: schema.Req, *, timeout: float = 5.0) -> schema.Resp:
    sock_path = Path(sock_path)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        try:
            s.connect(str(sock_path))
        except (FileNotFoundError, ConnectionRefusedError) as e:
            raise ConnectionError(f"cannot reach {sock_path}: {e}")
        _send(s, schema.encode(req))
        data = _recv(s)
        return schema.decode(data, schema.Resp)
    finally:
        s.close()

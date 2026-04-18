import contextlib
import errno
import fcntl
import os
from pathlib import Path


def find_project_root() -> Path:
    env = os.environ.get("CAIRN_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    cur = Path.cwd().resolve()
    for d in [cur, *cur.parents]:
        if (d / "experiment.yaml").exists():
            return d
    return cur


def project_root() -> Path:
    return find_project_root()


def new_dir() -> Path:
    d = project_root() / ".cairn"
    d.mkdir(parents=True, exist_ok=True)
    return d


def atomic_write(path: Path, data: str | bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, mode) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_pidfile(pf: Path, pid: int) -> None:
    atomic_write(pf, str(pid))


def read_pidfile(pf: Path) -> int | None:
    try:
        return int(pf.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError as e:
        return e.errno == errno.EPERM
    return True


@contextlib.contextmanager
def flock(path: Path, *, blocking: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        mode = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        fcntl.flock(fd, mode)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

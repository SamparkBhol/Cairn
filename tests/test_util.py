import os
from pathlib import Path

import pytest

from cairn import util


def test_project_root_autodetect(tmp_project):
    assert util.project_root() == tmp_project


def test_project_root_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CAIRN_PROJECT_ROOT", str(tmp_path))
    assert util.project_root() == tmp_path


def test_project_root_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CAIRN_PROJECT_ROOT", raising=False)
    assert util.project_root() == tmp_path


def test_new_dir_created(tmp_project):
    d = util.new_dir()
    assert d.exists() and d.is_dir()
    assert d == tmp_project / ".cairn"


def test_atomic_write_creates_file(tmp_project):
    p = tmp_project / "f.txt"
    util.atomic_write(p, "hello")
    assert p.read_text() == "hello"


def test_atomic_write_overwrites(tmp_project):
    p = tmp_project / "f.txt"
    p.write_text("old")
    util.atomic_write(p, "new")
    assert p.read_text() == "new"


def test_pidfile_roundtrip(tmp_project):
    pf = tmp_project / ".cairn" / "cairnd.pid"
    pf.parent.mkdir(parents=True)
    util.write_pidfile(pf, 4242)
    assert util.read_pidfile(pf) == 4242


def test_pidfile_stale_detection(tmp_project):
    pf = tmp_project / ".cairn" / "cairnd.pid"
    pf.parent.mkdir(parents=True)
    util.write_pidfile(pf, 999_999_999)
    assert util.pid_alive(util.read_pidfile(pf)) is False


def test_pid_alive_self():
    assert util.pid_alive(os.getpid()) is True


def test_flock_blocks_concurrent(tmp_project):
    lock = tmp_project / "lockfile"
    with util.flock(lock):
        with pytest.raises(BlockingIOError):
            with util.flock(lock, blocking=False):
                pass

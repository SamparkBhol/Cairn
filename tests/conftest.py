import pytest


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "experiment.yaml").touch()
    return tmp_path

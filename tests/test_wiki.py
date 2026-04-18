import pytest

from cairn import wiki


def test_init_creates_skeleton(tmp_project):
    wiki.init(tmp_project / "wiki")
    root = tmp_project / "wiki"
    for name in ["index.md", "log.md", "schema.md"]:
        assert (root / name).exists()
    for d in ["theses", "topics", "experiments"]:
        assert (root / d).is_dir()


def test_safe_path_inside(tmp_project):
    wiki.init(tmp_project / "wiki")
    p = wiki.safe_page_path(tmp_project / "wiki", "topics/learning-rate.md")
    assert p.parent.name == "topics"


def test_safe_path_rejects_traversal(tmp_project):
    wiki.init(tmp_project / "wiki")
    with pytest.raises(ValueError):
        wiki.safe_page_path(tmp_project / "wiki", "../etc/passwd")


def test_safe_path_rejects_absolute(tmp_project):
    wiki.init(tmp_project / "wiki")
    with pytest.raises(ValueError):
        wiki.safe_page_path(tmp_project / "wiki", "/tmp/bad")


def test_append_log_line(tmp_project):
    wiki.init(tmp_project / "wiki")
    wiki.append_log(tmp_project / "wiki", "ingest", "added page foo")
    text = (tmp_project / "wiki" / "log.md").read_text()
    assert "ingest" in text and "added page foo" in text


def test_rebuild_index(tmp_project):
    root = tmp_project / "wiki"
    wiki.init(root)
    (root / "topics" / "learning-rate.md").write_text(
        "# learning rate\nsome content\n"
    )
    (root / "experiments" / "0001-foo.md").write_text("# exp 1\n")
    wiki.rebuild_index(root)
    idx = (root / "index.md").read_text()
    assert "topics/learning-rate.md" in idx
    assert "experiments/0001-foo.md" in idx

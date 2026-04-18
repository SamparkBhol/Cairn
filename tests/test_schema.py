import msgspec
import pytest

from cairn import schema


def test_config_minimal():
    c = schema.load_config_yaml("""
run_command: python train.py
grep_pattern: "^val_loss:"
metric:
  name: val_loss
  direction: minimize
""")
    assert c.run_command == ["python", "train.py"]
    assert c.metric.direction == "minimize"
    assert c.workers == 1
    assert c.budget.max_experiments == 500


def test_config_bad_regex_refused():
    with pytest.raises(msgspec.ValidationError):
        schema.load_config_yaml("""
run_command: python train.py
grep_pattern: "["
metric:
  name: x
  direction: minimize
""")


def test_config_bad_direction_refused():
    with pytest.raises(msgspec.ValidationError):
        schema.load_config_yaml("""
run_command: python train.py
grep_pattern: "^x:"
metric:
  name: x
  direction: sideways
""")


def test_run_command_empty_refused():
    with pytest.raises(msgspec.ValidationError):
        schema.load_config_yaml("""
run_command: ""
grep_pattern: "^x:"
metric:
  name: x
  direction: minimize
""")


def test_rpc_request_roundtrip():
    r = schema.Req(type="status", payload=b"")
    b = schema.encode(r)
    back = schema.decode(b, schema.Req)
    assert back.type == "status"


def test_run_record_roundtrip():
    rr = schema.RunRecord(
        exp_num=1, commit_sha="abc1234", metric=0.1, metric_holdout=None,
        status="keep", duration_s=10.0, started_at=1.0, ended_at=11.0,
        hypothesis="h", verdict="v", description="d",
        log_path="logs/1.log", wiki_refs=[],
    )
    b = schema.encode(rr)
    back = schema.decode(b, schema.RunRecord)
    assert back.exp_num == 1
    assert back.status == "keep"

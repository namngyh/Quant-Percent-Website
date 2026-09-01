import io
import json
import sys

from vnindex_model.cli import build_parser, emit_result


def test_result_is_emitted_as_utf8_when_stdout_cannot_encode_vietnamese(monkeypatch):
    """Task Scheduler/cron redirect stdout, which defaults to cp1252 on Windows."""
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", newline=""))
    payload = {"status": "updated", "note": "Phiên mới đã được nạp; không refit mô hình nào"}
    emit_result(payload)
    assert json.loads(raw.getvalue().decode("utf-8")) == payload


def test_parser_exposes_both_online_commands():
    for command in ["init-online-state", "update-latest"]:
        arguments = build_parser().parse_args([command, "--config", "configs/quick.yaml"])
        assert arguments.command == command
        assert arguments.config == "configs/quick.yaml"

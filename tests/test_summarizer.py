import json
from io import BytesIO
from unittest.mock import patch

from websync.pipeline.summarizer import Summarizer


def _config(enabled=True):
    return {"ai_summary": {"enabled": enabled, "provider": "openai", "api_key": "test-key"}}


def test_summarizer_unavailable_when_disabled():
    s = Summarizer({"ai_summary": {"enabled": False}})
    assert s.summarize("t", "<p>x</p>") == ""


def test_call_openai_malformed_no_choices():
    s = Summarizer(_config())
    fake_resp = BytesIO(json.dumps({"id": "x"}).encode())

    with patch("urllib.request.urlopen", return_value=fake_resp):
        assert s._call_openai("prompt") == ""


def test_call_openai_empty_content():
    s = Summarizer(_config())
    fake_resp = BytesIO(json.dumps({"choices": [{"message": {"content": ""}}]}).encode())

    with patch("urllib.request.urlopen", return_value=fake_resp):
        assert s._call_openai("prompt") == ""


def test_call_openai_valid_response():
    s = Summarizer(_config())
    fake_resp = BytesIO(json.dumps({"choices": [{"message": {"content": "요약문입니다."}}]}).encode())

    with patch("urllib.request.urlopen", return_value=fake_resp):
        result = s._call_openai("prompt")
        assert "요약문입니다" in result
        assert "ai-summary" in result
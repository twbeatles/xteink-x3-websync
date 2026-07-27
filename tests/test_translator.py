"""Translator 단위 테스트 — N8(logger 주입) 중심.

외부 번역 API 호출은 mock 하고, logger 주입 동작만 검증한다.
"""
from io import BytesIO
import json
from unittest.mock import MagicMock, patch

from websync.pipeline.translator import Translator


def _config(provider="libretranslate", enabled=True):
    return {
        "translation": {
            "enabled": enabled,
            "provider": provider,
            "libretranslate_host": "http://localhost:5000",
            "libretranslate_api_key": "",
        }
    }


def test_translator_uses_logger_on_failure():
    """logger 주입 시 번역 실패를 logger.warning 으로 출력."""
    logger = MagicMock()
    t = Translator(_config(), logger=logger)

    with patch("urllib.request.urlopen", side_effect=RuntimeError("libre 죽음")):
        result = t.translate_html("<p>hello world this is long enough</p>", target_lang="ko")

    # 실패 시 원문 반환
    assert "hello world" in result
    logger.warning.assert_called()
    warned = " ".join(str(c) for c in logger.warning.call_args_list)
    assert "번역 실패" in warned


def test_translator_print_fallback_when_no_logger():
    """logger=None 일 때 print 폴백."""
    t = Translator(_config(), logger=None)
    with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
        with patch("builtins.print") as mock_print:
            t.translate_html("<p>hello world this is long enough</p>", target_lang="ko")
    mock_print.assert_called()


def test_translator_is_available_for_site_requires_translate_to():
    t = Translator(_config())
    assert t.is_available_for_site("") is False
    assert t.is_available_for_site("  ") is False


def test_translator_logger_warns_on_googletrans_load_failure():
    """googletrans provider 에서 로드 실패 시 logger.warning."""
    logger = MagicMock()
    t = Translator(_config(provider="googletrans", enabled=True), logger=logger)

    # googletrans import 자체가 실패하는 환경을 흉내
    builtins_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "googletrans":
            raise ImportError("no googletrans")
        return builtins_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        gt = t._get_gtrans()

    assert gt is None
    logger.warning.assert_called()
    warned = " ".join(str(c) for c in logger.warning.call_args_list)
    assert "googletrans 로드 실패" in warned


def test_translator_libretranslate_success():
    """libretranslate 정상 응답 시 번역문 반환."""
    t = Translator(_config())
    fake_resp = BytesIO(json.dumps({"translatedText": "안녕하세요"}).encode())
    with patch("urllib.request.urlopen", return_value=fake_resp):
        result = t._do_translate("hello", "ko", "en")
    assert result == "안녕하세요"

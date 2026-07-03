"""기사 번역 모듈 (googletrans 또는 LibreTranslate 지원)"""
import re


class Translator:
    """기사 HTML을 지정 언어로 번역하는 클래스. 설정 없으면 자동 스킵."""

    def __init__(self, config: dict):
        cfg = config.get("translation", {})
        self.enabled = cfg.get("enabled", False)
        self.provider = cfg.get("provider", "googletrans")  # 'googletrans' | 'libretranslate'
        self.libretranslate_host = cfg.get("libretranslate_host", "http://localhost:5000")
        self.libretranslate_api_key = cfg.get("libretranslate_api_key", "")
        self._gtrans = None

    def is_available(self) -> bool:
        return self.enabled

    def _get_gtrans(self):
        if self._gtrans is None:
            try:
                from googletrans import Translator as GT
                self._gtrans = GT()
            except Exception:
                self._gtrans = None
        return self._gtrans

    def translate_html(self, html_content: str, target_lang: str = "ko", source_lang: str = "auto") -> str:
        """HTML 내 텍스트 노드만 번역. 태그 구조는 보존."""
        if not self.is_available():
            return html_content
        try:
            # 텍스트 블록 단위 추출 (태그 사이 텍스트)
            parts = re.split(r"(<[^>]+>)", html_content)
            translated_parts = []
            for part in parts:
                if part.startswith("<"):
                    translated_parts.append(part)
                else:
                    stripped = part.strip()
                    if len(stripped) > 5:
                        translated = self._do_translate(stripped, target_lang, source_lang)
                        translated_parts.append(part.replace(stripped, translated))
                    else:
                        translated_parts.append(part)
            return "".join(translated_parts)
        except Exception as e:
            print(f"⚠️ 번역 실패: {e}")
            return html_content

    def _do_translate(self, text: str, target: str, source: str) -> str:
        if self.provider == "googletrans":
            gt = self._get_gtrans()
            if gt is None:
                return text
            result = gt.translate(text, dest=target, src=source if source != "auto" else None)
            return result.text
        elif self.provider == "libretranslate":
            import urllib.request
            import json
            payload = {"q": text, "source": source if source != "auto" else "en", "target": target, "api_key": self.libretranslate_api_key}
            req = urllib.request.Request(
                f"{self.libretranslate_host}/translate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
            return result.get("translatedText", text)
        return text

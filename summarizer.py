"""AI 기사 요약 모듈 (OpenAI API 또는 Ollama 로컬 LLM 지원)"""
import re


class Summarizer:
    """기사 텍스트를 AI로 요약하는 클래스. API 키가 없으면 자동 스킵."""

    def __init__(self, config: dict):
        ai_cfg = config.get("ai_summary", {})
        self.enabled = ai_cfg.get("enabled", False)
        self.provider = ai_cfg.get("provider", "openai")  # 'openai' | 'ollama'
        self.api_key = ai_cfg.get("api_key", "")
        self.ollama_host = ai_cfg.get("ollama_host", "http://localhost:11434")
        self.model = ai_cfg.get("model", "gpt-4o-mini")

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if self.provider == "openai" and not self.api_key:
            return False
        return True

    def _extract_text(self, html_content: str) -> str:
        """HTML 태그 제거 후 순수 텍스트 추출"""
        text = re.sub(r"<[^>]+>", " ", html_content)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:3000]  # 토큰 절약을 위해 최대 3000자

    def summarize(self, title: str, html_content: str) -> str:
        """기사를 요약해 HTML blockquote 형태로 반환. 실패 시 빈 문자열."""
        if not self.is_available():
            return ""
        try:
            text = self._extract_text(html_content)
            prompt = f"다음 기사를 한국어로 3문장 이내로 핵심만 요약해줘.\n\n제목: {title}\n\n내용: {text}"

            if self.provider == "openai":
                return self._call_openai(prompt)
            elif self.provider == "ollama":
                return self._call_ollama(prompt)
        except Exception as e:
            print(f"⚠️ AI 요약 실패: {e}")
        return ""

    def _call_openai(self, prompt: str) -> str:
        import urllib.request
        import json
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
        summary = result["choices"][0]["message"]["content"].strip()
        return f'<blockquote class="ai-summary"><strong>📝 AI 요약</strong><br/>{summary}</blockquote>'

    def _call_ollama(self, prompt: str) -> str:
        import urllib.request
        import json
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        req = urllib.request.Request(
            f"{self.ollama_host}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        summary = result.get("response", "").strip()
        return f'<blockquote class="ai-summary"><strong>📝 AI 요약</strong><br/>{summary}</blockquote>'

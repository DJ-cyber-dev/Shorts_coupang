"""Small stdlib-only adapter for OpenAI-compatible Chat Completions APIs."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from shorts_studio.core import MediaError
from .settings import ProviderSettings


class OpenAICompatibleClient:
    def __init__(self, settings: ProviderSettings | None = None, timeout: int = 120):
        self.settings = settings or ProviderSettings.load()
        self.settings.validate()
        if self.settings.provider == "disabled":
            raise MediaError("AI Provider가 비활성화되어 있습니다. Desktop의 AI Provider 설정에서 설정하세요.")
        if self.settings.provider != "openai-compatible":
            raise MediaError("현재 지원하는 Provider adapter는 openai-compatible입니다.")
        self.secret = self.settings.get_secret()
        if not self.secret:
            raise MediaError(f"API key가 없습니다. {self.settings.key_name} 또는 Windows Credential Manager를 설정하세요.")
        if not 5 <= timeout <= 300:
            raise ValueError("timeout은 5~300초여야 합니다.")
        self.timeout = timeout

    def complete(self, messages: list[dict], *, temperature: float = 0.2) -> str:
        endpoint = self.settings.base_url.rstrip("/") + "/chat/completions"
        body = json.dumps({"model": self.settings.model, "messages": messages,
                           "temperature": temperature}).encode("utf-8")
        request = Request(endpoint, data=body, headers={
            "Authorization": f"Bearer {self.secret}", "Content-Type": "application/json",
        }, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise MediaError("AI Provider 응답 크기가 제한을 초과했습니다.")
            payload = json.loads(raw)
        except HTTPError as exc:
            raise MediaError(f"AI Provider 요청 실패 (HTTP {exc.code}). 설정과 사용량을 확인하세요.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise MediaError(f"AI Provider에 연결할 수 없습니다: {type(exc).__name__}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MediaError("AI Provider 응답이 JSON이 아닙니다.") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(item.get("text", "") for item in content if item.get("type") == "text")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty content")
            return content
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MediaError("AI Provider 응답 형식이 올바르지 않습니다.") from exc

"""Native Gemini API client and settings for Korean script generation."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from shorts_studio.core import MediaError
from .settings import settings_path


DEFAULT_MODEL = "gemini-3.8-flash"
MODEL_OPTIONS = (
    {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash · 권장"},
    {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash"},
    {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash-Lite · 빠른 처리"},
    {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash-Lite · 경량 처리"},
)
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_RESPONSE_BYTES = 2_000_000


@dataclass(frozen=True)
class GeminiScriptSettings:
    model: str = DEFAULT_MODEL
    key_name: str = "SHORTS_GEMINI_API_KEY"

    def validate(self) -> None:
        if not isinstance(self.model, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", self.model):
            raise ValueError("Gemini model ID 형식이 올바르지 않습니다.")
        if not isinstance(self.key_name, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,63}", self.key_name):
            raise ValueError("API key 환경 변수 이름이 올바르지 않습니다.")

    @classmethod
    def load(cls, path: Path | None = None) -> "GeminiScriptSettings":
        path = Path(path) if path else settings_path().parent / "script-ai.json"
        if not path.exists():
            return cls()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Gemini 설정 파일을 읽지 못했습니다.") from exc
        if not isinstance(value, dict) or set(value) - {"model", "key_name"}:
            raise ValueError("Gemini 설정 필드가 올바르지 않습니다.")
        settings = cls(**value)
        settings.validate()
        return settings

    def save(self, path: Path | None = None) -> None:
        self.validate()
        path = Path(path) if path else settings_path().parent / "script-ai.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps({"model": self.model, "key_name": self.key_name}, indent=2), encoding="utf-8")
        os.replace(temp, path)

    def store_secret(self, secret: str) -> None:
        if not isinstance(secret, str) or not secret.strip():
            raise ValueError("Gemini API key를 입력하세요.")
        if os.name != "nt":
            raise RuntimeError(f"Windows 이외 환경에서는 {self.key_name} 환경 변수로 API key를 설정하세요.")
        from keyring.backends.Windows import WinVaultKeyring
        WinVaultKeyring().set_password("shorts-studio", self.key_name, secret.strip())

    def get_secret(self) -> str | None:
        value = os.getenv(self.key_name)
        if value:
            return value
        if os.name == "nt":
            from keyring.backends.Windows import WinVaultKeyring
            return WinVaultKeyring().get_password("shorts-studio", self.key_name)
        return None


class GeminiScriptClient:
    def __init__(self, settings: GeminiScriptSettings | None = None, *, opener=urlopen,
                 timeout: int = 90, sleep_fn=time.sleep, max_retries: int = 3):
        self.settings = settings or GeminiScriptSettings.load()
        self.settings.validate()
        self.secret = self.settings.get_secret()
        if not self.secret:
            raise MediaError(f"Gemini API key가 없습니다. {self.settings.key_name} 또는 Windows Credential Manager를 설정하세요.")
        if not 5 <= timeout <= 300:
            raise ValueError("timeout은 5~300초여야 합니다.")
        if not 0 <= max_retries <= 5:
            raise ValueError("max_retries는 0~5여야 합니다.")
        self.opener = opener
        self.timeout = timeout
        self.sleep_fn = sleep_fn
        self.max_retries = max_retries

    def complete(self, messages: list[dict], *, temperature: float = 0.5) -> str:
        system_parts = []
        contents = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("Gemini 대본 요청은 텍스트 메시지만 지원합니다.")
            if role == "system":
                system_parts.append(content)
            elif role in {"user", "assistant"}:
                contents.append({"role": "user" if role == "user" else "model",
                                 "parts": [{"text": content}]})
            else:
                raise ValueError("지원하지 않는 Gemini 대화 role입니다.")
        if not contents:
            raise ValueError("Gemini 요청에 user 메시지가 필요합니다.")
        body = {"contents": contents, "generationConfig": {"temperature": temperature,
                "responseMimeType": "application/json"}}
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        endpoint = f"{API_BASE}/{quote(self.settings.model, safe='')}:generateContent"
        request = Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"x-goog-api-key": self.secret, "Content-Type": "application/json"},
                          method="POST")
        for attempt in range(self.max_retries + 1):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise MediaError("Gemini API 응답 크기가 제한을 초과했습니다.")
                payload = json.loads(raw.decode("utf-8"))
                break
            except HTTPError as exc:
                if exc.code in {500, 502, 503, 504} and attempt < self.max_retries:
                    self.sleep_fn(min(2 ** attempt, 30))
                    continue
                if exc.code == 429:
                    raise MediaError("Gemini API 사용량 제한에 도달했습니다. Google AI Studio의 quota와 billing을 확인하세요.") from None
                if exc.code in {500, 502, 503, 504}:
                    raise MediaError(f"Gemini API를 일시적으로 사용할 수 없습니다 (HTTP {exc.code}). 잠시 후 다시 시도하세요.") from None
                raise MediaError(f"Gemini API 요청 실패 (HTTP {exc.code}). API key, model, 사용 권한을 확인하세요.") from None
            except (URLError, TimeoutError, OSError):
                raise MediaError("Gemini API에 연결할 수 없습니다. 네트워크를 확인하세요.") from None
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise MediaError("Gemini API 응답이 JSON이 아닙니다.") from None
        try:
            candidate = payload["candidates"][0]
            text = "".join(part["text"] for part in candidate["content"]["parts"] if isinstance(part.get("text"), str))
            if not text.strip():
                raise ValueError("empty response")
            return text
        except (KeyError, IndexError, TypeError, ValueError):
            prompt_feedback = payload.get("promptFeedback", {})
            if prompt_feedback.get("blockReason"):
                raise MediaError("Gemini가 요청을 차단했습니다. 입력한 영상 분석 내용을 확인하세요.") from None
            raise MediaError("Gemini API 응답에서 대본 텍스트를 찾지 못했습니다.") from None

    def test_connection(self) -> None:
        result = self.complete([{"role": "user", "content": 'Return only this JSON: {"status":"ok"}'}], temperature=0)
        try:
            if json.loads(result).get("status") != "ok":
                raise ValueError
        except (json.JSONDecodeError, AttributeError, ValueError):
            raise MediaError("Gemini 응답을 받았지만 연결 확인 결과가 올바르지 않습니다.") from None

from __future__ import annotations

import json
import logging
import time
from logging.handlers import RotatingFileHandler
from typing import Any

import httpx
import requests

from app.core.config import LOG_DIR, Settings
from app.providers.openrouter import PlannerResult


SYSTEM_PROMPT = (
    "Ты JARVIS, русскоязычный персональный AI-ассистент на Windows PC. "
    "Отвечай кратко, естественно и полезно. Для голосового режима держи ответ в 1-3 предложениях."
)
TEST_PROMPT = "Ответь одним словом: OK"


def _provider_logger(name: str, filename: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(
        isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "").endswith(filename)
        for handler in logger.handlers
    ):
        handler = RotatingFileHandler(LOG_DIR / filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    return logger


def classify_groq_exception(exc: BaseException) -> str:
    raw = f"{exc.__class__.__name__}: {exc}".lower()
    if "ssl" in raw or "certificate" in raw or "handshake" in raw:
        return "ssl_error"
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException, requests.exceptions.Timeout)):
        return "network_timeout"
    if isinstance(exc, (httpx.NetworkError, httpx.TransportError, requests.exceptions.ConnectionError)):
        return "network_error"
    return "provider_error"


def _fix_for(status_code: int | None, error_type: str) -> str:
    if error_type == "groq_key_missing":
        return "Добавьте JARVIS_GROQ_API_KEY или GROQ_API_KEY в .env."
    if error_type == "model_missing":
        return "Добавьте JARVIS_GROQ_MODEL в .env."
    if error_type in {"network_timeout", "network_error", "ssl_error"}:
        return "Проверьте интернет, VPN/proxy и доступ к api.groq.com."
    if error_type == "rate_limited" or status_code == 429:
        return "Groq вернул rate limit. Подождите или переключитесь на OpenRouter fallback."
    if status_code == 401:
        return "Groq API key неверный или отозван."
    if status_code == 403:
        return "Groq API key не имеет доступа к выбранной модели."
    if status_code == 404:
        return "Модель Groq не найдена. Проверьте JARVIS_GROQ_MODEL."
    if status_code and status_code >= 500:
        return "Groq временно недоступен. Повторите позже."
    return "Смотрите logs/groq.log и logs/provider.log."


class GroqPlanner:
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def plan(self, text: str, context: dict[str, Any] | None = None) -> PlannerResult:
        logger = _provider_logger("jarvis.provider.groq", "groq.log")
        provider_logger = _provider_logger("jarvis.provider", "provider.log")
        context = context or {}
        started = time.perf_counter()

        if not self.settings.groq_api_key:
            return self._unavailable("groq_key_missing", None, "Groq API key is missing.", 0, called=False)
        if not self.settings.groq_model:
            return self._unavailable("model_missing", None, "Groq model is missing.", 0, called=False)

        system_prompt = SYSTEM_PROMPT
        max_tokens = self.settings.groq_max_tokens
        if context.get("source") == "voice" or context.get("route") == "voice":
            system_prompt += " Голосовой ответ: максимум 1-3 коротких предложения."
            max_tokens = min(max_tokens, 120)

        payload = {
            "model": self.settings.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": self.settings.groq_temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(
            float(self.settings.groq_timeout_seconds),
            connect=min(5.0, float(self.settings.groq_timeout_seconds)),
            read=float(self.settings.groq_timeout_seconds),
            write=5.0,
            pool=5.0,
        )

        logger.info("[GROQ] called=true endpoint=%s model=%s", self.endpoint, self.settings.groq_model)
        provider_logger.info("[GROQ] called=true endpoint=%s model=%s", self.endpoint, self.settings.groq_model)

        try:
            with httpx.Client(timeout=timeout, trust_env=True) as client:
                response = client.post(self.endpoint, headers=headers, json=payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            raw_preview = response.text[:1000].replace("\n", " ")
            if response.status_code >= 400:
                error_type = self._status_error_type(response.status_code)
                message = self._extract_error_message(response.text) or response.reason_phrase
                logger.info("[GROQ] failed status_code=%s error_type=%s latency_ms=%s", response.status_code, error_type, latency_ms)
                return self._unavailable(error_type, response.status_code, message, latency_ms, called=True, raw_response_preview=raw_preview)

            data = response.json()
            answer = self._extract_answer_text(data)
            if not answer:
                return self._unavailable("provider_error", response.status_code, "Groq returned empty response.", latency_ms, called=True, raw_response_preview=raw_preview)
            preview = answer[:160].replace("\n", " ")
            logger.info("[GROQ] ok status_code=%s latency_ms=%s preview=%s", response.status_code, latency_ms, preview)
            return PlannerResult(
                status="answered",
                answer_text=answer,
                actions=[],
                provider="groq",
                model=self.settings.groq_model,
                status_code=response.status_code,
                latency_ms=latency_ms,
                endpoint=self.endpoint,
                openrouter_called=False,
                raw_response_preview=raw_preview,
                response_text_preview=preview,
            )
        except json.JSONDecodeError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return self._unavailable("provider_error", None, str(exc), latency_ms, called=True)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            fallback = self._requests_fallback(headers, payload, started)
            if fallback.status == "answered":
                return fallback
            latency_ms = int((time.perf_counter() - started) * 1000)
            error_type = classify_groq_exception(exc)
            logger.info("[GROQ] failed status_code=null error_type=%s latency_ms=%s", error_type, latency_ms)
            return self._unavailable(error_type, None, exc.__class__.__name__, latency_ms, called=True)

    def test(self, text: str = TEST_PROMPT, *, must_contain: str | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        result = self.plan(text)
        latency_ms = result.latency_ms if result.latency_ms is not None else int((time.perf_counter() - started) * 1000)
        normalized_answer = result.answer_text.upper().replace(".", "").replace("!", "").strip()
        contains_required = True if not must_contain else must_contain.upper() in normalized_answer or "\u041e\u041a" in normalized_answer
        answered = result.status == "answered"
        return {
            "ok": answered,
            "provider": "groq",
            "called": result.status != "unavailable" or result.error_type not in {"groq_key_missing", "model_missing"},
            "model": self.settings.groq_model,
            "status_code": result.status_code,
            "response_preview": result.answer_text[:160] if result.answer_text else None,
            "error_type": None if answered else result.error_type or "provider_error",
            "error_message": None if answered else result.error_message,
            "fix": "Groq answered, but did not repeat the control word exactly." if answered and not contains_required else None if answered else result.fix,
            "latency_ms": latency_ms,
        }

    def status_snapshot(self) -> dict[str, Any]:
        key_present = bool(self.settings.groq_api_key)
        if not key_present:
            return {
                "key_present": False,
                "model": self.settings.groq_model,
                "available": False,
                "last_error_type": "groq_key_missing",
                "latency_ms": 0,
            }
        result = self.test(TEST_PROMPT, must_contain="OK")
        return {
            "key_present": key_present,
            "model": self.settings.groq_model,
            "available": bool(result.get("ok")),
            "last_error_type": result.get("error_type"),
            "latency_ms": result.get("latency_ms"),
        }

    def _requests_fallback(self, headers: dict[str, str], payload: dict[str, Any], started: float) -> PlannerResult:
        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=(min(5, self.settings.groq_timeout_seconds), self.settings.groq_timeout_seconds),
            )
        except requests.exceptions.RequestException as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return self._unavailable(classify_groq_exception(exc), None, exc.__class__.__name__, latency_ms, called=True)

        latency_ms = int((time.perf_counter() - started) * 1000)
        raw_preview = response.text[:1000].replace("\n", " ")
        if response.status_code >= 400:
            error_type = self._status_error_type(response.status_code)
            message = self._extract_error_message(response.text) or response.reason
            return self._unavailable(error_type, response.status_code, message, latency_ms, called=True, raw_response_preview=raw_preview)

        try:
            data = response.json()
        except ValueError as exc:
            return self._unavailable("provider_error", response.status_code, str(exc), latency_ms, called=True, raw_response_preview=raw_preview)

        answer = self._extract_answer_text(data)
        if not answer:
            return self._unavailable("provider_error", response.status_code, "Groq returned empty response.", latency_ms, called=True, raw_response_preview=raw_preview)
        return PlannerResult(
            status="answered",
            answer_text=answer,
            actions=[],
            provider="groq",
            model=self.settings.groq_model,
            status_code=response.status_code,
            latency_ms=latency_ms,
            endpoint=self.endpoint,
            openrouter_called=False,
            raw_response_preview=raw_preview,
            response_text_preview=answer[:160].replace("\n", " "),
        )

    def _unavailable(
        self,
        error_type: str,
        status_code: int | None,
        message: str,
        latency_ms: int,
        *,
        called: bool,
        raw_response_preview: str | None = None,
    ) -> PlannerResult:
        return PlannerResult(
            status="unavailable",
            answer_text="Groq is unavailable.",
            actions=[],
            provider="groq",
            error=error_type,
            model=self.settings.groq_model,
            status_code=status_code,
            error_type=error_type,
            error_message=message,
            fix=_fix_for(status_code, error_type),
            latency_ms=latency_ms,
            endpoint=self.endpoint,
            openrouter_called=False,
            raw_response_preview=raw_response_preview,
            response_text_preview=None,
        )

    @staticmethod
    def _status_error_type(status_code: int) -> str:
        if status_code == 401:
            return "invalid_key"
        if status_code == 403:
            return "forbidden"
        if status_code == 404:
            return "model_not_found"
        if status_code == 429:
            return "rate_limited"
        return "provider_error"

    @staticmethod
    def _extract_answer_text(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content.strip()
        return ""

    @staticmethod
    def _extract_error_message(body: str) -> str | None:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body[:500] if body else None
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)
        if error:
            return str(error)
        if isinstance(data, dict) and data.get("message"):
            return str(data["message"])
        return body[:500] if body else None

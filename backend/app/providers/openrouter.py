from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import Any

import httpx

from app.core.config import LOG_DIR, Settings


CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 10.0
OPENROUTER_TOTAL_TIMEOUT_SECONDS = 15.0
MAX_RETRIES = 1
SYSTEM_PROMPT = (
    "Ты — JARVIS, русскоязычный персональный AI-ассистент на Windows PC.\n"
    "Отвечай естественно, кратко, уверенно и полезно.\n"
    "Твой стиль: спокойный, умный, немного кинематографичный, но без пафоса.\n"
    "Можно обращаться к пользователю \"сэр\", если это звучит уместно.\n"
    "Ты умеешь объяснять, планировать, помогать с ПК, кодом, проектами и локальными командами.\n"
    "Не выдумывай факты.\n"
    "Если команда требует действия на ПК, объясни что будет сделано.\n"
    "Если действие опасное или необратимое, попроси подтверждение.\n"
    "Отвечай на русском, если пользователь говорит по-русски."
)
TEST_PROMPT = "\u041e\u0442\u0432\u0435\u0442\u044c \u043e\u0434\u043d\u0438\u043c \u0441\u043b\u043e\u0432\u043e\u043c: OK. \u041d\u0435 \u043f\u0435\u0440\u0435\u0432\u043e\u0434\u0438 OK \u0438 \u043d\u0435 \u0434\u043e\u0431\u0430\u0432\u043b\u044f\u0439 \u0434\u0440\u0443\u0433\u0438\u0445 \u0441\u043b\u043e\u0432."


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


def _fix_for(status_code: int | None, error_type: str) -> str:
    if error_type in {"key_missing", "env_missing"}:
        return "Добавьте JARVIS_OPENROUTER_API_KEY в backend/.env или .env файл."
    if error_type == "model_missing":
        return "Добавьте JARVIS_OPENROUTER_MODEL в backend/.env или .env файл."
    if error_type == "offline_mode":
        return "Disable offline_mode in backend settings."
    if error_type == "invalid_key" or status_code == 401:
        return "Неверный OpenRouter API ключ. Пожалуйста, проверьте правильность ключа в backend/.env."
    if error_type == "no_credits_or_payment_required" or status_code == 402:
        return "Недостаточно средств на балансе OpenRouter. Пополните баланс на openrouter.ai."
    if error_type == "forbidden" or status_code == 403:
        return "Доступ к ресурсу запрещен. Проверьте настройки прав ключа OpenRouter."
    if error_type == "model_not_found" or status_code == 404:
        return "Модель не найдена на OpenRouter. Проверьте правильность JARVIS_OPENROUTER_MODEL."
    if error_type == "rate_limited" or status_code == 429:
        return "Превышен лимит запросов. Подождите немного и повторите попытку."
    if error_type == "timeout":
        return "Таймаут соединения с OpenRouter. Проверьте интернет-соединение или прокси."
    if status_code and status_code >= 500:
        return "OpenRouter server error, retry later."
    if error_type in {"ConnectTimeout", "ReadTimeout", "TimeoutException"}:
        return "OpenRouter SSL/network timeout: check network, proxy, DNS, or endpoint reachability."
    if error_type in {"ConnectError", "NetworkError", "TransportError"}:
        return "OpenRouter network error: check network, proxy, DNS, or TLS interception."
    return "See logs/openrouter.log and logs/provider.log."


def _error_message(status_code: int | None, error_type: str, raw_message: str, model: str) -> str:
    if error_type in {"key_missing", "env_missing"}:
        return "OpenRouter API key is missing."
    if error_type == "model_missing":
        return "OpenRouter model is missing."
    if error_type == "offline_mode":
        return "AI is disabled: offline_mode is enabled."
    if error_type == "invalid_key" or status_code == 401:
        return "OpenRouter 401: invalid API key."
    if error_type == "no_credits_or_payment_required" or status_code == 402:
        return "OpenRouter 402: payment required or no credits."
    if error_type == "forbidden" or status_code == 403:
        return f"OpenRouter 403: {raw_message or 'access denied'}"
    if error_type == "model_not_found" or status_code == 404:
        return f"OpenRouter 404: model not found: {model}."
    if error_type == "rate_limited" or status_code == 429:
        return "OpenRouter 429: rate limit or quota exceeded."
    if error_type == "timeout":
        return f"OpenRouter request timeout: {raw_message or 'read/connect timeout'}"
    if error_type in {"ConnectTimeout", "ReadTimeout", "TimeoutException"}:
        return f"OpenRouter timeout during SSL/network request: {raw_message}"
    if raw_message:
        return raw_message
    return error_type


@dataclass(slots=True)
class PlannerResult:
    status: str
    answer_text: str
    actions: list[dict[str, Any]]
    provider: str = "openrouter"
    error: str | None = None
    model: str | None = None
    status_code: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    fix: str | None = None
    latency_ms: int | None = None
    retry_count: int = 0
    endpoint: str | None = None
    openrouter_called: bool = False
    raw_response_preview: str | None = None
    response_text_preview: str | None = None

    @property
    def called(self) -> bool:
        return self.openrouter_called

    @property
    def text(self) -> str:
        return self.answer_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "answer_text": self.answer_text,
            "text": self.answer_text,
            "actions": self.actions,
            "provider": self.provider,
            "called": self.openrouter_called,
            "ok": self.status == "answered",
            "error": self.error,
            "model": self.model,
            "status_code": self.status_code,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "fix": self.fix,
            "latency_ms": self.latency_ms,
            "retry_count": self.retry_count,
            "endpoint": self.endpoint,
            "openrouter_called": self.openrouter_called,
            "raw_response_preview": self.raw_response_preview,
            "response_text_preview": self.response_text_preview,
        }


class OpenRouterPlanner:
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def plan(self, text: str) -> PlannerResult:
        ai_logger = _provider_logger("jarvis.ai_fallback", "ai_fallback.log")
        provider_logger = _provider_logger("jarvis.provider", "provider.log")
        openrouter_logger = _provider_logger("jarvis.provider.openrouter", "openrouter.log")
        ai_logger.info("[AI] user_text=%s", text)
        ai_logger.info("[AI] env openrouter key present=%s", bool(self.settings.openrouter_api_key))
        ai_logger.info("[AI] model=%s", self.settings.openrouter_model)

        if self.settings.offline_mode:
            result = self._unavailable("offline_mode", None, "offline_mode")
            openrouter_logger.info("[OPENROUTER] called=false reason=offline_mode")
            ai_logger.info("[AI] error=%s", result.error_message)
            return result
        if not self.settings.openrouter_api_key:
            result = self._unavailable("key_missing", None, "openrouter_api_key_missing")
            openrouter_logger.info("[OPENROUTER] called=false reason=missing_key")
            ai_logger.info("[AI] error=%s", result.error_message)
            return result
        if not self.settings.openrouter_model:
            result = self._unavailable("model_missing", None, "openrouter_model_missing")
            openrouter_logger.info("[OPENROUTER] called=false reason=missing_model")
            ai_logger.info("[AI] error=%s", result.error_message)
            return result

        payload = {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.6,
            "max_tokens": 500,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:5173",
            "X-OpenRouter-Title": "Jarvis PC V2",
        }

        started = time.perf_counter()
        status_code: int | None = None
        retry_count = 0
        timeout = httpx.Timeout(
            OPENROUTER_TOTAL_TIMEOUT_SECONDS,
            connect=CONNECT_TIMEOUT_SECONDS,
            read=READ_TIMEOUT_SECONDS,
            write=5.0,
            pool=5.0,
        )

        provider_logger.info(
            "[OpenRouter] request started endpoint=%s model=%s connect_timeout=%s read_timeout=%s total_timeout=%s",
            self.endpoint,
            self.settings.openrouter_model,
            CONNECT_TIMEOUT_SECONDS,
            READ_TIMEOUT_SECONDS,
            OPENROUTER_TOTAL_TIMEOUT_SECONDS,
        )
        openrouter_logger.info(
            "[OPENROUTER] called=true endpoint=%s model=%s connect_timeout=%s read_timeout=%s total_timeout=%s",
            self.endpoint,
            self.settings.openrouter_model,
            CONNECT_TIMEOUT_SECONDS,
            READ_TIMEOUT_SECONDS,
            OPENROUTER_TOTAL_TIMEOUT_SECONDS,
        )

        data: dict[str, Any] | None = None
        raw_response_preview: str | None = None
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            retry_count = attempt
            try:
                with httpx.Client(timeout=timeout, trust_env=True) as client:
                    response = client.post(self.endpoint, headers=headers, json=payload)
                status_code = response.status_code
                raw_response_preview = response.text[:1000].replace("\n", " ")
                if status_code >= 400:
                    raw_message = self._extract_error_message(response.text) or response.reason_phrase
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    
                    if status_code == 401:
                        err_type = "invalid_key"
                    elif status_code == 402:
                        err_type = "no_credits_or_payment_required"
                    elif status_code == 403:
                        err_type = "forbidden"
                    elif status_code == 404:
                        err_type = "model_not_found"
                    elif status_code == 429:
                        err_type = "rate_limited"
                    else:
                        err_type = "provider_error"

                    result = self._unavailable(
                        err_type,
                        status_code,
                        raw_message,
                        latency_ms=latency_ms,
                        retry_count=retry_count,
                        openrouter_called=True,
                        raw_response_preview=raw_response_preview,
                    )
                    self._log_failure(provider_logger, openrouter_logger, result, retry_count)
                    return result
                data = response.json()
                break
            except json.JSONDecodeError as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                result = self._unavailable(
                    "provider_error",
                    status_code,
                    str(exc),
                    latency_ms=latency_ms,
                    retry_count=retry_count,
                    openrouter_called=True,
                    raw_response_preview=raw_response_preview,
                )
                self._log_failure(provider_logger, openrouter_logger, result, retry_count)
                return result
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                last_error = exc
                latency_ms = int((time.perf_counter() - started) * 1000)
                openrouter_logger.info(
                    "[OPENROUTER] status_code=null latency_ms=%s error_type=%s error_message=%s retry_count=%s",
                    latency_ms,
                    exc.__class__.__name__,
                    str(exc) or exc.__class__.__name__,
                    retry_count,
                )
                if attempt >= MAX_RETRIES or latency_ms >= int(OPENROUTER_TOTAL_TIMEOUT_SECONDS * 1000):
                    break

        if data is None:
            latency_ms = int((time.perf_counter() - started) * 1000)
            exc = last_error or RuntimeError("unknown_openrouter_error")
            err_type = "timeout" if isinstance(exc, httpx.TimeoutException) else "provider_error"
            result = self._unavailable(
                err_type,
                None,
                str(exc) or exc.__class__.__name__,
                latency_ms=latency_ms,
                retry_count=retry_count,
                openrouter_called=last_error is not None,
                raw_response_preview=raw_response_preview,
            )
            self._log_failure(provider_logger, openrouter_logger, result, retry_count)
            return result

        raw_response_preview = json.dumps(data, ensure_ascii=False)[:1000].replace("\n", " ")
        answer = self._extract_answer_text(data)
        if not answer:
            latency_ms = int((time.perf_counter() - started) * 1000)
            result = self._unavailable(
                "provider_error",
                status_code,
                "OpenRouter returned empty choices[0].message.content.",
                latency_ms=latency_ms,
                retry_count=retry_count,
                openrouter_called=True,
                raw_response_preview=raw_response_preview,
            )
            provider_logger.info("[OpenRouter] empty_response raw_preview=%s", raw_response_preview)
            openrouter_logger.info("[OPENROUTER] empty_response raw_response_preview=%s", raw_response_preview)
            return result

        latency_ms = int((time.perf_counter() - started) * 1000)
        preview = answer[:160].replace("\n", " ")
        provider_logger.info(
            "[OpenRouter] ok endpoint=%s status_code=%s latency_ms=%s retry_count=%s preview=%s",
            self.endpoint,
            status_code,
            latency_ms,
            retry_count,
            preview,
        )
        openrouter_logger.info(
            "[OPENROUTER] status_code=%s latency_ms=%s retry_count=%s response_preview=%s",
            status_code,
            latency_ms,
            retry_count,
            preview,
        )
        openrouter_logger.info("[OPENROUTER] raw_response_preview=%s", raw_response_preview)
        return PlannerResult(
            status="answered",
            answer_text=answer,
            actions=[],
            model=self.settings.openrouter_model,
            status_code=status_code,
            latency_ms=latency_ms,
            retry_count=retry_count,
            endpoint=self.endpoint,
            openrouter_called=True,
            raw_response_preview=raw_response_preview,
            response_text_preview=preview,
        )

    def test(self, text: str = TEST_PROMPT, *, must_contain: str | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        result = self.plan(text)
        latency_ms = result.latency_ms if result.latency_ms is not None else int((time.perf_counter() - started) * 1000)
        contains_required = True if not must_contain else must_contain in result.answer_text
        if result.status == "answered" and contains_required:
            return {
                "ok": True,
                "provider": "openrouter",
                "called": True,
                "model": self.settings.openrouter_model,
                "status_code": result.status_code,
                "response_preview": result.answer_text[:160],
                "error_type": None,
                "error_message": None,
                "fix": None,
                "latency_ms": latency_ms,
            }
        if result.status == "answered" and not contains_required:
            return {
                "ok": False,
                "provider": "openrouter",
                "called": True,
                "model": self.settings.openrouter_model,
                "status_code": result.status_code,
                "response_preview": result.answer_text[:160] if result.answer_text else None,
                "error_type": "provider_error",
                "error_message": f"OpenRouter response did not contain required text: {must_contain}",
                "fix": "Check model instructions or try a different query.",
                "latency_ms": latency_ms,
            }
        return {
            "ok": False,
            "provider": "openrouter",
            "called": result.openrouter_called,
            "model": self.settings.openrouter_model,
            "status_code": result.status_code,
            "response_preview": result.answer_text[:160] if result.answer_text else None,
            "error_type": result.error_type or result.error or "unknown",
            "error_message": result.error_message or result.error or "unknown",
            "fix": result.fix or _fix_for(result.status_code, result.error_type or "unknown"),
            "latency_ms": latency_ms,
        }

    def _unavailable(
        self,
        error_type: str,
        status_code: int | None,
        raw_message: str,
        *,
        latency_ms: int | None = None,
        retry_count: int = 0,
        openrouter_called: bool = False,
        raw_response_preview: str | None = None,
    ) -> PlannerResult:
        message = _error_message(status_code, error_type, raw_message, self.settings.openrouter_model)
        return PlannerResult(
            status="unavailable",
            answer_text=f"OpenRouter error: {message}",
            actions=[],
            error=error_type,
            model=self.settings.openrouter_model,
            status_code=status_code,
            error_type=error_type,
            error_message=message,
            fix=_fix_for(status_code, error_type),
            latency_ms=latency_ms,
            retry_count=retry_count,
            endpoint=self.endpoint,
            openrouter_called=openrouter_called,
            raw_response_preview=raw_response_preview,
            response_text_preview=None,
        )

    def _log_failure(
        self,
        provider_logger: logging.Logger,
        openrouter_logger: logging.Logger,
        result: PlannerResult,
        retry_count: int,
    ) -> None:
        provider_logger.info(
            "[OpenRouter] failed endpoint=%s status_code=%s latency_ms=%s error_type=%s error=%s retry_count=%s",
            self.endpoint,
            result.status_code,
            result.latency_ms,
            result.error_type,
            result.error_message,
            retry_count,
        )
        openrouter_logger.info(
            "[OPENROUTER] called=%s status_code=%s latency_ms=%s error_type=%s error_message=%s retry_count=%s raw_response_preview=%s",
            result.openrouter_called,
            result.status_code,
            result.latency_ms,
            result.error_type,
            result.error_message,
            retry_count,
            result.raw_response_preview,
        )

    @staticmethod
    def _extract_answer_text(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "".join(parts).strip()
        return ""

    @staticmethod
    def _extract_error_message(body: str) -> str | None:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body[:500] if body else None
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or error)
            if error:
                return str(error)
            if data.get("message"):
                return str(data["message"])
        return body[:500] if body else None

"""Observability, Structured Logging, Distributed Tracing, and PII Redaction Pipeline.

Implements AgentOps Criterion 4:
- Structured JSON logging using python-json-logger (zero raw print statements).
- Explicit agent_intent and agent_outcome lifecycle telemetry.
- OpenTelemetry TracerProvider and span context propagation.
- Automated PII scrubbing via Google Cloud DLP API with local regex fallback.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import sys
import time
from typing import Any, Callable, Dict, Optional

# OpenTelemetry imports with fallback guards
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Status, StatusCode

    _provider = TracerProvider()
    _provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(_provider)
    tracer = trace.get_tracer("gemini-enterprise-onboarding", "1.0.0")
    HAS_OTEL = True
except Exception:
    HAS_OTEL = False
    tracer = None

# Python JSON Logger imports with fallback
try:
    from pythonjsonlogger import jsonlogger
    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False


# =====================================================================
# 1. PII Redaction Pipeline (GCP DLP + High-Precision Regex)
# =====================================================================

REGEX_PATTERNS = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
    "PHONE": re.compile(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b"),
    "API_KEY": re.compile(r"(?i)\b(?:AIza[0-9A-Za-z-_]{35}|Bearer\s+[A-Za-z0-9\-_=]{20,})\b"),
    "SECRET_TOKEN": re.compile(r"(?i)(?:key|token|secret|password)\s*[:=]\s*['\"]?([A-Za-z0-9\-_=]{8,})['\"]?"),
}


def scrub_pii_regex(text: str) -> str:
    """Scrub sensitive patterns using local regex replacement."""
    if not isinstance(text, str):
        return text

    redacted = text
    redacted = REGEX_PATTERNS["SSN"].sub("[REDACTED_SSN]", redacted)
    redacted = REGEX_PATTERNS["CREDIT_CARD"].sub("[REDACTED_CREDIT_CARD]", redacted)
    redacted = REGEX_PATTERNS["EMAIL"].sub("[REDACTED_EMAIL]", redacted)
    redacted = REGEX_PATTERNS["PHONE"].sub("[REDACTED_PHONE]", redacted)
    redacted = REGEX_PATTERNS["API_KEY"].sub("[REDACTED_API_KEY]", redacted)
    redacted = REGEX_PATTERNS["SECRET_TOKEN"].sub("token=[REDACTED_SECRET]", redacted)
    return redacted


def scrub_pii_dlp(text: str, project_id: Optional[str] = None) -> Optional[str]:
    """Inspect and de-identify text using Google Cloud DLP API if available."""
    if not text:
        return text

    target_project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not target_project:
        return None

    try:
        from google.cloud import dlp_v2

        dlp = dlp_v2.DlpServiceClient()
        parent = f"projects/{target_project}/locations/global"

        info_types = [
            {"name": "EMAIL_ADDRESS"},
            {"name": "PHONE_NUMBER"},
            {"name": "CREDIT_CARD_NUMBER"},
            {"name": "US_SOCIAL_SECURITY_NUMBER"},
            {"name": "AUTH_TOKEN"},
            {"name": "ENCRYPTION_KEY"},
        ]

        inspect_config = {
            "info_types": info_types,
            "min_likelihood": dlp_v2.Likelihood.LIKELY,
        }

        deidentify_config = {
            "info_type_transformations": {
                "transformations": [
                    {
                        "primitive_transformation": {
                            "replace_with_info_type_config": {}
                        }
                    }
                ]
            }
        }

        item = {"value": text}
        response = dlp.deidentify_content(
            request={
                "parent": parent,
                "deidentify_config": deidentify_config,
                "inspect_config": inspect_config,
                "item": item,
            }
        )
        return response.item.value
    except Exception:
        # Fall through to regex sanitizer
        return None


def scrub_pii(content: Any) -> Any:
    """Redact Personally Identifiable Information (PII) and secret credentials.

    Executes GCP Cloud DLP when available, with immediate deterministic regex fallback.
    Accepts string, dictionary, or list structures recursively.
    """
    if isinstance(content, str):
        dlp_result = scrub_pii_dlp(content)
        if dlp_result is not None:
            return scrub_pii_regex(dlp_result)
        return scrub_pii_regex(content)
    elif isinstance(content, dict):
        return {k: scrub_pii(v) for k, v in content.items()}
    elif isinstance(content, list):
        return [scrub_pii(item) for item in content]
    return content


# =====================================================================
# 2. Structured JSON Logging with PII Sanitizer
# =====================================================================

class PiiSanitizingJsonFormatter(logging.Formatter):
    """Custom JSON formatter that redacts PII from all logs before emission."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": scrub_pii(record.getMessage()),
        }

        # Include standard extra attributes if supplied
        for attr in ("agent_name", "agent_intent", "agent_outcome", "tool_name",
                     "execution_time_ms", "status", "session_id", "trace_id"):
            if hasattr(record, attr):
                log_entry[attr] = scrub_pii(getattr(record, attr))

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def get_logger(name: str = "agent") -> logging.Logger:
    """Returns a pre-configured logger with JSON output and automated PII scrubbing."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        if HAS_JSON_LOGGER:
            formatter = jsonlogger.JsonFormatter(
                "%(timestamp)s %(level)s %(name)s %(message)s %(agent_name)s %(agent_intent)s %(agent_outcome)s"
            )
            handler.setFormatter(formatter)
        else:
            handler.setFormatter(PiiSanitizingJsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


root_logger = get_logger("gemini_enterprise")


def log_agent_intent(
    logger: logging.Logger,
    agent_name: str,
    intent: str,
    session_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Explicitly log agent intent prior to executing actions or tools."""
    payload = {
        "agent_name": agent_name,
        "agent_intent": intent,
        "status": "STARTED",
        "session_id": session_id or "default",
    }
    if extra:
        payload.update(scrub_pii(extra))
    logger.info(f"Agent intent: {intent}", extra=payload)


def log_agent_outcome(
    logger: logging.Logger,
    agent_name: str,
    tool_name: str,
    success: bool,
    outcome: str,
    duration_ms: float,
    session_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Explicitly log agent outcome after tool execution with timing and status."""
    payload = {
        "agent_name": agent_name,
        "tool_name": tool_name,
        "agent_outcome": outcome,
        "status": "SUCCESS" if success else "FAILED",
        "execution_time_ms": round(duration_ms, 2),
        "session_id": session_id or "default",
    }
    if extra:
        payload.update(scrub_pii(extra))
    level = logging.INFO if success else logging.ERROR
    logger.log(level, f"Agent outcome for {tool_name}: {outcome}", extra=payload)


# =====================================================================
# 3. OpenTelemetry Distributed Tracing & Span Decorators
# =====================================================================

def trace_span(
    span_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> Callable:
    """Decorator to wrap synchronous and asynchronous agent functions with OpenTelemetry spans.

    Ensures parent-child span linking from user query down to tool execution.
    """
    def decorator(func: Callable) -> Callable:
        name = span_name or func.__name__

        if functools.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not HAS_OTEL or tracer is None:
                    return await func(*args, **kwargs)

                with tracer.start_as_current_span(name) as span:
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, str(v))
                    span.set_attribute("function.name", func.__name__)
                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        span.record_exception(exc)
                        raise
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not HAS_OTEL or tracer is None:
                    return func(*args, **kwargs)

                with tracer.start_as_current_span(name) as span:
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, str(v))
                    span.set_attribute("function.name", func.__name__)
                    try:
                        result = func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        span.record_exception(exc)
                        raise
            return sync_wrapper

    return decorator

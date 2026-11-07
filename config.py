"""Runtime configuration for Gemini Enterprise Deployment & AI Onboarding Prep.

Centralizes project identification, model routing endpoints, security flags,
and persistence settings across coordinator and specialist subagents.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class AppConfig:
    """Immutable application settings with sensible enterprise defaults."""

    # Google Cloud Project & Region
    project_id: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", "gemini-enterprise-onboarding")
    )
    region: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
    )

    # Secret Manager configuration
    gemini_api_key_secret_name: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY_SECRET_NAME", "gemini-api-key")
    )
    secret_version: str = field(
        default_factory=lambda: os.getenv("SECRET_VERSION", "latest")
    )

    # Strategic Model Routing (Gemini 2.5 Pro for planning, 2.5 Flash for subagents)
    coordinator_model: str = field(
        default_factory=lambda: os.getenv("COORDINATOR_MODEL", "gemini-2.5-pro")
    )
    discovery_model: str = field(
        default_factory=lambda: os.getenv("DISCOVERY_MODEL", "gemini-2.5-flash")
    )
    specialist_model: str = field(
        default_factory=lambda: os.getenv("SPECIALIST_MODEL", "gemini-2.5-flash")
    )

    # Storage and Persistence
    firestore_database: str = field(
        default_factory=lambda: os.getenv("FIRESTORE_DATABASE", "(default)")
    )
    firestore_collection: str = field(
        default_factory=lambda: os.getenv("FIRESTORE_COLLECTION", "gemini_onboarding_sessions")
    )
    local_storage_dir: str = field(
        default_factory=lambda: os.getenv("LOCAL_STORAGE_DIR", "./sessions_local")
    )

    # Security & Guardrails
    enable_model_armor: bool = field(
        default_factory=lambda: os.getenv("ENABLE_MODEL_ARMOR", "true").lower() == "true"
    )
    require_human_confirmation: bool = field(
        default_factory=lambda: os.getenv("REQUIRE_HUMAN_CONFIRMATION", "true").lower() == "true"
    )
    dlp_min_likelihood: str = field(
        default_factory=lambda: os.getenv("DLP_MIN_LIKELIHOOD", "LIKELY")
    )

    # Compaction & Context Window
    max_history_turns: int = field(
        default_factory=lambda: int(os.getenv("MAX_HISTORY_TURNS", "10"))
    )
    token_truncation_limit: int = field(
        default_factory=lambda: int(os.getenv("TOKEN_TRUNCATION_LIMIT", "8192"))
    )


# Global singleton instance
config = AppConfig()

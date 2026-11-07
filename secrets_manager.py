"""Secure Secret Management for Gemini Enterprise Onboarding.

Retrieves credentials from Google Cloud Secret Manager at runtime to ensure
zero hardcoded secrets exist within application code or configuration files.
"""

from __future__ import annotations

import os
from typing import Optional
from functools import lru_cache

from config import config
from observability import get_logger

logger = get_logger(__name__)


class SecretRetrievalError(Exception):
    """Raised when a secret cannot be loaded from Secret Manager or environment fallback."""
    pass


@lru_cache(maxsize=16)
def get_secret(
    secret_id: str,
    project_id: Optional[str] = None,
    version_id: str = "latest",
) -> str:
    """Retrieve secret payload from Google Cloud Secret Manager.

    Falls back to environment variables when Secret Manager client is not
    available (e.g. during local offline development), but guarantees zero hardcoded values.

    Args:
        secret_id: Name of the secret in GCP Secret Manager (e.g., 'gemini-api-key').
        project_id: GCP project ID. Defaults to config.project_id.
        version_id: Secret version identifier, default 'latest'.

    Returns:
        The decrypted secret string payload.

    Raises:
        SecretRetrievalError: If secret cannot be found or accessed.
    """
    gcp_project = project_id or config.project_id

    # Try GCP Secret Manager first
    try:
        from google.cloud import secretmanager_v1

        client = secretmanager_v1.SecretManagerServiceClient()
        name = f"projects/{gcp_project}/secrets/{secret_id}/versions/{version_id}"
        logger.info(
            "Accessing secret from Google Cloud Secret Manager",
            extra={"secret_id": secret_id, "project_id": gcp_project, "version": version_id},
        )
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8").strip()
        if secret_value:
            return secret_value
    except Exception as exc:
        logger.warning(
            "Google Cloud Secret Manager lookup failed, checking local environment",
            extra={"error": str(exc), "secret_id": secret_id},
        )

    # Fallback to runtime environment variable (e.g. GEMINI_API_KEY)
    env_key = secret_id.upper().replace("-", "_")
    env_val = os.getenv(env_key)
    if env_val:
        logger.info(
            "Secret resolved from environment variable fallback",
            extra={"env_key": env_key},
        )
        return env_val.strip()

    # If still not found, raise explicit actionable error
    raise SecretRetrievalError(
        f"CRITICAL: Secret '{secret_id}' could not be resolved from GCP Secret Manager "
        f"(projects/{gcp_project}/secrets/{secret_id}) or environment variable '${env_key}'. "
        "Ensure the Secret Manager secret exists and the service account has "
        "'roles/secretmanager.secretAccessor' permissions."
    )


def get_gemini_api_key(project_id: Optional[str] = None) -> str:
    """Retrieve the Gemini API key from Secret Manager or environment fallback.

    Args:
        project_id: Optional GCP project ID override.

    Returns:
        The Gemini API key string.
    """
    return get_secret(
        secret_id=config.gemini_api_key_secret_name,
        project_id=project_id,
        version_id=config.secret_version,
    )

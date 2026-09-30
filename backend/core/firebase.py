"""Firebase Admin bootstrap and ID-token verification.

Responsibilities
----------------
* Lazily initialise the default Firebase Admin app (idempotent, so uvicorn's
  ``--reload`` re-import does not raise "duplicate app").
* Verify an incoming Firebase ID token and turn it into a trusted
  :class:`~backend.core.auth.AuthenticatedUser`.

Role safety (Section 13.2)
--------------------------
The role is read **only** from the verified token's custom claims (or the
Firestore user document). A role supplied in a request body or query string is
never trusted - :func:`verify_id_token` is the single entry point and it only
accepts a bearer token.
"""

from __future__ import annotations

import functools
from typing import Any

from backend.core.config import get_settings
from backend.core.errors import InvalidTokenError, ProviderUnavailableError
from backend.core.logging import get_logger

logger = get_logger(__name__)

ROLE_CLAIM = "role"
FARM_IDS_CLAIM = "farm_ids"
LANGUAGE_CLAIM = "language"

# Roles defined in Section 12.1 / Section 7 M1.
ROLE_FARMER = "farmer"
ROLE_OFFICER = "officer"
ROLE_ADMIN = "admin"
VALID_ROLES = frozenset({ROLE_FARMER, ROLE_OFFICER, ROLE_ADMIN})


@functools.lru_cache(maxsize=1)
def get_firebase_app() -> Any:
    """Initialise and return the default Firebase Admin app.

    Raises :class:`ProviderUnavailableError` if credentials are not configured.
    """
    settings = get_settings()
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ProviderUnavailableError(
            "firebase-admin is not installed in this environment."
        ) from exc

    try:
        return firebase_admin.get_app()
    except ValueError:
        pass  # not initialised yet

    options: dict[str, Any] = {"projectId": settings.effective_project_id}
    cred = None
    if settings.google_application_credentials:
        cred = credentials.Certificate(settings.google_application_credentials)
        options["credential"] = cred
    elif settings.gcp_project_id:
        # Fall back to Application Default Credentials when running on GCP.
        options["credential"] = credentials.ApplicationDefault()

    try:
        return firebase_admin.initialize_app(options=options)
    except Exception as exc:  # pragma: no cover - needs real credentials
        logger.error("firebase_initialisation_failed", extra={"error_type": type(exc).__name__})
        raise ProviderUnavailableError(
            "Firebase is not configured. Set FIREBASE_PROJECT_ID and "
            "GOOGLE_APPLICATION_CREDENTIALS, or run with MOCK_SERVICES=true."
        ) from exc


def firestore_client() -> Any:
    """Return a Firestore client bound to the default Firebase app."""
    from firebase_admin import firestore

    get_firebase_app()
    return firestore.client()


def verify_id_token(id_token: str) -> dict[str, Any]:
    """Verify a Firebase ID token and return its decoded claims.

    Raises :class:`InvalidTokenError` for anything the SDK rejects.
    """
    try:
        from firebase_admin import auth
    except ImportError as exc:  # pragma: no cover
        raise ProviderUnavailableError("firebase-admin is not installed.") from exc

    get_firebase_app()
    try:
        return auth.verify_id_token(id_token, check_revoked=False)
    except Exception as exc:
        # The SDK's message can contain token internals; keep it server-side.
        logger.info("id_token_rejected", extra={"error_type": type(exc).__name__})
        raise InvalidTokenError("Authentication token is missing, expired or invalid.") from exc


def normalize_role(role: object) -> str:
    """Coerce a claim into a known role, defaulting to the most restrictive."""
    if isinstance(role, str):
        candidate = role.strip().lower()
        if candidate in VALID_ROLES:
            return candidate
    return ROLE_FARMER

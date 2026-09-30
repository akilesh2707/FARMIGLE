"""Authentication and role enforcement.

Three reusable FastAPI dependencies:

* :func:`get_current_user`  - any authenticated user
* :func:`require_farmer`    - role ``farmer`` (or ``admin``)
* :func:`require_officer`   - role ``officer`` (or ``admin``)

Trust model
-----------
The role always comes from the **verified** Firebase ID token (custom claims),
optionally refined by the user's Firestore document. It is never read from a
request body, query parameter or header that a client can set freely.

In ``MOCK_SERVICES=true`` mode a small set of fixed development tokens is
accepted so the API can be exercised without a Firebase project. Those tokens
are refused entirely when ``MOCK_SERVICES=false``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.config import Settings, get_settings
from backend.core.errors import ForbiddenError, UnauthenticatedError
from backend.core.firebase import (
    FARM_IDS_CLAIM,
    LANGUAGE_CLAIM,
    ROLE_ADMIN,
    ROLE_CLAIM,
    ROLE_FARMER,
    ROLE_OFFICER,
    normalize_role,
    verify_id_token,
)
from backend.core.logging import get_logger

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False, description="Firebase ID token")

# Fixed development identities used only in mock mode. Documented in README so
# they are never mistaken for real authentication.
DEV_TOKENS: dict[str, dict[str, Any]] = {
    "dev-farmer-token": {
        "uid": "dev_farmer_001",
        "email": "farmer@demo.invalid",
        "name": "Demo Farmer",
        "role": ROLE_FARMER,
        "language": "ta",
    },
    "dev-officer-token": {
        "uid": "dev_officer_001",
        "email": "officer@demo.invalid",
        "name": "Demo Agricultural Officer",
        "role": ROLE_OFFICER,
        "language": "en",
    },
}


@dataclass(frozen=True)
class AuthenticatedUser:
    """Trusted identity derived from a verified token."""

    uid: str
    role: str
    claims: dict[str, Any] = field(default_factory=dict)
    email: str | None = None
    display_name: str | None = None
    language: str | None = None
    farm_ids: list[str] = field(default_factory=list)
    simulated: bool = False

    @property
    def is_officer(self) -> bool:
        return self.role in (ROLE_OFFICER, ROLE_ADMIN)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_farmer(self) -> bool:
        return self.role in (ROLE_FARMER, ROLE_ADMIN)

    def can_access_farm(self, farm: dict[str, Any]) -> bool:
        """Officers/admins see any farm; a farmer sees only their own.

        Ownership falls back to the ``farm_ids`` custom claim because a farmer
        document may not exist yet on first login.
        """
        if self.is_officer:
            return True
        owner = farm.get("owner_uid")
        if owner and owner == self.uid:
            return True
        if owner:
            return False
        farm_id = farm.get("farm_id")
        return bool(farm_id and farm_id in self.farm_ids)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "role": self.role,
            "language": self.language,
            "display_name": self.display_name,
        }


def _user_from_claims(claims: dict[str, Any], *, simulated: bool = False) -> AuthenticatedUser:
    farm_ids = claims.get(FARM_IDS_CLAIM) or []
    if not isinstance(farm_ids, list):
        farm_ids = []
    return AuthenticatedUser(
        uid=str(claims.get("uid") or claims.get("sub") or ""),
        role=normalize_role(claims.get(ROLE_CLAIM)),
        claims=claims,
        email=claims.get("email"),
        display_name=claims.get("name") or claims.get("display_name"),
        language=claims.get(LANGUAGE_CLAIM) or claims.get("language"),
        farm_ids=[str(item) for item in farm_ids],
        simulated=simulated,
    )


def authenticate_token(
    token: str,
    settings: Settings | None = None,
    repository: Any | None = None,
) -> AuthenticatedUser:
    """Resolve a bearer token into a trusted :class:`AuthenticatedUser`."""
    resolved = settings or get_settings()

    if resolved.mock_services:
        dev_identity = DEV_TOKENS.get(token)
        if dev_identity is not None:
            return _user_from_claims(dev_identity, simulated=True)
        raise UnauthenticatedError(
            "Mock mode is enabled: use one of the documented development tokens "
            "(dev-farmer-token, dev-officer-token) or set MOCK_SERVICES=false."
        )

    claims = verify_id_token(token)
    user = _user_from_claims(claims)

    # A Firestore user document may carry a role the token lacks.
    if repository is not None:
        try:
            document = repository.get_user(user.uid)
        except Exception:  # pragma: no cover - never fail auth on a read error
            document = None
        if document:
            from backend.core.firebase import normalize_role as _normalize

            user = AuthenticatedUser(
                uid=user.uid,
                role=_normalize(document.get("role", user.role)),
                claims=user.claims,
                email=user.email or document.get("email"),
                display_name=user.display_name or document.get("display_name"),
                language=document.get("language") or user.language,
                farm_ids=[str(item) for item in document.get("farm_ids", user.farm_ids)],
                simulated=user.simulated,
            )
    return user


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    """Resolve the caller, or raise 401."""
    if credentials is None or not credentials.credentials:
        raise UnauthenticatedError("Authorization header with a bearer token is required.")
    repository = getattr(request.app.state, "container", None)
    repository = getattr(repository, "repository", None)
    user = authenticate_token(credentials.credentials, repository=repository)
    request.app.state.current_user = user
    return user


async def require_farmer(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if not user.is_farmer:
        raise ForbiddenError("This endpoint requires the 'farmer' role.")
    return user


async def require_officer(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    if not user.is_officer:
        raise ForbiddenError("This endpoint requires the 'officer' role.")
    return user


async def require_authenticated(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    return user


__all__ = [
    "AuthenticatedUser",
    "DEV_TOKENS",
    "ROLE_ADMIN",
    "ROLE_FARMER",
    "ROLE_OFFICER",
    "authenticate_token",
    "bearer_scheme",
    "get_current_user",
    "require_authenticated",
    "require_farmer",
    "require_officer",
]

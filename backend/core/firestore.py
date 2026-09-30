"""Persistence layer.

The rest of the backend only ever talks to the :class:`Repository` protocol.
Two implementations satisfy it:

* :class:`FirestoreRepository` - production, uses the Firestore layout from
  Section 12.1 of the documentation.
* :class:`InMemoryRepository` - local/demo mode (``MOCK_SERVICES=true``) and
  unit tests. Same semantics, same sort order, no network.

Because both share the protocol, the API layer, the analysis orchestrator and
the tests are identical in local and production runs.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

from backend.core.errors import FarmNotFoundError, ObservationNotFoundError
from backend.core.logging import get_logger
from backend.core.utils import utc_now_iso

logger = get_logger(__name__)

FARMER_OBSERVATION_PREFIX = "observations"
FARMER_ZONE_RESULTS = "zoneResults"
FARMER_RECOMMENDATIONS = "recommendations"

FARMS_COLLECTION = "farms"
USERS_COLLECTION = "users"


def field_filter(field: str, op: str, value: Any) -> Any:
    """Lazily import Firestore's FieldFilter so the module imports without GCP."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    return FieldFilter(field, op, value)


def _sort_key_analyzed(document: dict[str, Any]) -> tuple[str, str]:
    """Total ordering for zone results so "latest" is never ambiguous."""
    return (str(document.get("analyzed_at", "")), str(document.get("run_id", "")))


@runtime_checkable
class Repository(Protocol):
    """Persistence contract for the whole backend."""

    # -- users -------------------------------------------------------------
    def get_user(self, uid: str) -> dict[str, Any] | None: ...

    def upsert_user(self, uid: str, data: dict[str, Any]) -> dict[str, Any]: ...

    # -- farms -------------------------------------------------------------
    def create_farm(self, farm: dict[str, Any]) -> dict[str, Any]: ...

    def get_farm(self, farm_id: str) -> dict[str, Any] | None: ...

    def list_farms(
        self,
        *,
        owner_uid: str | None = None,
        district_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]: ...

    def update_farm(self, farm_id: str, updates: dict[str, Any]) -> dict[str, Any] | None: ...

    def delete_farm(self, farm_id: str) -> bool: ...

    # -- observations ------------------------------------------------------
    def create_observation(self, farm_id: str, observation: dict[str, Any]) -> dict[str, Any]: ...

    def get_observation(self, farm_id: str, observation_id: str) -> dict[str, Any] | None: ...

    def list_observations(
        self,
        farm_id: str,
        *,
        zone_id: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]: ...

    def delete_observation(self, farm_id: str, observation_id: str) -> bool: ...

    # -- zone results ------------------------------------------------------
    def save_zone_result(self, farm_id: str, result: dict[str, Any]) -> dict[str, Any]: ...

    def list_zone_results(
        self, farm_id: str, *, zone_id: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]: ...

    def latest_zone_results(self, farm_id: str) -> dict[str, dict[str, Any]]: ...

    def delete_zone_results_for_run(self, farm_id: str, run_id: str) -> int: ...

    # -- recommendations ---------------------------------------------------
    def create_recommendation(self, farm_id: str, recommendation: dict[str, Any]) -> dict[str, Any]: ...

    def list_recommendations(
        self, farm_id: str, *, zone_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]: ...


class InMemoryRepository:
    """Dict-backed :class:`Repository` for local development and tests.

    Deliberately simple and synchronous; it is a development stand-in, not a
    production datastore.
    """

    is_mock = True

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._users: dict[str, dict[str, Any]] = {}
        self._farms: dict[str, dict[str, Any]] = {}
        self._observations: dict[str, dict[str, dict[str, Any]]] = {}
        self._zone_results: dict[str, dict[str, dict[str, Any]]] = {}
        self._recommendations: dict[str, dict[str, dict[str, Any]]] = {}

    # -- users -------------------------------------------------------------
    def get_user(self, uid: str) -> dict[str, Any] | None:
        with self._lock:
            document = self._users.get(uid)
            return dict(document) if document else None

    def upsert_user(self, uid: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            existing = self._users.get(uid, {})
            merged = {**existing, **data, "uid": uid, "updated_at": utc_now_iso()}
            merged.setdefault("created_at", utc_now_iso())
            self._users[uid] = merged
            return dict(merged)

    # -- farms -------------------------------------------------------------
    def create_farm(self, farm: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            farm_id = farm["farm_id"]
            self._farms[farm_id] = dict(farm)
            self._observations.setdefault(farm_id, {})
            self._zone_results.setdefault(farm_id, {})
            self._recommendations.setdefault(farm_id, {})
            return dict(farm)

    def get_farm(self, farm_id: str) -> dict[str, Any] | None:
        with self._lock:
            document = self._farms.get(farm_id)
            return dict(document) if document else None

    def list_farms(
        self,
        *,
        owner_uid: str | None = None,
        district_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._lock:
            farms = list(self._farms.values())
        if owner_uid is not None:
            farms = [farm for farm in farms if farm.get("owner_uid") == owner_uid]
        if district_id is not None:
            farms = [farm for farm in farms if farm.get("district_id") == district_id]
        farms.sort(key=lambda farm: (str(farm.get("created_at", "")), str(farm.get("farm_id", ""))))
        return [dict(farm) for farm in farms[:limit]]

    def update_farm(self, farm_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            existing = self._farms.get(farm_id)
            if existing is None:
                return None
            merged = {**existing, **updates, "farm_id": farm_id, "updated_at": utc_now_iso()}
            self._farms[farm_id] = merged
            return dict(merged)

    def delete_farm(self, farm_id: str) -> bool:
        with self._lock:
            self._observations.pop(farm_id, None)
            self._zone_results.pop(farm_id, None)
            self._recommendations.pop(farm_id, None)
            return self._farms.pop(farm_id, None) is not None

    # -- observations ------------------------------------------------------
    def create_observation(self, farm_id: str, observation: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            bucket = self._observations.setdefault(farm_id, {})
            bucket[observation["observation_id"]] = dict(observation)
            return dict(observation)

    def get_observation(self, farm_id: str, observation_id: str) -> dict[str, Any] | None:
        with self._lock:
            document = self._observations.get(farm_id, {}).get(observation_id)
            return dict(document) if document else None

    def list_observations(
        self,
        farm_id: str,
        *,
        zone_id: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._lock:
            documents = list(self._observations.get(farm_id, {}).values())
        if zone_id is not None:
            documents = [doc for doc in documents if doc.get("zone_id") == zone_id]
        if source is not None:
            documents = [doc for doc in documents if doc.get("source") == source]
        documents.sort(
            key=lambda doc: (str(doc.get("timestamp", "")), str(doc.get("observation_id", ""))),
            reverse=True,
        )
        return [dict(doc) for doc in documents[:limit]]

    def delete_observation(self, farm_id: str, observation_id: str) -> bool:
        with self._lock:
            return self._observations.get(farm_id, {}).pop(observation_id, None) is not None

    # -- zone results ------------------------------------------------------
    def save_zone_result(self, farm_id: str, result: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            bucket = self._zone_results.setdefault(farm_id, {})
            bucket[result["zone_result_id"]] = dict(result)
            return dict(result)

    def list_zone_results(
        self, farm_id: str, *, zone_id: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        with self._lock:
            documents = list(self._zone_results.get(farm_id, {}).values())
        if zone_id is not None:
            documents = [doc for doc in documents if doc.get("zone_id") == zone_id]
        documents.sort(key=_sort_key_analyzed, reverse=True)
        return [dict(doc) for doc in documents[:limit]]

    def latest_zone_results(self, farm_id: str) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for document in self.list_zone_results(farm_id, limit=10_000):
            zone_id = str(document.get("zone_id", ""))
            if zone_id and zone_id not in latest:
                latest[zone_id] = document
        return latest

    def delete_zone_results_for_run(self, farm_id: str, run_id: str) -> int:
        with self._lock:
            bucket = self._zone_results.get(farm_id, {})
            doomed = [key for key, doc in bucket.items() if doc.get("run_id") == run_id]
            for key in doomed:
                bucket.pop(key, None)
            return len(doomed)

    # -- recommendations ---------------------------------------------------
    def create_recommendation(self, farm_id: str, recommendation: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            bucket = self._recommendations.setdefault(farm_id, {})
            bucket[recommendation["recommendation_id"]] = dict(recommendation)
            return dict(recommendation)

    def list_recommendations(
        self, farm_id: str, *, zone_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        with self._lock:
            documents = list(self._recommendations.get(farm_id, {}).values())
        if zone_id is not None:
            documents = [doc for doc in documents if doc.get("zone_id") == zone_id]
        documents.sort(
            key=lambda doc: (
                str(doc.get("created_at", "")),
                str(doc.get("recommendation_id", "")),
            ),
            reverse=True,
        )
        return [dict(doc) for doc in documents[:limit]]

    # -- test helpers ------------------------------------------------------
    def clear(self) -> None:
        with self._lock:
            self._users.clear()
            self._farms.clear()
            self._observations.clear()
            self._zone_results.clear()
            self._recommendations.clear()


class FirestoreRepository:
    """Production repository backed by Firestore (Section 12.1).

    Collection layout::

        users/{uid}
        farms/{farm_id}
        farms/{farm_id}/observations/{observation_id}
        farms/{farm_id}/zoneResults/{zone_result_id}
        farms/{farm_id}/recommendations/{recommendation_id}
    """

    is_mock = False

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            from backend.core.firebase import firestore_client

            self._client = firestore_client()
        return self._client

    # -- users -------------------------------------------------------------
    def get_user(self, uid: str) -> dict[str, Any] | None:
        document = self.client.collection(USERS_COLLECTION).document(uid).get()
        return dict(document.to_dict()) if document.exists else None

    def upsert_user(self, uid: str, data: dict[str, Any]) -> dict[str, Any]:
        reference = self.client.collection(USERS_COLLECTION).document(uid)
        snapshot = reference.get()
        payload = dict(data)
        payload["updated_at"] = utc_now_iso()
        if not snapshot.exists:
            payload.setdefault("created_at", payload["updated_at"])
        reference.set(payload, merge=True)
        return {**(snapshot.to_dict() or {}), **payload, "uid": uid}

    # -- farms -------------------------------------------------------------
    def create_farm(self, farm: dict[str, Any]) -> dict[str, Any]:
        self.client.collection(FARMS_COLLECTION).document(farm["farm_id"]).set(dict(farm))
        return dict(farm)

    def get_farm(self, farm_id: str) -> dict[str, Any] | None:
        document = self.client.collection(FARMS_COLLECTION).document(farm_id).get()
        return dict(document.to_dict()) if document.exists else None

    def list_farms(
        self,
        *,
        owner_uid: str | None = None,
        district_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query: Any = self.client.collection(FARMS_COLLECTION)
        if owner_uid is not None:
            query = query.where(filter=field_filter("owner_uid", "==", owner_uid))
        if district_id is not None:
            query = query.where(filter=field_filter("district_id", "==", district_id))
        return [dict(doc.to_dict() or {}) for doc in query.limit(limit).get()]

    def update_farm(self, farm_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        reference = self.client.collection(FARMS_COLLECTION).document(farm_id)
        if not reference.get().exists:
            return None
        payload = {**updates, "updated_at": utc_now_iso()}
        reference.set(payload, merge=True)
        return {**(reference.get().to_dict() or {}), **payload}

    def delete_farm(self, farm_id: str) -> bool:
        document = self.client.collection(FARMS_COLLECTION).document(farm_id)
        if not document.get().exists:
            return False
        for collection in (FARMER_OBSERVATION_PREFIX, FARMER_ZONE_RESULTS, FARMER_RECOMMENDATIONS):
            subcollection = document.reference.collection(collection)
            for sub_document in subcollection.stream():
                sub_document.reference.delete()
        document.delete()
        return True

    # -- observations ------------------------------------------------------
    def _observations_ref(self, farm_id: str) -> Any:
        return self.client.collection(FARMS_COLLECTION).document(farm_id).collection(
            FARMER_OBSERVATION_PREFIX
        )

    def create_observation(self, farm_id: str, observation: dict[str, Any]) -> dict[str, Any]:
        self._observations_ref(farm_id).document(observation["observation_id"]).set(dict(observation))
        return dict(observation)

    def get_observation(self, farm_id: str, observation_id: str) -> dict[str, Any] | None:
        document = self._observations_ref(farm_id).document(observation_id).get()
        return dict(document.to_dict()) if document.exists else None

    def list_observations(
        self,
        farm_id: str,
        *,
        zone_id: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = self._observations_ref(farm_id).order_by("timestamp", direction="DESCENDING")
        if zone_id is not None:
            query = query.where(filter=field_filter("zone_id", "==", zone_id))
        if source is not None:
            query = query.where(filter=field_filter("source", "==", source))
        documents = [dict(doc.to_dict() or {}) for doc in query.limit(limit).get()]
        documents.sort(
            key=lambda doc: (str(doc.get("timestamp", "")), str(doc.get("observation_id", ""))),
            reverse=True,
        )
        return documents

    def delete_observation(self, farm_id: str, observation_id: str) -> bool:
        reference = self._observations_ref(farm_id).document(observation_id)
        if not reference.get().exists:
            return False
        reference.delete()
        return True

    # -- zone results ------------------------------------------------------
    def _zone_results_ref(self, farm_id: str) -> Any:
        return self.client.collection(FARMS_COLLECTION).document(farm_id).collection(
            FARMER_ZONE_RESULTS
        )

    def save_zone_result(self, farm_id: str, result: dict[str, Any]) -> dict[str, Any]:
        self._zone_results_ref(farm_id).document(result["zone_result_id"]).set(dict(result))
        return dict(result)

    def list_zone_results(
        self, farm_id: str, *, zone_id: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        query = self._zone_results_ref(farm_id).order_by("analyzed_at", direction="DESCENDING")
        if zone_id is not None:
            query = query.where(filter=field_filter("zone_id", "==", zone_id))
        documents = [dict(doc.to_dict() or {}) for doc in query.limit(limit).get()]
        documents.sort(key=_sort_key_analyzed, reverse=True)
        return documents

    def latest_zone_results(self, farm_id: str) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for document in self.list_zone_results(farm_id, limit=5_000):
            zone_id = str(document.get("zone_id", ""))
            if zone_id and zone_id not in latest:
                latest[zone_id] = document
        return latest

    def delete_zone_results_for_run(self, farm_id: str, run_id: str) -> int:
        reference = self._zone_results_ref(farm_id)
        deleted = 0
        for document in reference.stream():
            if document.to_dict().get("run_id") == run_id:
                document.reference.delete()
                deleted += 1
        return deleted

    # -- recommendations ---------------------------------------------------
    def _recommendations_ref(self, farm_id: str) -> Any:
        return self.client.collection(FARMS_COLLECTION).document(farm_id).collection(
            FARMER_RECOMMENDATIONS
        )

    def create_recommendation(self, farm_id: str, recommendation: dict[str, Any]) -> dict[str, Any]:
        self._recommendations_ref(farm_id).document(recommendation["recommendation_id"]).set(
            dict(recommendation)
        )
        return dict(recommendation)

    def list_recommendations(
        self, farm_id: str, *, zone_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        query = self._recommendations_ref(farm_id).order_by("created_at", direction="DESCENDING")
        if zone_id is not None:
            query = query.where(filter=field_filter("zone_id", "==", zone_id))
        documents = [dict(doc.to_dict() or {}) for doc in query.limit(limit).get()]
        documents.sort(
            key=lambda doc: (str(doc.get("created_at", "")), str(doc.get("recommendation_id", ""))),
            reverse=True,
        )
        return documents


# ---------------------------------------------------------------------------
# Guards used by the service layer
# ---------------------------------------------------------------------------


def require_farm(repository: Repository, farm_id: str) -> dict[str, Any]:
    farm = repository.get_farm(farm_id)
    if farm is None:
        raise FarmNotFoundError(f"Farm '{farm_id}' was not found.")
    return farm


def require_observation(repository: Repository, farm_id: str, observation_id: str) -> dict[str, Any]:
    observation = repository.get_observation(farm_id, observation_id)
    if observation is None:
        raise ObservationNotFoundError(
            f"Observation '{observation_id}' was not found for farm '{farm_id}'."
        )
    return observation


def build_repository(settings: Any | None = None) -> Repository:
    """Choose the repository implementation from settings."""
    from backend.core.config import get_settings

    resolved = settings or get_settings()
    if resolved.mock_services:
        return InMemoryRepository()
    return FirestoreRepository()

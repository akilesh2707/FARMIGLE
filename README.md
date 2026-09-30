# AI Farm Intelligence Network — Backend

A modular FastAPI monolith that turns orchard imagery into **harvest-priority
decisions**: per-zone ripeness and health, a risk level, a harvest window and a
recommended action, with a Tamil-first voice path and GeoJSON harvest maps.

```text
observation ──▶ perception (CV only) ──▶ fusion ──▶ risk ──▶ harvest rules ──▶ recommendation
   (phone/drone)     fruit, ripeness,        role-     health     status,         Gemini explains
                     health, quality         weighted  + codes    window, action  in the farmer's
                                                                          │      language
                                                          satellite/weather ─┘ (context only)
```

## The boundaries this system holds

These are the rules that keep the output honest, and each one has a test:

| Boundary | Why it exists |
| --- | --- |
| Perception is computer vision only. Gemini never sees an image. | A language model cannot count fruit. |
| Decisions come from the rules in `configs/thresholds/`, never from Gemini. | A threshold can be reviewed by an agronomist; a sampled generation cannot. |
| Gemini only *explains* facts the pipeline already decided. | Section 12.7 schema, validated on the way in and out. |
| Satellite vegetation indices are canopy context. They never produce a ripeness score. | NDVI cannot see a fruit. |
| Disease wording is always "possible indicator … requires local confirmation". | Avoids diagnosing a farm from a JPEG. |
| Missing evidence lowers confidence; it is never treated as zero. | A phone photo with no drone pass is not "unripe". |
| A zone with no imagery is `NO_DATA` / `health_status: unknown`. Context can raise the risk level, but it can never create a health finding or a crop action. | A rain forecast is not a disease. |
| Every zone result carries `heuristic_version` and `heuristic_validated: false`. | The thresholds are not validated against agronomist labels. |
| District hotspots are counts, never farmer identities. | Aggregation for extension officers. |

## Quick start (mock mode, no credentials)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # optional: the defaults already run in mock mode
.venv/bin/uvicorn backend.main:app --reload
```

Then open:

- <http://127.0.0.1:8000/docs> — interactive API
- <http://127.0.0.1:8000/health> — which providers are live, which are mocked

With `MOCK_SERVICES=true` (the default) the entire pipeline runs locally and
deterministically, and every response is labelled `is_mock: true`.

### Development tokens

Accepted **only** while `MOCK_SERVICES=true`:

| Header | Role |
| --- | --- |
| `Authorization: Bearer dev-farmer-token` | farmer, `uid=dev_farmer_001` |
| `Authorization: Bearer dev-officer-token` | district officer, `uid=dev_officer_001` |

Officers may read any farm. Farmers may only reach farms they own — every
farm-scoped route enforces this in `backend/api/deps.py`.

### Try the full flow

```bash
BASE=http://127.0.0.1:8000
AUTH="Authorization: Bearer dev-farmer-token"

FARM=$(curl -s -X POST $BASE/farms -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "name": "North Block", "crop": "mango", "language": "ta",
  "boundary": {"type":"Polygon","coordinates":[[[77.10,11.90],[77.11,11.90],[77.11,11.91],[77.10,11.91],[77.10,11.90]]]}
}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["farm_id"])')

curl -s -X POST $BASE/farms/$FARM/analyze -H "$AUTH" -H 'Content-Type: application/json' -d '{}' \
  | python3 -m json.tool | head -30

curl -s "$BASE/farms/$FARM/harvest-map?refresh=true" -H "$AUTH" | python3 -m json.tool | head -20
curl -s -X POST $BASE/farms/$FARM/voice-query -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"text":"மண்டலம் 7 எப்படி உள்ளது?","language":"ta"}' | python3 -m json.tool
```

## API surface (Section 12.6)

| Method | Path | Role |
| --- | --- | --- |
| POST | `/farms` | farmer |
| GET | `/farms`, `/farms/{farm_id}` | farmer (own) / officer |
| PATCH, DELETE | `/farms/{farm_id}` | farmer (own) |
| GET | `/farms/{farm_id}/zones`, `/farms/{farm_id}/zones/{zone_id}` | farmer (own) |
| POST, GET | `/farms/{farm_id}/observations` | farmer (own) |
| GET, DELETE | `/farms/{farm_id}/observations/{observation_id}` | farmer (own) |
| POST | `/farms/{farm_id}/analyze` | farmer (own) |
| GET | `/farms/{farm_id}/health` | farmer (own) / officer |
| GET | `/farms/{farm_id}/harvest-map` | farmer (own) / officer |
| GET | `/farms/{farm_id}/recommendations` | farmer (own) / officer |
| POST | `/farms/{farm_id}/image-analysis` | farmer (own) |
| POST | `/farms/{farm_id}/voice-query` | farmer (own) |
| GET | `/district/hotspots` | officer only |
| GET | `/health`, `/` | public |

Errors are structured and always carry a machine-readable code:

```json
{"error": "ZONE_NOT_FOUND", "message": "...", "path": "/farms/farm_x/analyze", "details": {}}
```

Set `API_PREFIX=/api/v1` to serve everything under a prefix.

## Repository layout

```text
backend/
  main.py            FastAPI app, lifespan, error handlers
  container.py       composition root: one object owns every service
  core/              config, auth, errors, logging, media sniffing, storage, firestore
  api/               routers (farms, observations, analysis, intelligence, district)
  schemas/           request/response models
  farm/  observations/  ground/  fusion/  risk/  harvest/  recommendations/
  satellite/         canopy context providers
  multilingual/      STT, deterministic intent parsing, translation, TTS
  analysis/          orchestrator: the only place the pipeline is sequenced
ml/                  perception: fruit detection, ripeness, health, preprocessing
geospatial/          GeoJSON, zone grids, harvest map rendering
configs/             crops/, thresholds/, prompts/  ← tune the system here, not in code
tests/               pytest suite
infra/               Dockerfile and Cloud Build
```

Two rules keep the codebase navigable:

1. **Configuration lives in `configs/`.** Thresholds, crop zones, language
   defaults and the Gemini prompt are data, not code.
2. **`backend/container.py` is the only composition root.** Routers receive the
   container from `request.app.state.container`, so tests can swap the entire
   object for an in-memory one.

## Configuration

Everything is read in `backend/core/config.py`; see `.env.example` for the full
annotated list. The switches that matter most:

| Variable | Effect |
| --- | --- |
| `MOCK_SERVICES` | `true` replaces every Google service with a labelled local mock. |
| `ML_PROVIDER` | `mock` / `heuristic` (real OpenCV models) / `yolo` (needs `FRUIT_DETECTOR_WEIGHTS`). |
| `ML_RIPENESS_PROVIDER`, `ML_HEALTH_PROVIDER` | override the shared switch per model. |
| `WEATHER_PROVIDER` | `seeded` / `open_meteo` (no key) / `google`. |
| `SATELLITE_PROVIDER` | `seeded` / `earth_engine` (also needs `EARTH_ENGINE_ALLOW_LIVE=true`). |
| `GEMINI_PROVIDER` | `mock` / `vertex`. |

No trained weights ship with this repository. `ML_PROVIDER=heuristic` runs the
real colour/texture models with no weights at all, and is the honest default for
a demo; `yolo` is a deployment choice.

## Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests -q
```

The suite runs fully offline against the mocks. It covers the geospatial and
zone maths, the fusion/risk/harvest rules, observation and media validation,
recommendation structure, the multilingual path, the whole orchestrator
(including its degradation paths) and the HTTP contract including
role-based access and farm-ownership isolation.

## Deployment

```bash
docker build -f infra/Dockerfile -t farm-intelligence .
docker run --rm -p 8080:8080 -e MOCK_SERVICES=true farm-intelligence
```

For Cloud Run, `infra/cloudbuild.yaml` builds and deploys; see the comments in
that file for the substitutions and secrets it expects. Keep
`MOCK_SERVICES=false` in any deployed environment, and attach a service account
rather than shipping a credentials file.

## Status vocabulary

| Field | Values | Meaning |
| --- | --- | --- |
| `status` | `HARVEST_READY`, `NEAR_READY`, `NOT_READY`, `HEALTH_CONCERN`, `NO_DATA` | decided by `configs/thresholds/` from fused image evidence |
| `health_status` | `healthy`, `watch`, `poor`, `unknown` | `unknown` whenever no image measured health |
| `risk_level` | `none`, `low`, `medium`, `high` | may include weather and canopy context; the codes say which |
| `recommended_action` | `CAPTURE_EVIDENCE`, `HARVEST_NOW`, `MONITOR_AND_PREPARE`, `CONTINUE_MONITORING`, `INSPECT_ZONE` | derived from the status, never from Gemini |

A zone is `NO_DATA` until an image measures it. Weather and satellite appear as
`context_sources_used` and `risk_codes`; they can raise confidence and risk, and
they can move a harvest window, but they never produce a ripeness score or a
health finding.

## Limitations to state out loud

- The thresholds are **heuristic** and not validated against agronomist labels.
  Every response says so (`heuristic_validated: false`).
- Perception runs on generic colour/texture features. It is a decision aid for
  prioritising a harvest, not an instrument.
- Disease signals are indicators, never diagnoses.
- Satellite and weather adjust confidence and risk; they never measure a fruit.
- Real speech, translation, storage and Firestore paths exist but have only
  been exercised in mock mode in this repository.

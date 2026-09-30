# 🌾 AI Farm Intelligence Network
## Final Complete Project Documentation

**Type:** AI-powered precision agriculture and farm intelligence platform
**Hackathon use case:** Mango orchard harvest intelligence
**Core concept:** A continuously updated **Farm Digital Twin** built from satellite, optional drone, phone/ground imagery, farmer voice/text, weather, soil and crop data, which detects risks, estimates harvest readiness and recommends actions in the farmer's own language.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Vision and Problem](#2-vision-and-problem)
3. [Proposed Solution and Core Principle](#3-proposed-solution-and-core-principle)
4. [Scope: MVP vs Vision](#4-scope-mvp-vs-vision)
5. [End-to-End Workflow](#5-end-to-end-workflow)
6. [Farm Digital Twin](#6-farm-digital-twin)
7. [System Segments (Modules M1–M15)](#7-system-segments-modules-m1m15)
8. [Decision Logic](#8-decision-logic)
9. [Feasibility Verdict](#9-feasibility-verdict)
10. [Technical Architecture](#10-technical-architecture)
11. [Tech Stack (Google-first)](#11-tech-stack-google-first)
12. [Data Model, APIs and AI Contract](#12-data-model-apis-and-ai-contract)
13. [Safety, Guardrails and Privacy](#13-safety-guardrails-and-privacy)
14. [Repository Structure](#14-repository-structure)
15. [MVP Build Plan](#15-mvp-build-plan)
16. [Demo Plan](#16-demo-plan)
17. [Success Metrics](#17-success-metrics)
18. [Risks and Mitigations](#18-risks-and-mitigations)
19. [Roadmap](#19-roadmap)
20. [Differentiators](#20-differentiators)
21. [Pitch](#21-pitch)
22. [Conclusion](#22-conclusion)

---

# 1. Executive Summary

Farmers receive information from many disconnected sources: their own observation, crop photos, weather forecasts, satellite imagery, field inspections and advisories. The problem is not a lack of data. It is the lack of a unified system that answers one question:

> **What is happening on my farm, where is it happening, and what should I do next?**

The **AI Farm Intelligence Network** creates a digital intelligence layer for each farm. It uses a sensing hierarchy:

| Layer | Role |
|---|---|
| **Satellite** | Wide-area, low-cost monitoring. Answers "where should we look?" |
| **Drone** (optional) | High-resolution inspection of a flagged area |
| **Phone / ground / rover** | Close-up evidence of fruit, leaves and plants |
| **Farmer voice, text, photos** | Human observations and context |
| **Weather, soil, crop stage, history** | Environmental context |

Gemini and supporting models combine these signals into a **Farm Digital Twin**. For orchards, the first capability is **Harvest Intelligence**: identify ripe, near-ripe and not-ready zones, detect health anomalies, estimate days to harvest, draw a spatial harvest map, and explain the recommendation in the farmer's language.

The same data layer can be aggregated for agricultural officers to surface **potential** regional crop-health hotspots.

**One-line idea:**

> An AI-powered farm intelligence platform that combines satellite imagery, optional drone and ground imagery, farmer voice and photos, weather, soil and crop data to continuously understand farm health, detect risks, predict harvest readiness, and give farmers actionable advice in their own language.

---

# 2. Vision and Problem

## 2.1 Vision

Give every farm a continuously updated digital view of its condition and turn complex agricultural data into simple, actionable decisions.

```text
Individual Farm → Farm Digital Twin → District Intelligence
                → Regional Crop Monitoring → Agricultural Decision Support
```

The system stays modular so new crops, languages, sensors and models can be added without rewriting the architecture.

## 2.2 Problems addressed

| Level | Problem |
|---|---|
| **Farmer** | Knows something is wrong but not where, how large, what kind of problem, which zone to harvest first, or why an AI suggests an action |
| **Data** | Photos, satellite, drone, weather, soil and reports are fragmented and never fused |
| **Scale** | Humans cannot inspect every tree at the required frequency |
| **Officer** | Cannot see emerging regional patterns from scattered individual signals |
| **Language** | Most tools are English-only dashboards; farmers need voice and local language |

---

# 3. Proposed Solution and Core Principle

## 3.1 Solution

The platform creates a **Farm Digital Twin** per farm and runs an **AI Farm Engine** over it.

```text
   Satellite ─┐
   Drone ─────┤
   Phone/Rover┤
   Voice/Text ┼→  FARM DIGITAL TWIN → AI FARM ENGINE
   Weather ───┤        ┌──────────────┼──────────────┐
   Soil ──────┤   Crop Health   Harvest Readiness   Risk
   Crop info ─┤        └──────────────┼──────────────┘
   History ───┘                Recommendation
                                      ↓
                             Farmer / Officer
```

## 3.2 Core principle: multi-resolution intelligence

> **Use the cheapest and widest source first, then move to higher-resolution sensing only when needed.**

```text
SATELLITE      →  "Something is unusual here."          (where to look)
DRONE          →  "Here is the high-res spatial detail." (what it looks like)
PHONE / ROVER  →  "Here is the close-up evidence."       (what is happening)
WEATHER / SOIL →  "Here are the conditions."             (context)
GEMINI         →  "Here is what it means and what to do." (reasoning + language)
```

## 3.3 Model strategy: separate perception, context and reasoning

| Role | Done by | Never done by |
|---|---|---|
| **Perception** (fruit, ripeness, visible health) | Computer vision models (YOLO + OpenCV) | Gemini |
| **Context** (satellite, weather, soil, crop stage) | External data systems | Gemini |
| **Decision** (status, days-to-harvest) | Transparent, configurable rules | Gemini |
| **Reasoning and language** (explanation, dialogue, translation) | Gemini | n/a |

> Gemini is **never the sole source of truth**. It narrates evidence the pipeline produced.

---

# 4. Scope: MVP vs Vision

**MVP** stands for Minimum Viable Product: the smallest complete, working slice that proves the core idea. It is narrow and end-to-end, not a rough draft of everything.

> **MVP flow:** One farmer, one mango orchard. Upload a photo, get a harvest map, hear the advice in Tamil.

## 4.1 What we build now vs what stays in the vision

| Capability | Built in MVP | Stays in vision / roadmap |
|---|---|---|
| Crops | **Mango only** | Banana, tomato, paddy, more (via config + retraining) |
| Languages | **Tamil voice and text**, plus one extra language as text | More Indian languages |
| Drone | **Accept pre-captured drone images** for a flagged zone | Automated survey flights, drone control |
| Rover | **Phone photo** as the ground input | Rover integration |
| Edge | **Cloud inference only** | ONNX / INT8 TFLite on Jetson or Raspberry Pi + Coral |
| Satellite | **Precomputed** anomaly layer for the demo orchard | Continuous, production-grade processing |
| Soil | Basic or seeded context | Full soil sensing |
| Officer view | **Simple hotspot dashboard on labeled simulated farms** | Real workflows, intervention tracking |
| Diseases | Generic "possible health indicator" | Crop-specific disease models |
| Deployment | One demo farm | Village, district, state, national |

## 4.2 Explicitly out of scope for the MVP

Every crop, every Indian language, nationwide deployment, physical drone or rover control, complete soil sensing, every disease, full government workflow, BRICS-scale federation, production-grade satellite processing.

## 4.3 Pitch wording (keep claims honest)

| Do not say | Say instead |
|---|---|
| "Our drone surveys your farm" | "The system accepts drone imagery when a zone needs closer inspection" |
| "Runs on the edge" | "Cloud today, edge-ready by design" |
| "Detects disease" | "Flags a possible health indicator; local confirmation recommended" |
| "Detected an outbreak" | "Potential hotspot requiring validation" |

**The architecture does not change** when these are added later. Drone, rover and phone are all just input sources into the same ingestion and fusion pipeline. New crops are a new config plus model; new languages are supported by Speech and Translation.

---

# 5. End-to-End Workflow

## 5.1 Pipeline

```text
1. Farm + boundary → 2. Satellite context → 3. Anomaly zone flagged
      → 4. High-res evidence (drone image or phone photo)
      → 5. Vision pipeline (quality gate → preprocess → detect → ripeness/health)
      → 6. Add weather + crop stage + history
      → 7. Fusion → 8. Rules (status + days-to-harvest)
      → 9. Harvest map → 10. Gemini explanation
      → 11. Text / translated text / voice (Tamil)
      → 12. Aggregated signals to officer view
```

## 5.2 Step detail

| Step | What happens | Module |
|---|---|---|
| 1 | Farmer creates or selects the orchard, draws the boundary, picks the crop. Digital twin and zone grid are created | M1 |
| 2 | Platform loads satellite-derived indicators for the farm | M4 |
| 3 | System flags abnormal zones, for example "Zone C shows an abnormal signal" | M4 |
| 4 | Drone imagery for that zone if available, otherwise the farmer uploads a phone photo | M2, M5, M6 |
| 5 | Image passes the quality gate, then preprocessing, fruit detection, ripeness and health analysis | M3, M6 |
| 6 | Weather forecast, crop stage and history are added | M8 |
| 7 | Fusion creates a per-zone ripeness, health and risk result | M7, M8 |
| 8 | Rules assign `HARVEST_READY`, `NEAR_READY`, `NOT_READY` or `HEALTH_CONCERN`, plus a days-to-harvest window | M9 |
| 9 | Map shows exactly where to act | M10 |
| 10 | Gemini turns structured analysis into a clear recommendation | M11 |
| 11 | Delivered as text, translated text or voice | M12 |
| 12 | Anonymized zone signals roll up to the officer dashboard | M14, M15 |

## 5.3 Farmer question the MVP answers

> "Which part of my mango orchard should I harvest first?"

**Inputs:** satellite context, drone/ground imagery, ripeness and health analysis, weather, crop info, history.
**Outputs:** status per zone, days-to-harvest estimate, spatial harvest map, explanation, recommended action.

---

# 6. Farm Digital Twin

The **Farm Digital Twin** is the central data model: a continuously updated representation of the farm.

```text
Farm
 ├── Boundary
 ├── Crop
 ├── Crop Stage
 ├── Zones
 │    ├── Satellite observations
 │    ├── Drone observations
 │    ├── Ground observations
 │    ├── Ripeness
 │    ├── Health
 │    └── Risk
 ├── Weather history
 ├── Weather forecast
 ├── Soil information
 ├── Recommendations
 └── Historical runs
```

Every new observation updates the twin. All intelligence (health, ripeness, risk, recommendations, officer aggregates) is derived from it.

---

# 7. System Segments (Modules M1–M15)

## M1 — Farm and User Management
- **Purpose:** Accounts, roles (farmer / officer), farm creation, boundary, crop and stage.
- **Output:** `Farm` document with an auto-generated zone grid.
- **Tech:** Firebase Auth (roles as custom claims), Firestore, Maps JS drawing tools.
- **MVP:** One demo farmer, one mango orchard, a 4×5 zone grid.

## M2 — Observation Ingestion
- **Purpose:** One uniform entry point for every signal: satellite, drone, phone, rover, farmer report, weather, soil.
- **Output:** Normalized `Observation` record plus stored raw asset.
- **Tech:** Cloud Storage (signed-URL uploads), Firestore, Cloud Run endpoint.
- **MVP:** Image upload with zone tag and timestamp, plus voice/text report.

## M3 — Image Preprocessing
- **Purpose:** Make imagery reliable and reject bad input early.
- **Pipeline:** quality check → Laplacian blur detection → CLAHE lighting normalization → gray-world color constancy.
- **Tech:** Python and OpenCV. Each step is toggleable through config.
- **Behavior:** A blurry or dark image returns "please retake the photo" instead of a wrong prediction.

## M4 — Satellite Context
- **Purpose:** Broad, cheap monitoring; produce the "where to look" signal.
- **Output:** Per-zone vegetation index, change versus the previous period, anomaly flag.
- **Tech:** Google Earth Engine (Sentinel-2, NDVI plus a moisture-type index, cloud masking, time comparison).
- **MVP:** Precomputed for the demo orchard and cached.
- **Important:** Labeled "canopy condition anomaly," never "ripeness." At roughly 10 m per pixel, satellite cannot see fruit.

## M5 — Drone / Aerial Analysis
- **Purpose:** Optional high-resolution inspection of a flagged zone; fruit/cluster detection at zone scale.
- **Tech:** YOLO detector on Cloud Run or a Vertex AI endpoint; tiles mapped to zones by coordinates.
- **MVP:** Pre-supplied drone images. No physical drone control.

## M6 — Ground / Fruit Analysis
- **Purpose:** Close-up ripeness and health evidence.
- **Output:** Fruit boxes, per-fruit ripeness score (0–1), health/anomaly indicators (browning, texture).
- **Tech:** YOLO fine-tuned on a Mango + Banana dataset, plus a lightweight color/texture health module.
- **MVP:** Farmer uploads a mango or leaf photo; results in seconds.

## M7 — Multi-Source Fusion
- **Purpose:** Combine sources into one per-zone score.

```text
ripeness_zone = w_drone × drone_score + w_ground × ground_score
defaults: w_drone = 0.40, w_ground = 0.60   (configurable heuristic v0)
missing source → renormalize weights (never silently treat as zero)
```

- **Output:** `{ripeness, health, confidence, sources_used[]}` per zone.

## M8 — Farm Risk Engine
- **Purpose:** Combine crop image, farmer report, satellite, drone, weather, soil and crop stage.
- **Outputs:** disease indicator, water stress, weather risk, crop stress, harvest risk, each with reason codes.
- **Tech:** Transparent rules plus thresholds. Weather from Google Maps Platform Weather API, with Open-Meteo as a free fallback.

## M9 — Harvest Intelligence
- Status and days-to-harvest rules (see [Section 8](#8-decision-logic)).

## M10 — Spatial Mapping
- **Purpose:** Show where to act.
- **Output:** Zone polygons colored 🟢 ready, 🟡 near-ready, 🔴 health concern. GeoJSON export, optional PNG.
- **Tech:** Maps JS API Data layer; server-side polygons with Shapely/GeoPandas.

## M11 — Gemini Recommendation Engine
- **Purpose:** Turn structured analysis into farmer-friendly advice, separated as Evidence → Inference → Recommendation → Explanation.
- **Tech:** Gemini via Vertex AI with JSON-schema structured output, low temperature, guardrail system prompt.

## M12 — Multilingual Voice Interface

```text
Tamil voice → Speech-to-Text → Gemini (intent → structured query)
   → analysis → recommendation → Translation (if needed)
   → Text-to-Speech → Tamil audio
```

- **Tech:** Cloud Speech-to-Text, Cloud Translation, Cloud Text-to-Speech.
- **MVP:** One full Tamil path (voice in, text and voice out).

## M13 — Farmer Dashboard
- Mobile-first web app (React PWA on Firebase Hosting): farm map, zone colors, photo upload, mic button, recommendation card with evidence, language toggle.

## M14 — Officer Dashboard
- District heat view, potential hotspots, affected farm count, approximate area, trend over time, farms to inspect.
- Shows aggregated, anonymized data, labeled **"potential hotspot requiring validation."**

## M15 — Analytics and History
- Historical zone results, weather history, trends, hotspot clustering.
- **Tech:** Firestore to BigQuery, BigQuery GIS for spatial clustering, Looker Studio optional.

---

# 8. Decision Logic

The decision layer stays simple, transparent and configurable per crop.

## 8.1 Ripeness status

```text
score ≥ 0.70          → HARVEST_READY
0.40 ≤ score < 0.70   → NEAR_READY
score < 0.40          → NOT_READY
health risk high      → HEALTH_CONCERN (overrides or annotates status)
```

## 8.2 Days-to-harvest (heuristic v0)

```text
score ≥ 0.85 → 0–1 days
score ≥ 0.70 → 1–3 days
score ≥ 0.40 → 4–7 days
score < 0.40 → 8–14 days
health-risk adjustment: move earlier if waiting increases crop loss
```

## 8.3 Image quality gate

Blurry, dark or unusable images are rejected with a retake prompt before any inference.

> **Note:** Fusion weights, ripeness thresholds and days-to-harvest bands are **configurable, crop-specific heuristics**. They must be validated with agronomists or labeled harvest data before real-world use.

---

# 9. Feasibility Verdict

**Overall: the MVP is feasible in a hackathon if it stays a focused vertical slice.**

| Area | Feasibility | Note |
|---|---|---|
| Farm boundary and map UI | ✅ High | Maps JS API with drawing tools |
| Satellite anomaly layer | ✅ High | Earth Engine, one index and one time comparison, cached |
| Image upload and preprocessing | ✅ High | Standard OpenCV |
| Fusion and harvest scoring | ✅ High | Rule-based Python with YAML |
| Spatial harvest map | ✅ High | Zone grid, GeoJSON, Maps Data layer |
| Gemini structured explanation | ✅ High | Vertex AI JSON schema output |
| Tamil voice in and out | ✅ High | Speech, Translation, Text-to-Speech |
| Fruit detection and ripeness | 🟡 Medium | Needs pretrained or fine-tuned YOLO; color ripeness varies by variety |
| Officer hotspot dashboard | 🟡 Medium | Needs seeded, labeled simulated farms |
| Real drone or rover control, edge, all crops and languages | ❌ Out of scope | Roadmap only |

## 9.1 Key technical realities

| # | Reality | How we handle it |
|---|---|---|
| 1 | Satellite (about 10 m per pixel) cannot see fruit | Use it only as the "where to look" anomaly layer |
| 2 | Color-based ripeness is variety-dependent (some mangoes stay green when ripe) | Per-crop and per-variety config, confidence scores, validation on labeled data |
| 3 | Fusion weights and days-to-harvest are unvalidated heuristics | Keep configurable and label "heuristic v0" |
| 4 | Image models are not diagnoses | Always say "possible indicator, confirm locally"; no free-form pesticide advice |
| 5 | Gemini can hallucinate | Perception, then evidence, then rules; Gemini only explains |
| 6 | Phone photos have no reliable geo-footprint | Zone grid; farmer tags the zone or GPS EXIF is used |
| 7 | Live hardware is fragile in demos | Prepared satellite and drone data; live phone photo and voice |
| 8 | Few farms make hotspots look thin | Seeded synthetic farms, clearly labeled simulated |

---

# 10. Technical Architecture

## 10.1 Layers

```text
┌───────────────────────────────────────────────────────────────┐
│ EXPERIENCE   Farmer app (voice/text/photo)  |  Officer app    │
├───────────────────────────────────────────────────────────────┤
│ API          Cloud Run: FastAPI (auth, farms, analyze, voice) │
├───────────────────────────────────────────────────────────────┤
│ INTELLIGENCE Preprocess → Vision → Fusion → Risk → Harvest    │
│              → Gemini (explain / translate)                   │
├───────────────────────────────────────────────────────────────┤
│ CONTEXT      Earth Engine | Weather API | Soil / Crop config  │
├───────────────────────────────────────────────────────────────┤
│ DATA         Firestore | Cloud Storage | BigQuery             │
└───────────────────────────────────────────────────────────────┘
```

## 10.2 Final architecture

```text
   Farmer (PWA: map + photo + mic)               Officer (role-gated)
              │                                          ▲
              ▼                                          │
      Firebase Hosting + Auth ───────────►  BigQuery (aggregated, anonymized)
              │                                          ▲
              ▼                                          │
   ┌──────────────────── Cloud Run (FastAPI) ────────────┴────────────────┐
   │ Ingest → Quality gate → Preprocess (OpenCV)                          │
   │   → YOLO fruit detect + ripeness + health                            │
   │   → Fusion (drone × ground, configurable)                            │
   │   → Risk rules (weather, crop stage, satellite flag)                 │
   │   → Harvest status + days-to-harvest                                 │
   │   → Zone polygons → GeoJSON                                          │
   │   → Gemini (structured JSON → explanation)                           │
   │   → Translate → Text-to-Speech                                       │
   └──────┬───────────────┬───────────────┬───────────────┬───────────────┘
          ▼               ▼               ▼               ▼
     Firestore      Cloud Storage    Earth Engine     Weather API
```

## 10.3 Six architecture decisions

| # | Decision | Reason |
|---|---|---|
| D1 | Satellite is an anomaly detector only | Resolution cannot judge fruit ripeness |
| D2 | CV models produce evidence; Gemini never does | Prevents hallucinated sensor data |
| D3 | Rules and YAML configs for scoring | Transparent, tunable per crop, easy to explain |
| D4 | Gemini returns schema-constrained JSON | Testable contract; deterministic UI rendering |
| D5 | Modular monolith on Cloud Run | Fastest to build, deploy and debug; can split later |
| D6 | Precompute heavy geospatial; demo on curated data | No live-demo fragility, still architecturally real |

## 10.4 Real vs prepared in the demo

| Component | Demo mode |
|---|---|
| Satellite indices | Precomputed from real Earth Engine data, cached |
| Drone imagery | Provided sample images for the flagged zone |
| Ground image | Live phone upload (sample as fallback) |
| Vision inference, fusion, rules, map | Live |
| Gemini explanation | Live |
| Tamil voice in and out | Live |
| Officer hotspots | Seeded synthetic farms, labeled simulated |

## 10.5 Efficiency choices

- Cloud Run scales to zero; a small CPU-only YOLO model is enough for single-image demo inference.
- Call Gemini once per analysis with all structured evidence, not once per zone.
- Cache satellite results and weather (short TTL).
- Resize images client-side before upload.

---

# 11. Tech Stack (Google-first)

| Layer | Choice | Why |
|---|---|---|
| **Frontend** | React + Vite PWA on **Firebase Hosting** | Fast to build, mobile-first, one-command deploy |
| **Auth** | **Firebase Authentication** (Google sign-in or phone OTP), custom claims for `farmer` / `officer` | Phone OTP suits farmers; roles gate officer view |
| **Backend** | **Cloud Run** with **FastAPI (Python)** | Serverless, scales to zero, matches the CV and geo stack |
| **AI reasoning** | **Gemini on Vertex AI** (fast Flash-class tier by default; stronger tier only if needed) | Multimodal, multilingual, structured JSON output |
| **Vision** | **YOLO (Ultralytics)** and **OpenCV** on Cloud Run, or a Vertex AI endpoint for GPU | Reliable boxes and counts, cheap, edge-exportable later |
| **Speech in** | **Cloud Speech-to-Text** | Tamil and other Indian languages |
| **Translation** | **Cloud Translation** (or Gemini directly) | Consistent multilingual output |
| **Speech out** | **Cloud Text-to-Speech** | Voice replies |
| **Satellite** | **Google Earth Engine** | Sentinel-2 catalog with server-side indices |
| **Maps** | **Google Maps Platform** (Maps JS API, Data layer) | Native GeoJSON rendering, drawing tools |
| **Weather** | **Maps Platform Weather API** (fallback: Open-Meteo) | Google ecosystem, with a free fallback |
| **App database** | **Firestore** | Flexible documents, realtime updates |
| **Files** | **Cloud Storage** | Images, tiles, exports, audio |
| **Analytics** | **BigQuery** and BigQuery GIS | District aggregation, trends, clustering |
| **Async (post-MVP)** | **Pub/Sub** or **Cloud Tasks** | Decouple heavy analysis |
| **Secrets and CI** | **Secret Manager**, **Cloud Build** | Safe keys, easy deploys |
| **Charts (optional)** | **Looker Studio** | Officer trends with minimal code |

## 11.1 What we deliberately avoid

| Alternative | Verdict |
|---|---|
| Sending every image to Gemini for detection | Less reliable for exact counts and boxes, costlier at scale |
| Training a large model from scratch | Not feasible in a hackathon; fine-tune or use pretrained |
| Kubernetes / GKE | Overkill; Cloud Run is enough |
| Microservice per module | A modular monolith is faster to build |
| Live Earth Engine calls in the demo | Latency and quota risk; precompute |
| BigQuery as the app database | Wrong tool for low-latency reads |

## 11.2 Python libraries

```text
fastapi, uvicorn, pydantic
firebase-admin
google-cloud-storage, google-cloud-bigquery
google-cloud-speech, google-cloud-texttospeech, google-cloud-translate
google-genai / vertexai
earthengine-api
ultralytics, opencv-python-headless, numpy
shapely, geopandas
pyyaml
```

---

# 12. Data Model, APIs and AI Contract

## 12.1 Firestore collections

```text
users/{uid}                              role, language, farm_ids[]
farms/{farm_id}                          name, crop, crop_stage, boundary (GeoJSON), zones[]
farms/{farm_id}/observations/{id}        source, zone_id, timestamp, metrics, asset_uri
farms/{farm_id}/zoneResults/{id}         zone_id, ripeness, health, risk, status, window, confidence
farms/{farm_id}/recommendations/{id}     action, reason_codes[], language, text, audio_uri
```

`source` is one of: `satellite`, `drone`, `phone`, `rover`, `farmer_report`, `weather`, `soil`.

## 12.2 Farm

```json
{
  "farm_id": "farm_001",
  "name": "Mango Orchard",
  "crop": "mango",
  "crop_stage": "fruit_development",
  "boundary": {},
  "created_at": "..."
}
```

## 12.3 Observation

```json
{
  "observation_id": "obs_001",
  "farm_id": "farm_001",
  "source": "phone",
  "zone_id": "zone_07",
  "timestamp": "...",
  "location": {},
  "metrics": {},
  "image_reference": "..."
}
```

## 12.4 Zone result

```json
{
  "farm_id": "farm_001",
  "zone_id": "zone_07",
  "ripeness_score": 0.82,
  "status": "HARVEST_READY",
  "health_score": 0.88,
  "risk_level": "medium",
  "estimated_harvest_window": "1-3 days",
  "sources_used": ["satellite", "drone", "phone", "weather"],
  "confidence": 0.84
}
```

## 12.5 Recommendation

```json
{
  "recommendation_id": "rec_001",
  "farm_id": "farm_001",
  "zone_id": "zone_07",
  "action": "PRIORITIZE_HARVEST",
  "reason_codes": ["HIGH_RIPENESS", "WEATHER_CONTEXT"],
  "language": "ta"
}
```

## 12.6 API surface

```text
POST /farms                            GET  /farms/{farm_id}
POST /farms/{farm_id}/observations     GET  /farms/{farm_id}/observations
POST /farms/{farm_id}/analyze          GET  /farms/{farm_id}/health
GET  /farms/{farm_id}/harvest-map      GET  /farms/{farm_id}/recommendations
POST /farms/{farm_id}/image-analysis   POST /farms/{farm_id}/voice-query
GET  /district/hotspots                (officer role only)
```

## 12.7 Gemini output contract

Gemini must return schema-constrained JSON, not free prose, as its primary internal output.

```json
{
  "crop": "mango",
  "zone": "zone_07",
  "health_status": "healthy",
  "ripeness_status": "harvest_ready",
  "risk_level": "medium",
  "evidence": ["high_ripeness_score", "upcoming_weather_event"],
  "recommended_action": "prioritize_harvest",
  "explanation": "Zone 7 has the highest ripeness signal and rain is forecast soon.",
  "confidence": 0.84
}
```

The app validates against the schema, retries on violation, and falls back to a deterministic text template if needed. It then converts the result into farmer-friendly language.

## 12.8 Explainable recommendation format

| Part | Example |
|---|---|
| **Evidence** | Zone A has a high ripeness score. Forecast shows rain. Health signal acceptable. |
| **Inference** | Zone A has high immediate harvest priority. |
| **Recommendation** | Harvest Zone A first. |
| **Explanation** | Zone A has the highest ripeness signal, and upcoming weather increases the value of prioritizing mature fruit. |

This makes the system auditable and prevents free-form AI text from being mistaken for raw sensor evidence.

---

# 13. Safety, Guardrails and Privacy

## 13.1 Agronomic guardrails

```text
Model evidence → Structured analysis → Agronomic rule / trusted guidance
              → Gemini explanation → Farmer
```

- Disease wording: *"Possible disease indicator detected; local confirmation is recommended."*
- Never present an image classification as a definitive diagnosis.
- Recommendations involving pesticides, fertilizers or other interventions must be grounded in validated agricultural guidance, not generated freely by an LLM.
- Officer hotspots are always "potential, requires validation," never a confirmed outbreak.

## 13.2 Privacy principles

- Collect only necessary information.
- Separate personal identity from agricultural observations where possible.
- Enforce role-based access between farmer and officer views (Firebase Auth claims plus Firestore rules).
- Aggregate before district-level display.
- The officer dashboard focuses on agricultural intelligence, not personal details.

---

# 14. Repository Structure

```text
ai-farm-intelligence/
│
├── frontend/
│   ├── farmer/               # React PWA: map, upload, mic, recommendation card
│   ├── officer/              # Role-gated hotspot dashboard
│   └── shared/               # API client, i18n strings, UI components
│
├── backend/                  # FastAPI on Cloud Run
│   ├── api/                  # Routers: farms, observations, analyze, voice, district
│   ├── core/                 # Config, Firebase token verification, logging
│   ├── farm/                 # Farm and zone CRUD, grid generation
│   ├── observations/         # Ingestion and storage
│   ├── satellite/            # Earth Engine client, anomaly detection
│   ├── drone/                # Aerial tile to zone mapping
│   ├── ground/               # Phone/rover analysis orchestration
│   ├── fusion/               # Weighted, missing-source-safe fusion
│   ├── risk/                 # Rule-based risk engine
│   ├── harvest/              # Status and days-to-harvest
│   ├── recommendations/      # Gemini prompts, schema, guardrails
│   └── multilingual/         # STT, Translate, TTS wrappers
│
├── ml/
│   ├── preprocessing/        # Laplacian blur, CLAHE, gray-world
│   ├── fruit_detection/      # YOLO weights and inference
│   ├── ripeness/             # Ripeness score
│   ├── health/               # Color/texture anomaly module
│   └── training/             # Notebooks and scripts
│
├── geospatial/
│   ├── maps/                 # Grid and zone polygon generators
│   └── geojson/              # Exports, sample orchard boundary
│
├── data/
│   ├── satellite/            # Precomputed demo indices
│   ├── drone/                # Demo aerial images
│   ├── ground/               # Demo close-ups
│   └── seed/                 # Synthetic farms (labeled simulated)
│
├── configs/
│   ├── crops/mango.yaml      # Classes, stages, variety notes
│   ├── thresholds/mango.yaml # Ripeness cutoffs, days bands, fusion weights
│   └── prompts/              # Gemini system prompts and JSON schema
│
├── infra/                    # Dockerfile, cloudbuild.yaml, Firebase config
├── tests/                    # Unit (fusion, harvest), AI schema contract, e2e
├── docs/                     # Architecture, demo script, this document
└── README.md
```

## 14.1 Module to code map

| Module | Location |
|---|---|
| M1 Farm and User | `backend/farm`, `frontend/farmer` |
| M2 Ingestion | `backend/observations` |
| M3 Preprocessing | `ml/preprocessing` |
| M4 Satellite | `backend/satellite` |
| M5 Drone | `backend/drone`, `ml/fruit_detection` |
| M6 Ground | `backend/ground`, `ml/ripeness`, `ml/health` |
| M7 Fusion | `backend/fusion` |
| M8 Risk | `backend/risk` |
| M9 Harvest | `backend/harvest` |
| M10 Mapping | `geospatial/` |
| M11 Gemini | `backend/recommendations` |
| M12 Voice | `backend/multilingual` |
| M13 Farmer UI | `frontend/farmer` |
| M14 Officer UI | `frontend/officer` |
| M15 Analytics | BigQuery views, `docs/` |

## 14.2 Model and dataset strategy

- Mango + Banana dataset for close-up ripeness classification.
- Custom aerial orchard dataset for drone detection.
- YOLO-based detection and classification with configurable crop classes and ripeness scores.
- For the hackathon, use existing datasets and pretrained or fine-tuned models where practical.
- New crops are added through configuration and retraining, not a new architecture.

---

# 15. MVP Build Plan

| Phase | Deliverable | Priority |
|---|---|---|
| P0 | Repo, Firebase project, Cloud Run skeleton, Auth | Must |
| P1 | Farm creation, boundary, grid zones, map view | Must |
| P2 | Image upload, preprocessing, YOLO ripeness and health | Must |
| P3 | Fusion, harvest rules, zone map (GeoJSON on Maps) | Must |
| P4 | Gemini structured recommendation card | Must |
| P5 | Satellite anomaly layer (precomputed Earth Engine) | Must |
| P6 | Tamil voice in and out | Must |
| P7 | Officer dashboard (seeded data, BigQuery) | Should |
| P8 | Polish, tests, demo rehearsal, fallback assets | Must |

> **Rule:** get one zone working end to end (photo, status, map, Tamil advice) **before** adding breadth. The ripeness model is the biggest technical risk, so start there.

---

# 16. Demo Plan

Build the whole demo around one farmer.

| Scene | Action | Message |
|---|---|---|
| Opening | Show the farm | "This is Ravi's mango orchard." |
| 1 | Satellite-derived overview | "The system monitors the farm at broad scale." |
| 2 | Zone C highlighted | "Satellite says: look here." |
| 3 | Load drone imagery of Zone C | "The system accepts drone imagery when higher resolution is needed." |
| 4 | Upload a live close-up photo | "Ground evidence, analyzed in seconds." |
| 5 | Show weather forecast | "Context that affects timing." |
| 6 | Fusion panel: ✓ Satellite ✓ Drone ✓ Ground ✓ Weather | "One engine, all signals." |
| 7 | Harvest map: A 🟢 ready, B 🟡 near-ready, C 🔴 health concern | "Exactly where to act." |
| 8 | Recommendation card with Evidence, Inference, Action | "Explainable, not a black box." |
| 9 | Ask in Tamil voice, hear the reply in Tamil | "In the farmer's own language." |
| 10 | Officer view with nearby farms clustered | "A potential regional hotspot, needing validation." |

**Sample recommendation:** "Prioritize Zone A for harvesting. Inspect Zone C because the visual and contextual signals indicate a possible health issue."

**Demo architecture:**

```text
Browser → Firebase / Frontend → Cloud Run API
   → Farm Intelligence Service (preprocess, vision, aggregation, risk, harvest scoring)
   → Gemini / Vertex AI → Structured result → Farmer dashboard
```

---

# 17. Success Metrics

| Category | Metrics |
|---|---|
| **Vision** | Fruit detection precision and recall; ripeness accuracy; health anomaly detection performance |
| **Spatial** | Zone-level localization accuracy; valid map and GeoJSON generation |
| **System** | Inference latency; API reliability; image-processing time |
| **User experience** | Time to recommendation; steps required from the farmer; multilingual response quality |
| **Decision support** | Agreement between system recommendation and validated harvest labels |

---

# 18. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Ripeness model fails on real-world variety or lighting | Wrong advice | Quality gate, confidence display, per-variety config, expert validation |
| Earth Engine or API quota and latency in demo | Demo failure | Precompute and cache; offline fallback assets |
| Gemini output malformed | UI break | JSON schema, retry, deterministic fallback template |
| Overclaiming disease or outbreaks | Trust and safety | Wording rules, "requires validation" labels |
| Farmer data privacy | Ethical and legal | Minimal collection, role-based access, aggregation |
| Scope creep | Unfinished MVP | Enforce the out-of-scope list in Section 4.2 |
| Simulated officer data looks fake | Credibility | Label it clearly as simulated |

---

# 19. Roadmap

| Phase | Focus | Key capabilities |
|---|---|---|
| **1. Hackathon MVP** | Mango orchard | Farm view, satellite context, drone and ground imagery, ripeness, health, harvest map, Gemini recommendation, Tamil interaction |
| **2. Multi-crop** | Banana, tomato, paddy, regional crops | Crop configs, models, thresholds, agronomic rules |
| **3. Continuous Digital Twin** | Ongoing monitoring | Historical trends, crop lifecycle, recurring satellite refresh, richer soil and weather |
| **4. Agricultural Intelligence Network** | District scale | Hotspot detection, officer workflows, intervention tracking, regional analytics |
| **5. Edge and Cloud** | Low-connectivity farms | ONNX and INT8 TFLite on NVIDIA Jetson or Raspberry Pi with Coral Edge TPU; local inference with cloud sync |

```text
Geographic scale:  Farm → Village → District → State → India
Crop scale:        Mango → Banana → Tomato → Paddy → Others
```

---

# 20. Differentiators

1. **Multi-resolution sensing.** Satellite, then drone, then ground; the right level of detail rather than one sensor.
2. **Farm Digital Twin.** All observations become one evolving representation.
3. **Actionable intelligence.** Not "this image contains ripe fruit" but "harvest this zone first."
4. **Spatial decision support.** The farmer sees where to act.
5. **Explainable recommendations.** Evidence is shown behind every action.
6. **Multilingual voice interaction.** Farmers speak naturally in their own language.
7. **Two-sided platform.** One data architecture serves farmers and agricultural officers.

**Coherence rule:** the project is not "a satellite project plus a drone project plus a disease project plus a chatbot." Everything serves one concept: *build a continuously updated AI representation of the farm and use it to make better agricultural decisions.*

---

# 21. Pitch

## 21.1 Final product statement

> **AI Farm Intelligence Network is a multimodal agricultural intelligence platform that creates a digital twin of a farm by combining satellite imagery, optional drone surveys, ground/phone imagery, farmer observations, weather, soil and crop information. An AI engine fuses these signals to detect crop stress, identify potential health risks, estimate harvest readiness and generate spatial recommendations. Farmers receive simple, multilingual, explainable advice, while agricultural officers can view aggregated signals and potential regional hotspots.**
>
> **The first implementation focuses on mango orchards, demonstrating satellite-assisted monitoring, high-resolution inspection, fruit ripeness and health analysis, spatial harvest mapping and AI-powered harvest recommendations.**

## 21.2 30-second pitch

> **Farmers don't lack data. They lack a unified view of their farm.**
>
> We're building an AI Farm Intelligence Network that creates a digital twin of every farm. Satellite imagery continuously provides the broad view. When something needs a closer look, drone imagery adds high-resolution detail, and the farmer's phone provides close-up evidence. We combine these with weather, soil and crop information using Gemini.
>
> For our first use case, a mango farmer can see which parts of the orchard are ready to harvest, which areas show health concerns, roughly how many days remain, and exactly where to act, with the recommendation explained in their own language.
>
> **Satellite tells us where to look. Drone and ground imagery tell us what is there. AI tells the farmer what to do next.**

## 21.3 One-diagram summary

```text
                  🌾 AI FARM INTELLIGENCE NETWORK
                                │
        ┌───────────────────────┼───────────────────────┐
     🛰️ SATELLITE            🚁 DRONE               📷 GROUND
     wide-area               high-res (optional)     close-up
        └───────────────────────┼───────────────────────┘
                         🎙️ FARMER VOICE / TEXT
                                │
                     WEATHER · SOIL · CROP DATA
                                ↓
                       🧠 FARM DIGITAL TWIN
                                ↓
                       AI FARM INTELLIGENCE
        ┌───────────────────────┼───────────────────────┐
   🌱 CROP HEALTH         🥭 HARVEST READINESS        ⚠️ RISK
        └───────────────────────┼───────────────────────┘
                         🎯 DECISION ENGINE
        ┌───────────────────────┼───────────────────────┐
   👨‍🌾 FARMER ADVISORY     🗺️ HARVEST MAP / GIS    🏢 OFFICER DASHBOARD
   (Tamil / Hindi / Telugu, text + voice)
```

---

# 22. Conclusion

**The idea is strong, feasible as a focused MVP, and a natural fit for Google's stack.**

1. **The idea.** A Farm Digital Twin fuses many signals into one answer: what is happening, where, and what to do next. Its power is the multi-resolution logic and the actionable, explainable, multilingual output.
2. **What we build.** One mango orchard, end to end: boundary and zones, satellite anomaly flag, photo analysis, fusion and rules, a harvest map, a Gemini explanation, Tamil voice, and a simple officer hotspot view.
3. **What we do not build now.** Real drone or rover control, edge deployment, all crops and all languages. These stay in the roadmap and pitch, and the architecture already supports them.
4. **How we build it.** One modular Cloud Run service on a Google-first stack. Vision models produce evidence, rules produce decisions, and Gemini only explains and translates.
5. **What we stay honest about.** Satellite cannot judge ripeness. Fusion weights and days-to-harvest are heuristics to validate. Disease output is a possible indicator, and hotspots are potential until verified.

> **The product is not a drone system. It is not a satellite system. It is not a fruit-ripeness detector. It is an AI Farm Intelligence Network.**
> Satellite, drone, phone/rover, weather and soil are sensing layers. The **Farm Digital Twin is the core.** Gemini plus analytical models are the intelligence layer. And the farmer's actionable recommendation is the **final product**.

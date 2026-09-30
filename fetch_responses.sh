#!/bin/bash
TOKEN="dev-farmer-token"
BASE_URL="http://127.0.0.1:8000/farms"

echo "=== GET /farms ==="
FARM_JSON=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL")
echo "$FARM_JSON" | .venv/bin/python -m json.tool
FARM_ID=$(echo "$FARM_JSON" | .venv/bin/python -c "import sys, json; print(json.load(sys.stdin).get('farms', [{}])[0].get('farm_id', ''))")

if [ -z "$FARM_ID" ]; then
    echo "No farm found"
    exit 1
fi

echo -e "\n=== GET /farms/$FARM_ID ==="
curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/$FARM_ID" | .venv/bin/python -m json.tool | head -n 30

echo -e "\n=== GET /farms/$FARM_ID/health ==="
curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/$FARM_ID/health" | .venv/bin/python -m json.tool | head -n 40

echo -e "\n=== GET /farms/$FARM_ID/zones/zone_15 ==="
curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/$FARM_ID/zones/zone_15" | .venv/bin/python -m json.tool

echo -e "\n=== GET /farms/$FARM_ID/recommendations ==="
curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/$FARM_ID/recommendations" | .venv/bin/python -m json.tool

echo -e "\n=== POST /farms/$FARM_ID/voice-query ==="
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"text": "What should I do about my farm today?", "language": "en", "tier": "rules_only"}' "$BASE_URL/$FARM_ID/voice-query" | .venv/bin/python -m json.tool

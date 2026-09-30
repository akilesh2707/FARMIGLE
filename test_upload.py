import requests
import base64
import json

with open("data/ground/mango_sample.jpg", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")

payload = {
    "source": "phone",
    "zone_id": "zone_15",
    "image_base64": b64,
    "language": "en"
}

headers = {
    "Authorization": "Bearer dev-farmer-token",
    "Content-Type": "application/json"
}

res = requests.post("http://127.0.0.1:8000/farms/farm_jaefb5sjz8/observations", json=payload, headers=headers)
print(json.dumps(res.json(), indent=2))

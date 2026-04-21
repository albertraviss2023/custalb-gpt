import requests
import json

url = "http://localhost:8001/v1/chat/completions"
payload = {
    "model": "gemma4_26b_vllm",
    "messages": [{"role": "user", "content": "who developed you?"}],
    "stream": False
}
headers = {"Content-Type": "application/json"}

try:
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")

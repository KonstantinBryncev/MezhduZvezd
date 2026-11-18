import os
import httpx
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("CLOUDFLARE_HOST", "://cloudflare.com").strip()
acc_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
key = os.getenv("CLOUDFLARE_API_KEY", "").strip()
model = os.getenv("CLOUDFLARE_MODEL", "").strip()

endpoint = f"https://{host}/client/v4/accounts/{acc_id}/ai/v1/chat/completions"

headers = {
	"Authorization": f"Bearer {key}",
	"Content-Type": "application/json",
}

payload = {
	"model": model,
	"messages": [
		{"role": "user", "content": "Привет! Три карты таро: Семёрка пентаклей, рыцарь пентаклей, луна. Дай по ним краткий расклад на русском."}
	],
	"temperature": 0.7,
	"max_tokens": 3000,
}

print("=== 1. СОБРАННЫЙ АДРЕС ===")
print("Endpoint:", endpoint)
print("Model:", model)

print("\n=== 2. ОТПРАВКА ЗАПРОСА ===")
try:
	r = httpx.post(endpoint, headers=headers, json=payload, timeout=30)
	print("HTTP Статус:", r.status_code)
	print("\n=== 3. СЫРОЙ ОТВЕТ СЕРВЕРА ===")
	print(r.text)
except Exception as exc:
	print("ОШИБКА СОЕДИНЕНИЯ:", repr(exc))

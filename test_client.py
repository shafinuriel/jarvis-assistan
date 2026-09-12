# test_client.py
import asyncio
import json
import websockets

IP = "192.168.68.67"
PORT = 8765
TOKEN = "jarvis_secret_token_2026"

DEVICE_ID = "test_phone"
DEVICE_NAME = "Test Client"


async def main():
    uri = f"ws://{IP}:{PORT}"
    print(f"Подключаюсь к {uri} ...")

    async with websockets.connect(uri) as ws:
        # Регистрация
        register = {
            "action": "register",
            "device_id": DEVICE_ID,
            "device_type": "test",
            "name": DEVICE_NAME,
            "token": TOKEN
        }
        await ws.send(json.dumps(register))
        print("→ register отправлен")

        response = await ws.recv()
        print(f"← {response}")

        data = json.loads(response)
        if data.get("type") != "auth_ok":
            print("❌ Авторизация не прошла")
            return

        print("✅ Подключён. Жду команды от Jarvis...\n")

        # Слушаем команды от Хаба
        async for message in ws:
            print(f"← Команда: {message}")
            payload = json.loads(message)

            if payload.get("action") == "ping":
                reply = {
                    "device_id": DEVICE_ID,
                    "action": "pong",
                    "request_id": payload.get("request_id"),
                    "message": "pong from test_phone"
                }
                await ws.send(json.dumps(reply))
                print("→ Отправил pong")


if __name__ == "__main__":
    asyncio.run(main())
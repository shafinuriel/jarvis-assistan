# actions/remote_server.py
from __future__ import annotations

import asyncio
import json
import secrets
import socket
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

# ====================== НАСТРОЙКИ ======================
WS_PORT = 8765
TOKEN_LENGTH = 24

def get_local_ip() -> str:
    """Определяет локальный IPv4 адрес в текущей сети."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        s.connect(("8.8.8.8", 80))
        ip =s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
    
def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_LENGTH)

@dataclass
class Device:
    device_id: str
    device_type: str
    name: str
    websocket: WebSocketServerProtocol
    connected_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    
class JarvisRemoteServer:
    def __init__(self, on_message:  Optional[callable] = None):
        self.port = WS_PORT
        self.token = "jarvis_2026"
        self.local_ip = get_local_ip()
        self.devices: Dict[str, Device] = {}     #device_id -> Device
        self.clients: Set[WebSocketServerProtocol] = set()
        self.on_message = on_message
        self.server = None
        
    @property
    def connection_info(self) -> dict:
        return {
            "ip": self.local_ip,
            "port": self.port,
            "token": self.token,
            "hub_id": str(uuid.uuid4())[:8]
        }

    def get_qr_data(self) -> str:
        """Данные, которые будут в QR-коде."""
        return json.dumps(self.connection_info, ensure_ascii=False)
    
    def get_connected_devices(self) -> list:
        """Список подключенных устройств."""
        return[
            {
                "device_id": d.device_id,
                "device_type": d.device_type,
                "name": d.name
            }
            for d in self.devices.values()
        ]
    
    def list_devices(self) -> str:
        if not self.devices:
            return "Нет подключённых устройств."
        
        lines = ["Подключённые устроства:"]
        for d in self.devices.values():
            lines.append(f".{d.name} ({d.device_id}) - {d.device_type}")
        return "\n".join(lines)
    
    async def _handler(self, websocket: WebSocketServerProtocol):
        device_id = None
        try:
            print("[Remote] Новое входящее соединение...")
        
            raw = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            print(f"[Remote] Получено: {raw}")
        
            data = json.loads(raw)

            if data.get("action") != "register":
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "First message must be register"
                }))
                await websocket.close()
                return

            received_token = data.get("token")
            expected_token = self.token
            
            print("=" * 50)
            print(f"[Remote] Ожидаемый токен: '{expected_token}'")
            print(f"[Remote] Пришедший токен: '{received_token}'")
            print(f"[Remote] Длина ожидаемого: {len(expected_token) if expected_token else 0}")
            print(f"[Remote] Длина пришедшего: {len(received_token) if received_token else 0}")
            print("=" * 50)
            
            if received_token != expected_token:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid token"
                }))
                await websocket.close()
                return

            device_id = data.get("device_id") or f"device_{uuid.uuid4().hex[:6]}"
            device_type = data.get("device_type", "unknown")
            name = data.get("name", device_id)

            self.devices[device_id] = Device(
                device_id=device_id,
                device_type=device_type,
                name=name,
                websocket=websocket
            )
            self.clients.add(websocket)

            await websocket.send(json.dumps({
                "type": "auth_ok",
                "message": f"Registered as {device_id}",
                "device_id": device_id
            }))

            print(f"[Remote] + Устройство подключено: {name} ({device_id})")

            async for message in websocket:
                try:
                    payload = json.loads(message)
                    payload["_from_device"] = device_id
                    if self.on_message:
                        await self.on_message(payload, websocket)
                except Exception as e:
                    print(f"[Remote] Ошибка обработки сообщения: {e}")

        except Exception as e:
            print(f"[Remote] Ошибка соединения: {type(e).__name__}: {e}")
        finally:
            if device_id and device_id in self.devices:
                del self.devices[device_id]
                print(f"[Remote] - Устройство отключено: {device_id}")
            self.clients.discard(websocket)
            
    async def start(self):
        self._server = await websockets.serve(
            self._handler,
            "0.0.0.0",
            self.port,
            ping_interval=20,
            ping_timeout=20
        )
        print(f"[Remote] Сервер запущен -> {self.local_ip}:{self.port}")
        print(f"[Remote] Токен: {self.token}")
        
    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            print("[Remote] Сервер остановлен")
            
    async def send_to_device(self, device_id: str, data: dict) -> bool:
        """Отправить команду конкретному устройству."""
        device = self.devices.get(device_id)
        if not device:
            print(f"[Remote] Устройство {device_id} не найдено")
            return False
        
        try:
            await device.websocket.send(json.dumps(data, ensure_ascii=False))
            return True
        except Exception as e:
            print(f"[Remote] Не удалось отправить на {device_id}: {e}")
            return False
        
    async def broadcast(self, data: dict):
        """Отправляет всем подключённым устройствам."""
        if not self.clients:
            return
        message = json.dumps(data, ensure_ascii=False)
        await asyncio.gather(
            *[client.send(message) for client in self.clients],
            return_exceptions=True
        )
# Генерация QR
def generate_qr_image(data: str, filename: str = "jarvis_qr.png") -> str:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=ERROR_CORRECT_H,
        box_size=12,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(filename)
    return filename
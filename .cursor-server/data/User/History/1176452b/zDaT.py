import httpx
import json
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import re

class XUIClient:
    def __init__(self):
        from config import XUI_BASE_URL, XUI_PORT, XUI_WEBBASEPATH, XUI_USERNAME, XUI_PASSWORD
        
        self.base_url = f"http://{XUI_BASE_URL}:{XUI_PORT}/{XUI_WEBBASEPATH}"
        self.username = XUI_USERNAME
        self.password = XUI_PASSWORD
        self.session_cookies = None
        self.client = httpx.AsyncClient(verify=False, timeout=30.0)
    
    async def ensure_login(self):
        """Обеспечивает авторизацию в 3xUI"""
        if self.session_cookies:
            return
        
        login_url = f"{self.base_url}/login"
        login_data = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            response = await self.client.post(login_url, json=login_data)
            if response.status_code == 200:
                self.session_cookies = response.cookies
                print("Успешная авторизация в 3xUI")
            else:
                print(f"Ошибка авторизации: {response.status_code}")
                raise Exception("Ошибка авторизации в 3xUI")
        except Exception as e:
            print(f"Ошибка при авторизации: {e}")
            raise
    
    async def get_inbounds(self) -> Optional[Dict[str, Any]]:
        """Получение списка inbounds"""
        await self.ensure_login()
        try:
            url = f"{self.base_url}/panel/api/inbounds/list"
            response = await self.client.get(url, cookies=self.session_cookies)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Ошибка получения inbounds: {response.status_code}")
                return None
        except Exception as e:
            print(f"Ошибка при получении inbounds: {e}")
            return None
    
    async def create_user(self, email: str, days: int = 30, note: str = "", tg_id: str = "") -> Optional[Dict[str, Any]]:
        """Создание пользователя в 3xUI используя addClient API"""
        await self.ensure_login()
        try:
            # Генерируем уникальный ID для VLESS
            import uuid
            vless_id = str(uuid.uuid4())
            
            # Генерируем sub_id
            sub_id = f"sub_{int(datetime.now().timestamp())}"
            
            # Вычисляем время истечения
            expiry_time = datetime.now() + timedelta(days=days)
            expiry_time_ms = int(expiry_time.timestamp() * 1000)
            
            # Получаем правильный ID inbound
            inbounds = await self.get_inbounds()
            if not inbounds or not inbounds.get("obj"):
                print("Не удалось получить inbounds")
                return None
            
            inbound_id = None
            for inbound in inbounds["obj"]:
                if inbound.get("enable", False):
                    inbound_id = inbound.get("id")
                    break
            
            if not inbound_id:
                print("Не найден активный inbound")
                return None
            
            payload = {
                "id": inbound_id,  # Используем правильный ID inbound
                "settings": json.dumps({
                    "clients": [
                        {
                            "id": vless_id,
                            "flow": "xtls-rprx-vision",
                            "email": email,
                            "limitIp": 3,
                            "totalGB": 0,
                            "expiryTime": expiry_time_ms,
                            "enable": True,
                            "tgId": str(tg_id),
                            "subId": sub_id,
                            "reset": 0
                        }
                    ]
                })
            }
            
            add_client_url = f"{self.base_url}/panel/api/inbounds/addClient"
            response = await self.client.post(
                add_client_url, 
                json=payload, 
                cookies=self.session_cookies,
                headers={"Content-Type": "application/json", "Accept": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    print(f"Пользователь {email} успешно создан в 3xUI")
                    return {
                        "success": True,
                        "email": email,
                        "vless_id": vless_id,
                        "sub_id": sub_id,
                        "expiry_time": expiry_time_ms
                    }
                else:
                    print(f"Ошибка создания пользователя: {result.get('msg', 'Неизвестная ошибка')}")
                    return None
            else:
                print(f"Ошибка HTTP при создании пользователя: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Ошибка при создании пользователя: {e}")
            return None
    
    async def get_user_config(self, email: str) -> Optional[str]:
        """Получение конфигурации пользователя"""
        await self.ensure_login()
        try:
            # Получаем список inbounds
            inbounds = await self.get_inbounds()
            if not inbounds or not inbounds.get("obj"):
                return None
            
            # Ищем пользователя во всех inbounds
            for inbound in inbounds["obj"]:
                if not inbound.get("enable", False):
                    continue
                
                settings = json.loads(inbound.get("settings", "{}"))
                clients = settings.get("clients", [])
                
                for client in clients:
                    if client.get("email") == email:
                        # Формируем VLESS ссылку
                        server_config = inbound.get("streamSettings", {})
                        network = server_config.get("network", "tcp")
                        
                        if network == "ws":
                            # WebSocket конфигурация
                            ws_settings = server_config.get("wsSettings", {})
                            path = ws_settings.get("path", "")
                            host = ws_settings.get("headers", {}).get("Host", "")
                            
                            config = f"vless://{client['id']}@{self.base_url.split('://')[1].split('/')[0]}:443?type=ws&security=tls&path={path}&host={host}&sni={host}#{email}"
                        else:
                            # TCP конфигурация
                            config = f"vless://{client['id']}@{self.base_url.split('://')[1].split('/')[0]}:443?security=tls&sni={self.base_url.split('://')[1].split('/')[0]}&type=tcp#{email}"
                        
                        return config
            
            return None
            
        except Exception as e:
            print(f"Ошибка при получении конфигурации: {e}")
            return None
    
    async def sync_subscriptions(self) -> Dict[str, Any]:
        """Синхронизация подписок с 3xUI"""
        await self.ensure_login()
        try:
            # Получаем список inbounds
            inbounds = await self.get_inbounds()
            if not inbounds or not inbounds.get("obj"):
                return {"success": False, "msg": "Не удалось получить inbounds"}
            
            active_clients = []
            
            # Проходим по всем inbounds
            for inbound in inbounds["obj"]:
                if not inbound.get("enable", False):
                    continue
                
                settings = json.loads(inbound.get("settings", "{}"))
                clients = settings.get("clients", [])
                
                for client in clients:
                    if client.get("enable", True):
                        # Проверяем, не истек ли срок
                        expiry_time = client.get("expiryTime", 0)
                        if expiry_time > 0:
                            expiry_datetime = datetime.fromtimestamp(expiry_time / 1000)
                            if expiry_datetime > datetime.now():
                                active_clients.append({
                                    "email": client.get("email", ""),
                                    "id": client.get("id", ""),
                                    "expiryTime": expiry_time,
                                    "expiryDate": expiry_datetime.isoformat(),
                                    "tgId": client.get("tgId", ""),
                                    "subId": client.get("subId", "")
                                })
            
            return {
                "success": True,
                "active_clients": active_clients,
                "total_clients": len(active_clients)
            }
            
        except Exception as e:
            print(f"Ошибка при синхронизации: {e}")
            return {"success": False, "msg": str(e)}
    
    async def delete_user(self, email: str) -> bool:
        """Удаление пользователя из 3xUI"""
        await self.ensure_login()
        try:
            # Получаем список inbounds
            inbounds = await self.get_inbounds()
            if not inbounds or not inbounds.get("obj"):
                return False
            
            # Ищем пользователя во всех inbounds
            for inbound in inbounds["obj"]:
                if not inbound.get("enable", False):
                    continue
                
                settings = json.loads(inbound.get("settings", "{}"))
                clients = settings.get("clients", [])
                
                # Ищем клиента с нужным email
                client_to_remove = None
                for client in clients:
                    if client.get("email") == email:
                        client_to_remove = client
                        break
                
                if client_to_remove:
                    # Удаляем клиента из списка
                    clients.remove(client_to_remove)
                    
                    # Обновляем inbound
                    update_payload = {
                        "id": inbound["id"],
                        "settings": json.dumps({"clients": clients})
                    }
                    
                    update_url = f"{self.base_url}/panel/api/inbounds/update/{inbound['id']}"
                    response = await self.client.post(
                        update_url,
                        json=update_payload,
                        cookies=self.session_cookies,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success"):
                            print(f"Пользователь {email} успешно удален из 3xUI")
                            return True
                        else:
                            print(f"Ошибка удаления пользователя: {result.get('msg', 'Неизвестная ошибка')}")
                            return False
                    else:
                        print(f"Ошибка HTTP при удалении пользователя: {response.status_code}")
                        return False
            
            print(f"Пользователь {email} не найден в 3xUI")
            return False
            
        except Exception as e:
            print(f"Ошибка при удалении пользователя: {e}")
            return False
    
    async def close(self):
        """Закрытие соединения"""
        await self.client.aclose()

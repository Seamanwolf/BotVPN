import httpx
import json
from typing import Dict, Any, Optional
from config import XUI_BASE_URL, XUI_PORT, XUI_WEBBASEPATH, XUI_USERNAME, XUI_PASSWORD

class XUIClient:
    def __init__(self):
        # Формируем полный URL с портом и базовым путем
        if XUI_PORT:
            self.base_url = f"http://{XUI_BASE_URL}:{XUI_PORT}"
        else:
            self.base_url = f"http://{XUI_BASE_URL}"
        
        # Добавляем базовый путь если указан
        if XUI_WEBBASEPATH:
            self.base_url += f"/{XUI_WEBBASEPATH}"
        
        # print(f"DEBUG: Base URL = {self.base_url}")
        
        self.username = XUI_USERNAME
        self.password = XUI_PASSWORD
        self.client = httpx.AsyncClient(follow_redirects=True)
        self.session_cookies = None
        self.logged_in = False
    
    async def login(self) -> bool:
        """Авторизация в 3xUI"""
        if self.logged_in:
            return True
            
        try:
            login_url = f"{self.base_url}/login"
            # print(f"DEBUG: Login URL = {login_url}")
            
            login_data = {
                "username": self.username,
                "password": self.password
            }
            
            # print(f"DEBUG: Login data = {login_data}")
            
            response = await self.client.post(
                login_url,
                json=login_data,
                headers={"Content-Type": "application/json"}
            )
            
            # print(f"DEBUG: Login response status = {response.status_code}")
            # print(f"DEBUG: Login response text = {response.text[:200]}...")
            
            if response.status_code == 200:
                # Сохраняем cookies для последующих запросов
                self.session_cookies = response.cookies
                self.logged_in = True
                # print("DEBUG: Login successful")
                return True
            else:
                print(f"Ошибка авторизации: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"Ошибка при авторизации: {e}")
            return False
    
    async def ensure_login(self):
        """Гарантирует, что мы авторизованы"""
        if not self.logged_in:
            await self.login()
    
    async def get_inbounds(self) -> Optional[Dict[str, Any]]:
        """Получение списка inbounds"""
        await self.ensure_login()
        
        try:
            inbounds_url = f"{self.base_url}/panel/api/inbounds/list"
            # print(f"DEBUG: Inbounds URL = {inbounds_url}")
            
            response = await self.client.get(
                inbounds_url,
                cookies=self.session_cookies
            )
            
            # print(f"DEBUG: Inbounds response status = {response.status_code}")
            # print(f"DEBUG: Inbounds response text = {response.text[:200]}...")
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Ошибка получения inbounds: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Ошибка при получении inbounds: {e}")
            return None
    
    async def create_user(self, email: str, days: int = 30, note: str = "") -> Optional[Dict[str, Any]]:
        """Создание пользователя в 3xUI"""
        await self.ensure_login()
        
        try:
            # Сначала получаем список inbounds
            inbounds = await self.get_inbounds()
            if not inbounds or not inbounds.get("obj"):
                print("Не удалось получить список inbounds")
                return None
            
            # Берем первый inbound (можно настроить выбор конкретного)
            inbound = inbounds["obj"][0]
            inbound_id = inbound["id"]
            
            # Создаем только нового клиента
            import uuid
            user_data = {
                "id": inbound_id,
                "client": {
                    "id": str(uuid.uuid4()),  # UUID для VLESS
                    "flow": "xtls-rprx-vision",
                    "email": email,
                    "limitIp": 0,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": ""
                }
            }
            
            response = await self.client.post(
                f"{self.base_url}/panel/api/inbounds/addClient",
                json=user_data,
                cookies=self.session_cookies,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"Пользователь создан: {result}")
                return result
            else:
                print(f"Ошибка создания пользователя: {response.status_code}")
                print(f"Ответ: {response.text}")
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
            
            # Ищем пользователя в inbounds
            for inbound in inbounds["obj"]:
                import json
                settings = json.loads(inbound["settings"])
                stream_settings = json.loads(inbound["streamSettings"])
                
                if "clients" in settings:
                    for client in settings["clients"]:
                        if client.get("email") == email:
                            # Формируем ссылку на основе протокола
                            protocol = inbound.get("protocol", "vless")
                            if protocol == "vless":
                                # VLESS Reality ссылка
                                reality_settings = stream_settings.get("realitySettings", {})
                                server_name = reality_settings.get("serverNames", [""])[0]
                                public_key = reality_settings.get("settings", {}).get("publicKey", "")
                                short_ids = reality_settings.get("shortIds", [""])
                                
                                config = f"vless://{client['id']}@{server_name}:{inbound['port']}?type=tcp&security=reality&sni={server_name}&fp=chrome&pbk={public_key}&sid={short_ids[0]}&spx=%2F#{email}"
                                return config
                            else:
                                # Другие протоколы
                                return f"{protocol}://{client['id']}@{stream_settings.get('serverName', '')}:{inbound['port']}"
            
            return None
            
        except Exception as e:
            print(f"Ошибка при получении конфигурации: {e}")
            return None
    
    async def close(self):
        """Закрытие клиента"""
        await self.client.aclose()

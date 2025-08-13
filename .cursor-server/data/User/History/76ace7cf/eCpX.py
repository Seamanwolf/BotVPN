#!/usr/bin/env python3
"""
Тестовый скрипт для проверки API 3xUI
"""

import asyncio
import httpx
import json
from config import XUI_BASE_URL, XUI_PORT, XUI_WEBBASEPATH, XUI_USERNAME, XUI_PASSWORD

class XUITester:
    def __init__(self):
        # Формируем полный URL с портом и базовым путем
        if XUI_PORT:
            self.base_url = f"http://{XUI_BASE_URL}:{XUI_PORT}"
        else:
            self.base_url = f"http://{XUI_BASE_URL}"
        
        # Добавляем базовый путь если указан
        if XUI_WEBBASEPATH:
            self.base_url += f"/{XUI_WEBBASEPATH}"
        
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
            print(f"🔧 Login URL: {login_url}")
            
            login_data = {
                "username": self.username,
                "password": self.password
            }
            
            response = await self.client.post(
                login_url,
                json=login_data,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"🔧 Login status: {response.status_code}")
            print(f"🔧 Login response: {response.text[:200]}...")
            
            if response.status_code == 200:
                self.session_cookies = response.cookies
                self.logged_in = True
                print("✅ Login successful")
                return True
            else:
                print(f"❌ Login failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    async def get_inbounds(self):
        """Получение списка inbounds"""
        if not self.logged_in:
            await self.login()
        
        try:
            inbounds_url = f"{self.base_url}/panel/api/inbounds/list"
            print(f"🔧 Inbounds URL: {inbounds_url}")
            
            response = await self.client.get(
                inbounds_url,
                cookies=self.session_cookies
            )
            
            print(f"🔧 Inbounds status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"🔧 Inbounds: {json.dumps(result, indent=2)}")
                return result
            else:
                print(f"❌ Inbounds failed: {response.status_code}")
                print(f"❌ Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Inbounds error: {e}")
            return None
    
    async def test_add_client(self, inbound_id):
        """Тест добавления клиента"""
        if not self.logged_in:
            await self.login()
        
        try:
            # Тестовые данные
            test_payload = {
                "id": inbound_id,
                "settings": json.dumps({
                    "clients": [
                        {
                            "id": "test-uuid-123",
                            "flow": "xtls-rprx-vision",
                            "email": "test@example.com",
                            "limitIp": 3,
                            "totalGB": 0,
                            "expiryTime": 1755114301574,
                            "enable": True,
                            "tgId": "123456789",
                            "subId": "test-sub-123",
                            "reset": 0
                        }
                    ]
                })
            }
            
            add_client_url = f"{self.base_url}/panel/api/inbounds/addClient"
            print(f"🔧 Testing addClient URL: {add_client_url}")
            print(f"🔧 Payload: {json.dumps(test_payload, indent=2)}")
            
            response = await self.client.post(
                add_client_url,
                json=test_payload,
                cookies=self.session_cookies,
                headers={"Content-Type": "application/json", "Accept": "application/json"}
            )
            
            print(f"🔧 AddClient status: {response.status_code}")
            print(f"🔧 AddClient response: {response.text}")
            
            return response.json() if response.status_code == 200 else None
            
        except Exception as e:
            print(f"❌ AddClient error: {e}")
            return None
    
    async def close(self):
        """Закрытие клиента"""
        await self.client.aclose()

async def main():
    tester = XUITester()
    
    try:
        print("🚀 Тестирование API 3xUI...")
        
        # Получаем inbounds
        inbounds = await tester.get_inbounds()
        if inbounds and inbounds.get("obj"):
            inbound_id = inbounds["obj"][0]["id"]
            print(f"🔧 Найден inbound ID: {inbound_id}")
            
            # Тестируем addClient
            result = await tester.test_add_client(inbound_id)
            print(f"🔧 Результат теста: {result}")
        else:
            print("❌ Не удалось получить inbounds")
    
    finally:
        await tester.close()

if __name__ == "__main__":
    asyncio.run(main())

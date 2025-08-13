#!/usr/bin/env python3
"""
Тестовый скрипт для проверки создания пользователя в 3xUI
"""

import asyncio
import httpx
import json
import uuid
from config import XUI_BASE_URL, XUI_PORT, XUI_WEBBASEPATH, XUI_USERNAME, XUI_PASSWORD

async def test_create_user():
    # Формируем URL
    if XUI_PORT:
        base_url = f"http://{XUI_BASE_URL}:{XUI_PORT}"
    else:
        base_url = f"http://{XUI_BASE_URL}"
    
    if XUI_WEBBASEPATH:
        base_url += f"/{XUI_WEBBASEPATH}"
    
    print(f"Testing URL: {base_url}")
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            # 1. Авторизация
            print("\n1. Login...")
            login_data = {
                "username": XUI_USERNAME,
                "password": XUI_PASSWORD
            }
            
            login_response = await client.post(
                f"{base_url}/login",
                json=login_data,
                headers={"Content-Type": "application/json"}
            )
            
            if login_response.status_code != 200:
                print(f"Login failed: {login_response.status_code}")
                return
            
            print("Login successful!")
            
            # 2. Получаем inbounds
            print("\n2. Getting inbounds...")
            inbounds_response = await client.get(
                f"{base_url}/panel/api/inbounds/list",
                cookies=login_response.cookies
            )
            
            if inbounds_response.status_code != 200:
                print(f"Failed to get inbounds: {inbounds_response.status_code}")
                return
            
            inbounds_data = inbounds_response.json()
            if not inbounds_data.get("success") or not inbounds_data.get("obj"):
                print("No inbounds found")
                return
            
            inbound = inbounds_data["obj"][0]
            inbound_id = inbound["id"]
            print(f"Found inbound ID: {inbound_id}")
            
            # 3. Создаем тестового пользователя
            print("\n3. Creating test user...")
            test_email = f"test_user_{int(asyncio.get_event_loop().time())}@vpn.local"
            
            user_data = {
                "id": inbound_id,
                "client": {
                    "id": str(uuid.uuid4()),  # UUID для VLESS
                    "flow": "xtls-rprx-vision",
                    "email": test_email,
                    "limitIp": 0,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": ""
                }
            }
            
            print(f"User data: {json.dumps(user_data, indent=2)}")
            
            create_response = await client.post(
                f"{base_url}/panel/api/inbounds/updateClient/{inbound_id}",
                json=user_data,
                cookies=login_response.cookies,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"Create response status: {create_response.status_code}")
            print(f"Create response: {create_response.text}")
            
            if create_response.status_code == 200:
                result = create_response.json()
                print(f"User created successfully: {result}")
            else:
                print("Failed to create user")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_create_user())

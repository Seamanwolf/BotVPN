#!/usr/bin/env python3
"""
Тестовый скрипт для проверки API 3xUI
"""

import asyncio
import httpx
from config import XUI_BASE_URL, XUI_PORT, XUI_WEBBASEPATH, XUI_USERNAME, XUI_PASSWORD

async def test_xui_api():
    # Формируем URL
    if XUI_PORT:
        base_url = f"http://{XUI_BASE_URL}:{XUI_PORT}"
    else:
        base_url = f"http://{XUI_BASE_URL}"
    
    if XUI_WEBBASEPATH:
        base_url += f"/{XUI_WEBBASEPATH}"
    
    print(f"Testing URL: {base_url}")
    print(f"Username: {XUI_USERNAME}")
    print(f"Password: {XUI_PASSWORD}")
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            # Тест 1: Проверяем доступность сервера
            print("\n1. Testing server availability...")
            response = await client.get(base_url)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text[:500]}...")
            
            # Тест 2: Пробуем авторизацию
            print("\n2. Testing login...")
            login_data = {
                "username": XUI_USERNAME,
                "password": XUI_PASSWORD
            }
            
            login_response = await client.post(
                f"{base_url}/login",
                json=login_data,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"Login Status: {login_response.status_code}")
            print(f"Login Response: {login_response.text[:500]}...")
            
            if login_response.status_code == 200:
                print("Login successful!")
                
                # Тест 3: Получаем inbounds
                print("\n3. Testing inbounds...")
                inbounds_response = await client.get(
                    f"{base_url}/panel/api/inbounds/list",
                    cookies=login_response.cookies
                )
                
                print(f"Inbounds Status: {inbounds_response.status_code}")
                print(f"Inbounds Response: {inbounds_response.text[:500]}...")
                
                if inbounds_response.status_code == 200:
                    try:
                        data = inbounds_response.json()
                        print(f"Inbounds JSON: {data}")
                    except Exception as e:
                        print(f"JSON parse error: {e}")
            else:
                print("Login failed!")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_xui_api())

#!/usr/bin/env python3
"""
Тестовый скрипт для проверки подключения к 3xUI
"""

import asyncio
import os
from xui_client import XUIClient

async def test_xui_connection():
    """Тестирование подключения к 3xUI"""
    print("🔍 Тестирование подключения к 3xUI...")
    
    # Устанавливаем переменные окружения
    os.environ['XUI_BASE_URL'] = 'nl.universaltools.pro'
    os.environ['XUI_PORT'] = '34235'
    os.environ['XUI_WEBBASEPATH'] = 'CVbzPVZjXGDiTsw'
    os.environ['XUI_USERNAME'] = 'XBYiLVDMb5'
    os.environ['XUI_PASSWORD'] = 'zclNU7rzrF'
    
    client = XUIClient()
    
    print(f"📍 Base URL: {client.base_url}")
    print(f"👤 Username: {client.username}")
    print(f"🔑 Password: {client.password}")
    
    # Тестируем авторизацию
    print("\n🔐 Тестирование авторизации...")
    login_success = await client.login()
    print(f"✅ Авторизация: {'Успешно' if login_success else 'Ошибка'}")
    
    if login_success:
        # Тестируем получение inbounds
        print("\n📋 Получение списка inbounds...")
        inbounds = await client.get_inbounds()
        
        if inbounds:
            print(f"✅ Inbounds получены: {len(inbounds.get('obj', []))} inbound(s)")
            for i, inbound in enumerate(inbounds.get('obj', [])):
                print(f"  {i+1}. ID: {inbound.get('id')}, Remark: {inbound.get('remark')}")
        else:
            print("❌ Не удалось получить inbounds")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(test_xui_connection())

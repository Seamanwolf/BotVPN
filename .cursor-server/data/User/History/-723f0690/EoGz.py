#!/usr/bin/env python3
"""
Скрипт для проверки клиентов в 3xUI
"""

import asyncio
from xui_client import XUIClient

async def check_xui_clients():
    """Проверка клиентов в 3xUI"""
    print("🔍 Проверяем клиентов в 3xUI...")
    
    xui_client = XUIClient()
    try:
        sync_result = await xui_client.sync_subscriptions()
        
        if sync_result.get("success"):
            active_clients = sync_result.get("active_clients", [])
            print(f"📊 Активных клиентов в 3xUI: {len(active_clients)}")
            
            for i, client in enumerate(active_clients, 1):
                print(f"\n📋 Клиент {i}:")
                print(f"   Email: {client.get('email', 'N/A')}")
                print(f"   ID: {client.get('id', 'N/A')}")
                print(f"   SubId: {client.get('subId', 'N/A')}")
                print(f"   Inbound ID: {client.get('inbound_id', 'N/A')}")
                print(f"   Inbound Port: {client.get('inbound_port', 'N/A')}")
        else:
            print(f"❌ Ошибка получения данных из 3xUI: {sync_result.get('msg', 'Неизвестная ошибка')}")
            
    except Exception as e:
        print(f"❌ Ошибка при проверке 3xUI: {e}")
    finally:
        await xui_client.close()

if __name__ == "__main__":
    asyncio.run(check_xui_clients())


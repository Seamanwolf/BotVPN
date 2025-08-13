#!/usr/bin/env python3

from xui_client import XUIClient
import asyncio

async def check_inbounds():
    try:
        xui_client = XUIClient()
        await xui_client.ensure_login()
        
        print("Получаем список inbounds...")
        inbounds = await xui_client.get_inbounds()
        
        if inbounds and 'obj' in inbounds:
            print(f"Найдено inbounds: {len(inbounds['obj'])}")
            for i, inbound in enumerate(inbounds['obj']):
                print(f"\nInbound {i+1}:")
                print(f"  ID: {inbound.get('id')}")
                print(f"  Name: {inbound.get('remark', 'N/A')}")
                print(f"  Port: {inbound.get('port')}")
                print(f"  Protocol: {inbound.get('protocol')}")
                print(f"  Enable: {inbound.get('enable')}")
                
                # Проверяем клиентов
                if 'settings' in inbound and inbound['settings']:
                    import json
                    try:
                        settings = json.loads(inbound['settings'])
                        if 'clients' in settings:
                            print(f"  Клиентов: {len(settings['clients'])}")
                            for j, client in enumerate(settings['clients']):
                                print(f"    Клиент {j+1}: {client.get('email', 'N/A')}")
                        else:
                            print(f"  Клиентов: 0")
                    except:
                        print(f"  Ошибка парсинга settings")
                else:
                    print(f"  Клиентов: 0")
        else:
            print("Не удалось получить inbounds")
            
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(check_inbounds())

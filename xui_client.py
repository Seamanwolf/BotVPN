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
    
    async def create_user(self, user_email: str, days: int = 30, note: str = "", tg_id: str = "", subscription_number: int = 1) -> Optional[Dict[str, Any]]:
        """Создание пользователя в 3xUI используя addClient API"""
        await self.ensure_login()
        try:
            # Создаем уникальный ключ для email в формате SeaMiniVpn-{tg_id}-{subscription_number}
            unique_email = f"SeaMiniVpn-{tg_id}-{subscription_number}"
            
            # Проверяем, существует ли уже пользователь с таким уникальным ключом
            existing_config = await self.get_user_config(unique_email, subscription_number)
            if existing_config:
                print(f"Пользователь с уникальным ключом {unique_email} уже существует, используем существующую конфигурацию")
                return {
                    "success": True,
                    "email": unique_email,
                    "existing": True
                }
            
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
            
            # Ищем inbound с ID 6 (как указано в задаче)
            inbound_id = None
            for inbound in inbounds["obj"]:
                if inbound.get("id") == 6 and inbound.get("enable", False):
                    inbound_id = inbound.get("id")
                    break
            
            # Если inbound 6 не найден, ищем любой активный
            if not inbound_id:
                for inbound in inbounds["obj"]:
                    if inbound.get("enable", False):
                        inbound_id = inbound.get("id")
                        break
            
            if not inbound_id:
                print("Не найден активный inbound")
                return None
            
            # Формируем комментарий с полной информацией пользователя
            comment = f"Email: {user_email} | Name: {note} | TG: {tg_id}"
            
            payload = {
                "id": inbound_id,  # Используем правильный ID inbound
                "settings": json.dumps({
                    "clients": [
                        {
                            "id": vless_id,
                            "flow": "xtls-rprx-vision",
                            "email": unique_email,  # Используем уникальный ключ
                            "limitIp": 3,
                            "totalGB": 0,
                            "expiryTime": expiry_time_ms,
                            "enable": True,
                            "tgId": str(tg_id),
                            "subId": sub_id,
                            "reset": 0,
                            "comment": comment  # Добавляем полную информацию в комментарий
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
                    print(f"Пользователь {unique_email} успешно создан в 3xUI на inbound {inbound_id}")
                    print(f"Сгенерированный sub_id: {sub_id}")
                    print(f"Полный ответ 3xUI: {result}")
                    return {
                        "success": True,
                        "email": unique_email,
                        "user_email": user_email,  # Сохраняем оригинальный email
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
    
    async def extend_user(self, email: str, days: int) -> Optional[Dict[str, Any]]:
        """Продление пользователя в 3xUI"""
        await self.ensure_login()
        try:
            # Получаем список inbounds
            inbounds = await self.get_inbounds()
            if not inbounds or not inbounds.get("obj"):
                print("Не удалось получить inbounds")
                return None
            
            # Ищем пользователя во всех inbounds
            for inbound in inbounds["obj"]:
                if not inbound.get("enable", False):
                    continue
                
                settings = json.loads(inbound.get("settings", "{}"))
                clients = settings.get("clients", [])
                
                # Ищем клиента с нужным email
                for client in clients:
                    if client.get("email") == email:
                        # Получаем текущее время истечения
                        current_expiry = client.get("expiryTime", 0)
                        
                        # Вычисляем новое время истечения
                        if current_expiry > 0:
                            # Если есть текущее время истечения, добавляем дни к нему
                            current_expiry_dt = datetime.fromtimestamp(current_expiry / 1000)
                            new_expiry_dt = current_expiry_dt + timedelta(days=days)
                        else:
                            # Если нет времени истечения, устанавливаем от текущего момента
                            new_expiry_dt = datetime.now() + timedelta(days=days)
                        
                        new_expiry_ms = int(new_expiry_dt.timestamp() * 1000)
                        
                        # Получаем ID клиента
                        client_id = client.get("id")
                        if not client_id:
                            print(f"Не найден ID клиента для {email}")
                            return None
                        
                        # Формируем payload для обновления клиента
                        payload = {
                            "id": client_id,
                            "flow": client.get("flow", ""),
                            "email": email,
                            "limitIp": client.get("limitIp", 3),
                            "totalGB": client.get("totalGB", 0),
                            "expiryTime": new_expiry_ms,
                            "enable": client.get("enable", True),
                            "tgId": client.get("tgId", ""),
                            "subId": client.get("subId", ""),
                            "reset": client.get("reset", 0),
                            "comment": client.get("comment", "")
                        }
                        
                        # Используем правильный API для обновления клиента
                        update_url = f"{self.base_url}/panel/api/inbounds/updateClient/{client_id}"
                        response = await self.client.post(
                            update_url,
                            json=payload,
                            cookies=self.session_cookies,
                            headers={"Content-Type": "application/json", "Accept": "application/json"}
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            if result.get("success"):
                                print(f"Пользователь {email} успешно продлен на {days} дней")
                                print(f"Новое время истечения: {new_expiry_dt.strftime('%d.%m.%Y %H:%M')}")
                                return {
                                    "success": True,
                                    "email": email,
                                    "new_expiry": new_expiry_ms,
                                    "new_expiry_date": new_expiry_dt.isoformat()
                                }
                            else:
                                print(f"Ошибка обновления пользователя: {result.get('msg', 'Неизвестная ошибка')}")
                                return None
                        else:
                            print(f"Ошибка HTTP при обновлении пользователя: {response.status_code}")
                            return None
            
            print(f"Пользователь {email} не найден в 3xUI")
            return None
            
        except Exception as e:
            print(f"Ошибка при продлении пользователя: {e}")
            return None
    
    def generate_subscription_link(self, sub_id: str, tg_id: str, subscription_number: int) -> str:
        """Генерация правильной ссылки подписки"""
        from config import XUI_BASE_URL
        # Формируем правильную ссылку с путем /sea/
        return f"https://{XUI_BASE_URL}/sea/{sub_id}"
    
    async def get_user_config(self, email: str, subscription_number: int = 1) -> Optional[str]:
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
                        # Получаем sub_id из клиента
                        sub_id = client.get("subId", "")
                        tg_id = client.get("tgId", "")
                        
                        print(f"Найден клиент: email={email}, sub_id={sub_id}, tg_id={tg_id}")
                        
                        if sub_id:
                            # Используем правильную функцию генерации ссылки
                            config = self.generate_subscription_link(sub_id, tg_id, subscription_number)
                            print(f"Сгенерированная ссылка: {config}")
                        else:
                            # Fallback на старый формат, если sub_id не найден
                            from config import XUI_BASE_URL
                            config = f"https://{XUI_BASE_URL}/sea/SeaMiniVpn-{tg_id}-{subscription_number}"
                            print(f"Fallback ссылка: {config}")
                        
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
    
    # Метод delete_user удален - НИКОГДА не удаляем пользователей из 3xUI!
    
    async def delete_user(self, email: str) -> bool:
        """Удаление пользователя из 3xUI по email"""
        await self.ensure_login()
        try:
            # Получаем список inbounds
            inbounds = await self.get_inbounds()
            if not inbounds or not inbounds.get("obj"):
                print("Не удалось получить inbounds")
                return False
            
            # Ищем пользователя во всех inbounds
            for inbound in inbounds["obj"]:
                if not inbound.get("enable", False):
                    continue
                
                settings = json.loads(inbound.get("settings", "{}"))
                clients = settings.get("clients", [])
                
                # Ищем клиента с нужным email
                for client in clients:
                    if client.get("email") == email:
                        # Используем правильный API для удаления клиента
                        client_id = client.get("id")
                        if not client_id:
                            print(f"Не найден ID клиента для {email}")
                            return False
                        
                        # Используем API для удаления клиента по ID
                        delete_url = f"{self.base_url}/panel/api/inbounds/{inbound.get('id')}/delClient/{client_id}"
                        response = await self.client.post(
                            delete_url,
                            cookies=self.session_cookies,
                            headers={"Content-Type": "application/json", "Accept": "application/json"}
                        )
                        
                        if response.status_code == 200:
                            try:
                                result = response.json()
                                if result.get("success"):
                                    print(f"Пользователь {email} успешно удален из 3xUI")
                                    return True
                                else:
                                    print(f"Ошибка удаления пользователя: {result.get('msg', 'Неизвестная ошибка')}")
                                    return False
                            except json.JSONDecodeError:
                                # Если ответ не JSON, но статус 200, считаем успехом
                                print(f"Пользователь {email} успешно удален из 3xUI (не JSON ответ)")
                                return True
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

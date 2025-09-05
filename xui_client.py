import httpx
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import re

class XUIClient:
    def __init__(self):
        from config import XUI_BASE_URL, XUI_PORT, XUI_WEBBASEPATH, XUI_USERNAME, XUI_PASSWORD
        
        # Пробуем сначала HTTPS, потом HTTP
        self.base_url_https = f"https://{XUI_BASE_URL}:{XUI_PORT}/{XUI_WEBBASEPATH}"
        self.base_url_http = f"http://{XUI_BASE_URL}:{XUI_PORT}/{XUI_WEBBASEPATH}"
        self.base_url = self.base_url_https  # Начинаем с HTTPS
        self.username = XUI_USERNAME
        self.password = XUI_PASSWORD
        self.session_cookies = None
        self.client = None
    
    async def _get_client(self):
        """Создает новый httpx клиент для каждого запроса"""
        try:
            # Всегда создаем новый клиент для каждого запроса с поддержкой редиректов
            return httpx.AsyncClient(
                verify=False, 
                timeout=30.0,
                follow_redirects=True,  # Автоматически следуем редиректам
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        except Exception as e:
            logging.error(f"Ошибка создания httpx клиента: {e}")
            # Создаем новый клиент при ошибке
            return httpx.AsyncClient(
                verify=False, 
                timeout=30.0,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
    
    def _switch_protocol(self):
        """Переключает между HTTP и HTTPS"""
        if self.base_url == self.base_url_https:
            self.base_url = self.base_url_http
            print("Переключились на HTTP")
        else:
            self.base_url = self.base_url_https
            print("Переключились на HTTPS")
        # Сбрасываем cookies при смене протокола
        self.session_cookies = None
    
    async def ensure_login(self):
        """Обеспечивает авторизацию в 3xUI"""
        if self.session_cookies:
            return
        
        max_attempts = 2  # Пробуем HTTPS и HTTP
        for attempt in range(max_attempts):
            client = await self._get_client()
            login_url = f"{self.base_url}/login"
            login_data = {
                "username": self.username,
                "password": self.password
            }
            
            try:
                print(f"Попытка авторизации {attempt + 1}: {self.base_url}")
                response = await client.post(login_url, json=login_data)
                
                if response.status_code == 200:
                    self.session_cookies = response.cookies
                    print("Успешная авторизация в 3xUI")
                    await client.aclose()
                    return
                else:
                    print(f"Ошибка авторизации: {response.status_code}")
                    if attempt < max_attempts - 1:
                        self._switch_protocol()
                        continue
                    else:
                        raise Exception(f"Ошибка авторизации в 3xUI: {response.status_code}")
                        
            except Exception as e:
                print(f"Ошибка при авторизации (попытка {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    self._switch_protocol()
                    continue
                else:
                    await client.aclose()
                    raise
            finally:
                try:
                    await client.aclose()
                except:
                    pass
    
    async def get_inbounds(self) -> Optional[Dict[str, Any]]:
        """Получение списка inbounds"""
        await self.ensure_login()
        client = None
        try:
            client = await self._get_client()
            url = f"{self.base_url}/panel/api/inbounds/list"
            response = await client.get(url, cookies=self.session_cookies)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Ошибка получения inbounds: {response.status_code}")
                return None
        except Exception as e:
            print(f"Ошибка при получении inbounds: {e}")
            return None
        finally:
            if client:
                try:
                    await client.aclose()
                except:
                    pass
    
    async def create_user(self, user_email: str, days: int = 30, note: str = "", tg_id: str = "", subscription_number: int = 1, ip_limit: int = 3) -> Optional[Dict[str, Any]]:
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
                            "limitIp": ip_limit,
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
            client = await self._get_client()
            response = await client.post(
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
                print(f"Ответ сервера: {response.text}")
                # Если получили 307, пробуем переключить протокол
                if response.status_code == 307:
                    print("Получен HTTP 307, пробуем переключить протокол...")
                    self._switch_protocol()
                    # Повторяем попытку с новым протоколом
                    await self.ensure_login()
                    response = await client.post(
                        add_client_url, 
                        json=payload, 
                        cookies=self.session_cookies,
                        headers={"Content-Type": "application/json", "Accept": "application/json"}
                    )
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success"):
                            print(f"Пользователь {unique_email} успешно создан в 3xUI после переключения протокола")
                            return {
                                "success": True,
                                "email": unique_email,
                                "user_email": user_email,
                                "vless_id": vless_id,
                                "sub_id": sub_id,
                                "expiry_time": expiry_time_ms
                            }
                return None
                
        except Exception as e:
            print(f"Ошибка при создании пользователя: {e}")
            return None
    
    async def extend_user(self, email: str, days: int) -> Optional[Dict[str, Any]]:
        """Продление пользователя в 3xUI"""
        import logging
        logging.debug(f"XUI: Начало продления пользователя {email} на {days} дней")
        
        # Создаем новый клиент для каждого запроса
        try:
            await self.ensure_login()
        except Exception as e:
            logging.error(f"XUI: Ошибка при авторизации: {e}")
            # Сбрасываем клиент и пробуем снова
            self.client = None
            try:
                await self.ensure_login()
            except Exception as e2:
                logging.error(f"XUI: Повторная ошибка при авторизации: {e2}")
                return None
        
        try:
            # Получаем список inbounds
            try:
                inbounds = await self.get_inbounds()
                if not inbounds or not inbounds.get("obj"):
                    logging.error("XUI: Не удалось получить inbounds")
                    return None
            except Exception as e:
                logging.error(f"XUI: Ошибка при получении inbounds: {e}")
                # Сбрасываем клиент и пробуем снова
                self.client = None
                try:
                    inbounds = await self.get_inbounds()
                    if not inbounds or not inbounds.get("obj"):
                        logging.error("XUI: Повторная ошибка получения inbounds")
                        return None
                except Exception as e2:
                    logging.error(f"XUI: Повторная ошибка при получении inbounds: {e2}")
                    return None
            
            # Ищем пользователя во всех inbounds
            logging.debug(f"XUI: Ищем пользователя {email} в {len(inbounds['obj'])} inbounds")
            for inbound in inbounds["obj"]:
                if not inbound.get("enable", False):
                    continue
                
                settings = json.loads(inbound.get("settings", "{}"))
                clients = settings.get("clients", [])
                logging.debug(f"XUI: Проверяем inbound {inbound.get('id')} с {len(clients)} клиентами")
                
                # Ищем клиента с нужным email
                for client in clients:
                    if client.get("email") == email:
                        logging.debug(f"XUI: Найден клиент {email} в inbound {inbound.get('id')}")
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
                            "id": inbound.get("id"),  # ID inbound, а не клиента
                            "settings": json.dumps({
                                "clients": [
                                    {
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
                                ]
                            })
                        }
                        
                        # Используем правильный API для обновления клиента
                        update_url = f"{self.base_url}/panel/api/inbounds/updateClient/{client_id}"
                        http_client = None
                        try:
                            http_client = await self._get_client()
                            response = await http_client.post(
                                update_url,
                                json=payload,
                                cookies=self.session_cookies,
                                headers={"Content-Type": "application/json", "Accept": "application/json"}
                            )
                            
                            if response.status_code == 200:
                                result = response.json()
                                logging.debug(f"XUI: Ответ от API: {result}")
                                if result.get("success"):
                                    logging.info(f"XUI: Пользователь {email} успешно продлен на {days} дней")
                                    logging.debug(f"XUI: Новое время истечения: {new_expiry_dt.strftime('%d.%m.%Y %H:%M')}")
                                    return {
                                        "success": True,
                                        "email": email,
                                        "new_expiry": new_expiry_ms,
                                        "new_expiry_date": new_expiry_dt.isoformat()
                                    }
                                else:
                                    logging.error(f"XUI: Ошибка обновления пользователя: {result.get('msg', 'Неизвестная ошибка')}")
                                    return None
                            else:
                                logging.error(f"XUI: Ошибка HTTP при обновлении пользователя: {response.status_code}")
                                return None
                        finally:
                            if http_client:
                                try:
                                    await http_client.aclose()
                                except:
                                    pass
            
            logging.warning(f"XUI: Пользователь {email} не найден в 3xUI")
            return None
            
        except Exception as e:
            logging.error(f"XUI: Ошибка при продлении пользователя: {e}")
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
    
    async def get_client_traffics(self, email: str) -> Optional[Dict[str, Any]]:
        """Получение трафика клиента через специальный API endpoint"""
        await self.ensure_login()
        try:
            client = await self._get_client()
            traffics_url = f"{self.base_url}/panel/api/inbounds/getClientTraffics/{email}"
            
            print(f"Запрос трафика для {email}: {traffics_url}")
            response = await client.get(
                traffics_url,
                cookies=self.session_cookies,
                headers={"Accept": "application/json"}
            )
            
            if response.status_code == 200:
                traffics_data = response.json()
                print(f"Данные трафика для {email}: {traffics_data}")
                return traffics_data
            else:
                print(f"Ошибка получения трафика: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Ошибка при получении трафика клиента {email}: {e}")
            return None
        finally:
            try:
                await client.aclose()
            except:
                pass

    async def get_user_stats(self, unique_email: str) -> Optional[Dict[str, Any]]:
        """Получение статистики пользователя из 3xUI"""
        await self.ensure_login()
        try:
            # Получаем список inbounds
            inbounds = await self.get_inbounds()
            if not inbounds or not inbounds.get("obj"):
                print("Не удалось получить inbounds для статистики")
                return None
            
            # Ищем пользователя во всех inbounds
            for inbound in inbounds["obj"]:
                if not inbound.get("enable", False):
                    continue
                    
                inbound_id = inbound.get("id")
                settings = inbound.get("settings", {})
                
                if isinstance(settings, str):
                    try:
                        settings = json.loads(settings)
                    except:
                        continue
                
                clients = settings.get("clients", [])
                for client in clients:
                    if client.get("email") == unique_email:
                        # Получаем реальный трафик через специальный API
                        traffics_data = await self.get_client_traffics(unique_email)
                        
                        # Извлекаем данные трафика
                        traffic_used = 0
                        traffic_limit = 0
                        
                        if traffics_data and traffics_data.get("success"):
                            traffic_info = traffics_data.get("obj", {})
                            # Трафик может быть в разных полях, проверим несколько вариантов
                            if "up" in traffic_info and "down" in traffic_info:
                                traffic_used = traffic_info.get("up", 0) + traffic_info.get("down", 0)
                            elif "total" in traffic_info:
                                traffic_used = traffic_info.get("total", 0)
                            elif "used" in traffic_info:
                                traffic_used = traffic_info.get("used", 0)
                            
                            # Лимит трафика
                            if "totalGB" in traffic_info:
                                traffic_limit = traffic_info.get("totalGB", 0) * 1024 * 1024 * 1024
                            elif "limit" in traffic_info:
                                traffic_limit = traffic_info.get("limit", 0)
                        
                        # Если не удалось получить трафик через API, используем данные из клиента
                        if traffic_used == 0 and traffic_limit == 0:
                            # Проверяем разные поля для трафика в клиенте
                            if "up" in client and "down" in client:
                                traffic_used = client.get("up", 0) + client.get("down", 0)
                            elif "total" in client:
                                traffic_used = client.get("total", 0)
                            
                            if "totalGB" in client:
                                traffic_limit = client.get("totalGB", 0) * 1024 * 1024 * 1024
                        
                        stats = {
                            "email": unique_email,
                            "inbound_id": inbound_id,
                            "traffic_used": traffic_used,
                            "traffic_limit": traffic_limit,
                            "expiry_time": client.get("expiryTime", 0),
                            "enable": client.get("enable", False),
                            "limit_ip": client.get("limitIp", 0),
                            "tg_id": client.get("tgId", ""),
                            "sub_id": client.get("subId", ""),
                            "comment": client.get("comment", ""),
                            "raw_traffics_data": traffics_data  # Добавляем сырые данные для отладки
                        }
                        print(f"Статистика пользователя {unique_email}: {stats}")
                        return stats
            
            print(f"Пользователь {unique_email} не найден в 3xUI")
            return None
            
        except Exception as e:
            print(f"Ошибка при получении статистики пользователя {unique_email}: {e}")
            return None
    
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
                        client = await self._get_client()
                        response = await client.post(
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
    
    async def get_online_users(self) -> Optional[List[str]]:
        """Получение списка онлайн пользователей"""
        await self.ensure_login()
        try:
            client = await self._get_client()
            onlines_url = f"{self.base_url}/panel/api/inbounds/onlines"
            
            print(f"Запрос онлайн пользователей: {onlines_url}")
            response = await client.post(
                onlines_url,
                cookies=self.session_cookies,
                headers={"Accept": "application/json"}
            )
            
            if response.status_code == 200:
                onlines_data = response.json()
                print(f"Данные онлайн пользователей: {onlines_data}")
                
                if onlines_data.get("success") and isinstance(onlines_data.get("obj"), list):
                    online_emails = onlines_data.get("obj", [])
                    print(f"Найдено онлайн пользователей: {len(online_emails)}")
                    return online_emails
                else:
                    print("Некорректный формат ответа для онлайн пользователей")
                    return []
            else:
                print(f"Ошибка получения онлайн пользователей: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            print(f"Ошибка при получении онлайн пользователей: {e}")
            return []
        finally:
            try:
                await client.aclose()
            except:
                pass

    async def close(self):
        """Закрытие соединения"""
        if self.client:
            await self.client.aclose()

# Руководство по настройке 3xUI API

## 1. Получение доступа к API 3xUI

### Шаг 1: Авторизация
В 3xUI нет постоянного API ключа. Авторизация происходит через логин/пароль:

1. Откройте браузер и перейдите на вашу 3xUI панель
2. Откройте DevTools (F12)
3. Перейдите на вкладку Network
4. Войдите в панель с вашими учетными данными
5. Найдите запрос `/login` в Network вкладке
6. Изучите структуру запроса и ответа

### Шаг 2: Структура запроса авторизации
```json
POST /login
Content-Type: application/json

{
  "username": "admin",
  "password": "your_password"
}
```

### Шаг 3: Получение cookies
После успешной авторизации в ответе будут cookies, которые нужно использовать для всех последующих запросов.

## 2. Основные эндпоинты API

### Получение списка inbounds
```http
GET /panel/inbounds
```

### Создание пользователя
```http
POST /panel/inbound/updateClient/{inbound_id}
Content-Type: application/json

{
  "id": 1,
  "settings": {
    "clients": [
      {
        "id": "user-uuid",
        "flow": "",
        "email": "user@example.com",
        "limitIp": 0,
        "totalGB": 0,
        "expiryTime": 0,
        "enable": true,
        "tgId": "",
        "subId": ""
      }
    ]
  }
}
```

### Получение конфигурации пользователя
```http
GET /panel/inbound/get/{inbound_id}
```

## 3. Настройка в боте

### Шаг 1: Обновите файл .env
```bash
# 3xUI Configuration
XUI_BASE_URL=https://your-3xui-domain.com
XUI_USERNAME=admin
XUI_PASSWORD=your_password
```

### Шаг 2: Проверьте настройки inbound
1. Войдите в 3xUI панель
2. Перейдите в раздел Inbounds
3. Убедитесь, что у вас настроен Reality протокол
4. Запомните ID inbound'а

### Шаг 3: Настройка протокола Reality
Убедитесь, что в настройках inbound:
- Protocol: VLESS
- Security: Reality
- Server Name: ваш домен
- Public Key: сгенерированный ключ
- Short IDs: настроены

## 4. Тестирование API

### Тест авторизации
```bash
curl -X POST "https://your-3xui-domain.com/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}'
```

### Тест получения inbounds
```bash
curl -b cookies.txt "https://your-3xui-domain.com/panel/inbounds"
```

## 5. Обработка ошибок

### Частые ошибки:
1. **401 Unauthorized** - неправильные логин/пароль
2. **404 Not Found** - неправильный URL или эндпоинт
3. **500 Internal Server Error** - ошибка на стороне 3xUI

### Решения:
1. Проверьте правильность URL в .env
2. Убедитесь, что логин/пароль корректны
3. Проверьте, что 3xUI панель работает
4. Убедитесь, что inbound настроен правильно

## 6. Переход от демо к продакшену

### Шаг 1: Остановите демо-бот
```bash
pkill -f bot_demo.py
```

### Шаг 2: Настройте .env файл
```bash
# Обновите настройки 3xUI
XUI_BASE_URL=https://your-real-3xui-domain.com
XUI_USERNAME=your_admin_username
XUI_PASSWORD=your_admin_password
```

### Шаг 3: Запустите продакшен бота
```bash
python3 bot.py
```

## 7. Мониторинг и логи

### Просмотр логов бота
```bash
tail -f bot.log
```

### Проверка подключения к БД
```bash
sudo -u postgres psql -d vpn_bot -c "SELECT COUNT(*) FROM users;"
```

### Проверка активных подписок
```bash
sudo -u postgres psql -d vpn_bot -c "SELECT u.full_name, s.plan, s.expires_at FROM users u JOIN subscriptions s ON u.id = s.user_id WHERE s.status = 'active';"
```

## 8. Безопасность

### Рекомендации:
1. Используйте HTTPS для 3xUI панели
2. Регулярно меняйте пароли
3. Ограничьте доступ к API по IP
4. Используйте firewall
5. Регулярно обновляйте 3xUI

### Настройка firewall
```bash
# Разрешить доступ только с определенных IP
ufw allow from YOUR_SERVER_IP to any port 5432
ufw deny 5432
```

## 9. Масштабирование

### Добавление новых серверов:
1. Создайте новый inbound в 3xUI
2. Обновите код для выбора сервера
3. Добавьте балансировку нагрузки

### Мониторинг нагрузки:
```bash
# Проверка нагрузки на сервер
htop
# Проверка использования БД
sudo -u postgres psql -d vpn_bot -c "SELECT COUNT(*) FROM subscriptions WHERE status = 'active';"
```

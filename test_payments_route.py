#!/usr/bin/env python3
"""
Тест маршрута платежей
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from admin_web import app

def test_payments_route():
    """Тестирует маршрут платежей"""
    with app.test_client() as client:
        # Тестируем маршрут платежей
        response = client.get('/payments')
        print(f"Статус ответа: {response.status_code}")
        print(f"Заголовки: {dict(response.headers)}")
        
        if response.status_code == 302:
            print("✅ Редирект на логин (ожидаемое поведение)")
        else:
            print("❌ Неожиданный статус")

if __name__ == "__main__":
    test_payments_route()

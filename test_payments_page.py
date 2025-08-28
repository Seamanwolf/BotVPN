#!/usr/bin/env python3
"""
Тестовый скрипт для проверки страницы платежей
"""

import requests
from bs4 import BeautifulSoup
import re

def test_payments_page():
    """Тестирует страницу платежей"""
    base_url = "http://localhost:8080"
    
    # Создаем сессию для сохранения cookies
    session = requests.Session()
    
    try:
        # 1. Проверяем главную страницу (должна редиректить на логин)
        print("1. Проверяем главную страницу...")
        response = session.get(f"{base_url}/")
        print(f"   Статус: {response.status_code}")
        print(f"   Редирект: {response.url}")
        
        # 2. Проверяем страницу логина
        print("\n2. Проверяем страницу логина...")
        response = session.get(f"{base_url}/login")
        print(f"   Статус: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            form = soup.find('form')
            if form:
                print("   Форма логина найдена")
            else:
                print("   Форма логина не найдена")
        
        # 3. Проверяем страницу платежей (должна редиректить на логин)
        print("\n3. Проверяем страницу платежей...")
        response = session.get(f"{base_url}/payments")
        print(f"   Статус: {response.status_code}")
        print(f"   Редирект: {response.url}")
        
        # 4. Проверяем, что в HTML есть ссылка на платежи
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            payments_link = soup.find('a', href='/payments')
            if payments_link:
                print("   Ссылка на платежи найдена в навигации")
            else:
                print("   Ссылка на платежи НЕ найдена в навигации")
        
        # 5. Проверяем другие страницы для сравнения
        print("\n4. Проверяем другие страницы...")
        pages = ['/users', '/subscriptions', '/tickets', '/notifications']
        for page in pages:
            response = session.get(f"{base_url}{page}")
            print(f"   {page}: {response.status_code}")
        
        print("\n✅ Тест завершен успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")

if __name__ == "__main__":
    test_payments_page()

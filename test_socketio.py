#!/usr/bin/env python3

import requests
import json

def test_socketio():
    """Тестирует Socket.IO сервер"""
    
    # Тест 1: Проверяем основной сайт
    print("Тест 1: Основной сайт")
    try:
        response = requests.get('http://127.0.0.1:8080/', timeout=5)
        print(f"Статус: {response.status_code}")
        if response.status_code == 302:
            print("✅ Основной сайт работает (редирект на логин)")
        else:
            print("❌ Основной сайт не работает")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    print()
    
    # Тест 2: Проверяем Socket.IO клиент
    print("Тест 2: Socket.IO клиент")
    try:
        response = requests.get('http://127.0.0.1:8080/socket.io/socket.io.js', timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Контент: {response.text[:100]}...")
        if response.status_code == 200:
            print("✅ Socket.IO клиент доступен")
        else:
            print("❌ Socket.IO клиент недоступен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    print()
    
    # Тест 3: Проверяем Socket.IO handshake
    print("Тест 3: Socket.IO handshake")
    try:
        response = requests.get('http://127.0.0.1:8080/socket.io/?EIO=4&transport=polling', timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Контент: {response.text[:100]}...")
        if response.status_code == 200:
            print("✅ Socket.IO handshake работает")
        else:
            print("❌ Socket.IO handshake не работает")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_socketio()

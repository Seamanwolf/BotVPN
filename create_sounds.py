#!/usr/bin/env python3

import wave
import struct
import math
import os

def create_simple_beep(filename, frequency=800, duration=0.5, sample_rate=44100):
    """Создает простой звуковой файл с одним тоном"""
    
    # Создаем папку если её нет
    os.makedirs('static/sounds', exist_ok=True)
    
    # Параметры звука
    amplitude = 0.3
    num_samples = int(sample_rate * duration)
    
    # Создаем WAV файл
    with wave.open(f'static/sounds/{filename}', 'w') as wav_file:
        # Настройки WAV файла
        wav_file.setnchannels(1)  # Моно
        wav_file.setsampwidth(2)  # 16 бит
        wav_file.setframerate(sample_rate)
        
        # Генерируем звуковые данные
        for i in range(num_samples):
            # Синусоидальная волна
            value = amplitude * math.sin(2 * math.pi * frequency * i / sample_rate)
            # Конвертируем в 16-битное целое
            packed_value = struct.pack('<h', int(value * 32767))
            wav_file.writeframes(packed_value)

def main():
    """Создаем звуковые файлы для разных типов уведомлений"""
    
    # Звук для новых тикетов (высокий тон)
    create_simple_beep('ticket.wav', frequency=1000, duration=0.3)
    
    # Звук для новых пользователей (средний тон)
    create_simple_beep('user.wav', frequency=800, duration=0.3)
    
    # Звук для новых подписок (низкий тон)
    create_simple_beep('subscription.wav', frequency=600, duration=0.3)
    
    # Звук для новых сообщений (двойной тон)
    create_simple_beep('message.wav', frequency=900, duration=0.4)
    
    print("Звуковые файлы созданы успешно!")

if __name__ == "__main__":
    main()

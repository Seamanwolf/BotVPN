#!/usr/bin/env python3

import wave
import struct
import math

def create_simple_wav(filename, frequency=800, duration=0.5, sample_rate=44100):
    """Создает простой WAV файл с тоном заданной частоты"""
    
    # Количество сэмплов
    num_samples = int(sample_rate * duration)
    
    # Создаем WAV файл
    with wave.open(filename, 'w') as wav_file:
        # Устанавливаем параметры
        wav_file.setnchannels(1)  # Моно
        wav_file.setsampwidth(2)  # 16 бит
        wav_file.setframerate(sample_rate)
        
        # Генерируем сэмплы
        for i in range(num_samples):
            # Простой синусоидальный тон
            value = math.sin(2 * math.pi * frequency * i / sample_rate)
            # Преобразуем в 16-битное целое
            packed_value = struct.pack('<h', int(value * 32767))
            wav_file.writeframes(packed_value)

if __name__ == "__main__":
    # Создаем звуковой файл для уведомлений
    create_simple_wav('static/sounds/new.wav', frequency=800, duration=0.3)
    print("Звуковой файл new.wav создан!")

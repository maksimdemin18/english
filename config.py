#!/usr/bin/env python3\

# Конфигурационные параметры для бота и базы данных
DB_CONFIG = {
    'dbname': 'english_bot',      # Название базы данных
    'user': 'postgres',           # Пользователь PostgreSQL
    'password': 'postgres',       # Пароль пользователя
    'host': 'localhost',          # Хост базы данных
    'port': '5432'                # Порт базы данных
}

BOT_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'  # Токен вашего Telegram бота

# Настройки викторины
QUIZ_SETTINGS = {
    'options_count': 4,           # Количество вариантов ответов
    'common_words_first': True    # Показывать сначала общие слова
}

# Настройки интерфейса
INTERFACE = {
    'words_per_page': 10,         # Количество слов на странице в списке
    'max_word_length': 255        # Максимальная длина слова
}

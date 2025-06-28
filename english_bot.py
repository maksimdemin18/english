#!/usr/bin/env python3

import re
import os
import time
import random
import socket
import platform
import subprocess
from typing import Optional, Tuple, List, Dict, Any
import telebot
import psycopg2
from telebot import types
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from config import DB_CONFIG, BOT_TOKEN, QUIZ_SETTINGS, INTERFACE


class EnglishBot:
    """Основной класс Telegram-бота."""
    
    # Константы состояний пользователя
    IDLE = 'idle'
    ADDING_WORD_RUSSIAN = 'adding_word_russian'
    ADDING_WORD_ENGLISH = 'adding_word_english'
    DELETING_WORD = 'deleting_word'
    QUIZ = 'quiz'
    VIEWING_WORDS = 'viewing_words'
    
    def __init__(self, token: str, db_config: Dict[str, Any]) -> None:
        """Инициализация бота и базы данных."""
        self.token = token
        self.db_config = db_config
        self.bot = telebot.TeleBot(token)
        self.user_states = {}  # Состояния пользователей
        self.temp_data = {}    # Временные данные
        self.quiz_data = {}    # Данные викторины
        self.words_pagination = {}  # Пагинация для списка слов
        self.conn = None
        self.cursor = None
        self.connect_to_database()
        self._register_handlers()
    
    def connect_to_database(self) -> bool:
        """Подключение к базе данных."""
        try:
            self.conn = psycopg2.connect(
                dbname=self.db_config['dbname'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                host=self.db_config['host'],
                port=self.db_config['port']
            )
            self.conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.cursor = self.conn.cursor()
            print("Успешное подключение к базе данных")
            
            self.create_tables()
            self.fill_common_words()
            
            return True
        except Exception as e:
            print(f"Ошибка подключения к базе данных: {e}")
            return False
    
    def create_tables(self) -> bool:
        """Создание таблиц в базе данных."""
        try:
            # Создание таблицы пользователей
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Создание таблицы слов
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS words (
                    id SERIAL PRIMARY KEY,
                    russian_word VARCHAR(255) NOT NULL,
                    english_word VARCHAR(255) NOT NULL,
                    is_common BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Создание таблицы слов пользователей
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_words (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    word_id INTEGER REFERENCES words(id) ON DELETE CASCADE,
                    correct_count INTEGER DEFAULT 0,
                    attempt_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, word_id)
                )
            ''')
            
            print("Таблицы успешно созданы")
            return True
        except Exception as e:
            print(f"Ошибка создания таблиц: {e}")
            return False
    
    def fill_common_words(self) -> bool:
        """Заполнение базы данных общим набором слов."""
        common_words = [
            ("красный", "red"),
            ("синий", "blue"),
            ("зеленый", "green"),
            ("желтый", "yellow"),
            ("черный", "black"),
            ("белый", "white"),
            ("я", "I"),
            ("ты", "you"),
            ("он", "he"),
            ("она", "she")
        ]
        
        try:
            self.cursor.execute("SELECT COUNT(*) FROM words WHERE is_common = TRUE")
            count = self.cursor.fetchone()[0]
            
            if count == 0:
                for russian, english in common_words:
                    self.cursor.execute(
                        "INSERT INTO words (russian_word, english_word, is_common) "
                        "VALUES (%s, %s, TRUE)",
                        (russian, english)
                    )
                print(f"Добавлено {len(common_words)} общих слов")
            return True
        except Exception as e:
            print(f"Ошибка при заполнении общих слов: {e}")
            return False
    
       def _register_handlers(self) -> None:
        """Регистрация обработчиков сообщений."""
        @self.bot.message_handler(commands=['start'])
        def handle_start(message: types.Message) -> None:
            self._handle_start(message)
        
        @self.bot.message_handler(commands=['help'])
        def handle_help(message: types.Message) -> None:
            self._handle_help(message)
        
        @self.bot.message_handler(func=lambda message: message.text == 'Викторина 🎮')
        def handle_quiz(message: types.Message) -> None:
            self._handle_quiz(message)
        
        @self.bot.message_handler(func=lambda message: message.text == 'Добавить слово ➕')
        def handle_add_word(message: types.Message) -> None:
            self._handle_add_word(message)
        
        @self.bot.message_handler(func=lambda message: message.text == 'Удалить слово ➖')
        def handle_delete_word(message: types.Message) -> None:
            self._handle_delete_word(message)
        
        @self.bot.message_handler(func=lambda message: message.text == 'Список слов 📋')
        def handle_words_list(message: types.Message) -> None:
            self._handle_words_list(message)
        
        @self.bot.message_handler(func=lambda message: message.text == 'Отмена ❌')
        def handle_cancel(message: types.Message) -> None:
            self._handle_cancel(message)
        
        @self.bot.message_handler(func=lambda message: True)
        def handle_messages(message: types.Message) -> None:
            self._handle_messages(message)

    def _handle_start(self, message: types.Message) -> None:
        """Обработчик команды /start."""
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name
        
        db_user_id = self.register_user(user_id, username)
        
        if db_user_id:
            self.user_states[user_id] = self.IDLE
            markup = self._create_main_keyboard()
            
            self.bot.send_message(
                user_id,
                f"Привет, {username}! 👋\n\n"
                "Я бот для изучения английских слов. С моей помощью ты сможешь:\n"
                "• Проверять свои знания в викторине 🎮\n"
                "• Добавлять новые слова для изучения ➕\n"
                "• Удалять слова, которые ты уже выучил ➖\n"
                "• Просматривать список своих слов 📋\n\n"
                "Выбери действие из меню ниже 👇",
                reply_markup=markup
            )

    def _handle_help(self, message: types.Message) -> None:
        """Обработчик команды /help."""
        self.bot.send_message(
            message.from_user.id,
            "📚 *Справка по использованию бота* 📚\n\n"
            "*Основные команды:*\n"
            "/start - Начать работу с ботом\n"
            "/help - Показать эту справку\n\n"
            "*Доступные действия:*\n"
            "• *Викторина* 🎮 - Проверка знаний английских слов\n"
            "• *Добавить слово* ➕ - Добавление нового слова для изучения\n"
            "• *Удалить слово* ➖ - Удаление слова из вашего списка\n"
            "• *Список слов* 📋 - Просмотр всех ваших слов\n\n"
            "Для начала работы нажмите на одну из кнопок в меню 👇",
            parse_mode='Markdown'
        )

    def _handle_quiz(self, message: types.Message) -> None:
        """Обработчик для кнопки 'Викторина'."""
        user_id = message.from_user.id
        db_user_id = self.get_user_id(user_id)
        
        if not db_user_id:
            self.bot.send_message(user_id, "Пожалуйста, используйте /start для начала работы.")
            return
        
        word = self.get_random_word(db_user_id)
        
        if not word:
            self.bot.send_message(
                user_id,
                "У вас пока нет слов для викторины. Добавьте слова с помощью кнопки 'Добавить слово ➕'."
            )
            return
        
        word_id, russian_word, english_word = word
        self.quiz_data[user_id] = word_id
        
        options, correct_answer = self.get_options(word_id, db_user_id)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        buttons = [types.KeyboardButton(option) for option in options]
        markup.add(*buttons)
        
        self.user_states[user_id] = self.QUIZ
        
        self.bot.send_message(
            user_id,
            f"Переведите слово: *{russian_word}*",
            reply_markup=markup,
            parse_mode='Markdown'
        )

    def _handle_add_word(self, message: types.Message) -> None:
        """Обработчик для кнопки 'Добавить слово'."""
        user_id = message.from_user.id
        self.user_states[user_id] = self.ADDING_WORD_RUSSIAN
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        cancel_btn = types.KeyboardButton('Отмена ❌')
        markup.add(cancel_btn)
        
        self.bot.send_message(
            user_id,
            "Введите слово на русском языке:",
            reply_markup=markup
        )

    def _handle_delete_word(self, message: types.Message) -> None:
        """Обработчик для кнопки 'Удалить слово'."""
        user_id = message.from_user.id
        db_user_id = self.get_user_id(user_id)
        
        if not db_user_id:
            self.bot.send_message(user_id, "Пожалуйста, используйте /start для начала работы.")
            return
        
        words = self.get_user_words(db_user_id)
        
        if not words:
            self.bot.send_message(user_id, "У вас пока нет слов для удаления.")
            return
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        for word_id, russian, english in words:
            btn = types.KeyboardButton(f"{russian} - {english} (ID: {word_id})")
            markup.add(btn)
        
        cancel_btn = types.KeyboardButton('Отмена ❌')
        markup.add(cancel_btn)
        
        self.user_states[user_id] = self.DELETING_WORD
        
        self.bot.send_message(
            user_id,
            "Выберите слово для удаления:",
            reply_markup=markup
        )

    def _handle_words_list(self, message: types.Message) -> None:
        """Обработчик для кнопки 'Список слов'."""
        user_id = message.from_user.id
        db_user_id = self.get_user_id(user_id)
        
        if not db_user_id:
            self.bot.send_message(user_id, "Пожалуйста, используйте /start для начала работы.")
            return
        
        words = self.get_user_words(db_user_id)
        
        if not words:
            self.bot.send_message(
                user_id,
                "У вас пока нет слов. Добавьте слова с помощью кнопки 'Добавить слово ➕'."
            )
            return
        
        message_text = "📋 *Ваш список слов:*\n\n"
        for i, (word_id, russian, english) in enumerate(words, 1):
            message_text += f"{i}. {russian} - {english}\n"
        
        markup = self._create_main_keyboard()
        
        self.bot.send_message(
            user_id,
            message_text,
            reply_markup=markup,
            parse_mode='Markdown'
        )

    def _handle_cancel(self, message: types.Message) -> None:
        """Обработчик для кнопки 'Отмена'."""
        user_id = message.from_user.id
        self.user_states[user_id] = self.IDLE
        
        if user_id in self.temp_data:
            del self.temp_data[user_id]
        
        markup = self._create_main_keyboard()
        
        self.bot.send_message(
            user_id,
            "Действие отменено. Выберите другое действие:",
            reply_markup=markup
        )

    def _handle_messages(self, message: types.Message) -> None:
        """Обработчик для всех остальных сообщений."""
        user_id = message.from_user.id
        db_user_id = self.get_user_id(user_id)
        
        if not db_user_id:
            self.bot.send_message(user_id, "Пожалуйста, используйте /start для начала работы.")
            return
        
        state = self.user_states.get(user_id, self.IDLE)
        
        if state == self.ADDING_WORD_RUSSIAN:
            russian_word = message.text.strip().lower()
            
            if user_id not in self.temp_data:
                self.temp_data[user_id] = {}
            self.temp_data[user_id]['russian'] = russian_word
            
            self.user_states[user_id] = self.ADDING_WORD_ENGLISH
            
            self.bot.send_message(
                user_id,
                f"Теперь введите перевод слова '{russian_word}' на английском языке:"
            )
        
        elif state == self.ADDING_WORD_ENGLISH:
            english_word = message.text.strip().lower()
            russian_word = self.temp_data[user_id]['russian']
            
            success, word_count = self.add_word(db_user_id, russian_word, english_word)
            
            markup = self._create_main_keyboard()
            
            if success:
                self.bot.send_message(
                    user_id,
                    f"✅ Слово '{russian_word} - {english_word}' успешно добавлено!\n"
                    f"Всего у вас {word_count} слов для изучения.",
                    reply_markup=markup
                )
            else:
                self.bot.send_message(
                    user_id,
                    "❌ Ошибка при добавлении слова. Пожалуйста, попробуйте еще раз.",
                    reply_markup=markup
                )
            
            self.user_states[user_id] = self.IDLE
            del self.temp_data[user_id]
        
        elif state == self.DELETING_WORD:
            text = message.text
            match = re.search(r'ID: (\d+)', text)
            
            if match:
                word_id = int(match.group(1))
                success = self.delete_word(db_user_id, word_id)
                
                markup = self._create_main_keyboard()
                
                if success:
                    self.bot.send_message(
                        user_id,
                        "✅ Слово успешно удалено!",
                        reply_markup=markup
                    )
                else:
                    self.bot.send_message(
                        user_id,
                        "❌ Ошибка при удалении слова. Пожалуйста, попробуйте еще раз.",
                        reply_markup=markup
                    )
                
                self.user_states[user_id] = self.IDLE
        
        elif state == self.QUIZ:
            user_answer = message.text.strip().lower()
            word_id = self.quiz_data.get(user_id)
            
            if not word_id:
                self.bot.send_message(user_id, "Произошла ошибка. Пожалуйста, начните викторину заново.")
                return
            
            self.cursor.execute(
                "SELECT english_word FROM words WHERE id = %s",
                (word_id,)
            )
            correct_answer = self.cursor.fetchone()[0].lower()
            
            markup = self._create_main_keyboard()
            is_correct = user_answer.lower() == correct_answer.lower()
            
            self.update_word_stats(db_user_id, word_id, is_correct)
            
            if is_correct:
                self.bot.send_message(
                    user_id,
                    f"✅ Правильно! '{user_answer}' - верный ответ.\n\n"
                    f"Нажмите 'Викторина 🎮' для следующего вопроса.",
                    reply_markup=markup
                )
            else:
                self.bot.send_message(
                    user_id,
                    f"❌ Неправильно. Правильный ответ: '{correct_answer}'.\n\n"
                    f"Нажмите 'Викторина 🎮' для следующего вопроса.",
                    reply_markup=markup
                )
            
            self.user_states[user_id] = self.IDLE
            del self.quiz_data[user_id]
        
        else:
            self.bot.send_message(
                user_id,
                "Пожалуйста, выберите действие из меню ниже 👇"
            )

    def _create_main_keyboard(self) -> types.ReplyKeyboardMarkup:
        """Создание основной клавиатуры с кнопками."""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        quiz_btn = types.KeyboardButton('Викторина 🎮')
        add_word_btn = types.KeyboardButton('Добавить слово ➕')
        delete_word_btn = types.KeyboardButton('Удалить слово ➖')
        words_list_btn = types.KeyboardButton('Список слов 📋')
        
        markup.add(quiz_btn, add_word_btn, delete_word_btn, words_list_btn)
        return markup

    def register_user(self, telegram_id: int, username: str) -> Optional[int]:
        """Регистрация нового пользователя."""
        try:
            self.cursor.execute(
                "SELECT id FROM users WHERE telegram_id = %s", 
                (telegram_id,)
            )
            user = self.cursor.fetchone()
            
            if not user:
                self.cursor.execute(
                    "INSERT INTO users (telegram_id, username) VALUES (%s, %s) RETURNING id",
                    (telegram_id, username)
                )
                user_id = self.cursor.fetchone()[0]
                
                self.cursor.execute(
                    """
                    INSERT INTO user_words (user_id, word_id)
                    SELECT %s, id FROM words WHERE is_common = TRUE
                    """,
                    (user_id,)
                )
                
                print(f"Зарегистрирован новый пользователь: {username} (ID: {telegram_id})")
                return user_id
            return user[0] if user else None
        except Exception as e:
            print(f"Ошибка при регистрации пользователя: {e}")
            return None

    def get_user_id(self, telegram_id: int) -> Optional[int]:
        """Получение ID пользователя по Telegram ID."""
        try:
            self.cursor.execute(
                "SELECT id FROM users WHERE telegram_id = %s", 
                (telegram_id,)
            )
            user = self.cursor.fetchone()
            return user[0] if user else None
        except Exception as e:
            print(f"Ошибка при получении ID пользователя: {e}")
            return None

    def add_word(self, user_id: int, russian_word: str, english_word: str) -> Tuple[bool, int]:
        """Добавление нового слова для пользователя."""
        try:
            self.cursor.execute(
                "SELECT id FROM words WHERE russian_word = %s AND english_word = %s",
                (russian_word, english_word)
            )
            word = self.cursor.fetchone()
            
            if not word:
                self.cursor.execute(
                    "INSERT INTO words (russian_word, english_word, is_common) "
                    "VALUES (%s, %s, FALSE) RETURNING id",
                    (russian_word, english_word)
                )
                word_id = self.cursor.fetchone()[0]
            else:
                word_id = word[0]
            
            self.cursor.execute(
                """
                INSERT INTO user_words (user_id, word_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, word_id) DO NOTHING
                """,
                (user_id, word_id)
            )
            
            self.cursor.execute(
                "SELECT COUNT(*) FROM user_words WHERE user_id = %s",
                (user_id,)
            )
            word_count = self.cursor.fetchone()[0]
            
            return True, word_count
        except Exception as e:
            print(f"Ошибка при добавлении слова: {e}")
            return False, 0

    def delete_word(self, user_id: int, word_id: int) -> bool:
        """Удаление слова у пользователя."""
        try:
            self.cursor.execute(
                "DELETE FROM user_words WHERE user_id = %s AND word_id = %s",
                (user_id, word_id)
            )
            return True
        except Exception as e:
            print(f"Ошибка при удалении слова: {e}")
            return False

    def get_user_words(self, user_id: int) -> List[Tuple[int, str, str]]:
        """Получение всех слов пользователя."""
        try:
            self.cursor.execute(
                """
                SELECT w.id, w.russian_word, w.english_word
                FROM words w
                JOIN user_words uw ON w.id = uw.word_id
                WHERE uw.user_id = %s
                """,
                (user_id,)
            )
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Ошибка при получении слов пользователя: {e}")
            return []

    def get_random_word(self, user_id: int) -> Optional[Tuple[int, str, str]]:
        """Получение случайного слова для проверки знаний."""
        try:
            self.cursor.execute(
                """
                SELECT w.id, w.russian_word, w.english_word
                FROM words w
                JOIN user_words uw ON w.id = uw.word_id
                WHERE uw.user_id = %s
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (user_id,)
            )
            return self.cursor.fetchone()
        except Exception as e:
            print(f"Ошибка при получении случайного слова: {e}")
            return None

    def get_options(self, correct_word_id: int, user_id: int) -> Tuple[List[str], str]:
        """Получение вариантов ответа для викторины."""
        try:
            self.cursor.execute(
                "SELECT english_word FROM words WHERE id = %s",
                (correct_word_id,)
            )
            correct_answer = self.cursor.fetchone()[0]
            
            self.cursor.execute(
                """
                SELECT w.english_word
                FROM words w
                JOIN user_words uw ON w.id = uw.word_id
                WHERE uw.user_id = %s AND w.id != %s
                ORDER BY RANDOM()
                LIMIT 3
                """,
                (user_id, correct_word_id)
            )
            
            other_answers = [row[0] for row in self.cursor.fetchall()]
            
            if len(other_answers) < 3:
                self.cursor.execute(
                    """
                    SELECT english_word
                    FROM words
                    WHERE id != %s AND english_word != %s
                    ORDER BY RANDOM()
                    LIMIT %s
                    """,
                    (correct_word_id, correct_answer, 3 - len(other_answers))
                )
                other_answers.extend([row[0] for row in self.cursor.fetchall()])
            
            all_options = [correct_answer] + other_answers
            random.shuffle(all_options)
            
            return all_options, correct_answer
        except Exception as e:
            print(f"Ошибка при получении вариантов ответа: {e}")
            return [], ""

    def update_word_stats(self, user_id: int, word_id: int, is_correct: bool) -> bool:
        """Обновление статистики слова."""
        try:
            self.cursor.execute(
                """
                UPDATE user_words
                SET attempt_count = attempt_count + 1,
                    correct_count = correct_count + %s
                WHERE user_id = %s AND word_id = %s
                """,
                (1 if is_correct else 0, user_id, word_id)
            )
            return True
        except Exception as e:
            print(f"Ошибка при обновлении статистики слова: {e}")
            return False

    def close(self) -> None:
        """Закрытие соединения с базой данных."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("Соединение с базой данных закрыто")
    
    def start(self) -> None:
        """Запуск бота."""
        try:
            print("Бот запущен. Нажмите Ctrl+C для остановки.")
            self.bot.infinity_polling()
        except Exception as e:
            print(f"Ошибка при запуске бота: {e}")
        finally:
            self.close()


def check_host_availability(host: str, port: int = 5432, timeout: int = 5) -> bool:
    """Проверка доступности хоста."""
    try:
        socket_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_obj.settimeout(timeout)
        result = socket_obj.connect_ex((host, port))
        socket_obj.close()
        return result == 0
    except Exception as e:
        print(f"Ошибка при проверке доступности хоста: {e}")
        return False


def setup_database(db_config: Dict[str, Any]) -> bool:
    """Настройка базы данных на указанном хосте."""
    if not check_host_availability(db_config['host'], int(db_config['port'])):
        print(f"Хост {db_config['host']}:{db_config['port']} недоступен")
        return False
    
    try:
        conn = psycopg2.connect(
            user=db_config['user'],
            password=db_config['password'],
            host=db_config['host'],
            port=db_config['port']
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        cursor.execute(
            f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{db_config['dbname']}'"
        )
        exists = cursor.fetchone()
        
        if not exists:
            cursor.execute(f"CREATE DATABASE {db_config['dbname']}")
            print(f"База данных '{db_config['dbname']}' успешно создана")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка при настройке базы данных: {e}")
        return False


def install_postgresql() -> bool:
    """Установка PostgreSQL в зависимости от операционной системы."""
    os_name = platform.system().lower()
    print(f"Определена операционная система: {os_name}")
    
    if os_name == 'windows':
        print("Для установки PostgreSQL на Windows:")
        print("1. Скачайте установщик с https://www.postgresql.org/download/windows/")
        print("2. Запустите установщик и следуйте инструкциям")
        return False
    
    try:
        if os_name == 'linux':
            if os.path.exists('/etc/debian_version'):
                subprocess.run(['sudo', 'apt', 'update'], check=True)
                subprocess.run(
                    ['sudo', 'apt', 'install', '-y', 'postgresql', 'postgresql-contrib'],
                    check=True
                )
            elif os.path.exists('/etc/redhat-release'):
                subprocess.run(
                    ['sudo', 'dnf', 'install', '-y', 'postgresql-server', 'postgresql-contrib'],
                    check=True
                )
                subprocess.run(['sudo', 'postgresql-setup', 'initdb'], check=True)
            
            subprocess.run(['sudo', 'systemctl', 'start', 'postgresql'], check=True)
            subprocess.run(['sudo', 'systemctl', 'enable', 'postgresql'], check=True)
            return True
        
        elif os_name == 'darwin':
            try:
                subprocess.run(['brew', '--version'], check=True, stdout=subprocess.PIPE)
            except (subprocess.CalledProcessError, FileNotFoundError):
                install_cmd = (
                    '/bin/bash -c "$(curl -fsSL '
                    'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
                )
                subprocess.run(install_cmd, shell=True, check=True)
            
            subprocess.run(['brew', 'install', 'postgresql'], check=True)
            subprocess.run(['brew', 'services', 'start', 'postgresql'], check=True)
            return True
        
        print(f"Неподдерживаемая ОС: {os_name}")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при установке PostgreSQL: {e}")
        return False


if __name__ == '__main__':
    print("Настройка подключения к базе данных")
    if not setup_database(DB_CONFIG):
        print("Не удалось настроить базу данных")
        if input("Попробовать установить PostgreSQL? (y/n): ").lower() == 'y':
            if install_postgresql():
                time.sleep(5)
                setup_database(DB_CONFIG)
    
    print("Запуск бота...")
    bot = EnglishBot(BOT_TOKEN, DB_CONFIG)
    bot.start()

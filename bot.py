import sqlite3
from pyrogram import Client, filters, idle
from pyrogram.types import Message
import time
from os import environ

# Настройки из переменных окружения
api_id = int(environ.get("API_ID"))
api_hash = environ.get("API_HASH")
group_id = int(environ.get("GROUP_ID"))
tracked_chats = [8068560344]  # Чаты для отслеживания

# Создаем клиент
app = Client("my_account", api_id=api_id, api_hash=api_hash)

# Настройка базы данных SQLite
def setup_database():
    conn = sqlite3.connect("messages.db")  # Относительный путь
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            message_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            user_id INTEGER,
            text TEXT,
            date INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def save_message_to_db(message_id, chat_id, user_id, text, date):
    with sqlite3.connect("messages.db") as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO messages (message_id, chat_id, user_id, text, date)
            VALUES (?, ?, ?, ?, ?)
        ''', (message_id, chat_id, user_id, text, date))
        conn.commit()

def get_message_from_db(message_id):
    with sqlite3.connect("messages.db") as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT chat_id, user_id, text, date FROM messages WHERE message_id = ?', (message_id,))
        result = cursor.fetchone()
        if result:
            date = int(result[3]) if isinstance(result[3], str) else result[3]
            return {"chat_id": result[0], "user_id": result[1], "text": result[2], "date": date}
    return None

def delete_message_from_db(message_id):
    with sqlite3.connect("messages.db") as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM messages WHERE message_id = ?', (message_id,))
        conn.commit()

setup_database()

# Обработчик сообщений (только новые)
@app.on_message(filters.chat(tracked_chats))
async def handle_messages(client: Client, message: Message):
    print(f"[TRACKED] Новое сообщение: chat_id={message.chat.id}, text={message.text}")
    if message.text and not message.edit_date:
        save_message_to_db(
            message_id=message.id,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            text=message.text,
            date=message.date
        )
        print(f"[TRACKED] Сообщение сохранено: {message.id}")

# Обработчик сырых обновлений
@app.on_raw_update()
async def handle_raw_updates(client: Client, update, users, chats):
    update_type = update.__class__.__name__
    print(f"[RAW] Обновление: тип={update_type}, данные={update}")

    if update_type == "UpdateDeleteMessages":
        deleted_ids = getattr(update, "messages", [])
        chat_id_raw = getattr(update, "chat_id", None)
        print(f"[RAW] Удаление: chat_id_raw={chat_id_raw}, deleted_ids={deleted_ids}")
        for msg_id in deleted_ids:
            deleted_message = get_message_from_db(msg_id)
            if deleted_message:
                chat_id = deleted_message["chat_id"]
                if chat_id in tracked_chats:
                    notification = (
                        f"Сообщение удалено в чате {chat_id}:\n"
                        f"Пользователь: {deleted_message['user_id']}\n"
                        f"Текст: {deleted_message['text']}\n"
                        f"Время отправки: {time.ctime(deleted_message['date'])}"
                    )
                    await client.send_message(group_id, notification)
                    delete_message_from_db(msg_id)
                    print(f"[RAW] Уведомление об удалении отправлено: {msg_id}")

    elif update_type == "UpdateUserTyping":
        user_id = getattr(update, "user_id", None)
        chat_id = getattr(update, "chat_id", None) or user_id
        print(f"[RAW] Печать: user_id={user_id}, chat_id={chat_id}")
        if chat_id in tracked_chats:
            notification = (
                f"Пользователь {user_id} печатает в чате {chat_id}"
            )
            await client.send_message(group_id, notification)
            print(f"[RAW] Уведомление о печати отправлено")

    elif update_type == "UpdateEditMessage":
        message = getattr(update, "message", None)
        if message:
            chat_id = getattr(message.peer_id, "user_id", None) or getattr(message.peer_id, "chat_id", None)
            msg_id = message.id
            new_text = message.message
            print(f"[RAW] Редактирование: chat_id={chat_id}, msg_id={msg_id}, new_text={new_text}")
            if chat_id in tracked_chats:
                original = get_message_from_db(msg_id)
                if original and original["text"] != new_text:
                    notification = (
                        f"Сообщение отредактировано в чате {chat_id}:\n"
                        f"Пользователь: {original['user_id']}\n"
                        f"Было: {original['text']}\n"
                        f"Стало: {new_text}\n"
                        f"Время: {time.ctime(message.edit_date)}"
                    )
                    await client.send_message(group_id, notification)
                    save_message_to_db(msg_id, chat_id, original['user_id'], new_text, message.date)
                    print(f"[RAW] Уведомление об изменении отправлено: {msg_id}")

# Запуск бота
async def main():
    await app.start()
    await app.send_message(group_id, "Бот запущен и готов к работе!")
    print("Бот запущен")
    await idle()

if __name__ == "__main__":
    print("Бот запускается...")
    app.run(main())
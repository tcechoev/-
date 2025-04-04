import sqlite3
from pyrogram import Client, filters, idle
from pyrogram.types import Message
import time
from os import environ

# Настройки
api_id = int(environ.get("API_ID"))
api_hash = environ.get("API_HASH")
group_id = int(environ.get("GROUP_ID"))
phone_number = environ.get("PHONE_NUMBER")
tracked_chats = [8068560344]

# Создаем клиент
app = Client("my_account", api_id=api_id, api_hash=api_hash)

# Настройка базы данных SQLite
def setup_database():
    conn = sqlite3.connect("messages.db")
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
            return {"chat_id": result[0], "user_id": result[1], "text": result[2], "date": result[3]}
    return None

def delete_message_from_db(message_id):
    with sqlite3.connect("messages.db") as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM messages WHERE message_id = ?', (message_id,))
        conn.commit()

setup_database()

# Функция для получения username
async def get_username(client, user_id):
    try:
        user = await client.get_users(user_id)
        return user.username if user.username else user.first_name if user.first_name else str(user_id)
    except Exception as e:
        print(f"[ERROR] Не удалось получить username для user_id={user_id}: {e}")
        return str(user_id)  # Fallback на user_id в случае ошибки

# Обработчик сообщений (только новые)
@app.on_message(filters.chat(tracked_chats))
async def handle_messages(client: Client, message: Message):
    print(f"[TRACKED] Новое сообщение: chat_id={message.chat.id}, text={message.text}, edit_date={message.edit_date}")
    if message.text and not message.edit_date:
        save_message_to_db(
            message_id=message.id,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            text=message.text,
            date=message.date
        )
        print(f"[TRACKED] Сообщение сохранено: {message.id}, text={message.text}")

# Обработчик сырых обновлений
@app.on_raw_update()
async def handle_raw_updates(client: Client, update, users, chats):
    update_type = update.__class__.__name__
    print(f"[RAW] Обновление: тип={update_type}, данные={update}")

    # Удаление сообщений (группы и чаты)
    if update_type == "UpdateDeleteMessages":
        deleted_ids = getattr(update, "messages", [])
        chat_id_raw = getattr(update, "chat_id", None)
        print(f"[RAW] Удаление (UpdateDeleteMessages): chat_id_raw={chat_id_raw}, deleted_ids={deleted_ids}")
        for msg_id in deleted_ids:
            deleted_message = get_message_from_db(msg_id)
            print(f"[DEBUG] Извлеченное сообщение из БД: {deleted_message}")
            if deleted_message:
                chat_id = deleted_message["chat_id"]
                print(f"[DEBUG] chat_id из БД: {chat_id}, tracked_chats: {tracked_chats}")
                if chat_id in tracked_chats or -chat_id in tracked_chats:
                    username = await get_username(client, deleted_message["user_id"])
                    date = deleted_message["date"]
                    if isinstance(date, str):
                        date_str = date
                    else:
                        date_str = time.ctime(date)
                    notification = (
                        f"Сообщение удалено в чате {chat_id}:\n"
                        f"Пользователь: @{username}\n"
                        f"Текст: {deleted_message['text']}\n"
                        f"Время отправки: {date_str}"
                    )
                    try:
                        await client.send_message(group_id, notification)
                        print(f"[RAW] Уведомление об удалении отправлено: {msg_id}")
                    except Exception as e:
                        print(f"[ERROR] Ошибка при отправке уведомления: {e}")
                    delete_message_from_db(msg_id)
            else:
                print(f"[DEBUG] Сообщение с id={msg_id} не найдено в базе данных")

    # Собеседник печатает
    elif update_type == "UpdateUserTyping":
        user_id = getattr(update, "user_id", None)
        chat_id = getattr(update, "chat_id", None) or user_id
        print(f"[RAW] Печать: user_id={user_id}, chat_id={chat_id}")
        if chat_id in tracked_chats or -chat_id in tracked_chats:
            username = await get_username(client, user_id)
            notification = f"Пользователь @{username} печатает в чате {chat_id}"
            try:
                await client.send_message(group_id, notification)
                print(f"[RAW] Уведомление о печати отправлено")
            except Exception as e:
                print(f"[ERROR] Ошибка при отправке уведомления: {e}")

    # Редактирование сообщения
    elif update_type == "UpdateEditMessage":
        message = getattr(update, "message", None)
        if message:
            chat_id = getattr(message.peer_id, "user_id", None) or getattr(message.peer_id, "chat_id", None)
            msg_id = message.id
            new_text = message.message
            print(f"[RAW] Редактирование: chat_id={chat_id}, msg_id={msg_id}, new_text={new_text}")
            if chat_id in tracked_chats or -chat_id in tracked_chats:
                original = get_message_from_db(msg_id)
                if original and original["text"] != new_text:
                    username = await get_username(client, original["user_id"])
                    notification = (
                        f"Сообщение отредактировано в чате {chat_id}:\n"
                        f"Пользователь: @{username}\n"
                        f"Было: {original['text']}\n"
                        f"Стало: {new_text}\n"
                        f"Время: {time.ctime(message.edit_date)}"
                    )
                    try:
                        await client.send_message(group_id, notification)
                        print(f"[RAW] Уведомление об изменении отправлено: {msg_id}")
                    except Exception as e:
                        print(f"[ERROR] Ошибка при отправке уведомления: {e}")
                    save_message_to_db(msg_id, chat_id, original['user_id'], new_text, message.date)

# Запуск бота
async def main():
    await app.start()
    await app.send_message(group_id, "Бот запущен и готов к работе!")
    print("Бот запущен")
    await idle()

if __name__ == "__main__":
    print("Бот запускается...")
    app.run(main())
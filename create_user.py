"""
Скрипт для управления пользователями
Использование:
    python create_user.py add username password    - добавить пользователя
    python create_user.py list                      - список пользователей
    python create_user.py delete username           - удалить пользователя
    python create_user.py reset username password   - сменить пароль
"""

import sys
import sqlite3
from werkzeug.security import generate_password_hash
import os

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'journal.db')


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def add_user(username, password):
    if len(password) < 6:
        print("❌ Пароль должен быть не менее 6 символов!")
        return

    conn = get_db()
    try:
        password_hash = generate_password_hash(password)
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )
        conn.commit()
        print(f"✅ Пользователь '{username}' успешно создан!")
    except sqlite3.IntegrityError:
        print(f"❌ Пользователь '{username}' уже существует!")
    finally:
        conn.close()


def list_users():
    conn = get_db()
    users = conn.execute("SELECT id, username FROM users ORDER BY id").fetchall()
    conn.close()

    if users:
        print("\n📋 Список пользователей:")
        print("-" * 30)
        for user in users:
            print(f"  ID: {user['id']} | Логин: {user['username']}")
        print("-" * 30)
        print(f"Всего пользователей: {len(users)}")
    else:
        print("❌ Нет пользователей!")


def delete_user(username):
    conn = get_db()
    cursor = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()

    if not user:
        print(f"❌ Пользователь '{username}' не найден!")
        conn.close()
        return

    count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
    if count['count'] <= 1:
        print("❌ Нельзя удалить последнего пользователя!")
        conn.close()
        return

    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    print(f"✅ Пользователь '{username}' удален!")


def reset_password(username, new_password):
    if len(new_password) < 6:
        print("❌ Пароль должен быть не менее 6 символов!")
        return

    conn = get_db()
    cursor = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()

    if not user:
        print(f"❌ Пользователь '{username}' не найден!")
        conn.close()
        return

    password_hash = generate_password_hash(new_password)
    conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                 (password_hash, username))
    conn.commit()
    conn.close()
    print(f"✅ Пароль для '{username}' изменен на: {new_password}")


def print_help():
    print("""
📚 Использование:
    python create_user.py add username password      - добавить пользователя
    python create_user.py list                        - список пользователей
    python create_user.py delete username             - удалить пользователя
    python create_user.py reset username new_password - сменить пароль

Примеры:
    python create_user.py add ivanov 123456
    python create_user.py list
    python create_user.py reset ivanov newpass123
    python create_user.py delete ivanov
    """)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == 'add' and len(sys.argv) == 4:
        add_user(sys.argv[2], sys.argv[3])
    elif command == 'list':
        list_users()
    elif command == 'delete' and len(sys.argv) == 3:
        confirm = input(f"Удалить пользователя '{sys.argv[2]}'? (yes/no): ")
        if confirm.lower() in ['yes', 'y', 'да']:
            delete_user(sys.argv[2])
        else:
            print("Отменено")
    elif command == 'reset' and len(sys.argv) == 4:
        reset_password(sys.argv[2], sys.argv[3])
    else:
        print("❌ Неверная команда!")
        print_help()
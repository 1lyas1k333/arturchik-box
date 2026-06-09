from flask import Flask, jsonify, request, send_file, session, redirect, url_for
from flask_cors import CORS
import sqlite3
import uuid
import json
from datetime import datetime
import os
import io
import hashlib
import secrets
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

app = Flask(__name__)
app.secret_key = 'secret_key_for_session_12345'
# === EMAIL НАСТРОЙКИ (MAIL.RU) ===
SMTP_SERVER = "smtp.mail.ru"
SMTP_PORT = 465
SMTP_USER = "ilyas.ryurik@bk.ru"
SMTP_PASSWORD = "few5gcXG6TCa2XLiwavq"  # твой пароль приложения

def send_email(to_email, subject, body):
    """Отправка email через Mail.ru"""
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"[EMAIL] Отправлено на {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] Ошибка: {e}")
        return False

def send_order_status_email(order_id, customer_name, customer_email, status, tracking_number=None):
    """Заглушка для email (пока не настроен SMTP)"""
    print(f"[EMAIL] (заглушка) Письмо для {customer_email} о заказе {order_id}, статус: {status}")
    return True
    
    html_body = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background: #0d1f0d; color: white; border-radius: 20px; }}
            .header {{ text-align: center; padding-bottom: 20px; border-bottom: 1px solid #2d8c4e; }}
            .content {{ padding: 20px 0; }}
            .status {{ color: #2d8c4e; font-weight: bold; }}
            .footer {{ text-align: center; padding-top: 20px; font-size: 12px; color: #aaa; }}
            a {{ color: #4ade80; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📦 АРТУРЧИК box</h1>
                <p>Статус вашего заказа обновлён</p>
            </div>
            <div class="content">
                <p>Здравствуйте, <strong>{customer_name}</strong>!</p>
                <p>Статус вашего заказа <strong>№{order_id}</strong> изменился на:</p>
                <p class="status">{status_text}</p>
                {tracking_html}
                <p>Спасибо, что выбрали нас!</p>
            </div>
            <div class="footer">
                <p>© 2026 АРТУРЧИК box | Футбольные боксы</p>
            </div>
        </div>
    </body>
    </html>
    '''
    
    subject = f"Статус заказа №{order_id} изменён"
    send_email(customer_email, subject, html_body)
# === TELEGRAM НАСТРОЙКИ ===
TELEGRAM_TOKEN = "8694164916:AAEYQey-DSovguWmgy-mZLG4nMVhSV4BunQ"
TELEGRAM_CHAT_ID = "1056646376"

def send_telegram_message(message):
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[TG] Ошибка: {e}")
def send_telegram_to_user(chat_id, message):
    """Отправка сообщения конкретному пользователю в Telegram"""
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload, timeout=5)
        print(f"[TG_USER] Статус: {response.status_code}, Отправлено пользователю {chat_id}")
        return True
    except Exception as e:
        print(f"[TG_USER] Ошибка: {e}")
        return False
# === ОБРАБОТКА ВХОДЯЩИХ СООБЩЕНИЙ ОТ ПОКУПАТЕЛЕЙ ===
def handle_customer_message(chat_id, text):
    if text.startswith('/status'):
        parts = text.split(' ')
        if len(parts) > 1:
            order_id = parts[1]
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT status, tracking_number, total_amount, created_at, customer_name
                FROM orders WHERE order_id = ?
            ''', (order_id,))
            order = cursor.fetchone()
            conn.close()
            
            if order:
                status_text = {
                    'pending': '⏳ Ожидает оплаты',
                    'paid': '✅ Оплачен',
                    'shipped': '📦 Отправлен',
                    'completed': '🎉 Завершён'
                }.get(order[0], order[0])
                
                msg = f"""📦 <b>Заказ {order_id}</b>

👤 Получатель: {order[4]}
💰 Сумма: {order[2]} ₽
📌 Статус: {status_text}
📅 Дата: {order[3][:10] if order[3] else '—'}"""

                if order[1]:
                    msg += f"\n\n📦 Трек-номер: {order[1]}\n🔗 Отследить: https://www.cdek.ru/track?order_id={order[1]}"
                
                send_telegram_to_user(chat_id, msg)
            else:
                send_telegram_to_user(chat_id, "❌ Заказ не найден. Проверьте номер.")
        else:
            send_telegram_to_user(chat_id, "ℹ️ Используйте: /status НОМЕР_ЗАКАЗА")
    else:
        send_telegram_to_user(chat_id, "ℹ️ Доступные команды:\n/status НОМЕР - узнать статус заказа")

# === КОНФИГУРАЦИЯ ===
ADMIN_PASSWORD = "123"
DB_NAME = 'orders.db'

# === CORS НАСТРОЙКИ ===
CORS(app, 
     origins=["https://1lyas1k333.github.io", "http://127.0.0.1:5500", "http://localhost:5500", "http://127.0.0.1:5000", "http://localhost:5000", "https://arturchik-box-2.onrender.com"],
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token(user_id):
    token_data = f"{user_id}:{datetime.now().isoformat()}:{secrets.token_hex(8)}"
    return hashlib.sha256(token_data.encode()).hexdigest()

def init_db():
    """Создаём таблицы при первом запуске"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            password TEXT,
            name TEXT,
            phone TEXT,
            telegram_id TEXT,
            created_at TEXT
        )
    ''')
    
    # Таблица заказов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            order_id TEXT UNIQUE,
            user_id TEXT,
            customer_name TEXT,
            customer_phone TEXT,
            customer_email TEXT,
            customer_address TEXT,
            customer_city TEXT,
            customer_extra TEXT,
            customer_notes TEXT,
            items TEXT,
            total_amount INTEGER,
            status TEXT,
            payment_id TEXT,
            tracking_number TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("[DB] База данных инициализирована")
# === ПРИНУДИТЕЛЬНОЕ СОЗДАНИЕ ТАБЛИЦ ПРИ ЗАПУСКЕ ===
# === ПРИНУДИТЕЛЬНОЕ СОЗДАНИЕ ТАБЛИЦ И МИГРАЦИЯ ===
import os

if not os.path.exists(DB_NAME):
    init_db()
    print(f"[DB] Создана новая база данных: {DB_NAME}")
else:
    # Проверяем, есть ли таблица users
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cursor.fetchone():
        print("[DB] Таблица users не найдена, создаём заново...")
        init_db()
    else:
        print("[DB] База данных уже существует")
    
    # ПРИНУДИТЕЛЬНО ДОБАВЛЯЕМ КОЛОНКУ telegram_id (даже если уже есть)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN telegram_id TEXT DEFAULT ''")
        conn.commit()
        print("[DB] Колонка telegram_id добавлена (или уже была)")
    except Exception as e:
        print(f"[DB] Колонка telegram_id уже есть или ошибка: {e}")
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT ''")
        conn.commit()
        print("[DB] Колонка created_at добавлена (или уже была)")
    except Exception as e:
        print(f"[DB] Колонка created_at уже есть или ошибка: {e}")
    
    conn.close()

# === ПОЛЬЗОВАТЕЛИ ===
def create_user(email, password, name, phone, telegram_id=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    user_id = str(uuid.uuid4())
    hashed_pw = hash_password(password)
    try:
        cursor.execute('''
            INSERT INTO users (id, email, password, name, phone, telegram_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, email, hashed_pw, name, phone, telegram_id, datetime.now().isoformat()))
        conn.commit()
        print(f"[REGISTER] Новый пользователь: {email}, telegram: {telegram_id}")
        return {'success': True, 'user_id': user_id}
    except sqlite3.IntegrityError:
        return {'success': False, 'error': 'Email уже зарегистрирован'}
    finally:
        conn.close()

def authenticate_user(email, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    hashed_input = hash_password(password)
    cursor.execute('SELECT id, name, email, phone FROM users WHERE email = ? AND password = ?', 
                   (email, hashed_input))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {'success': True, 'user_id': row[0], 'name': row[1], 'email': row[2], 'phone': row[3]}
    return {'success': False, 'error': 'Неверный email или пароль'}

def get_user_orders(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT order_id, items, total_amount, status, created_at 
        FROM orders 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    orders = []
    for row in rows:
        try:
            items = json.loads(row[1]) if row[1] else []
        except:
            items = []
        orders.append({
            'order_id': row[0],
            'items': items,
            'total_amount': row[2],
            'status': row[3],
            'created_at': row[4]
        })
    return orders

def save_order(order_data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO orders 
        (id, order_id, user_id, customer_name, customer_phone, customer_email, customer_address, customer_city, customer_extra, customer_notes, items, total_amount, status, payment_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        str(uuid.uuid4()),
        order_data.get('order_id'),
        order_data.get('user_id'),
        order_data.get('customer_name', ''),
        order_data.get('customer_phone', ''),
        order_data.get('customer_email', ''),
        order_data.get('customer_address', ''),
        order_data.get('customer_city', ''),
        order_data.get('customer_extra', ''),
        order_data.get('customer_notes', ''),
        json.dumps(order_data.get('items', []), ensure_ascii=False),
        order_data.get('total_amount'),
        order_data.get('status', 'pending'),
        order_data.get('payment_id', ''),
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()
    print(f"[DB] Заказ {order_data.get('order_id')} сохранён")
    
    # === ОТПРАВКА УВЕДОМЛЕНИЯ АДМИНУ В TELEGRAM ===
    try:
        msg = f"""🆕 <b>НОВЫЙ ЗАКАЗ!</b>
    
        
📦 Заказ: {order_data.get('order_id')}
👤 Клиент: {order_data.get('customer_name', 'Не указан')}
📞 Телефон: {order_data.get('customer_phone', 'Не указан')}
📧 Email: {order_data.get('customer_email', 'Не указан')}
💰 Сумма: {order_data.get('total_amount')} ₽
📍 Адрес: {order_data.get('customer_city', '')}, {order_data.get('customer_address', '')}

🔗 Админка: https://arturchik-box-2.onrender.com/admin"""
        
        send_telegram_message(msg)
    except Exception as e:
        print(f"[TG] Ошибка отправки уведомления админу: {e}")
        # Отправляем email покупателю о создании заказа
    try:
        send_order_status_email(
            order_data.get('order_id'),
            order_data.get('customer_name', ''),
            order_data.get('customer_email', ''),
            'pending'
        )
    except Exception as e:
        print(f"[EMAIL] Ошибка при отправке письма: {e}")

    # === УВЕДОМЛЕНИЕ ПОКУПАТЕЛЮ В TELEGRAM ===
    try:
        # Получаем telegram_id пользователя
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id FROM users WHERE id = ?', (order_data.get('user_id'),))
        user = cursor.fetchone()
        conn.close()
        
        if user and user[0]:
            msg_user = f"""📦 <b>АРТУРЧИК box</b>
            
Здравствуйте, {order_data.get('customer_name')}!
Ваш заказ <b>№{order_data.get('order_id')}</b> успешно создан.

📋 Состав заказа:
{', '.join([f"{item.get('name', '')} ({item.get('size', '')}) x{item.get('quantity', 1)}" for item in order_data.get('items', [])])}

💰 Сумма: {order_data.get('total_amount')} ₽
📌 Статус: ⏳ Ожидает оплаты

✅ После оплаты мы отправим вам трек-номер для отслеживания.

Спасибо за покупку!"""
            send_telegram_to_user(user[0], msg_user)
    except Exception as e:
        print(f"[TG_USER] Ошибка уведомления покупателя: {e}")

def get_all_orders():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT order_id, customer_name, customer_email, customer_phone, 
               customer_address, customer_city, customer_extra, customer_notes,
               items, total_amount, status, created_at, tracking_number 
        FROM orders 
        ORDER BY created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    orders = []
    for row in rows:
        try:
            items = json.loads(row[8]) if row[8] else []
        except:
            items = []
        orders.append({
            'order_id': row[0],
            'customer_name': row[1] or '',
            'customer_email': row[2] or '',
            'customer_phone': row[3] or '',
            'customer_address': row[4] or '',
            'customer_city': row[5] or '',
            'customer_extra': row[6] or '',
            'customer_notes': row[7] or '',
            'items': items,
            'total_amount': row[9],
            'status': row[10],
            'created_at': row[11],
            'tracking_number': row[12] or ''
        })
    return orders

def update_order_status(order_id, status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE orders 
        SET status = ?, updated_at = ?
        WHERE order_id = ?
    ''', (status, datetime.now().isoformat(), order_id))
    conn.commit()
    conn.close()

# === HTML ДЛЯ АДМИН-ПАНЕЛИ ===
ADMIN_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Админ-панель | АРТУРЧИК box</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: system-ui;
            background: linear-gradient(135deg, #0a0a0a 0%, #1a2a1a 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #2d8c4e; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }
        .stat-card { background: rgba(0,0,0,0.6); backdrop-filter: blur(10px); padding: 20px; border-radius: 20px; border: 1px solid #2d8c4e; min-width: 150px; text-align: center; }
        .stat-number { font-size: 36px; font-weight: bold; color: #2d8c4e; }
        .stat-label { color: #ccc; font-size: 14px; }
        .export-btn { background: #2d8c4e; color: white; border: none; padding: 12px 24px; border-radius: 12px; cursor: pointer; font-size: 16px; margin-bottom: 20px; }
        table { width: 100%; background: rgba(0,0,0,0.6); border-radius: 20px; overflow: hidden; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); color: white; }
        th { background: #2d8c4e; cursor: pointer; }
        tr:hover { background: rgba(45,140,78,0.2); }
        select { background: #1a2a1a; color: white; border: 1px solid #2d8c4e; padding: 5px 10px; border-radius: 8px; cursor: pointer; }
        .refresh-btn, .logout-btn { background: #2d8c4e; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .logout-btn { background: #ff4444; }
        @media (max-width: 768px) { th, td { padding: 8px; font-size: 12px; } .stats { gap: 10px; } .stat-card { padding: 10px; min-width: 100px; } .stat-number { font-size: 24px; } }
    </style>
</head>
<body>
       <div class="container">
        <h1>📦 Админ-панель АРТУРЧИК box <div><button class="refresh-btn" onclick="loadOrders()">🔄 Обновить</button><button class="logout-btn" onclick="logout()">🚪 Выйти</button></div></h1>
        
        <div class="stats">
            <div class="stat-card"><div class="stat-number" id="totalOrders">0</div><div class="stat-label">Всего заказов</div></div>
            <div class="stat-card"><div class="stat-number" id="totalAmount">0</div><div class="stat-label">Сумма (₽)</div></div>
            <div class="stat-card"><div class="stat-number" id="pendingOrders">0</div><div class="stat-label">Ожидают оплаты</div></div>
        </div>
        
       
                <!-- БЛОК ФИЛЬТРОВ -->
        <div style="display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; align-items: center;">
            <select id="statusFilter" onchange="applyFilters()" style="background: #1a2a1a; color: white; border: 1px solid #2d8c4e; padding: 10px 15px; border-radius: 10px;">
                <option value="all">📋 Все статусы</option>
                <option value="pending">⏳ Ожидают оплаты</option>
                <option value="paid">✅ Оплаченные</option>
                <option value="shipped">📦 Отправленные</option>
                <option value="completed">🎉 Завершённые</option>
            </select>
            
            <input type="date" id="dateFrom" onchange="applyFilters()" style="background: #1a2a1a; color: white; border: 1px solid #2d8c4e; padding: 10px 15px; border-radius: 10px;">
            <span style="color: white;">—</span>
            <input type="date" id="dateTo" onchange="applyFilters()" style="background: #1a2a1a; color: white; border: 1px solid #2d8c4e; padding: 10px 15px; border-radius: 10px;">
            
            <button onclick="resetFilters()" style="background: #2d8c4e; color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer;">🔄 Сбросить</button>
        </div>
        
        <button class="export-btn" onclick="exportExcel()">📊 Экспорт в Excel</button>
        
        <table>
            <thead>
                <tr>
                    <th>№ заказа</th>
                    <th>Покупатель</th>
                    <th>Email/Телефон</th>
                    <th>Сумма</th>
                    <th>Статус</th>
                    <th>Трек-номер</th>
                    <th>Дата</th>
                </tr>
            </thead>
            <tbody id="ordersBody">
                <tr><td colspan="7">Загрузка...</td></tr>
            </tbody>
        </table>
    </div>
    <script>
        let ordersData = [];
        let allOrdersData = [];
                        function applyFilters() {
            const status = document.getElementById('statusFilter').value;
            const search = document.getElementById('searchInput').value.toLowerCase();
            const dateFrom = document.getElementById('dateFrom').value;
            const dateTo = document.getElementById('dateTo').value;
            
            let filtered = [...allOrdersData];
            
            // Фильтр по статусу
            if (status !== 'all') {
                filtered = filtered.filter(order => order.status === status);
            }
            
            // Фильтр по поиску
            if (search) {
                filtered = filtered.filter(order => 
                    order.order_id.toLowerCase().includes(search) || 
                    (order.customer_name && order.customer_name.toLowerCase().includes(search))
                );
            }
            
            // Фильтр по дате (от)
            if (dateFrom) {
                const fromDate = new Date(dateFrom);
                filtered = filtered.filter(order => new Date(order.created_at) >= fromDate);
            }
            
            // Фильтр по дате (до)
            if (dateTo) {
                const toDate = new Date(dateTo);
                toDate.setHours(23, 59, 59);
                filtered = filtered.filter(order => new Date(order.created_at) <= toDate);
            }
            
            ordersData = filtered;
            renderOrders();
            updateStats();
        }
        
                function resetFilters() {
            document.getElementById('statusFilter').value = 'all';
            document.getElementById('searchInput').value = '';
            document.getElementById('dateFrom').value = '';
            document.getElementById('dateTo').value = '';
            ordersData = [...allOrdersData];
            renderOrders();
            updateStats();
        }
        async function loadOrders() {
            try {
                const response = await fetch('/api/orders');
                const data = await response.json();
                if (data.success) { 
                    allOrdersData = data.orders; 
                    ordersData = [...allOrdersData];
                    renderOrders(); 
                    updateStats(); 
                }
            } catch(error) { 
                document.getElementById('ordersBody').innerHTML = '<tr><td colspan="7">Ошибка загрузки</td></tr>'; 
            }
        }
        function renderOrders() {
    const tbody = document.getElementById('ordersBody');
    if (!ordersData.length) { 
        tbody.innerHTML = '<tr><td colspan="7">Нет заказов</td></tr>'; 
        return; 
    }
    tbody.innerHTML = ordersData.map(order => `<tr>
        <td>${order.order_id}</td>
        <td>${order.customer_name || '—'}</td>
        <td>${order.customer_email || '—'}<br><small>${order.customer_phone || ''}</small></td>
        <td>${order.total_amount} ₽</td>
        <td>
            <select onchange="updateStatus('${order.order_id}', this.value)">
                <option value="pending" ${order.status === 'pending' ? 'selected' : ''}>⏳ Ожидает</option>
                <option value="paid" ${order.status === 'paid' ? 'selected' : ''}>✅ Оплачен</option>
                <option value="shipped" ${order.status === 'shipped' ? 'selected' : ''}>📦 Отправлен</option>
                <option value="completed" ${order.status === 'completed' ? 'selected' : ''}>🎉 Завершён</option>
            </select>
        </td>
        <td>
            <input type="text" id="track_${order.order_id}" 
                   value="${order.tracking_number || ''}" 
                   placeholder="Введите трек-номер"
                   onchange="updateTracking('${order.order_id}', this.value)"
                   style="background: #1a2a1a; color: white; border: 1px solid #2d8c4e; padding: 5px; border-radius: 8px; width: 150px;">
        </td>
        <td>${new Date(order.created_at).toLocaleString()}</td>
         <td>
            <button onclick="showOrderDetails('${order.order_id}')" 
                    style="background: #2d8c4e; border: none; padding: 5px 10px; border-radius: 5px; cursor: pointer; color: white;">
                📋 Подробнее
            </button>
        </td>
    </td>`).join('');
}
        function updateStats() {
            document.getElementById('totalOrders').textContent = ordersData.length;
            document.getElementById('totalAmount').textContent = ordersData.reduce((s,o) => s + o.total_amount, 0).toLocaleString();
            document.getElementById('pendingOrders').textContent = ordersData.filter(o => o.status === 'pending').length;
        }
        async function updateStatus(orderId, newStatus) {
            await fetch('/api/update-status', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order_id: orderId, status: newStatus})});
            loadOrders();
        }
        function exportExcel() { window.open('/export-orders', '_blank'); }
        function logout() { window.location.href = '/admin/logout'; }
       function showOrderDetails(orderId) {
    const order = ordersData.find(o => o.order_id === orderId);
    if (!order) return;
    
    // Формируем список товаров с белым текстом
    const itemsHtml = order.items.map(item => `
        <div style="margin-bottom: 10px; padding: 8px; background: rgba(255,255,255,0.1); border-radius: 8px; color: white;">
            <strong style="color: #2d8c4e;">${item.name}</strong><br>
            <span style="color: white;">📏 Размер: ${item.size}</span><br>
            <span style="color: white;">🚫 Исключения: ${item.exclusions?.join(', ') || 'нет'}</span><br>
            <span style="color: white;">📦 Количество: ${item.quantity}</span><br>
            <span style="color: white;">💰 Цена: ${item.price} ₽</span>
        </div>
    `).join('');
    
    const modalHtml = `
        <div id="orderDetailModal" style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: #0d1f0d; padding: 25px; border-radius: 20px; z-index: 10003; max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto; border: 1px solid #2d8c4e;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3 style="color: #2d8c4e;">📦 Заказ ${order.order_id}</h3>
                <button onclick="closeOrderDetailModal()" style="background: #ff4444; border: none; padding: 5px 10px; border-radius: 5px; cursor: pointer; color: white;">✕</button>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">👤 Покупатель:</strong>
                <div style="color: white; margin-top: 5px;">${order.customer_name || '—'}</div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">📧 Email:</strong>
                <div style="color: white; margin-top: 5px;">${order.customer_email || '—'}</div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">📞 Телефон:</strong>
                <div style="color: white; margin-top: 5px;">${order.customer_phone || '—'}</div>
            </div>
            
                        <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">📍 Адрес доставки:</strong>
                <div style="color: white; margin-top: 5px;" id="addressText_${order.order_id}">
                    ${order.customer_address || '—'}, ${order.customer_city || '—'}${order.customer_extra ? ', ' + order.customer_extra : ''}
                </div>
                <button onclick="copyAddress('${order.order_id}')" 
                        style="background: #2d8c4e; border: none; padding: 5px 12px; border-radius: 5px; cursor: pointer; color: white; margin-top: 8px;">
                    📋 Скопировать адрес
                </button>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">📋 Состав заказа:</strong>
                <div style="margin-top: 5px;">${itemsHtml}</div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">💰 Сумма:</strong>
                <div style="color: white; margin-top: 5px;">${order.total_amount} ₽</div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">📌 Статус:</strong>
                <div style="color: white; margin-top: 5px;">${order.status === 'pending' ? '⏳ Ожидает оплаты' : order.status === 'paid' ? '✅ Оплачен' : order.status === 'shipped' ? '📦 Отправлен' : '🎉 Завершён'}</div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">📅 Дата создания:</strong>
                <div style="color: white; margin-top: 5px;">${new Date(order.created_at).toLocaleString()}</div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">📦 Трек-номер:</strong>
                <div style="color: white; margin-top: 5px;">${order.tracking_number || 'ещё не присвоен'}</div>
            </div>
            
            ${order.customer_notes ? `
            <div style="margin-bottom: 15px;">
                <strong style="color: #2d8c4e;">📝 Примечание к заказу:</strong>
                <div style="color: white; margin-top: 5px;">${order.customer_notes}</div>
            </div>
            ` : ''}
        </div>
        <div id="orderDetailOverlay" onclick="closeOrderDetailModal()" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10002;"></div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}
        loadOrders();
        setInterval(loadOrders, 30000);

        async function updateTracking(orderId, trackingNumber) {
    try {
        const response = await fetch('/api/update-tracking', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order_id: orderId, tracking_number: trackingNumber })
        });
        const data = await response.json();
        if (data.success) {
            showToast('Трек-номер сохранён');
        } else {
            showToast('Ошибка: ' + data.error);
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showToast('Ошибка соединения');
    }
}

function closeOrderDetailModal() {
    const modal = document.getElementById('orderDetailModal');
    const overlay = document.getElementById('orderDetailOverlay');
    if (modal) modal.remove();
    if (overlay) overlay.remove();
}
function showToast(message) {
    alert(message);
}
        function copyAddress(orderId) {
            const addressElement = document.getElementById(`addressText_${orderId}`);
            if (addressElement) {
                const address = addressElement.innerText;
                navigator.clipboard.writeText(address).then(() => {
                    alert('Адрес скопирован в буфер обмена');
                }).catch(() => {
                    alert('Не удалось скопировать адрес');
                });
            }
        }

        
    </script>
</body>
</html>
'''

# === HTML ДЛЯ ВХОДА В АДМИНКУ ===
LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><title>Вход в админ-панель</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: system-ui;
            background: linear-gradient(135deg, #0a0a0a 0%, #1a2a1a 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #2d8c4e; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }
        .stat-card { background: rgba(0,0,0,0.6); backdrop-filter: blur(10px); padding: 20px; border-radius: 20px; border: 1px solid #2d8c4e; min-width: 150px; text-align: center; }
        .stat-number { font-size: 36px; font-weight: bold; color: #2d8c4e; }
        .stat-label { color: #ccc; font-size: 14px; }
        .export-btn { background: #2d8c4e; color: white; border: none; padding: 12px 24px; border-radius: 12px; cursor: pointer; font-size: 16px; margin-bottom: 20px; }
        table { width: 100%; background: rgba(0,0,0,0.6); border-radius: 20px; overflow: hidden; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); color: white; }
        th { background: #2d8c4e; cursor: pointer; }
        tr:hover { background: rgba(45,140,78,0.2); }
        select { background: #1a2a1a; color: white; border: 1px solid #2d8c4e; padding: 5px 10px; border-radius: 8px; cursor: pointer; }
        .refresh-btn, .logout-btn { background: #2d8c4e; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .logout-btn { background: #ff4444; }
        @media (max-width: 768px) { th, td { padding: 8px; font-size: 12px; } .stats { gap: 10px; } .stat-card { padding: 10px; min-width: 100px; } .stat-number { font-size: 24px; } }
        
        /* СТИЛИ ДЛЯ ФИЛЬТРОВ — ДОБАВИТЬ СЮДА */
        .filters {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: center;
        }
        .filters select, .filters input {
            background: #1a2a1a;
            color: white;
            border: 1px solid #2d8c4e;
            padding: 10px 15px;
            border-radius: 10px;
        }
        .filters button {
            background: #2d8c4e;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 10px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>🔐 Вход в админ-панель</h2>
        <form method="post"><input type="password" name="password" placeholder="Введите пароль" autofocus><button type="submit">Войти</button></form>
    </div>
</body>
</html>
'''

# === API РОУТЫ ===

@app.route('/')
def home():
    return jsonify({'status': 'ok', 'message': 'Сервер работает', 'time': datetime.now().isoformat()})

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            return ADMIN_HTML
        return LOGIN_HTML + '<div class="error">❌ Неверный пароль</div>'
    return LOGIN_HTML

@app.route('/admin/dashboard')
def admin_dashboard():
    return ADMIN_HTML

@app.route('/admin/logout')
def admin_logout():
    return redirect(url_for('admin_panel'))

# === ПОЛЬЗОВАТЕЛЬСКИЕ РОУТЫ ===

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        print(f"[DEBUG] Получены данные: {data}")  # ← ЭТО ВАЖНО
        
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        password = data.get('password')
        telegram = data.get('telegram')
        
        print(f"[DEBUG] telegram = {telegram}")  # ← ЭТО ВАЖНО
        
        if not email or not password or not name:
            return jsonify({'success': False, 'error': 'Все поля обязательны'}), 400
        
        result = create_user(email, password, name, phone, telegram)
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        result = authenticate_user(email, password)
        if result['success']:
            # 👇 ДОБАВЬ ЭТИ ТРИ СТРОКИ — они сохраняют данные в сессию
            session['user_id'] = result['user_id']
            session['user_name'] = result['name']
            session['user_email'] = result['email']
            
            token = generate_token(result['user_id'])
            return jsonify({
                'success': True,
                'token': token,
                'user': {
                    'id': result['user_id'],
                    'name': result['name'],
                    'email': result['email']
                }
            })
        else:
            return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)
    return jsonify({'success': True})

@app.route('/api/me', methods=['GET'])
def get_current_user():
    if session.get('user_id'):
        return jsonify({
            'success': True,
            'user': {
                'id': session['user_id'],
                'name': session['user_name'],
                'email': session['user_email']
            }
        })
    return jsonify({'success': False, 'error': 'Не авторизован'}), 401

@app.route('/api/my-orders', methods=['GET'])
def get_my_orders():
    # ВРЕМЕННО: возвращаем заказы для пользователя с email = 123@bk.ru
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', ('123@bk.ru',))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        orders = get_user_orders(user[0])
        return jsonify({'success': True, 'orders': orders})
    
    return jsonify({'success': True, 'orders': []})
def get_api_orders():
    orders = get_all_orders()
    return jsonify({'success': True, 'orders': orders, 'count': len(orders)})

@app.route('/api/update-status', methods=['POST'])
def update_status_api():
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        status = data.get('status')
        
        if not order_id or not status:
            return jsonify({'success': False, 'error': 'Missing fields'}), 400
        
        # Получаем информацию о заказе и пользователе
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.customer_name, o.customer_email, u.telegram_id, o.total_amount, o.tracking_number
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.id
            WHERE o.order_id = ?
        ''', (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        update_order_status(order_id, status)
        
        status_text = {
            'pending': '⏳ Ожидает оплаты',
            'paid': '✅ Оплачен',
            'shipped': '📦 Отправлен',
            'completed': '🎉 Завершён'
        }.get(status, status)
        
        tracking_text = ''
        if order and order[4] and status == 'shipped':
            tracking_text = f'\n\n📦 Трек-номер для отслеживания:\nhttps://www.cdek.ru/track?order_id={order[4]}'
        
        # Уведомление админу (уже есть)
        msg_admin = f"""🔄 <b>СТАТУС ЗАКАЗА ИЗМЕНЁН</b>
📦 Заказ: {order_id}
👤 Клиент: {order[0] if order else 'Не указан'}
💰 Сумма: {order[3] if order else '?'} ₽
📌 Новый статус: {status_text}
🔗 Админка: https://arturchik-box-2.onrender.com/admin"""
        send_telegram_message(msg_admin)
        
        # Уведомление покупателю
        if order and order[2]:  # если есть telegram_id
            msg_user = f"""📦 <b>АРТУРЧИК box</b>
            
Здравствуйте, {order[0]}!
Статус вашего заказа <b>№{order_id}</b> изменился на:
{status_text}
{tracking_text}
Спасибо, что выбрали нас!"""
            send_telegram_to_user(order[2], msg_user)
                # Отправляем email покупателю
        if order and order[1]:
            send_order_status_email(order_id, order[0], order[1], status, order[4])
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"[ERROR] update_status_api: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/export-orders', methods=['GET'])
def export_orders():
    try:
        orders = get_all_orders()
        wb = Workbook()
        ws = wb.active
        ws.title = "Заказы"
        headers = ['№ заказа', 'Покупатель', 'Email', 'Телефон', 'Товары', 'Сумма (₽)', 'Статус', 'Дата создания']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="2d8c4e", end_color="2d8c4e", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")
        for row_idx, order in enumerate(orders, 2):
            items_text = ', '.join([f"{item.get('name', '')} ({item.get('size', '')}) x{item.get('quantity', 1)}" for item in order.get('items', [])])
            ws.cell(row=row_idx, column=1, value=order.get('order_id', ''))
            ws.cell(row=row_idx, column=2, value=order.get('customer_name', ''))
            ws.cell(row=row_idx, column=3, value=order.get('customer_email', ''))
            ws.cell(row=row_idx, column=4, value=order.get('customer_phone', ''))
            ws.cell(row=row_idx, column=5, value=items_text)
            ws.cell(row=row_idx, column=6, value=order.get('total_amount', 0))
            ws.cell(row=row_idx, column=7, value=order.get('status', 'pending'))
            ws.cell(row=row_idx, column=8, value=order.get('created_at', ''))
        for col in range(1, 9):
            ws.column_dimensions[chr(64 + col)].width = 20
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name=f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/create-payment', methods=['POST'])
def create_payment():
    try:
        data = request.get_json()
        amount = data.get('amount', 3490)
        cart_items = data.get('items', [])
        customer = data.get('customer', {})
        
        # 👇 ЭТОЙ СТРОКИ НЕ ХВАТАЕТ
        user_id = data.get('user_id')  # может быть None, если пользователь не авторизован
        
        customer_name = customer.get('fullName', '')
        customer_phone = customer.get('phone', '')
        customer_email = customer.get('email', '')
        customer_address = customer.get('address', '')
        customer_city = customer.get('city', '')
        customer_extra = customer.get('extraAddress', '')
        customer_notes = customer.get('notes', '')
        
        order_id = f"ORDER_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        order_data = {
            'order_id': order_id,
            'user_id': user_id,  # ← теперь user_id определён
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'customer_email': customer_email,
            'customer_address': customer_address,
            'customer_city': customer_city,
            'customer_extra': customer_extra,
            'customer_notes': customer_notes,
            'items': cart_items,
            'total_amount': amount,
            'status': 'pending',
            'payment_id': ''
        }
        save_order(order_data)
        
        print(f"[DEBUG] Заказ создан: {order_id}, город={customer_city}, адрес={customer_address}")
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'amount': amount
        })
        
    except Exception as e:
        print(f"[ERROR] create_payment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/update-tracking', methods=['POST'])
def update_tracking():
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        tracking_number = data.get('tracking_number')
        
        if not order_id:
            return jsonify({'success': False, 'error': 'order_id required'}), 400
        
        # Обновляем трек-номер
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('UPDATE orders SET tracking_number = ? WHERE order_id = ?', 
                       (tracking_number, order_id))
        conn.commit()
        
        # Получаем информацию о заказе и покупателе для уведомления
        cursor.execute('''
            SELECT o.customer_name, u.telegram_id 
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.id
            WHERE o.order_id = ?
        ''', (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        print(f"[TRACKING] Заказ {order_id} обновлён: {tracking_number}")
        print(f"[TRACKING] order = {order}")
        print(f"[TRACKING] telegram_id = {order[1] if order else 'None'}")
        
        # ✅ ПРИНУДИТЕЛЬНАЯ ОТПРАВКА ТЕБЕ (АДМИНУ) — ВСЕГДА РАБОТАЕТ
        send_telegram_message(f"""📦 <b>ТРЕК-НОМЕР ДОБАВЛЕН</b>
        
📦 Заказ: {order_id}
🚚 Трек-номер: {tracking_number}
🔗 Ссылка: https://www.cdek.ru/track?order_id={tracking_number}
👤 Клиент: {order[0] if order else 'Неизвестен'}
🔗 Админка: https://arturchik-box-2.onrender.com/admin""")
        
        # Отправляем покупателю, если есть telegram_id
        if order and order[1] and tracking_number:
            msg_user = f"""📦 <b>АРТУРЧИК box</b>

Здравствуйте, {order[0]}!

Ваш заказ <b>№{order_id}</b> отправлен!

📦 Трек-номер для отслеживания:
<a href="https://www.cdek.ru/track?order_id={tracking_number}">{tracking_number}</a>

Вы можете отслеживать посылку на сайте СДЭК.

Спасибо, что выбрали нас!"""
            send_telegram_to_user(order[1], msg_user)
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"[ERROR] update_tracking: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.get_json()
        message = data.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')
        
        # Не отвечаем админу (у него свои уведомления)
        if str(chat_id) != TELEGRAM_CHAT_ID and text:
            handle_customer_message(chat_id, text)
        else:
            print(f"[BOT] Сообщение от админа: {text}")
        
        return jsonify({'ok': True})
    except Exception as e:
        print(f"[BOT] Ошибка: {e}")
        return jsonify({'ok': False}), 500
# === ВОССТАНОВЛЕНИЕ ПАРОЛЯ И ПРИВЯЗКА TELEGRAM ===
reset_codes_tg = {}

@app.route('/api/reset-password-telegram', methods=['POST'])
def reset_password_telegram():
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'error': 'Email обязателен'}), 400
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, telegram_id FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        telegram_id = user[2]
        if not telegram_id:
            return jsonify({'success': False, 'error': 'У этого аккаунта не указан Telegram. Привяжите его в личном кабинете.'}), 400
        
        import random
        import string
        code = ''.join(random.choices(string.digits, k=6))
        expires = datetime.now().timestamp() + 900
        
        reset_codes_tg[email] = {'code': code, 'expires': expires}
        
        msg = f"""🔐 <b>Восстановление пароля АРТУРЧИК box</b>

Ваш код для сброса пароля: <code>{code}</code>

Код действителен в течение 15 минут.

Если вы не запрашивали сброс пароля, просто проигнорируйте это сообщение."""
        
        send_telegram_to_user(telegram_id, msg)
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"[ERROR] reset_password_telegram: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/set-telegram', methods=['POST'])
def set_telegram():
    try:
        data = request.get_json()
        telegram_id = data.get('telegram_id')
        email = data.get('email')
        
        print(f"[DEBUG] set_telegram: telegram_id={telegram_id}, email={email}")
        
        if not telegram_id:
            return jsonify({'success': False, 'error': 'Telegram ID не указан'}), 400
        
        if not email:
            return jsonify({'success': False, 'error': 'Email не указан'}), 400
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET telegram_id = ? WHERE email = ?', (telegram_id, email))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'success': False, 'error': 'Пользователь с таким email не найден'}), 404
        
        conn.commit()
        conn.close()
        
        # Отправляем тестовое сообщение
        try:
            send_telegram_to_user(telegram_id, "✅ Ваш Telegram успешно привязан к аккаунту АРТУРЧИК box!")
        except Exception as e:
            print(f"[TG] Ошибка отправки: {e}")
        
        return jsonify({'success': True, 'message': 'Telegram успешно привязан!'})
        
    except Exception as e:
        print(f"[ERROR] set_telegram: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/test-telegram', methods=['POST'])
def test_telegram():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Не авторизован'}), 401
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user and user[0]:
            send_telegram_to_user(user[0], "✅ Связь с ботом работает! Если вы видите это сообщение, всё настроено правильно.")
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Telegram не привязан'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/confirm-reset-telegram', methods=['POST', 'OPTIONS'])
def confirm_reset_telegram():
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        data = request.get_json()
        email = data.get('email')
        code = data.get('code')
        new_password = data.get('new_password')
        
        if not email or not code or not new_password:
            return jsonify({'success': False, 'error': 'Все поля обязательны'}), 400
        
        stored = reset_codes_tg.get(email)
        if not stored:
            return jsonify({'success': False, 'error': 'Код не найден или истёк'}), 400
        
        if datetime.now().timestamp() > stored['expires']:
            del reset_codes_tg[email]
            return jsonify({'success': False, 'error': 'Код истёк. Запросите новый'}), 400
        
        if stored['code'] != code:
            return jsonify({'success': False, 'error': 'Неверный код'}), 400
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        hashed_pw = hash_password(new_password)
        cursor.execute('UPDATE users SET password = ? WHERE email = ?', (hashed_pw, email))
        conn.commit()
        conn.close()
        
        del reset_codes_tg[email]
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"[ERROR] confirm_reset_telegram: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', 'https://1lyas1k333.github.io')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response
if __name__ == '__main__':
    app.run(debug=True, port=5000)

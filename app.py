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
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

app = Flask(__name__)
app.secret_key = 'secret_key_for_session_12345'

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
            telegram_id
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
        # Проверяем, есть ли колонка tracking_number
        cursor.execute("PRAGMA table_info(orders)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'tracking_number' not in columns:
            print("[DB] Добавляем колонку tracking_number...")
            cursor.execute("ALTER TABLE orders ADD COLUMN tracking_number TEXT DEFAULT ''")
            conn.commit()
            print("[DB] Колонка tracking_number добавлена")
        else:
            print("[DB] База данных уже существует")
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
            VALUES (?, ?, ?, ?, ?, ?)
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
        SELECT order_id, customer_name, customer_email, customer_phone, items, total_amount, status, created_at, tracking_number 
        FROM orders 
        ORDER BY created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    orders = []
    for row in rows:
        try:
            items = json.loads(row[4]) if row[4] else []
        except:
            items = []
        orders.append({
            'order_id': row[0],
            'customer_name': row[1] or '',
            'customer_email': row[2] or '',
            'customer_phone': row[3] or '',
            'items': items,
            'total_amount': row[5],
            'status': row[6],
            'created_at': row[7],
            'tracking_number': row[8] or ''
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
        <div class="stats"><div class="stat-card"><div class="stat-number" id="totalOrders">0</div><div class="stat-label">Всего заказов</div></div><div class="stat-card"><div class="stat-number" id="totalAmount">0</div><div class="stat-label">Сумма (₽)</div></div><div class="stat-card"><div class="stat-number" id="pendingOrders">0</div><div class="stat-label">Ожидают оплаты</div></div></div>
        <button class="export-btn" onclick="exportExcel()">📊 Экспорт в Excel</button>
        <table><thead><tr><th>№ заказа</th><th>Покупатель</th><th>Email/Телефон</th><th>Сумма</th><th>Статус</th><th>Трек-номер</th><th>Дата</th></tr></thead><tbody id="ordersBody"></table><td colspan="6">Загрузка...</td></tbody></table>
    </div>
    <script>
        let ordersData = [];
        async function loadOrders() {
            try {
                const response = await fetch('/api/orders');
                const data = await response.json();
                if (data.success) { ordersData = data.orders; renderOrders(); updateStats(); }
            } catch(error) { document.getElementById('ordersBody').innerHTML = '<td><td colspan="6">Ошибка</td></tr>'; }
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

function showToast(message) {
    alert(message);
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
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:system-ui;background:linear-gradient(135deg,#0a0a0a 0%,#1a2a1a 100%);min-height:100vh;display:flex;justify-content:center;align-items:center}
    .login-box{background:rgba(0,0,0,0.7);backdrop-filter:blur(10px);padding:40px;border-radius:30px;border:1px solid #2d8c4e;text-align:center;width:350px}
    h2{color:#2d8c4e;margin-bottom:20px}
    input{width:100%;padding:12px;margin:10px 0;border:1px solid #2d8c4e;border-radius:12px;background:rgba(0,0,0,0.5);color:white;font-size:16px}
    button{background:#2d8c4e;color:white;border:none;padding:12px;border-radius:12px;cursor:pointer;font-size:16px;width:100%}
    .error{color:#ff4444;margin-top:10px}
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
        email = data.get('email')
        password = data.get('password')
        name = data.get('name')
        phone = data.get('phone')
        
        if not email or not password or not name:
            return jsonify({'success': False, 'error': 'Все поля обязательны'}), 400
        
        result = create_user(email, password, name, phone)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        result = authenticate_user(email, password)
        if result['success']:
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
    if not session.get('user_id'):
        return jsonify({'success': False, 'error': 'Не авторизован'}), 401
    orders = get_user_orders(session['user_id'])
    return jsonify({'success': True, 'orders': orders})

@app.route('/api/orders', methods=['GET'])
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
            'user_id': None,
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
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('UPDATE orders SET tracking_number = ? WHERE order_id = ?', 
                       (tracking_number, order_id))
        conn.commit()
        conn.close()
        
        print(f"[TRACKING] Заказ {order_id} обновлён: {tracking_number}")
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"[ERROR] update_tracking: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
def send_telegram_to_user(chat_id, message):
    """Отправка сообщения конкретному пользователю в Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=5)
        print(f"[TG_USER] Отправлено пользователю {chat_id}")
        return True
    except Exception as e:
        print(f"[TG_USER] Ошибка: {e}")
        return False

if __name__ == '__main__':
    app.run(debug=True, port=5000)

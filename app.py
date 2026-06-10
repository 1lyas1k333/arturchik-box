import os
import uuid
import json
import hashlib
import secrets
import requests
from datetime import datetime
from flask import Flask, jsonify, request, session, redirect, send_file
from flask_cors import CORS
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'secret_key_for_session_12345'

# === CORS ===
CORS(app, origins=["https://1lyas1k333.github.io", "https://arturchik-box-2.onrender.com"], supports_credentials=True)

# === SUPABASE ===
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://xszdufdzgvzwtiyppyxs.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# === TELEGRAM ===
TELEGRAM_TOKEN = "8694164916:AAEYQey-DSovguWmgy-mZLG4nMVhSV4BunQ"
TELEGRAM_CHAT_ID = "1056646376"

# === PLATEGA ===
PLATEGA_SHOP_ID = "a8922d02-2beb-44a0-b24a-4b6e6caa33ef"
PLATEGA_API_KEY = "osj9xJrzJb9jeFXjUHBMucfuR8DXydxScLOGImdzGaiMXNLj8KuiBDsH3AUBZ1vlsckfPWD4jZhdw5HQzJPJdQJWTkitFDtBCAtL"
PLATEGA_API_URL = "https://app.platega.io/transaction/process"

# === АДМИН ===
ADMIN_PASSWORD = "123"

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token(user_id):
    data = f"{user_id}:{datetime.now().isoformat()}:{secrets.token_hex(8)}"
    return hashlib.sha256(data.encode()).hexdigest()

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=5)
    except Exception as e:
        print(f"[TG] Ошибка: {e}")

def send_telegram_to_user(chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=5)
        print(f"[TG_USER] Отправлено пользователю {chat_id}")
    except Exception as e:
        print(f"[TG_USER] Ошибка: {e}")

def update_order_status(order_id, status):
    supabase.table("orders").update({"status": status, "updated_at": datetime.now().isoformat()}).eq("order_id", order_id).execute()
    print(f"[DB] Заказ {order_id} обновлён → {status}")

# ========== API РОУТЫ ==========
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    user_id = str(uuid.uuid4())
    hashed_pw = hash_password(data['password'])
    try:
        supabase.table("users").insert({
            "id": user_id, "email": data['email'], "password": hashed_pw,
            "name": data['name'], "phone": data['phone'], "telegram_id": data.get('telegram'),
            "created_at": datetime.now().isoformat()
        }).execute()
        return jsonify({"success": True, "user_id": user_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    hashed_input = hash_password(data['password'])
    res = supabase.table("users").select("*").eq("email", data['email']).eq("password", hashed_input).execute()
    if not res.data:
        return jsonify({"success": False, "error": "Неверный email или пароль"}), 401
    user = res.data[0]
    token = generate_token(user['id'])
    supabase.table("user_tokens").insert({
        "id": str(uuid.uuid4()), "user_id": user['id'], "token": token,
        "created_at": datetime.now().isoformat(), "expires_at": datetime.now().timestamp() + 30*24*3600
    }).execute()
    session['user_id'] = user['id']
    return jsonify({"success": True, "token": token, "user": {"id": user['id'], "name": user['name'], "email": user['email']}})

@app.route('/api/my-orders', methods=['GET'])
def get_my_orders():
    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Bearer '):
        return jsonify({"success": False, "error": "Не авторизован"}), 401
    token = auth.split(' ')[1]
    res = supabase.table("user_tokens").select("user_id").eq("token", token).execute()
    if not res.data:
        return jsonify({"success": False, "error": "Не авторизован"}), 401
    user_id = res.data[0]['user_id']
    orders = supabase.table("orders").select("*").eq("user_id", user_id).execute()
    return jsonify({"success": True, "orders": orders.data})

@app.route('/api/orders', methods=['GET'])
def get_all_orders():
    orders = supabase.table("orders").select("*").execute()
    return jsonify({"success": True, "orders": orders.data, "count": len(orders.data)})



@app.route('/api/update-tracking', methods=['POST'])
def update_tracking():
    data = request.get_json()
    order_id = data.get('order_id')
    tracking_number = data.get('tracking_number')
    
    # Обновляем трек-номер в базе данных
    supabase.table("orders").update({"tracking_number": tracking_number}).eq("order_id", order_id).execute()
    
    # Уведомление админу (в Telegram)
    send_telegram_message(f"📦 Трек-номер для заказа {order_id}: {tracking_number}")
    
    # Получаем информацию о заказе и пользователе для уведомления покупателя
    order_res = supabase.table("orders").select("customer_name, user_id").eq("order_id", order_id).execute()
    if order_res.data:
        user_res = supabase.table("users").select("telegram_id").eq("id", order_res.data[0].get('user_id')).execute()
        if user_res.data and user_res.data[0].get('telegram_id'):
            msg_user = f"""📦 <b>Ваш заказ отправлен!</b>

Здравствуйте, {order_res.data[0].get('customer_name')}!

Ваш заказ №{order_id} отправлен.

📦 Трек-номер: {tracking_number}
🔗 Отследить: https://www.cdek.ru/track?order_id={tracking_number}

Спасибо за покупку!"""
            send_telegram_to_user(user_res.data[0]['telegram_id'], msg_user)
        else:
            print(f"[TRACKING] У пользователя нет Telegram ID для заказа {order_id}")
    
    return jsonify({"success": True})

@app.route('/create-payment', methods=['POST'])
def create_payment():
    data = request.get_json()
    amount = data.get('amount', 3490)
    cart_items = data.get('items', [])
    customer = data.get('customer', {})
    user_id = data.get('user_id')
    
    order_id = f"ORDER_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    order_data = {
        "id": str(uuid.uuid4()), "order_id": order_id, "user_id": user_id,
        "customer_name": customer.get('fullName'), "customer_phone": customer.get('phone'),
        "customer_email": customer.get('email'), "customer_address": customer.get('address'),
        "customer_city": customer.get('city'), "customer_extra": customer.get('extraAddress'),
        "customer_notes": customer.get('notes'), "items": json.dumps(cart_items),
        "total_amount": amount, "status": "pending", "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    supabase.table("orders").insert(order_data).execute()
    
    try:
        headers = {"X-MerchantId": PLATEGA_SHOP_ID, "X-Secret": PLATEGA_API_KEY, "Content-Type": "application/json"}
        payload = {
            "paymentMethod": 2, "paymentDetails": {"amount": float(amount), "currency": "RUB"},
            "description": f"Футбольный бокс, заказ {order_id}",
            "return": "https://1lyas1k333.github.io/payment-success",
            "failedUrl": "https://1lyas1k333.github.io/payment-failed",
            "payload": order_id, "callback_url": "https://arturchik-box-2.onrender.com/platega-webhook"
        }
        response = requests.post(PLATEGA_API_URL, json=payload, headers=headers, timeout=30)
        result = response.json()
        if response.status_code == 200 and result.get('redirect'):
            return jsonify({"success": True, "order_id": order_id, "amount": amount, "payment_url": result['redirect']})
        return jsonify({"success": False, "error": "Ошибка создания платежа"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/platega-webhook', methods=['POST', 'GET'])
def platega_webhook():
    if request.method == 'GET':
        return jsonify({"status": "ok"}), 200
    data = request.get_json()
    print(f"[WEBHOOK] {data}")
    order_id = data.get('payload')
    if order_id and data.get('status') == 'CONFIRMED':
        update_order_status(order_id, 'paid')
        
        # Уведомление админу
        send_telegram_message(f"✅ ОПЛАЧЕН ЗАКАЗ {order_id}")
        
        # Уведомление покупателю
        order_res = supabase.table("orders").select("customer_name, user_id").eq("order_id", order_id).execute()
        if order_res.data:
            user_res = supabase.table("users").select("telegram_id").eq("id", order_res.data[0].get('user_id')).execute()
            if user_res.data and user_res.data[0].get('telegram_id'):
                msg_user = f"""✅ <b>Заказ оплачен!</b>

Здравствуйте, {order_res.data[0].get('customer_name')}!

Ваш заказ №{order_id} успешно оплачен.

Мы начинаем комплектацию и скоро отправим трек-номер для отслеживания.

Спасибо за покупку!"""
                send_telegram_to_user(user_res.data[0]['telegram_id'], msg_user)
    
    return jsonify({"success": True}), 200

# ========== АДМИН-ПАНЕЛЬ ==========
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            return redirect('/admin/dashboard')
        return '<h2>❌ Неверный пароль</h2><a href="/admin">Вернуться</a>'
    return '''
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Вход в админ-панель</title>
    <style>
        body { background: linear-gradient(135deg, #0a0a0a 0%, #1a2a1a 100%); font-family: system-ui; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: rgba(0,0,0,0.6); backdrop-filter: blur(10px); padding: 40px; border-radius: 30px; border: 1px solid #2d8c4e; text-align: center; width: 300px; }
        h2 { color: #2d8c4e; margin-bottom: 20px; }
        input { width: 100%; padding: 12px; margin-bottom: 15px; border-radius: 12px; border: 1px solid #2d8c4e; background: rgba(0,0,0,0.5); color: white; }
        button { background: #2d8c4e; color: white; padding: 12px; border: none; border-radius: 12px; width: 100%; cursor: pointer; }
    </style>
    </head>
    <body><div class="login-box"><h2>🔐 Вход в админ-панель</h2>
    <form method="post"><input type="password" name="password" placeholder="Введите пароль" autofocus><button type="submit">Войти</button></form>
    </div></body></html>
    '''

@app.route('/admin/dashboard')
def admin_dashboard():
    return '''
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Админ-панель</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: system-ui; background: linear-gradient(135deg, #0a0a0a 0%, #1a2a1a 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #2d8c4e; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }
        .stat-card { background: rgba(0,0,0,0.6); backdrop-filter: blur(10px); padding: 20px; border-radius: 20px; border: 1px solid #2d8c4e; min-width: 150px; text-align: center; }
        .stat-number { font-size: 36px; font-weight: bold; color: #2d8c4e; }
        .stat-label { color: #ccc; font-size: 14px; }
        table { width: 100%; background: rgba(0,0,0,0.6); border-radius: 20px; overflow: hidden; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); color: white; }
        th { background: #2d8c4e; }
        select, input { background: #1a2a1a; color: white; border: 1px solid #2d8c4e; padding: 5px 10px; border-radius: 8px; }
        .refresh-btn, .logout-btn { background: #2d8c4e; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .logout-btn { background: #ff4444; }
    </style>
    </head>
    <body>
    <div class="container">
        <h1>📦 Админ-панель <div><button class="refresh-btn" onclick="loadOrders()">🔄 Обновить</button><button class="logout-btn" onclick="logout()">🚪 Выйти</button></div></h1>
        <div class="stats"><div class="stat-card"><div class="stat-number" id="totalOrders">0</div><div class="stat-label">Всего заказов</div></div>
        <div class="stat-card"><div class="stat-number" id="totalAmount">0</div><div class="stat-label">Сумма (₽)</div></div>
        <div class="stat-card"><div class="stat-number" id="pendingOrders">0</div><div class="stat-label">Ожидают оплаты</div></div></div>
        <table><thead><tr><th>№ заказа</th><th>Покупатель</th><th>Email</th><th>Сумма</th><th>Статус</th><th>Трек-номер</th><th>Дата</th></tr></thead>
        <tbody id="ordersBody"><tr><td colspan="7">Загрузка...</td></tr></tbody></table>
    </div>
    <script>
        async function loadOrders() {
            const res = await fetch('/api/orders');
            const data = await res.json();
            if (!data.success) return;
            const orders = data.orders;
            document.getElementById('totalOrders').innerText = orders.length;
            document.getElementById('totalAmount').innerText = orders.reduce((s,o) => s + o.total_amount, 0);
            document.getElementById('pendingOrders').innerText = orders.filter(o => o.status === 'pending').length;
            const tbody = document.getElementById('ordersBody');
            if (!orders.length) { tbody.innerHTML = '<tr><td colspan="7">Нет заказов</td></tr>'; return; }
            tbody.innerHTML = orders.map(order => `
                <tr>
                    <td>${order.order_id}</td>
                    <td>${order.customer_name || '—'}</td>
                    <td>${order.customer_email || '—'}</td>
                    <td>${order.total_amount} ₽</td>
                    <td><select onchange="updateStatus('${order.order_id}', this.value)">
                        <option value="pending" ${order.status === 'pending' ? 'selected' : ''}>⏳ Ожидает</option>
                        <option value="paid" ${order.status === 'paid' ? 'selected' : ''}>✅ Оплачен</option>
                        <option value="shipped" ${order.status === 'shipped' ? 'selected' : ''}>📦 Отправлен</option>
                        <option value="completed" ${order.status === 'completed' ? 'selected' : ''}>🎉 Завершён</option>
                    </select></td>
                    <td><input type="text" placeholder="Трек-номер" onchange="updateTracking('${order.order_id}', this.value)"></td>
                    <td>${new Date(order.created_at).toLocaleString()}</td>
                </tr>
            `).join('');
        }
        async function updateStatus(orderId, status) {
            await fetch('/api/update-status', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order_id: orderId, status})});
            loadOrders();
        }
        async function updateTracking(orderId, tracking) {
            await fetch('/api/update-tracking', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order_id: orderId, tracking_number: tracking})});
        }
        function logout() { window.location.href = '/admin/logout'; }
        loadOrders();
        setInterval(loadOrders, 30000);
    </script>
    </body></html>
    '''

@app.route('/admin/logout')
def admin_logout():
    return redirect('/admin')

@app.route('/')
def home():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})
# ========== TELEGRAM ПРИВЯЗКА И ВОССТАНОВЛЕНИЕ ПАРОЛЯ ==========
reset_codes_tg = {}

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
        
        result = supabase.table("users").update({"telegram_id": telegram_id}).eq("email", email).execute()
        if not result.data:
            return jsonify({'success': False, 'error': 'Пользователь с таким email не найден'}), 404
        
        try:
            send_telegram_to_user(telegram_id, "✅ Ваш Telegram успешно привязан к аккаунту АРТУРЧИК box!")
        except Exception as e:
            print(f"[TG] Ошибка отправки: {e}")
        
        return jsonify({'success': True, 'message': 'Telegram успешно привязан!'})
    except Exception as e:
        print(f"[ERROR] set_telegram: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reset-password-telegram', methods=['POST'])
def reset_password_telegram():
    try:
        data = request.get_json()
        email = data.get('email')
        if not email:
            return jsonify({'success': False, 'error': 'Email обязателен'}), 400
        
        res = supabase.table("users").select("id, name, telegram_id").eq("email", email).execute()
        if not res.data:
            return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
        
        user = res.data[0]
        telegram_id = user.get('telegram_id')
        if not telegram_id:
            return jsonify({'success': False, 'error': 'У этого аккаунта не указан Telegram. Привяжите его в личном кабинете.'}), 400
        
        import random, string
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

@app.route('/api/confirm-reset-telegram', methods=['POST'])
def confirm_reset_telegram():
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
        
        hashed_pw = hash_password(new_password)
        supabase.table("users").update({"password": hashed_pw}).eq("email", email).execute()
        del reset_codes_tg[email]
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"[ERROR] confirm_reset_telegram: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/test-telegram', methods=['POST'])
def test_telegram():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Не авторизован'}), 401
        
        token = auth_header.split(' ')[1]
        res = supabase.table("user_tokens").select("user_id").eq("token", token).execute()
        if not res.data:
            return jsonify({'success': False, 'error': 'Не авторизован'}), 401
        
        user_id = res.data[0]['user_id']
        user_res = supabase.table("users").select("telegram_id").eq("id", user_id).execute()
        
        if user_res.data and user_res.data[0].get('telegram_id'):
            send_telegram_to_user(user_res.data[0]['telegram_id'], "✅ Связь с ботом работает! Если вы видите это сообщение, всё настроено правильно.")
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Telegram не привязан'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/update-status', methods=['POST'])
def update_status_api():
    data = request.get_json()
    order_id = data.get('order_id')
    status = data.get('status')
    if not order_id or not status:
        return jsonify({"success": False, "error": "Missing fields"}), 400
    
    update_order_status(order_id, status)
    
    # Уведомление админу
    send_telegram_message(f"🔄 Статус заказа {order_id} изменён на {status}")
    
    # Получаем информацию для уведомления покупателя
    order_res = supabase.table("orders").select("customer_name, user_id").eq("order_id", order_id).execute()
    if order_res.data:
        user_res = supabase.table("users").select("telegram_id").eq("id", order_res.data[0].get('user_id')).execute()
        if user_res.data and user_res.data[0].get('telegram_id'):
            status_text = {
                'pending': '⏳ Ожидает оплаты',
                'paid': '✅ Оплачен',
                'shipped': '📦 Отправлен',
                'completed': '🎉 Завершён'
            }.get(status, status)
            msg_user = f"""📦 <b>Статус заказа изменён</b>

Здравствуйте, {order_res.data[0].get('customer_name')}!

Статус вашего заказа №{order_id} изменён на: {status_text}

Спасибо, что выбрали нас!"""
            send_telegram_to_user(user_res.data[0]['telegram_id'], msg_user)
    
    return jsonify({"success": True})
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})
@app.route('/api/delete-order', methods=['POST'])
def delete_order():
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        if not order_id:
            return jsonify({'success': False, 'error': 'order_id required'}), 400
        supabase.table("orders").delete().eq("order_id", order_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/export-orders', methods=['GET'])
def export_orders():
    try:
        from openpyxl import Workbook
        orders = supabase.table("orders").select("*").execute()
        wb = Workbook()
        ws = wb.active
        ws.title = "Заказы"
        
        headers = ['№ заказа', 'Покупатель', 'Email', 'Телефон', 'Товары', 'Сумма (₽)', 'Статус', 'Дата создания']
        ws.append(headers)
        
        for order in orders.data:
            items = json.loads(order.get('items', '[]')) if order.get('items') else []
            items_text = ', '.join([f"{i.get('name')} ({i.get('size')}) x{i.get('quantity')}" for i in items])
            ws.append([
                order.get('order_id'),
                order.get('customer_name'),
                order.get('customer_email'),
                order.get('customer_phone'),
                items_text,
                order.get('total_amount'),
                order.get('status'),
                order.get('created_at')
            ])
        
        from io import BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name=f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

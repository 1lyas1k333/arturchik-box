import os
import uuid
import json
import hashlib
import secrets
from datetime import datetime
from flask import Flask, jsonify, request, session, redirect, url_for
from flask_cors import CORS
import requests
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'secret_key_for_session_12345'
CORS(app, origins=["https://1lyas1k333.github.io", "https://arturchik-box-2.onrender.com"], supports_credentials=True)

# === SUPABASE ===
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# === TELEGRAM ===
TELEGRAM_TOKEN = "8694164916:AAEYQey-DSovguWmgy-mZLG4nMVhSV4BunQ"
TELEGRAM_CHAT_ID = "1056646376"

# === PLATEGA ===
PLATEGA_SHOP_ID = "a8922d02-2beb-44a0-b24a-4b6e6caa33ef"
PLATEGA_API_KEY = "osj9xJrzJb9jeFXjUHBMucfuR8DXydxScLOGImdzGaiMXNLj8KuiBDsH3AUBZ1vlsckfPWD4jZhdw5HQzJPJdQJWTkitFDtBCAtL"
PLATEGA_API_URL = "https://app.platega.io/transaction/process"

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[TG] Ошибка: {e}")

def send_telegram_to_user(chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[TG_USER] Ошибка: {e}")

def create_platega_payment(amount, email, phone, name, order_id):
    try:
        headers = {
            "X-MerchantId": PLATEGA_SHOP_ID,
            "X-Secret": PLATEGA_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "paymentMethod": 2,
            "paymentDetails": {"amount": float(amount), "currency": "RUB"},
            "description": f"Футбольный бокс, заказ {order_id}",
            "return": "https://1lyas1k333.github.io/payment-success",
            "failedUrl": "https://1lyas1k333.github.io/payment-failed",
            "payload": order_id,
            "callback_url": "https://arturchik-box-2.onrender.com/platega-webhook"
        }
        response = requests.post(PLATEGA_API_URL, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get('redirect'):
                return {'success': True, 'payment_url': result['redirect'], 'payment_id': result.get('transactionId')}
        return {'success': False, 'error': f'HTTP {response.status_code}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# === API РОУТЫ ===
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
    token_data = f"{user['id']}:{datetime.now()}:{secrets.token_hex(8)}"
    token = hashlib.sha256(token_data.encode()).hexdigest()
    supabase.table("user_tokens").insert({
        "id": str(uuid.uuid4()), "user_id": user['id'], "token": token,
        "created_at": datetime.now().isoformat(),
        "expires_at": datetime.now().timestamp() + 30*24*3600
    }).execute()
    return jsonify({"success": True, "token": token, "user": {"id": user['id'], "name": user['name'], "email": user['email']}})

@app.route('/api/my-orders', methods=['GET'])
def get_my_orders():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"success": False, "error": "Не авторизован"}), 401
    token = auth_header.split(' ')[1]
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

@app.route('/api/update-status', methods=['POST'])
def update_status_api():
    data = request.get_json()
    order_id = data.get('order_id')
    status = data.get('status')
    supabase.table("orders").update({"status": status, "updated_at": datetime.now().isoformat()}).eq("order_id", order_id).execute()
    send_telegram_message(f"🔄 СТАТУС ЗАКАЗА ИЗМЕНЁН\n📦 Заказ: {order_id}\n📌 Новый статус: {status}")
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
    payment = create_platega_payment(amount, customer.get('email'), customer.get('phone'), customer.get('fullName'), order_id)
    if not payment['success']:
        return jsonify({"success": False, "error": payment.get('error')}), 500
    supabase.table("orders").update({"payment_id": payment.get('payment_id')}).eq("order_id", order_id).execute()
    return jsonify({"success": True, "order_id": order_id, "amount": amount, "payment_url": payment.get('payment_url')})

@app.route('/platega-webhook', methods=['POST', 'GET'])
def platega_webhook():
    if request.method == 'GET':
        return jsonify({'status': 'ok', 'message': 'Webhook is active'}), 200
    try:
        data = request.get_json()
        order_id = data.get('payload') or data.get('order_id')
        status = data.get('status')
        if status == 'CONFIRMED':
            supabase.table("orders").update({"status": "paid", "updated_at": datetime.now().isoformat()}).eq("order_id", order_id).execute()
            send_telegram_message(f"✅ ОПЛАЧЕН ЗАКАЗ\n📦 Заказ: {order_id}")
            # Уведомление покупателю
            res = supabase.table("orders").select("customer_name, user_id").eq("order_id", order_id).execute()
            if res.data:
                user_res = supabase.table("users").select("telegram_id").eq("id", res.data[0]['user_id']).execute()
                if user_res.data and user_res.data[0]['telegram_id']:
                    send_telegram_to_user(user_res.data[0]['telegram_id'], f"✅ Заказ {order_id} оплачен! Скоро отправим трек-номер.")
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))

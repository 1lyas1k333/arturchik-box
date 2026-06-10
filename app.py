import os
import uuid
import json
import hashlib
import secrets
import requests
from datetime import datetime
from flask import Flask, jsonify, request, session, redirect
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

# === PLATEGA ===
PLATEGA_SHOP_ID = "a8922d02-2beb-44a0-b24a-4b6e6caa33ef"
PLATEGA_API_KEY = "osj9xJrzJb9jeFXjUHBMucfuR8DXydxScLOGImdzGaiMXNLj8KuiBDsH3AUBZ1vlsckfPWD4jZhdw5HQzJPJdQJWTkitFDtBCAtL"
PLATEGA_API_URL = "https://app.platega.io/transaction/process"

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token(user_id):
    data = f"{user_id}:{datetime.now().isoformat()}:{secrets.token_hex(8)}"
    return hashlib.sha256(data.encode()).hexdigest()

def update_order_status(order_id, status):
    supabase.table("orders").update({"status": status, "updated_at": datetime.now().isoformat()}).eq("order_id", order_id).execute()
    print(f"[DB] Заказ {order_id} обновлён → {status}")

# === API ===
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

@app.route('/create-payment', methods=['POST'])
def create_payment():
    data = request.get_json()
    amount = data.get('amount', 3490)
    cart_items = data.get('items', [])
    customer = data.get('customer', {})
    user_id = data.get('user_id')
    
    order_id = f"ORDER_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    # Сохраняем заказ в Supabase
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
    
    # === ВЫЗОВ PLATEGA ===
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
        result = response.json()
        
        if response.status_code == 200 and result.get('redirect'):
            return jsonify({
                "success": True,
                "order_id": order_id,
                "amount": amount,
                "payment_url": result['redirect']
            })
        else:
            print(f"[PLATEGA] Ошибка: {result}")
            return jsonify({"success": False, "error": "Ошибка создания платежа в Platega"}), 500
            
    except Exception as e:
        print(f"[PLATEGA] Исключение: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/platega-webhook', methods=['POST', 'GET'])
def platega_webhook():
    if request.method == 'GET':
        return jsonify({"status": "ok", "message": "Webhook is active"}), 200
    data = request.get_json()
    print(f"[WEBHOOK] {data}")
    order_id = data.get('payload') or data.get('order_id')
    if order_id and data.get('status') == 'CONFIRMED':
        update_order_status(order_id, 'paid')
        send_telegram_message(f"✅ ОПЛАЧЕН ЗАКАЗ\n📦 {order_id}")
    return jsonify({"success": True}), 200

@app.route('/')
def home():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))

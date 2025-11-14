# main.py - Толық дамыған дауыс беру жүйесі
import os
import json
import uuid
import csv
import threading
import base64
from time import time
from functools import wraps
from io import StringIO, BytesIO

from flask import Flask, render_template, request, redirect, session, jsonify, abort, send_file
import telebot
from telebot import types

# ----------------- Config -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8271092808:AAGAwS8--dC7VphQzyUfKE8bxpEZEpIjDbY")
ADMIN_TELEGRAM_ID = (int("8408918708"), int("800458904"))
ADMIN_WEB_PASSWORD = os.environ.get("ADMIN_WEB_PASSWORD", "root123455")
FLASK_SECRET = os.environ.get("FLASK_SECRET", "change_this_secret")
PORT = int(os.environ.get("PORT", 8080))

# ----------------- Files -----------------
DATA_FILE = "data.json"
USERS_FILE = "users.json"

# ----------------- JSON helpers -----------------
def load_json(path, default):
    if not os.path.exists(path):
        save_json(path, default)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# ----------------- Initial data -----------------
data = load_json(DATA_FILE, {
    "polls": {},
    "meta": {"last_updated": time()}
})
users = load_json(USERS_FILE, {})

def touch_data():
    data["meta"]["last_updated"] = time()
    save_json(DATA_FILE, data)

def save_users():
    save_json(USERS_FILE, users)

# ----------------- Flask app -----------------
app = Flask(__name__, template_folder="templates")
app.secret_key = FLASK_SECRET

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return abort(403)
        return f(*args, **kwargs)
    return wrapped

@app.route("/")
def index():
    if os.path.exists("templates/index.html"):
        return render_template("index.html")
    
    polls = []
    for pid, p in data["polls"].items():
        candidates = []
        for cid, candidate in p["candidates"].items():
            name = candidate.get("name", "Unknown")
            avatar = candidate.get("avatar", "")
            votes_count = sum(1 for v in p["votes"].values() if v == cid)
            candidates.append({
                "id": cid, 
                "name": name, 
                "avatar": avatar,
                "votes": votes_count
            })
        polls.append({
            "id": pid,
            "title": p["title"],
            "candidates": candidates,
            "active": p.get("active", False),
            "created_at": p.get("created_at")
        })
    
    return render_template("index.html", polls=polls, users_count=len(users))

@app.route("/api/polls")
def api_polls():
    out = []
    for pid, p in data["polls"].items():
        candidates = []
        for cid, candidate in p["candidates"].items():
            votes_count = sum(1 for v in p["votes"].values() if v == cid)
            candidates.append({
                "id": cid, 
                "name": candidate.get("name", "Unknown"),
                "avatar": candidate.get("avatar", ""),
                "votes": votes_count
            })
        out.append({
            "id": pid,
            "title": p["title"],
            "candidates": candidates,
            "active": p.get("active", False),
            "created_at": p.get("created_at")
        })
    return jsonify({"polls": out, "last_updated": data["meta"]["last_updated"]})

@app.route("/admin/login", methods=["POST"])
def admin_login():
    if request.form.get("password") == ADMIN_WEB_PASSWORD:
        session["admin"] = True
    return redirect("/")

@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin", None)
    return redirect("/")

# ----------------- Telegram bot -----------------
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

def register_user_tele(msg_or_user):
    try:
        uid = str(msg_or_user.from_user.id) if hasattr(msg_or_user, "from_user") else str(msg_or_user.id)
    except:
        uid = str(msg_or_user.id)
    
    if uid not in users:
        first_name = ""
        username = ""
        if hasattr(msg_or_user, "from_user"):
            u = msg_or_user.from_user
            first_name = getattr(u, "first_name", "") or ""
            username = getattr(u, "username", "") or ""
        else:
            first_name = getattr(msg_or_user, "first_name", "") or ""
            username = getattr(msg_or_user, "username", "") or ""
        
        users[uid] = {"name": None, "username": username, "first_seen": time()}
        save_users()

# ==================== USER HANDLERS ====================
@bot.message_handler(commands=['start'])
def tg_start(msg):
    uid = str(msg.from_user.id)
    is_admin = (msg.from_user.id in ADMIN_TELEGRAM_ID)
    
    if uid not in users:
        users[uid] = {"name": None, "username": msg.from_user.username or "", "first_seen": time()}
        save_users()

    if is_admin:
        text = "👑 *Сәлем, Админ!*\n\nБұл — админ панелі. /help деп жазыңыз көмек және командалар үшін."
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Админ панелі ⚙️", callback_data="admin:create_panel"))
        bot.send_message(msg.chat.id, text, reply_markup=markup)
        return

    if not users[uid].get("name"):
        bot.send_message(msg.chat.id,
            "👋 *Сәлем!* Ботқа қош келдің.\n\n"
            "📝 Төменге атыңыз бен фамилияңызды толық және дұрыс енгізіңіз.",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, tg_save_name)
    else:
        bot.send_message(msg.chat.id, f"✅ Сәлем, *{users[uid]['name']}*! Дауыс беру үшін /vote деп жазыңыз.")

def tg_save_name(msg):
    uid = str(msg.from_user.id)
    name = (msg.text or "").strip()
    if not name:
        bot.send_message(msg.chat.id, "⚠️ Атыңыз бос болмауы тиіс. Қайталап көріңіз.")
        bot.register_next_step_handler(msg, tg_save_name)
        return
    users[uid]["name"] = name
    users[uid]["username"] = msg.from_user.username or ""
    save_users()
    bot.send_message(msg.chat.id, f"✅ Атыңыз сақталды: *{name}*.\nЕнді /vote деп жазыңыз.", parse_mode="Markdown")

@bot.message_handler(commands=['vote'])
def tg_vote(msg):
    uid = str(msg.from_user.id)
    if uid not in users or not users[uid].get("name"):
        bot.send_message(msg.chat.id, "⚠️ Алдымен /start арқылы атыңызды тіркеңіз.")
        return
    
    active_polls = [p for p in data["polls"].values() if p.get("active")]
    if not active_polls:
        bot.send_message(msg.chat.id, "⛔ Қазір белсенді дауыс берулер жоқ.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for p in active_polls:
        markup.add(types.InlineKeyboardButton(p["title"], callback_data=f"poll_{p['id']}"))
    bot.send_message(msg.chat.id, "🏷 Қай дауыс беруге қатысқыңыз келеді?", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("poll_"))
def cb_poll_select(call):
    pid = str(call.data.split("_", 1)[1])
    p = data["polls"].get(pid)
    if not p or not p.get("active"):
        bot.answer_callback_query(call.id, "Дауыс беру табылмады немесе белсенді емес.")
        return

    markup = types.InlineKeyboardMarkup()
    candidates_list = list(p["candidates"].items())
    
    for index, (cid, candidate) in enumerate(candidates_list):
        # Индекс арқылы іздеу (қысқа callback_data)
        callback_data = f"vote_{pid}_{index}"
        markup.add(types.InlineKeyboardButton(candidate.get("name", "Unknown"), callback_data=callback_data))

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"📊 *{p['title']}*\nКандидатты таңдаңыз:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("vote_"))
def cb_vote(call):
    try:
        parts = call.data.split("_")
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Қателік орын алды.")
            return
            
        pid = parts[1]
        candidate_index = int(parts[2])  # Индекс арқылы кандидатты табу
        
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id, "Қателік орын алды.")
        return

    uid = str(call.from_user.id)
    p = data["polls"].get(pid)
    if not p or not p.get("active"):
        bot.answer_callback_query(call.id, "Бұл дауыс беру белсенді емес.", show_alert=True)
        return

    # Индекс бойынша кандидатты табу
    candidates_list = list(p["candidates"].items())
    if candidate_index < 0 or candidate_index >= len(candidates_list):
        bot.answer_callback_query(call.id, "Кандидат табылмады.", show_alert=True)
        return
        
    cid, candidate = candidates_list[candidate_index]

    if uid in p["votes"]:
        bot.answer_callback_query(call.id, "Сіз бұл дауыс беруге қатысып қойсыз.", show_alert=True)
        return

    p["votes"][uid] = cid
    touch_data()
    bot.answer_callback_query(call.id, "✅ Дауысыңыз қабылданды!")
    
    candidate_name = candidate.get("name", "Unknown")
    bot.send_message(call.from_user.id, f"🗳 Сіздің таңдауыңыз: *{candidate_name}*", parse_mode="Markdown")

    # Админге хабарлау
    try:
        u = users.get(uid, {})
        uname = f"@{u.get('username')}" if u.get('username') else "—"
        text = (
            f"🆕 *Жаңа дауыс*\n\n"
            f"👤 Аты: {u.get('name','—')}\n"
            f"🆔 `{uid}`\n"
            f"💬 {uname}\n"
            f"🗳 Дауыс беру: *{p['title']}*\n"
            f"✅ Таңдаған: *{candidate_name}*"
        )
        bot.send_message(ADMIN_TELEGRAM_ID, text, parse_mode="Markdown")
    except Exception:
        pass

# ==================== ADMIN PANEL ====================
def build_admin_panel_markup():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🆕 Жаңа дауыс беру", callback_data="admin:createpoll"),
        types.InlineKeyboardButton("📋 Барлық дауыс берулер", callback_data="admin:listpolls"),
    )
    kb.add(
        types.InlineKeyboardButton("👥 Қолданушылар", callback_data="admin:users"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin:stats"),
    )
    kb.add(
        types.InlineKeyboardButton("📤 Экспорт", callback_data="admin:export"),
        types.InlineKeyboardButton("🗑 Тазалау", callback_data="admin:clear"),
    )
    kb.add(types.InlineKeyboardButton("📢 Жіберу", callback_data="admin:broadcast"))
    return kb

@bot.callback_query_handler(func=lambda cq: cq.data and cq.data.startswith("admin:"))
def handle_admin_cb(cq: types.CallbackQuery):
    if cq.from_user.id not in ADMIN_TELEGRAM_ID:
        bot.answer_callback_query(cq.id, "Рұқсат жоқ.")
        return
        
    action = cq.data.split(":", 1)[1]
    
    if action == "create_panel":
        kb = build_admin_panel_markup()
        bot.send_message(cq.message.chat.id, "⚙️ *Админ панелі*", parse_mode="Markdown", reply_markup=kb)
        bot.answer_callback_query(cq.id, "")
        
    elif action == "createpoll":
        bot.answer_callback_query(cq.id, "Жаңа дауыс беру атауын жіберіңіз")
        msg = bot.send_message(cq.message.chat.id, "📝 Дауыс беру атауын енгізіңіз:")
        bot.register_next_step_handler(msg, admin_createpoll_step)
        
    elif action == "listpolls":
        send_admin_listpolls(cq.message.chat.id)
        bot.answer_callback_query(cq.id, "")
        
    elif action == "users":
        show_users_list(cq.message.chat.id)
        bot.answer_callback_query(cq.id, "")
        
    elif action == "stats":
        show_stats(cq.message.chat.id)
        bot.answer_callback_query(cq.id, "")
        
    elif action == "export":
        export_to_csv(cq.message.chat.id)
        bot.answer_callback_query(cq.id, "Экспорт жасалып жатыр...")
        
    elif action == "clear":
        clear_all_data(cq.message.chat.id)
        bot.answer_callback_query(cq.id, "Деректер тазаланып жатыр...")
        
    elif action == "broadcast":
        bot.answer_callback_query(cq.id, "Жіберілетін хабарды енгізіңіз")
        msg = bot.send_message(cq.message.chat.id, "📢 Хабарлама мәтінін енгізіңіз:")
        bot.register_next_step_handler(msg, admin_broadcast_step)

def send_admin_listpolls(chat_id):
    if not data["polls"]:
        bot.send_message(chat_id, "📭 Дауыс берулер әлі жоқ")
        return
        
    text = "📋 *Барлық дауыс берулер:*\n\n"
    for pid, p in data["polls"].items():
        status = "🟢 Ашық" if p.get("active") else "🔴 Жабық"
        candidates_count = len(p["candidates"])
        votes_count = len(p["votes"])
        text += f"• *{p['title']}* - {status}\n  Кандидаттар: {candidates_count}, Дауыстар: {votes_count}\n  ID: `{pid}`\n\n"
    
    bot.send_message(chat_id, text, parse_mode="Markdown")
    
    # Тек бір хабар ретінде барлық басқару кнопкаларын жіберу
    kb = types.InlineKeyboardMarkup(row_width=2)
    for pid, p in data["polls"].items():
        kb.add(types.InlineKeyboardButton(f"⚙️ {p['title']}", callback_data=f"pollmgmt:view:{pid}"))
    
    if kb.keyboard:  # Егер кнопкалар болса ғана жіберу
        bot.send_message(chat_id, "🔧 Дауыс беруді басқару үшін төмендегі батырмаларды пайдаланыңыз:", reply_markup=kb)

def send_poll_management_panel(chat_id, pid, p):
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    # Негізгі операциялар
    if p.get("active"):
        kb.add(types.InlineKeyboardButton("🔴 Жабу", callback_data=f"pollmgmt:close:{pid}"))
    else:
        kb.add(types.InlineKeyboardButton("🟢 Ашу", callback_data=f"pollmgmt:open:{pid}"))
        
    kb.add(
        types.InlineKeyboardButton("👥 Кандидаттар", callback_data=f"pollmgmt:candidates:{pid}"),
        types.InlineKeyboardButton("📊 Статистика", callback_data=f"pollmgmt:stats:{pid}")
    )
    
    # Кандидат қосу опциялары
    kb.add(
        types.InlineKeyboardButton("➕ Кандидат қосу", callback_data=f"pollmgmt:add_candidate:{pid}"),
        types.InlineKeyboardButton("🖼 Фото қосу", callback_data=f"pollmgmt:add_avatar:{pid}")
    )
    
    # Қосымша операциялар
    kb.add(
        types.InlineKeyboardButton("🔄 Қайта бастау", callback_data=f"pollmgmt:reset:{pid}"),
        types.InlineKeyboardButton("🗑 Жою", callback_data=f"pollmgmt:delete:{pid}")
    )
    
    # Артқа бату кнопкасы
    kb.add(types.InlineKeyboardButton("⬅️ Тізімге оралу", callback_data="admin:listpolls"))
    
    status = "🟢 АШЫҚ" if p.get("active") else "🔴 ЖАБЫҚ"
    candidates_count = len(p["candidates"])
    votes_count = len(p["votes"])
    
    text = f"""
📊 *{p['title']}*

📊 Статус: {status}
👥 Кандидаттар: {candidates_count}
🗳 Дауыстар: {votes_count}
🆔 ID: `{pid}`
    """
    
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

# ==================== POLL MANAGEMENT ====================
@bot.callback_query_handler(func=lambda cq: cq.data and cq.data.startswith("pollmgmt:view:"))
def handle_poll_view(cq: types.CallbackQuery):
    if cq.from_user.id not in ADMIN_TELEGRAM_ID:
        bot.answer_callback_query(cq.id, "Рұқсат жоқ.")
        return
        
    pid = cq.data.split(":")[2]
    p = data["polls"].get(pid)
    if not p:
        bot.answer_callback_query(cq.id, "Дауыс беру табылмады.")
        return
        
    send_poll_management_panel(cq.message.chat.id, pid, p)
    bot.answer_callback_query(cq.id, "")
    
@bot.callback_query_handler(func=lambda cq: cq.data and cq.data.startswith("pollmgmt:"))
def handle_poll_management(cq: types.CallbackQuery):
    if cq.from_user.id not in ADMIN_TELEGRAM_ID:
        bot.answer_callback_query(cq.id, "Рұқсат жоқ.")
        return
        
    parts = cq.data.split(":")
    action = parts[1]
    pid = parts[2]
    p = data["polls"].get(pid)
    
    if not p:
        bot.answer_callback_query(cq.id, "Дауыс беру табылмады.")
        return
        
    if action == "open":
        p["active"] = True
        touch_data()
        bot.answer_callback_query(cq.id, "✅ Дауыс беру ашылды!")
        update_poll_message(cq.message.chat.id, cq.message.message_id, pid, p)
        
    elif action == "close":
        p["active"] = False
        touch_data()
        bot.answer_callback_query(cq.id, "✅ Дауыс беру жабылды!")
        update_poll_message(cq.message.chat.id, cq.message.message_id, pid, p)
        
    elif action == "candidates":
        show_candidates_management(cq.message.chat.id, pid, p)
        bot.answer_callback_query(cq.id, "")
        
    elif action == "stats":
        show_poll_stats(cq.message.chat.id, pid, p)
        bot.answer_callback_query(cq.id, "")
        
    elif action == "add_candidate":
        bot.answer_callback_query(cq.id, "Кандидат атын енгізіңіз")
        msg = bot.send_message(cq.message.chat.id, "👤 Кандидаттың аты-жөнін енгізіңіз:")
        bot.register_next_step_handler(msg, lambda m: add_candidate_name(m, pid))
        
    elif action == "add_avatar":
        bot.answer_callback_query(cq.id, "Аватар қосу үшін кандидатты таңдаңыз")
        show_candidate_selection_for_avatar(cq.message.chat.id, pid, p)
        
    elif action == "reset":
        p["votes"] = {}
        touch_data()
        bot.answer_callback_query(cq.id, "✅ Дауыс беру қайта басталды!")
        update_poll_message(cq.message.chat.id, cq.message.message_id, pid, p)
        
    elif action == "delete":
        del data["polls"][pid]
        touch_data()
        bot.answer_callback_query(cq.id, "✅ Дауыс беру жойылды!")
        try:
            bot.delete_message(cq.message.chat.id, cq.message.message_id)
        except:
            pass

def update_poll_message(chat_id, message_id, pid, p):
    try:
        kb = types.InlineKeyboardMarkup(row_width=2)
        if p.get("active"):
            kb.add(types.InlineKeyboardButton("🔴 Жабу", callback_data=f"pollmgmt:close:{pid}"))
        else:
            kb.add(types.InlineKeyboardButton("🟢 Ашу", callback_data=f"pollmgmt:open:{pid}"))
            
        kb.add(
            types.InlineKeyboardButton("👥 Кандидаттар", callback_data=f"pollmgmt:candidates:{pid}"),
            types.InlineKeyboardButton("📊 Статистика", callback_data=f"pollmgmt:stats:{pid}")
        )
        
        kb.add(
            types.InlineKeyboardButton("➕ Кандидат қосу", callback_data=f"pollmgmt:add_candidate:{pid}"),
            types.InlineKeyboardButton("🖼 Фото қосу", callback_data=f"pollmgmt:add_avatar:{pid}")
        )
        
        kb.add(
            types.InlineKeyboardButton("🔄 Қайта бастау", callback_data=f"pollmgmt:reset:{pid}"),
            types.InlineKeyboardButton("🗑 Жою", callback_data=f"pollmgmt:delete:{pid}")
        )
        
        status = "🟢 АШЫҚ" if p.get("active") else "🔴 ЖАБЫҚ"
        text = f"📊 *{p['title']}*\n\n📊 Статус: {status}\n👥 Кандидаттар: {len(p['candidates'])}\n🗳 Дауыстар: {len(p['votes'])}"
        
        bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        print(f"Хабарды жаңарту қатесі: {e}")

# ==================== CANDIDATE MANAGEMENT ====================







def show_candidates_management(chat_id, pid, p):
    if not p["candidates"]:
        bot.send_message(chat_id, "📭 Бұл дауыс беруде кандидаттар жоқ")
        return
        
    text = f"👥 *{p['title']}* - Кандидаттар:\n\n"
    for cid, candidate in p["candidates"].items():
        votes_count = sum(1 for v in p["votes"].values() if v == cid)
        avatar_status = "🖼" if candidate.get("avatar") else "📝"
        text += f"{avatar_status} *{candidate.get('name', 'Unknown')}* - {votes_count} дауыс\n"
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Кандидат қосу", callback_data=f"pollmgmt:add_candidate:{pid}"),
        types.InlineKeyboardButton("🖼 Фото қосу", callback_data=f"pollmgmt:add_avatar:{pid}")
    )
    
    for cid, candidate in p["candidates"].items():
        candidate_name = candidate.get('name', 'Unknown')
        if len(candidate_name) > 15:
            display_name = candidate_name[:15] + "..."
        else:
            display_name = candidate_name
            
        kb.add(types.InlineKeyboardButton(f"🗑 {display_name}", callback_data=f"cand_del:{cid}"))
    
    kb.add(types.InlineKeyboardButton("⬅️ Артқа", callback_data=f"pollmgmt:back:{pid}"))
    
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

def add_candidate_name(message: types.Message, pid: str):
    if message.from_user.id not in ADMIN_TELEGRAM_ID:
        return
        
    candidate_name = (message.text or "").strip()
    if not candidate_name:
        bot.reply_to(message, "❌ Кандидат аты бос болмауы керек")
        return
        
    p = data["polls"].get(pid)
    if not p:
        bot.reply_to(message, "❌ Дауыс беру табылмады")
        return
        
    cid = str(uuid.uuid4())
    p["candidates"][cid] = {"name": candidate_name, "avatar": ""}
    touch_data()
    
    bot.reply_to(message, f"✅ Кандидат '{candidate_name}' қосылды!")
    show_candidates_management(message.chat.id, pid, p)

def show_candidate_selection_for_avatar(chat_id, pid, p):
    if not p["candidates"]:
        bot.send_message(chat_id, "❌ Алдымен кандидат қосу керек")
        return
        
    kb = types.InlineKeyboardMarkup(row_width=2)
    for cid, candidate in p["candidates"].items():
        candidate_name = candidate.get("name", "Unknown")
        if len(candidate_name) > 15:
            display_name = candidate_name[:15] + "..."
        else:
            display_name = candidate_name
            
        kb.add(types.InlineKeyboardButton(display_name, callback_data=f"ava_sel:{cid}"))
    
    kb.add(types.InlineKeyboardButton("⬅️ Артқа", callback_data=f"pollmgmt:back:{pid}"))
    
    bot.send_message(chat_id, "🖼 Кандидатты таңдаңыз:", reply_markup=kb)

# ==================== ТҮЗЕТІЛГЕН CALLBACK HANDLERS ====================

# Кандидатты өшіру үшін
@bot.callback_query_handler(func=lambda cq: cq.data and cq.data.startswith("cand_del:"))
def handle_candidate_delete(cq: types.CallbackQuery):
    if cq.from_user.id not in ADMIN_TELEGRAM_ID:
        bot.answer_callback_query(cq.id, "Рұқсат жоқ.")
        return
        
    cid = cq.data.split(":")[1]
    
    # Poll ID мен кандидатты іздеу
    target_pid = None
    target_p = None
    for pid, p in data["polls"].items():
        if cid in p["candidates"]:
            target_pid = pid
            target_p = p
            break
    
    if not target_p or cid not in target_p["candidates"]:
        bot.answer_callback_query(cq.id, "Кандидат табылмады.")
        return
        
    candidate_name = target_p["candidates"][cid].get("name", "Unknown")
    # Кандидатты жою
    del target_p["candidates"][cid]
    # Дауыстарды жою
    target_p["votes"] = {uid: vote_cid for uid, vote_cid in target_p["votes"].items() if vote_cid != cid}
    touch_data()
    
    bot.answer_callback_query(cq.id, f"✅ {candidate_name} жойылды!")
    show_candidates_management(cq.message.chat.id, target_pid, target_p)

# Аватар таңдау үшін
@bot.callback_query_handler(func=lambda cq: cq.data and cq.data.startswith("ava_sel:"))
def handle_avatar_selection(cq: types.CallbackQuery):
    if cq.from_user.id not in ADMIN_TELEGRAM_ID:
        bot.answer_callback_query(cq.id, "Рұқсат жоқ.")
        return
        
    cid = cq.data.split(":")[1]
    
    # Poll ID мен кандидатты іздеу
    target_pid = None
    target_p = None
    for pid, p in data["polls"].items():
        if cid in p["candidates"]:
            target_pid = pid
            target_p = p
            break
    
    if not target_p or cid not in target_p["candidates"]:
        bot.answer_callback_query(cq.id, "Кандидат табылмады.")
        return
        
    candidate_name = target_p["candidates"][cid].get("name", "Unknown")
    bot.answer_callback_query(cq.id, f"{candidate_name} үшін фото жіберіңіз")
    
    msg = bot.send_message(cq.message.chat.id, 
        f"🖼 *{candidate_name}* үшін фото жіберіңіз\n\n"
        "📎 Суретті жіберу үшін:",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, lambda m: process_avatar_photo(m, target_pid, cid))

def process_avatar_photo(message: types.Message, pid: str, cid: str):
    if message.from_user.id not in ADMIN_TELEGRAM_ID:
        return
        
    p = data["polls"].get(pid)
    if not p or cid not in p["candidates"]:
        bot.reply_to(message, "❌ Кандидат табылмады")
        return
        
    if message.photo:
        # Ең үлкен фотоны алу
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Фотодан base64 жасау
        avatar_base64 = base64.b64encode(downloaded_file).decode('utf-8')
        p["candidates"][cid]["avatar"] = f"data:image/jpeg;base64,{avatar_base64}"
        touch_data()
        
        candidate_name = p["candidates"][cid].get("name", "Unknown")
        bot.reply_to(message, f"✅ {candidate_name} үшін аватар сәтті сақталды!")
        show_candidates_management(message.chat.id, pid, p)
    else:
        bot.reply_to(message, "❌ Сурет жіберіңіз!")

@bot.callback_query_handler(func=lambda cq: cq.data and cq.data.startswith("pollmgmt:back:"))
def handle_back_to_poll(cq: types.CallbackQuery):
    if cq.from_user.id not in ADMIN_TELEGRAM_ID:
        bot.answer_callback_query(cq.id, "Рұқсат жоқ.")
        return
        
    pid = cq.data.split(":")[2]
    p = data["polls"].get(pid)
    if not p:
        bot.answer_callback_query(cq.id, "Дауыс беру табылмады.")
        return
        
    try:
        bot.delete_message(cq.message.chat.id, cq.message.message_id)
    except:
        pass
    send_poll_management_panel(cq.message.chat.id, pid, p)

# ==================== STATISTICS & UTILITIES ====================
def show_poll_stats(chat_id, pid, p):
    text = f"📊 *{p['title']}* - Статистика\n\n"
    total_votes = len(p["votes"])
    
    if not p["candidates"]:
        text += "📭 Кандидаттар жоқ\n"
    else:
        for cid, candidate in p["candidates"].items():
            votes_count = sum(1 for v in p["votes"].values() if v == cid)
            percentage = (votes_count / total_votes * 100) if total_votes > 0 else 0
            text += f"• *{candidate.get('name', 'Unknown')}* - {votes_count} дауыс ({percentage:.1f}%)\n"
    
    text += f"\n🗳 Жалпы дауыс: {total_votes}"  # БҰЛ ЖЕРДЕ ҚАТЕ БОЛМАЙДЫ
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⬅️ Артқа", callback_data=f"pollmgmt:back:{pid}"))
    
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)

def show_users_list(chat_id):
    if not users:
        bot.send_message(chat_id, "📭 Қолданушылар жоқ")
        return
        
    text = f"👥 *Тіркелген қолданушылар* - {len(users)} адам\n\n"
    for i, (uid, user) in enumerate(list(users.items())[:50], 1):
        name = user.get('name', '—')
        username = f"@{user.get('username', '—')}" if user.get('username') else "—"
        text += f"{i}. {name} - {username}\n"
    
    if len(users) > 50:
        text += f"\n... және тағы {len(users) - 50} қолданушы"
    
    bot.send_message(chat_id, text, parse_mode="Markdown")

def show_stats(chat_id):
    polls_count = len(data["polls"])
    active_polls = sum(1 for p in data["polls"].values() if p.get("active"))
    total_votes = sum(len(p["votes"]) for p in data["polls"].values())
    total_candidates = sum(len(p["candidates"]) for p in data["polls"].values())
    
    text = f"""
📈 *Жүйе статистикасы*

📊 Дауыс берулер: {polls_count}
🟢 Белсенді: {active_polls}
🔴 Белсенді емес: {polls_count - active_polls}

👥 Қолданушылар: {len(users)}
🗳 Жалпы дауыс: {total_votes}
🎭 Жалпы кандидат: {total_candidates}
    """
    
    bot.send_message(chat_id, text, parse_mode="Markdown")

def export_to_csv(chat_id):
    try:
        si = StringIO()
        writer = csv.writer(si)
        writer.writerow(["Дауыс беру ID", "Дауыс беру атауы", "Кандидат ID", "Кандидат аты", "Қолданушы ID", "Қолданушы аты", "Қолданушы логині"])
        
        for pid, p in data["polls"].items():
            for uid, cid in p["votes"].items():
                u = users.get(uid, {})
                candidate_name = p["candidates"].get(cid, {}).get("name", "Unknown")
                writer.writerow([
                    pid, p["title"], cid, candidate_name,
                    uid, u.get("name", ""), u.get("username", "")
                ])
        
        si.seek(0)
        csv_data = si.getvalue().encode('utf-8')
        
        bot.send_document(chat_id, ("дауыс_беру_деректері.csv", csv_data))
    except Exception as e:
        bot.send_message(chat_id, f"❌ Экспорт қатесі: {str(e)}")

def clear_all_data(chat_id):
    data["polls"] = {}
    touch_data()
    bot.send_message(chat_id, "✅ Барлық дауыс берулер тазаланды!")

def admin_createpoll_step(message: types.Message):
    if message.from_user.id not in ADMIN_TELEGRAM_ID:
        return
        
    title = (message.text or "").strip()
    if not title:
        bot.reply_to(message, "❌ Атауы бос болмауы керек")
        return
        
    pid = str(uuid.uuid4())
    data["polls"][pid] = {
        "id": pid,
        "title": title,
        "candidates": {},
        "votes": {},
        "active": False,
        "created_at": time()
    }
    touch_data()
    
    bot.reply_to(message, f"✅ Дауыс беру '{title}' құрылды!")
    send_admin_listpolls(message.chat.id)

def admin_broadcast_step(message: types.Message):
    if message.from_user.id not in ADMIN_TELEGRAM_ID:
        return
        
    text = (message.text or "").strip()
    if not text:
        bot.reply_to(message, "❌ Хабарлама бос болмауы керек")
        return
        
    success = 0
    failed = 0
    
    for uid in list(users.keys()):
        try:
            bot.send_message(int(uid), f"📢 *Жүйе хабарламасы:*\n\n{text}", parse_mode="Markdown")
            success += 1
        except Exception:
            failed += 1
    
    bot.reply_to(message, f"📤 Жіберу нәтижесі:\n✅ Сәтті: {success}\n❌ Сәтсіз: {failed}")

# ==================== ADDITIONAL ADMIN COMMANDS ====================
@bot.message_handler(commands=['help'])
def tg_help(msg):
    if msg.from_user.id in ADMIN_TELEGRAM_ID:
        text = """
👑 *Админ командалары*

/start - Ботты бастау
/help - Көмек алу
/vote - Дауыс беру

📊 *Админ панеліне кіру үшін:*
"Админ панелі ⚙️" батырмасын басыңыз
        """
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Админ панелі ⚙️", callback_data="admin:create_panel"))
        bot.send_message(msg.chat.id, text, parse_mode="Markdown", reply_markup=markup)
    else:
        text = """
ℹ️ *Қолданушы командалары*

/start - Тіркелу
/vote - Дауыс беру
/setname - Атыңызды өзгерту
        """
        bot.send_message(msg.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['setname'])
def tg_setname(msg):
    uid = str(msg.from_user.id)
    if uid not in users:
        bot.send_message(msg.chat.id, "Алдымен /start жазыңыз")
        return
    bot.send_message(msg.chat.id, "📝 Жаңа атыңызды енгізіңіз:")
    bot.register_next_step_handler(msg, tg_save_name)

# ==================== FLASK ROUTES FOR AVATARS ====================
@app.route('/candidate_avatar/<poll_id>/<candidate_id>')
def get_candidate_avatar(poll_id, candidate_id):
    p = data["polls"].get(poll_id)
    if not p or candidate_id not in p["candidates"]:
        return abort(404)
        
    avatar_data = p["candidates"][candidate_id].get("avatar", "")
    if not avatar_data or not avatar_data.startswith("data:image"):
        return abort(404)
        
    # Base64 деректерді бөлу
    header, base64_str = avatar_data.split(",", 1)
    image_data = base64.b64decode(base64_str)
    
    return send_file(
        BytesIO(image_data),
        mimetype="image/jpeg",
        as_attachment=False
    )

# ==================== START SERVER ====================
def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False)

if __name__ == "__main__":
    # Ensure files exist
    save_json(DATA_FILE, data)
    save_json(USERS_FILE, users)
    
    print("🚀 Дауыс беру жүйесі іске қосылуда...")
    print(f"🤖 Бот: @{bot.get_me().username}")
    print(f"👑 Админ ID: {ADMIN_TELEGRAM_ID}")
    print(f"🌐 Веб-панель: http://localhost:{PORT}")
    
    # Start Flask in background
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    
    # Start bot polling
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        print("❌ Бот тоқтатылды")
    except Exception as e:
        print(f"❌ Қате: {e}")
import os
import random
import logging
import psycopg2
import asyncio
import nest_asyncio
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from threading import Thread

# === 环境准备 ===
load_dotenv()
nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
GAME_BASE_URL = "https://你的域名/dice_game"  # ← 替换为你 Render 的实际域名

# === Flask 应用 ===
app = Flask(__name__)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with get_conn() as conn, conn.cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                phone TEXT,
                points INTEGER DEFAULT 0,
                plays INTEGER DEFAULT 0,
                created_at TEXT,
                last_play TEXT,
                invited_by BIGINT,
                is_blocked INTEGER DEFAULT 0
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS game_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                user_score INTEGER,
                bot_score INTEGER,
                result TEXT,
                points_change INTEGER
            );
        """)
        conn.commit()

# === Telegram Bot 功能 ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    try:
        with get_conn() as conn, conn.cursor() as c:
            c.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
            if c.fetchone() is None:
                c.execute("""
                    INSERT INTO users (user_id, first_name, last_name, username, created_at, is_blocked)
                    VALUES (%s, %s, %s, %s, %s, 0)
                """, (
                    user_id,
                    user.first_name,
                    user.last_name,
                    user.username,
                    datetime.now().isoformat()
                ))
                conn.commit()

        # 请求共享手机号
        btn = KeyboardButton("📱 授权手机号", request_contact=True)
        keyboard = ReplyKeyboardMarkup([[btn]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("请点击下方按钮授权手机号：", reply_markup=keyboard)

    except Exception as e:
        logging.exception(e)
        await update.message.reply_text("❌ 系统错误，请稍后重试")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        return
    user_id = contact.user_id
    phone = contact.phone_number
    try:
        with get_conn() as conn, conn.cursor() as c:
            c.execute("UPDATE users SET phone = %s WHERE user_id = %s", (phone, user_id))
            conn.commit()

        link = f"{GAME_BASE_URL}?user_id={user_id}"
        await update.message.reply_text(f"✅ 授权成功！点击开始游戏：\n{link}")
    except Exception as e:
        logging.exception(e)
        await update.message.reply_text("❌ 授权失败，请稍后重试")

def run_bot():
    app_telegram = ApplicationBuilder().token(BOT_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    asyncio.run(app_telegram.run_polling())

# === Flask 路由 ===

@app.route("/")
def index():
    with get_conn() as conn, conn.cursor() as c:
        c.execute("SELECT user_id FROM users WHERE phone IS NOT NULL AND is_blocked = 0 ORDER BY created_at ASC LIMIT 1")
        row = c.fetchone()
        if not row:
            return "❌ 没有可用用户，请先注册并授权手机号", 400
        return f'<meta http-equiv="refresh" content="0; url=/dice_game?user_id={row[0]}">'

@app.route("/dice_game")
def dice_game():
    return render_template("dice_game.html")

@app.route("/api/play_game")
def api_play_game():
    try:
        user_id = request.args.get("user_id", type=int)
        if not user_id:
            return jsonify({"error": "缺少 user_id 参数"}), 400

        with get_conn() as conn, conn.cursor() as c:
            c.execute("SELECT is_blocked, plays, phone FROM users WHERE user_id = %s", (user_id,))
            row = c.fetchone()
            if not row:
                return jsonify({"error": "用户不存在"})
            is_blocked, plays, phone = row
            if is_blocked:
                return jsonify({"error": "你已被封禁"})
            if not phone:
                return jsonify({"error": "请先授权手机号"})
            if plays >= 10:
                return jsonify({"error": "今日游戏次数已满"})

            user_score = random.randint(1, 6)
            bot_score = random.randint(1, 6)
            score = 10 if user_score > bot_score else -5 if user_score < bot_score else 0
            result = "赢" if score > 0 else "输" if score < 0 else "平局"
            now = datetime.now()

            c.execute("UPDATE users SET points = points + %s, plays = plays + 1, last_play = %s WHERE user_id = %s",
                      (score, now, user_id))
            c.execute("INSERT INTO game_history (user_id, created_at, user_score, bot_score, result, points_change) "
                      "VALUES (%s, %s, %s, %s, %s, %s)",
                      (user_id, now, user_score, bot_score, result, score))
            c.execute("SELECT points FROM users WHERE user_id = %s", (user_id,))
            total_points = c.fetchone()[0]
            conn.commit()

        return jsonify({
            "user_score": user_score,
            "bot_score": bot_score,
            "message": f"你{result}了！{'+' if score > 0 else ''}{score}分",
            "total_points": total_points
        })
    except Exception as e:
        import traceback
        return jsonify({"error": "服务器错误", "trace": traceback.format_exc()}), 500

# === 启动 ===

if __name__ == "__main__":
    init_db()
    Thread(target=run_bot).start()
    app.run(debug=True)

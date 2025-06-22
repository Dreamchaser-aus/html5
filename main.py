import os
import logging
import psycopg2
import asyncio
import nest_asyncio
from datetime import datetime
from flask import Flask, request, jsonify, session, redirect, url_for
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()
nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or "supersecretkey"

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# 初始化数据库表
def init_db():
    with get_conn() as conn, conn.cursor() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                phone TEXT,
                points INTEGER DEFAULT 0,
                plays INTEGER DEFAULT 0,
                created_at TIMESTAMP,
                last_play TIMESTAMP
            );
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS game_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                user_score INTEGER,
                bot_score INTEGER,
                result TEXT,
                points_change INTEGER
            );
        ''')
        conn.commit()

# Telegram /start 指令，保存用户并发送带token的网页链接
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with get_conn() as conn, conn.cursor() as c:
        c.execute("SELECT 1 FROM users WHERE user_id = %s", (user.id,))
        if not c.fetchone():
            now = datetime.now()
            c.execute("""
                INSERT INTO users (user_id, first_name, last_name, username, points, plays, created_at)
                VALUES (%s, %s, %s, %s, 0, 0, %s)
            """, (user.id, user.first_name, user.last_name, user.username, now))
            conn.commit()

    # 生成简单token，这里用用户ID字符串（安全可改）
    token = str(user.id)

    game_url = f"{get_base_url(request)} /game?token={token}"

    keyboard = ReplyKeyboardMarkup([[KeyboardButton("开始玩网页游戏", url=game_url)]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(f"欢迎 {user.first_name}！点击下方按钮打开网页游戏：", reply_markup=keyboard)

def get_base_url(req):
    # 取当前请求根域名，方便生成完整链接
    scheme = req.scheme
    host = req.host
    return f"{scheme}://{host}"

# 网页登录页，利用token写入session，跳转真正游戏页
@app.route("/game")
def game_login():
    token = request.args.get("token", "")
    if not token:
        return "缺少token参数，请从Telegram机器人启动游戏。", 400

    # 简单验证token是否是数字，即用户ID
    if not token.isdigit():
        return "非法token", 403

    # 写入session
    session['user_id'] = int(token)

    # 重定向到真正游戏页面
    return redirect(url_for("game_page"))

# 游戏页面（真实界面）
@app.route("/game_page")
def game_page():
    # 检查登录
    if 'user_id' not in session:
        return "未登录，请从Telegram机器人点击链接登录。", 403

    return '''
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>掷骰子小游戏</title>
<style>
  body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
  #dice-container { margin: 20px; font-size: 60px; }
  #result { font-size: 24px; margin-top: 20px; }
  button { font-size: 20px; padding: 10px 20px; cursor: pointer; }
  #points { margin-top: 20px; font-weight: bold; }
</style>
</head>
<body>

<h1>掷骰子小游戏</h1>

<div id="dice-container">
  <span id="user-dice">🎲</span> vs <span id="bot-dice">🎲</span>
</div>

<button id="roll-btn">开始掷骰</button>

<div id="result"></div>
<div id="points"></div>

<script>
const userDiceElem = document.getElementById('user-dice');
const botDiceElem = document.getElementById('bot-dice');
const resultElem = document.getElementById('result');
const pointsElem = document.getElementById('points');
const rollBtn = document.getElementById('roll-btn');

let userPoints = 0;
let playCount = 0;
const maxPlaysPerDay = 10;

function getRandomDice() {
  return Math.floor(Math.random() * 6) + 1;
}

function diceEmoji(num) {
  const diceEmojis = ['⚀','⚁','⚂','⚃','⚄','⚅'];
  return diceEmojis[num - 1];
}

async function loadUserData() {
  try {
    const res = await fetch('/api/user_stats');
    if (res.ok) {
      const data = await res.json();
      userPoints = data.points || 0;
      playCount = data.play_count || 0;
      pointsElem.textContent = `当前积分：${userPoints}，已玩次数：${playCount} / ${maxPlaysPerDay}`;
    }
  } catch (e) {
    console.error('加载用户数据失败', e);
  }
}

rollBtn.onclick = async function() {
  if (playCount >= maxPlaysPerDay) {
    alert("今天已玩满10次，请明天再来！");
    return;
  }

  rollBtn.disabled = true;
  resultElem.textContent = "掷骰中...";
  userDiceElem.textContent = "🎲";
  botDiceElem.textContent = "🎲";

  await new Promise(r => setTimeout(r, 1000));

  const userRoll = getRandomDice();
  const botRoll = getRandomDice();

  userDiceElem.textContent = diceEmoji(userRoll);
  botDiceElem.textContent = diceEmoji(botRoll);

  let scoreChange = 0;
  let resultText = "";

  if (userRoll > botRoll) {
    scoreChange = 10;
    resultText = "你赢了！+10积分 🎉🎉🎉";
  } else if (userRoll < botRoll) {
    scoreChange = -5;
    resultText = "你输了... -5积分 😞";
  } else {
    resultText = "平局！😐";
  }

  playCount++;
  userPoints += scoreChange;

  resultElem.textContent = `结果：你掷出${userRoll}，机器人掷出${botRoll}。${resultText}`;
  pointsElem.textContent = `当前积分：${userPoints}，已玩次数：${playCount} / ${maxPlaysPerDay}`;

  try {
    const resp = await fetch('/api/record_game_result', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_score: userRoll,
        bot_score: botRoll,
        result: scoreChange > 0 ? '赢' : scoreChange < 0 ? '输' : '平局',
        points_change: scoreChange
      })
    });
    if (!resp.ok) {
      console.error("上传游戏结果失败");
    }
  } catch(e) {
    console.error("请求失败", e);
  }

  rollBtn.disabled = false;
}

// 页面加载时初始化用户数据
loadUserData();
</script>

</body>
</html>
'''

# 获取用户积分和今日游戏次数接口
@app.route("/api/user_stats")
def user_stats():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"points": 0, "play_count": 0})
    with get_conn() as conn, conn.cursor() as c:
        c.execute("SELECT points, plays FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    if not row:
        return jsonify({"points": 0, "play_count": 0})
    return jsonify({"points": row[0] or 0, "play_count": row[1] or 0})

# 接收游戏结果接口
@app.route("/api/record_game_result", methods=["POST"])
def record_game_result():
    try:
        data = request.json
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "未登录"}), 401

        user_score = int(data.get("user_score"))
        bot_score = int(data.get("bot_score"))
        result = data.get("result")
        points_change = int(data.get("points_change"))
        now = datetime.now()

        with get_conn() as conn, conn.cursor() as c:
            c.execute("""
                UPDATE users 
                SET points = points + %s, plays = plays + 1, last_play = %s
                WHERE user_id = %s
            """, (points_change, now, user_id))

            c.execute("""
                INSERT INTO game_history (user_id, created_at, user_score, bot_score, result, points_change)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, now, user_score, bot_score, result, points_change))
            conn.commit()

        return jsonify({"status": "ok"})
    except Exception as e:
        logging.error(f"记录游戏结果失败: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


async def run_telegram_bot():
    app_ = ApplicationBuilder().token(BOT_TOKEN).build()
    app_.add_handler(CommandHandler("start", start))
    await app_.run_polling()

def reset_daily():
    with get_conn() as conn, conn.cursor() as c:
        c.execute("UPDATE users SET plays = 0")
        conn.commit()
    logging.info("每日游戏次数重置完成")

async def main():
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(reset_daily, "cron", hour=0, minute=0)
    scheduler.start()
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = ["0.0.0.0:8080"]
    web_task = serve(app, config)
    bot_task = run_telegram_bot()
    await asyncio.gather(web_task, bot_task)

if __name__ == "__main__":
    asyncio.run(main())

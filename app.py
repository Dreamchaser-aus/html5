from flask import Flask, render_template, request, jsonify
from datetime import datetime
import random

app = Flask(__name__)

# 模拟数据库
mock_users = {
    1: {"points": 100, "plays": 0, "phone": "123456789", "is_blocked": 0},
    2: {"points": 50, "plays": 9, "phone": "987654321", "is_blocked": 0}
}

@app.route("/dice_game")
def dice_game():
    return render_template("dice_game.html")

@app.route("/api/play_game")
def api_play_game():
    user_id = request.args.get("user_id", type=int)
    if not user_id or user_id not in mock_users:
        return jsonify({"error": "无效用户ID"})
    user = mock_users[user_id]
    if user["is_blocked"]:
        return jsonify({"error": "你已被封禁"})
    if not user["phone"]:
        return jsonify({"error": "请先授权手机号"})
    if user["plays"] >= 10:
        return jsonify({"error": "今日已达游戏次数上限"})

    user_score = random.randint(1, 6)
    bot_score = random.randint(1, 6)
    score = 10 if user_score > bot_score else -5 if user_score < bot_score else 0
    result = '赢' if score > 0 else '输' if score < 0 else '平局'
    user["points"] += score
    user["plays"] += 1

    return jsonify({
        "user_score": user_score,
        "bot_score": bot_score,
        "message": f"你{result}了！{'+' if score > 0 else ''}{score} 分",
        "total_points": user["points"]
    })

if __name__ == "__main__":
    app.run(debug=True)

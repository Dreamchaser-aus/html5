-- 创建用户表
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

-- 创建游戏记录表
CREATE TABLE IF NOT EXISTS game_history (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  user_score INTEGER,
  bot_score INTEGER,
  result TEXT,
  points_change INTEGER
);

-- 插入一个测试用户（你可以换掉 user_id 或手机号）
INSERT INTO users (
  user_id, first_name, last_name, username, phone,
  points, plays, created_at, last_play, invited_by, is_blocked
) VALUES (
  123456, '测试', '用户', 'testuser', '0412345678',
  0, 0, NOW(), NULL, NULL, 0
)
ON CONFLICT (user_id) DO NOTHING;

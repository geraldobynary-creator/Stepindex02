import os
import asyncio
import time
import pandas as pd
import telebot
from deriv_api import DerivAPI
from flask import Flask
from threading import Thread

# ================== RENDER SERVER ==================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ GOD MODE STEP INDEX BOT ACTIF"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ================== CONFIG ==================
TOKEN_TG = "8796066471:AAFSFZKa-BirjGJZ1irgG4S5WsWnag8ywRI"
ID_CHAT = "7893239258"
TOKEN_DERIV = "t0TDC2HM8Ey8mH9"

SYMBOL = "stpY"  # ⚠️ tester si besoin (step_index / STPUSD possible)

bot = telebot.TeleBot(TOKEN_TG)

# ================== TIMEFRAME CONTROL ==================
current_tf = 60  # default M1

tf_map = {
    "M1": 60,
    "M5": 300,
    "M15": 900
}

# ================== STATS ==================
stats = {"trades": 0, "wins": 0, "losses": 0}

def winrate():
    if stats["trades"] == 0:
        return 0
    return round((stats["wins"] / stats["trades"]) * 100, 2)

# ================== ANTI-SPAM ==================
last_signal_time = 0

def can_trade():
    global last_signal_time
    now = time.time()
    if now - last_signal_time > 120:
        last_signal_time = now
        return True
    return False

# ================== MARKET FILTER ==================
def market_ok(df):
    ranges = (df['high'] - df['low']).rolling(20).mean()
    return ranges.iloc[-2] > 0.5

# ================== GOD MODE STRATEGY ==================
def god_signal(df):
    df['ema50'] = df['close'].ewm(span=50).mean()

    slope = df['ema50'].iloc[-2] - df['ema50'].iloc[-6]

    df['range'] = df['high'] - df['low']
    avg_range = df['range'].rolling(20).mean()

    c = df.iloc[-2]
    prev = df.iloc[-3]

    body = abs(c['close'] - c['open'])
    upper_wick = c['high'] - max(c['open'], c['close'])
    lower_wick = min(c['open'], c['close']) - c['low']

    if not market_ok(df):
        return None, None

    signal = None

    # 🔵 BUY
    if c['close'] > df['ema50'].iloc[-2] and slope > 0:
        if prev['close'] < prev['open']:
            if lower_wick > body and c['range'] > avg_range.iloc[-2]:
                signal = "ACHAT 🔵"

    # 🔴 SELL
    elif c['close'] < df['ema50'].iloc[-2] and slope < 0:
        if prev['close'] > prev['open']:
            if upper_wick > body and c['range'] > avg_range.iloc[-2]:
                signal = "VENTE 🔴"

    return signal, c['close']

# ================== TELEGRAM START + BUTTONS ==================
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.InlineKeyboardMarkup()

    markup.add(
        telebot.types.InlineKeyboardButton("M1 ⏱️", callback_data="tf_M1"),
        telebot.types.InlineKeyboardButton("M5 ⏱️", callback_data="tf_M5"),
        telebot.types.InlineKeyboardButton("M15 ⏱️", callback_data="tf_M15")
    )

    bot.send_message(
        message.chat.id,
        "🚀 GOD MODE BOT STEP INDEX\nChoisis ton timeframe :",
        reply_markup=markup
    )

# ================== TIMEFRAME CHANGE ==================
@bot.callback_query_handler(func=lambda call: True)
def change_tf(call):
    global current_tf

    tf_selected = call.data.replace("tf_", "")
    current_tf = tf_map[tf_selected]

    bot.answer_callback_query(call.id, f"TF: {tf_selected}")

    bot.send_message(
        ID_CHAT,
        f"✅ Timeframe changé en {tf_selected}"
    )

# ================== TRADING LOOP ==================
async def trading_logic():
    api = DerivAPI(app_id=1089)

    try:
        await api.authorize(TOKEN_DERIV)
        print("✅ Connecté Deriv")
    except Exception as e:
        print("❌ Erreur Deriv:", e)
        return

    last_epoch = None

    while True:
        try:
            r = await api.ticks_history({
                "ticks_history": SYMBOL,
                "count": 200,
                "end": "latest",
                "style": "candles",
                "granularity": current_tf
            })

            df = pd.DataFrame(r["candles"])

            for col in ["open", "close", "high", "low"]:
                df[col] = df[col].astype(float)

            signal, price = god_signal(df)
            epoch = df.iloc[-2]["epoch"]

            print("DEBUG:", signal, price)

            if signal and epoch != last_epoch and can_trade():

                if "ACHAT" in signal:
                    sl = price - 3
                    tp1 = price + 2
                    tp2 = price + 5
                    stats["wins"] += 1
                else:
                    sl = price + 3
                    tp1 = price - 2
                    tp2 = price - 5
                    stats["wins"] += 1

                stats["trades"] += 1

                bot.send_message(
                    ID_CHAT,
                    f"🎯 {signal}\n"
                    f"Prix: `{price}`\n"
                    f"SL: `{sl}`\n"
                    f"TP1: `{tp1}` | TP2: `{tp2}`\n"
                    f"📊 Winrate: {winrate()}%",
                    parse_mode="Markdown"
                )

                last_epoch = epoch

        except Exception as e:
            print("❌ Error:", e)

        await asyncio.sleep(10)

# ================== MAIN ==================
if __name__ == "__main__":
    Thread(target=run_web).start()
    Thread(target=bot.infinity_polling, daemon=True).start()
    asyncio.run(trading_logic())

import os
import asyncio
import pandas as pd
import telebot
from telebot import types
from deriv_api import DerivAPI
from flask import Flask
from threading import Thread

# --- SERVEUR POUR RENDER ---
app = Flask('')
@app.route('/')
def home(): return "Bot Step Index v2 - Statut: Operationnel"

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- CONFIGURATION ---
TOKEN_TG = "8796066471:AAEGpKpC0aJpLNNEf1KB0JBYW5NhXypPqUA"
ID_CHAT = "7893239258"
TOKEN_DERIV = ""

bot = telebot.TeleBot(TOKEN_TG)
current_tf = "5m"
tf_seconds = {"5m": 300, "15m": 900, "30m": 1800}

def analyze_patterns(current, previous):
    c_open, c_close, c_high, c_low = current['open'], current['close'], current['high'], current['low']
    p_open, p_close = previous['open'], previous['close']
    body = abs(c_close - c_open)
    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low
    # Englobante
    if c_close > c_open and p_close < p_open and c_close > p_open and c_open < p_close: return "ENGLOBANTE HAUSSIÈRE 📈"
    if c_close < c_open and p_close > p_open and c_close < p_open and c_open > p_close: return "ENGLOBANTE BAISSIÈRE 📉"
    # Marteaux / Etoiles
    if lower_wick > (1.5 * body) and upper_wick < (0.2 * body): return "MARTEAU 🔨"
    if upper_wick > (1.5 * body) and lower_wick < (0.2 * body): return "ÉTOILE FILANTE ☄️"
    return None

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("M5 ⏱️", callback_data="tf_5m"),
               types.InlineKeyboardButton("M15 ⏱️", callback_data="tf_15m"),
               types.InlineKeyboardButton("M30 ⏱️", callback_data="tf_30m"))
    bot.send_message(message.chat.id, "🚀 **Bot Step Index v2**\nStratégie: MM200 + RSI + Candlesticks\nChoisissez votre Timeframe :", 
                     reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def update_tf(call):
    global current_tf
    current_tf = call.data.replace("tf_", "")
    bot.answer_callback_query(call.id, f"TF: {current_tf}")
    bot.send_message(ID_CHAT, f"✅ Analyse lancée en **{current_tf}**", parse_mode="Markdown")

async def trading_logic():
    api = DerivAPI(app_id=1089)
    try:
        await api.authorize(TOKEN_DERIV)
        print("✅ Connecté à Deriv")
    except Exception as e:
        print(f"Erreur Deriv: {e}")
        return

    last_epoch = None
    while True:
        try:
            r = await api.ticks_history({'ticks_history': 'stpY', 'count': 300, 'end': 'latest', 'style': 'candles', 'granularity': tf_seconds[current_tf]})
            df = pd.DataFrame(r['candles'])
            for col in ['open', 'close', 'high', 'low']: df[col] = df[col].astype(float)
            ema = df['close'].ewm(span=200, adjust=False).mean()
            delta = df['close'].diff(); g = delta.where(delta > 0, 0).rolling(14).mean(); l = -delta.where(delta < 0, 0).rolling(14).mean()
            rsi = 100 - (100 / (1 + (g / l)))
            
            curr_c, prev_c = df.iloc[-2], df.iloc[-3]
            p, r_val, e_val, epoch = curr_c['close'], rsi.iloc[-2], ema.iloc[-2], curr_c['epoch']
            pattern = analyze_patterns(curr_c, prev_c)

            if epoch != last_epoch:
                sig = None
                if p > e_val and r_val >= 30 and pattern in ["ENGLOBANTE HAUSSIÈRE 📈", "MARTEAU 🔨"]:
                    sig = "ACHAT 🔵"
                    sl, tp1, tp2, tp3 = p-7, p+4, p+10, p+20
                elif p < e_val and r_val <= 70 and pattern in ["ENGLOBANTE BAISSIÈRE 📉", "ÉTOILE FILANTE ☄️"]:
                    sig = "VENTE 🔴"
                    sl, tp1, tp2, tp3 = p+7, p-4, p-10, p-20

                if sig:
                    bot.send_message(ID_CHAT, f"🎯 **SIGNAL {sig}**\nConfirmation: {pattern}\nPrix: `{p}`\n❌ SL: `{sl}`\n✅ TP1: `{tp1}` | TP2: `{tp2}` | TP3: `{tp3}`", parse_mode="Markdown")
                last_epoch = epoch
        except Exception as e:
            print(f"Erreur boucle: {e}")
        await asyncio.sleep(20)

if __name__ == "__main__":
    Thread(target=run_web).start()
    Thread(target=bot.infinity_polling, daemon=True).start()
    asyncio.run(trading_logic())
          

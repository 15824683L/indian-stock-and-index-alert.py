import time
import yfinance as yf
import requests
import logging
from datetime import datetime
import pytz
import ssl
import certifi
import os

# SSL cert path set
os.environ['SSL_CERT_FILE'] = certifi.where()

# Telegram Bot Config
TELEGRAM_BOT_TOKEN = "8100205821:AAE0sGJhnA8ySkuSusEXSf9bYU5OU6sFzVg"
TELEGRAM_CHAT_ID = "-1002689167916"

# Stocks List
STOCKS = [ "TCS.NS", "INFY.NS", "ICICIBANK.NS", "HDFCBANK.NS"]

# Timeframes
TIMEFRAMES = ["15m", "30m"]

# Signal Trackers
active_trades = {}

# Logging Setup
logging.basicConfig(filename="trade_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Timezone
kolkata_tz = pytz.timezone("Asia/Kolkata")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram Error: {e}")

def fetch_data(symbol, tf):
    try:
        df = yf.download(tickers=symbol, period="2d", interval=tf)
        df.reset_index(inplace=True)
        df.rename(columns={"Open":"open", "High":"high", "Low":"low", "Close":"close", "Volume":"volume"}, inplace=True)
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        return df
    except Exception as e:
        logging.error(f"Data Fetch Error {symbol}: {e}")
        return None

def calculate_vwap(df):
    df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
    return df

def check_liquidity_bos(df):
    df = calculate_vwap(df)
    df['prev_high'] = df['high'].shift(1)
    df['prev_low'] = df['low'].shift(1)

    grab_high = df['high'] > df['prev_high']
    grab_low = df['low'] < df['prev_low']

    if grab_low.iloc[-2] and df['close'].iloc[-1] > df['high'].iloc[-2] and df['close'].iloc[-1] > df['vwap'].iloc[-1]:
        entry = df['close'].iloc[-1]
        sl = df['low'].iloc[-2]
        tp = round(entry + (entry - sl) * 2, 2)
        return "BUY", round(entry,2), round(sl,2), tp
    elif grab_high.iloc[-2] and df['close'].iloc[-1] < df['low'].iloc[-2] and df['close'].iloc[-1] < df['vwap'].iloc[-1]:
        entry = df['close'].iloc[-1]
        sl = df['high'].iloc[-2]
        tp = round(entry - (sl - entry) * 2, 2)
        return "SELL", round(entry,2), round(sl,2), tp
    else:
        return "NO", None, None, None

def log_signal(stock, tf, signal, entry, sl, tp):
    now = datetime.now(kolkata_tz).strftime('%Y-%m-%d %H:%M:%S')
    with open("/mnt/data/signal_log.txt", "a") as f:
        f.write(f"{now} - {stock} - {tf} - {signal} - Entry: {entry}, SL: {sl}, TP: {tp}\n")

while True:
    for stock in STOCKS:
        for tf in TIMEFRAMES:
            key = f"{stock}_{tf}"  # ইউনিক কী তৈরি স্টক + টাইমফ্রেম ভিত্তিতে

            df = fetch_data(stock, tf)
            if df is not None and not df.empty:
                # ট্রেড সক্রিয় থাকলে TP/SL চেক করা হবে
                if key in active_trades:
                    last_price = df['close'].iloc[-1]
                    trade = active_trades[key]
                    now_time = datetime.now(kolkata_tz).strftime('%Y-%m-%d %H:%M')

                    if trade['type'] == "BUY" and last_price >= trade['tp']:
                        send_telegram_message(f"✅ TP HIT for {stock} [{tf}] at {last_price} ({now_time})")
                        del active_trades[key]
                    elif trade['type'] == "BUY" and last_price <= trade['sl']:
                        send_telegram_message(f"❌ SL HIT for {stock} [{tf}] at {last_price} ({now_time})")
                        del active_trades[key]
                    elif trade['type'] == "SELL" and last_price <= trade['tp']:
                        send_telegram_message(f"✅ TP HIT for {stock} [{tf}] at {last_price} ({now_time})")
                        del active_trades[key]
                    elif trade['type'] == "SELL" and last_price >= trade['sl']:
                        send_telegram_message(f"❌ SL HIT for {stock} [{tf}] at {last_price} ({now_time})")
                        del active_trades[key]
                    continue

                # নতুন সিগন্যাল চেক করা হচ্ছে
                signal, entry, sl, tp = check_liquidity_bos(df)

                # Duplicate checker: আগের মতই সিগন্যাল থাকলে স্কিপ করুন
                if signal != "NO":
                    if key in active_trades and active_trades[key]['type'] == signal:
                        continue  # ডুপ্লিকেট সিগন্যাল

                    now = datetime.now(kolkata_tz).strftime('%Y-%m-%d %H:%M:%S')
                    msg = f"*{signal} Signal for {stock} [{tf}]*\nTime: `{now}`\nEntry: `{entry}`\nSL: `{sl}`\nTP: `{tp}`"
                    send_telegram_message(msg)
                    log_signal(stock, tf, signal, entry, sl, tp)
                    active_trades[key] = {"type": signal, "entry": entry, "sl": sl, "tp": tp}

    time.sleep(60)

import time
import yfinance as yf
import requests
import logging
from datetime import datetime
import ssl
import certifi
import os
from keep_alive import keep_alive

# Start keep_alive server for Render deployment
keep_alive()

# Fix SSL cert error
os.environ['SSL_CERT_FILE'] = certifi.where()

# Telegram Config
TELEGRAM_BOT_TOKEN = "8100205821:AAE0sGJhnA8ySkuSusEXSf9bYU5OU6sFzVg"
TELEGRAM_CHAT_ID = ""  # Optional personal ID
TELEGRAM_GROUP_CHAT_ID = "-1002689167916"

# Stock List (add more if needed)
INDIAN_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "LT.NS", "SBIN.NS", "KOTAKBANK.NS", "ITC.NS"
]

ALL_SYMBOLS = INDIAN_STOCKS

timeframes = {
    "Intraday 15m": "15m",
    "Intraday 30m": "30m",
    "Swing": "1h",
    "Position": "1d"
}

active_trades = {}
last_signal_time = time.time()

logging.basicConfig(filename="trade_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

def send_telegram_message(message, chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

def fetch_data(symbol, tf):
    interval_map = {"15m": "15m", "30m": "30m", "1h": "60m", "1d": "1d"}
    try:
        df = yf.download(tickers=symbol, period="2d", interval=interval_map[tf])
        df.reset_index(inplace=True)
        df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
        df['timestamp'] = df['Datetime'] if 'Datetime' in df.columns else df['Date']
        df['vwap'] = ((df['high'] + df['low'] + df['close']) / 3 * df['volume']).cumsum() / df['volume'].cumsum()
        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'vwap']]
    except Exception as e:
        logging.error(f"Error fetching {symbol} - {e}")
        return None

def liquidity_grab_order_block_vwap(df):
    df['high_shift'] = df['high'].shift(1)
    df['low_shift'] = df['low'].shift(1)
    df.dropna(inplace=True)

    try:
        liquidity_grab = (df['high'] > df['high_shift']) & (df['low'] < df['low_shift'])
        df = df[liquidity_grab]
    except Exception as e:
        logging.error(f"Alignment Error: {e}")
        return "NO SIGNAL", None, None, None, None, None

    if df.empty:
        return "NO SIGNAL", None, None, None, None, None

    order_block = df['close'] > df['open']
    price_above_vwap = df['close'] > df['vwap']
    price_below_vwap = df['close'] < df['vwap']

    # BUY Signal
    if order_block.iloc[-1] and price_above_vwap.iloc[-1]:
        entry = round(df['close'].iloc[-1], 2)
        sl = round(df['low'].iloc[-2], 2)
        tp = round(entry + (entry - sl) * 2, 2)
        tsl = round(entry + (entry - sl) * 1.5, 2)
        return "BUY", entry, sl, tp, tsl, "🟢"

    # SELL Signal
    elif not order_block.iloc[-1] and price_below_vwap.iloc[-1]:
        entry = round(df['close'].iloc[-1], 2)
        sl = round(df['high'].iloc[-2], 2)
        tp = round(entry - (sl - entry) * 2, 2)
        tsl = round(entry - (sl - entry) * 1.5, 2)
        return "SELL", entry, sl, tp, tsl, "🔴"

    return "NO SIGNAL", None, None, None, None, None

# Main Loop
while True:
    signal_found = False

    for stock in ALL_SYMBOLS:
        if stock in active_trades:
            df = fetch_data(stock, "15m")
            if df is not None and not df.empty:
                last_price = df['close'].iloc[-1]
                trade = active_trades[stock]
                now_time = datetime.now().strftime('%Y-%m-%d %H:%M')
                signal_time = trade['signal_time']

                if trade['direction'] == "BUY":
                    if last_price >= trade['tp']:
                        msg = f"✅ *TP HIT for {stock}*\nSignal Time: `{signal_time}`\nHit Time: `{now_time}`\nPrice: `{last_price}`"
                        send_telegram_message(msg, TELEGRAM_GROUP_CHAT_ID)
                        del active_trades[stock]
                    elif last_price <= trade['sl']:
                        msg = f"🛑 *SL HIT for {stock}*\nSignal Time: `{signal_time}`\nHit Time: `{now_time}`\nPrice: `{last_price}`"
                        send_telegram_message(msg, TELEGRAM_GROUP_CHAT_ID)
                        del active_trades[stock]

                elif trade['direction'] == "SELL":
                    if last_price <= trade['tp']:
                        msg = f"✅ *TP HIT for {stock}*\nSignal Time: `{signal_time}`\nHit Time: `{now_time}`\nPrice: `{last_price}`"
                        send_telegram_message(msg, TELEGRAM_GROUP_CHAT_ID)
                        del active_trades[stock]
                    elif last_price >= trade['sl']:
                        msg = f"🛑 *SL HIT for {stock}*\nSignal Time: `{signal_time}`\nHit Time: `{now_time}`\nPrice: `{last_price}`"
                        send_telegram_message(msg, TELEGRAM_GROUP_CHAT_ID)
                        del active_trades[stock]
            continue

        for label, tf in timeframes.items():
            df = fetch_data(stock, tf)
            if df is not None and not df.empty:
                signal, entry, sl, tp, tsl, emoji = liquidity_grab_order_block_vwap(df)
                if signal != "NO SIGNAL":
                    signal_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S")
                    msg = (
                        f"{emoji} *{signal} Signal for {stock}*\n"
                        f"Type: {label}\nTimeframe: {tf}\nTime: `{signal_time}`\n"
                        f"Entry: `{entry}`\nSL: `{sl}`\nTP: `{tp}`\nTSL: `{tsl}`"
                    )
                    send_telegram_message(msg, TELEGRAM_GROUP_CHAT_ID)

                    active_trades[stock] = {
                        "signal_time": signal_time,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "direction": signal
                    }
                    signal_found = True
                    break
        if signal_found:
            break

    if not signal_found and (time.time() - last_signal_time > 3600):
        send_telegram_message("⚠️ No Signal in the Last 1 Hour (Indian Stocks + Index)", TELEGRAM_GROUP_CHAT_ID)
        last_signal_time = time.time()

    time.sleep(60)
    print("Bot is running 24/7!")

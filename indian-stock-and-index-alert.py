import time
import yfinance as yf
import requests
import logging
from datetime import datetime
import ssl
import certifi
import os
from keep_alive import keep_alive

keep_alive()

# Set SSL certificates
os.environ['SSL_CERT_FILE'] = certifi.where()

# Telegram Bot Config
TELEGRAM_BOT_TOKEN = "8100205821:AAE0sGJhnA8ySkuSusEXSf9bYU5OU6sFzVg"
TELEGRAM_CHAT_ID = "8191014589"
TELEGRAM_GROUP_CHAT_ID = "-1002689167916"

# Top 20 Indian Stocks + Indexes (Yahoo Tickers)
INDIAN_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "LT.NS", "SBIN.NS", "KOTAKBANK.NS", "ITC.NS"
]
INDICES = ["^NSEI", "^NSEBANK", "^BSESN", "^NSEFIN"]
ALL_SYMBOLS = INDIAN_STOCKS + INDICES

# Timeframes
timeframes = {
    "Intraday 15m": "15m",
    "Intraday 30m": "30m",
    "Swing": "1h",
    "Position": "1d"
}

# Active trades and signal time
active_trades = {}
last_signal_time = time.time()

# Set up logging
logging.basicConfig(filename="trade_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Telegram message sender
def send_telegram_message(message, chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    requests.post(url, data=data)

# Fetch OHLCV
def fetch_data(symbol, tf):
    interval_map = { "4h": "240m", "1d": "1d"}
    try:
        df = yf.download(tickers=symbol, period="2d", interval=interval_map[tf])
        df.reset_index(inplace=True)
        df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
        df = df[['Datetime' if 'Datetime' in df.columns else 'Date', 'open', 'high', 'low', 'close', 'volume']]
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        return df
    except Exception as e:
        logging.error(f"Error fetching {symbol} - {e}")
        return None

# Strategy
def liquidity_grab_order_block(df):
    df['high_shift'] = df['high'].shift(1)
    df['low_shift'] = df['low'].shift(1)
    liquidity_grab = (df['high'] > df['high_shift']) & (df['low'] < df['low_shift'])
    order_block = df['close'] > df['open']

    if liquidity_grab.iloc[-1] and order_block.iloc[-1]:
        entry = round(df['close'].iloc[-1], 2)
        sl = round(df['low'].iloc[-2], 2)
        tp = round(entry + (entry - sl) * 2, 2)
        tsl = round(entry + (entry - sl) * 1.5, 2)
        return "BUY", entry, sl, tp, tsl, "\U0001F7E2"
    elif liquidity_grab.iloc[-1] and not order_block.iloc[-1]:
        entry = round(df['close'].iloc[-1], 2)
        sl = round(df['high'].iloc[-2], 2)
        tp = round(entry - (sl - entry) * 2, 2)
        tsl = round(entry - (sl - entry) * 1.5, 2)
        return "SELL", entry, sl, tp, tsl, "\U0001F534"
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

                if trade['direction'] == "BUY":
                    if last_price >= trade['tp']:
                        send_telegram_message(f"✅ *TP HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`", TELEGRAM_CHAT_ID)
                        send_telegram_message(f"✅ *TP HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`", TELEGRAM_GROUP_CHAT_ID)
                        del active_trades[stock]  # Remove trade after TP hit
                    elif last_price <= trade['sl']:
                        send_telegram_message(f"🛑 *SL HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`", TELEGRAM_CHAT_ID)
                        send_telegram_message(f"🛑 *SL HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`", TELEGRAM_GROUP_CHAT_ID)
                        del active_trades[stock]  # Remove trade after SL hit

                elif trade['direction'] == "SELL":
                    if last_price <= trade['tp']:
                        send_telegram_message(f"✅ *TP HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`", TELEGRAM_CHAT_ID)
                        send_telegram_message(f"✅ *TP HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`", TELEGRAM_GROUP_CHAT_ID)
                        del active_trades[stock]  # Remove trade after TP hit
                    elif last_price >= trade['sl']:
                        send_telegram_message(f"🛑 *SL HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`", TELEGRAM_CHAT_ID)
                        send_telegram_message(f"🛑 *SL HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`", TELEGRAM_GROUP_CHAT_ID)
                        del active_trades[stock]  # Remove trade after SL hit
            continue

        for label, tf in timeframes.items():
            df = fetch_data(stock, tf)
            if df is not None and not df.empty:
                signal, entry, sl, tp, tsl, emoji = liquidity_grab_order_block(df)
                if signal != "NO SIGNAL":
                    signal_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    msg = (
                        f"{emoji} *{signal} Signal for {stock}*\n"
                        f"Type: {label}\nTimeframe: {tf}\nTime: `{signal_time}`\n"
                        f"Entry: `{entry}`\nSL: `{sl}`\nTP: `{tp}`\nTSL: `{tsl}`"
                    )
                    send_telegram_message(msg, TELEGRAM_CHAT_ID)
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

    # No signal alert
    if not signal_found and (time.time() - last_signal_time > 3600):
        send_telegram_message("⚠️ No Signal in the Last 1 Hour (Indian Stocks + Index)", TELEGRAM_CHAT_ID)
        send_telegram_message("⚠️ No Signal in the Last 1 Hour (Indian Stocks + Index)", TELEGRAM_GROUP_CHAT_ID)
        last_signal_time = time.time()

    time.sleep(60)
    print("Bot is running 24/7!")

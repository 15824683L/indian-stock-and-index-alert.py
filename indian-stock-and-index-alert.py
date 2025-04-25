import time
import yfinance as yf
import requests
import logging
from datetime import datetime
import ssl
import certifi
import os
from keep_alive import keep_alive

# Start server for deployment
keep_alive()

# SSL Fix
os.environ['SSL_CERT_FILE'] = certifi.where()

# Telegram Setup
TELEGRAM_BOT_TOKEN = "8100205821:AAE0sGJhnA8ySkuSusEXSf9bYU5OU6sFzVg"
TELEGRAM_CHAT_ID = "-1002689167916"  # Group ID

# Stock List
INDIAN_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "LT.NS", "SBIN.NS", "KOTAKBANK.NS", "ITC.NS",
    "AXISBANK.NS", "BHARTIARTL.NS", "ASIANPAINT.NS", "BAJFINANCE.NS", "HCLTECH.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "NESTLEIND.NS", "WIPRO.NS", "TITAN.NS",
    "ULTRACEMCO.NS", "HDFCLIFE.NS", "POWERGRID.NS", "TECHM.NS", "ONGC.NS",
    "NTPC.NS", "COALINDIA.NS", "JSWSTEEL.NS", "TATASTEEL.NS", "BPCL.NS",
    "BRITANNIA.NS", "DIVISLAB.NS", "ADANIENT.NS", "ADANIPORTS.NS", "GRASIM.NS",
    "CIPLA.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "HINDALCO.NS", "DRREDDY.NS",
    "BAJAJFINSV.NS", "SBILIFE.NS", "BAJAJ-AUTO.NS", "INDUSINDBK.NS", "M&M.NS"
]

# Timeframes
TIMEFRAMES = {"15m": "15m", "30m": "30m", "1h": "60m", "1d": "1d"}

# Track Active Trades
active_trades = {}
last_signal_time = time.time()

# Logger
logging.basicConfig(filename="bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Telegram Send Message
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

# Fetch Data from Yahoo Finance
def fetch_data(symbol, tf):
    try:
        df = yf.download(tickers=symbol, period="2d", interval=TIMEFRAMES[tf])
        df.reset_index(inplace=True)
        df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
        df['timestamp'] = df['Datetime'] if 'Datetime' in df.columns else df['Date']
        df['vwap'] = ((df['high'] + df['low'] + df['close']) / 3 * df['volume']).cumsum() / df['volume'].cumsum()
        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'vwap']]
    except Exception as e:
        logging.error(f"{symbol} fetch error: {e}")
        return None
# কৌশল: লিকুইডিটি গ্র্যাব + অর্ডার ব্লক + VWAP
def strategy(df):
    df['high_prev'] = df['high'].shift(1)
    df['low_prev'] = df['low'].shift(1)
    df.dropna(inplace=True)

    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

 # Liquidity Grab: Wick extends above or below previous
liquidity = ((last_row['high'] > prev_row['high']) & (last_row['low'] < prev_row['low'])).all()
    if liquidity:
        # অর্ডার ব্লক লজিক
        is_bullish_block = last_row['close'] > last_row['open']
        is_bearish_block = last_row['close'] < last_row['open']

        # VWAP শর্ত
        if is_bullish_block and last_row['close'] > last_row['vwap']:
            entry = round(last_row['close'], 2)
            sl = round(prev_row['low'], 2)
            tp = round(entry + (entry - sl) * 2, 2)
            tsl = round(entry + (entry - sl) * 1.5, 2)
            return "BUY", entry, sl, tp, tsl, "🟢"

        elif is_bearish_block and last_row['close'] < last_row['vwap']:
            entry = round(last_row['close'], 2)
            sl = round(prev_row['high'], 2)
            tp = round(entry - (sl - entry) * 2, 2)
            tsl = round(entry - (sl - entry) * 1.5, 2)
            return "SELL", entry, sl, tp, tsl, "🔴"

    return "NO SIGNAL", None, None, None, None, None
# Main Bot Loop
while True:
    for symbol in INDIAN_STOCKS:
        if symbol in active_trades:
            df = fetch_data(symbol, "15m")
            if df is not None:
                last_price = df['close'].iloc[-1]
                trade = active_trades[symbol]

                if trade['direction'] == "BUY" and last_price >= trade['tp']:
                    send_telegram(f"✅ *TP HIT* for {symbol}\nEntry: `{trade['entry']}` → TP: `{trade['tp']}`")
                    del active_trades[symbol]
                elif trade['direction'] == "BUY" and last_price <= trade['sl']:
                    send_telegram(f"🛑 *SL HIT* for {symbol}\nEntry: `{trade['entry']}` → SL: `{trade['sl']}`")
                    del active_trades[symbol]
                elif trade['direction'] == "SELL" and last_price <= trade['tp']:
                    send_telegram(f"✅ *TP HIT* for {symbol}\nEntry: `{trade['entry']}` → TP: `{trade['tp']}`")
                    del active_trades[symbol]
                elif trade['direction'] == "SELL" and last_price >= trade['sl']:
                    send_telegram(f"🛑 *SL HIT* for {symbol}\nEntry: `{trade['entry']}` → SL: `{trade['sl']}`")
                    del active_trades[symbol]
            continue

        for tf in TIMEFRAMES:
            df = fetch_data(symbol, tf)
            if df is not None:
                signal, entry, sl, tp, tsl, emoji = strategy(df)
                if signal != "NO SIGNAL":
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    msg = (
                        f"{emoji} *{signal} Signal for {symbol}*\n"
                        f"Timeframe: `{tf}`\nTime: `{now}`\n"
                        f"Entry: `{entry}` | SL: `{sl}` | TP: `{tp}` | TSL: `{tsl}`"
                    )
                    send_telegram(msg)

                    active_trades[symbol] = {
                        "signal_time": now,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "direction": signal
                    }
                    break

    # No signal alert after 1 hour
    if time.time() - last_signal_time > 3600:
        send_telegram("⚠️ No Signal in Last 1 Hour (VWAP + Order Block + Liquidity Strategy)")
        last_signal_time = time.time()

    time.sleep(60)
    print("Bot running...")

import time
import datetime
import pytz
import requests
import pandas as pd
import pandas_ta as ta
from nsepython import *
from keep_alive import keep_alive

# Keep bot alive
keep_alive()

# Telegram Bot Info
TOKEN = "8100205821:AAE0sGJhnA8ySkuSusEXSf9bYU5OU6sFzVg"
CHANNEL_ID = "@swingtreadingSmartbot"

# Stocks to monitor
stocks = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "LT", "KOTAKBANK", "SBIN", "AXISBANK", "ITC",
    "BHARTIARTL", "ASIANPAINT", "HINDUNILVR", "HCLTECH", "WIPRO", "BAJFINANCE", "BAJAJFINSV", "NESTLEIND",
    "SUNPHARMA", "ULTRACEMCO", "TITAN", "POWERGRID", "NTPC", "COALINDIA", "TECHM", "ADANIENT", "MARUTI",
    "CIPLA", "HINDALCO", "JSWSTEEL", "GRASIM", "TATASTEEL", "ONGC", "SBILIFE", "HDFCLIFE", "DIVISLAB",
    "BPCL", "EICHERMOT", "HEROMOTOCO", "BRITANNIA", "DRREDDY", "APOLLOHOSP", "BAJAJ-AUTO", "M&M", "INDUSINDBK"
]
def get_intraday_data(stock):
    try:
        candles = nsefetch(f"https://www.nseindia.com/api/chart-databyindex?index={stock}&preopen=true")['grapthData']
        df = pd.DataFrame(candles, columns=['timestamp', 'price'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['Close'] = df['price']
        df = df.set_index('timestamp').resample('5T').ffill()
        df["High"] = df["Close"]
        df["Low"] = df["Close"]
        df["Open"] = df["Close"]
        df["Volume"] = 1000  # Placeholder volume
        return df.drop(columns=["price"])
    except Exception as e:
        print(f"Error fetching data for {stock}: {e}")
        return pd.DataFrame()

def calculate_supertrend(df):
    df.ta.supertrend(length=14, multiplier=3, append=True)
    return df["SUPERT_14_3.0"]

def calculate_macd(df):
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    return df["MACD_12_26_9"], df["MACDs_12_26_9"]

def calculate_vwap(df):
    df['vwap'] = (df['Volume'] * (df['High'] + df['Low'] + df['Close']) / 3).cumsum() / df['Volume'].cumsum()
    return df['vwap']

def calculate_volume_breakout(df, period=20):
    avg_volume = df['Volume'].rolling(window=period).mean()
    return df['Volume'] > (1.5 * avg_volume)

def check_signal(stock):
    df = get_intraday_data(stock)
    if df.empty or len(df) < 2:
        return None

    supertrend = calculate_supertrend(df)
    macd, macdsignal = calculate_macd(df)
    vwap = calculate_vwap(df)
    volume_breakout = calculate_volume_breakout(df)

    last_close = df["Close"].iloc[-1]
    prev_close = df["Close"].iloc[-2]

    supertrend_signal = last_close > supertrend.iloc[-1]
    macd_signal = macd.iloc[-1] > macdsignal.iloc[-1]
    vwap_signal = last_close > vwap.iloc[-1]
    volume_signal = volume_breakout.iloc[-1]

    if supertrend_signal and macd_signal and vwap_signal and volume_signal:
        return {
            "stock": stock,
            "entry": round(prev_close, 2),
            "target": round(last_close * 1.02, 2),
            "type": "BUY"
        }
    elif not supertrend_signal and not macd_signal and not vwap_signal and not volume_signal:
        return {
            "stock": stock,
            "entry": round(prev_close, 2),
            "target": round(last_close * 0.98, 2),
            "type": "SELL"
        }

    return None

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

def get_ist_time():
    return datetime.datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p")

def run_bot():
    last_no_signal_time = time.time() - 3600
    while True:
        found_signal = False
        for stock in stocks:
            signal = check_signal(stock)
            if signal:
                found_signal = True
                time_now = get_ist_time()
                msg = f"[{signal['type']} SIGNAL - {signal['stock']}]\nTarget: ₹{signal['target']}\nEntry: ₹{signal['entry']}\nTime: {time_now} (IST)"
                send_to_telegram(msg)

        if not found_signal:
            current_time = time.time()
            if current_time - last_no_signal_time >= 3600:
                time_now = get_ist_time()
                send_to_telegram(f"[NO SIGNAL]\nKono stock e signal hit koreni.\nTime: {time_now} (IST)")
                last_no_signal_time = current_time

        time.sleep(300)  # wait 5 minutes

if __name__ == "__main__":
    run_bot()

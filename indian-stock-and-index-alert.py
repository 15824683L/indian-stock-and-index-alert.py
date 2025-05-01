import yfinance as yf
import pytz
import datetime
import time
import requests

TOKEN = "8100205821:AAE0sGJhnA8ySkuSusEXSf9bYU5OU6sFzVg"
CHANNEL_ID = "@swingtreadingSmartbot"

stocks = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "LT.NS", "KOTAKBANK.NS", "SBIN.NS",
          "AXISBANK.NS", "ITC.NS", "BHARTIARTL.NS", "ASIANPAINT.NS", "HINDUNILVR.NS", "BAJFINANCE.NS", "WIPRO.NS",
          "ULTRACEMCO.NS", "HCLTECH.NS", "MARUTI.NS", "TECHM.NS", "SUNPHARMA.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS",
          "TITAN.NS", "GRASIM.NS", "BPCL.NS", "DIVISLAB.NS", "NESTLEIND.NS", "JSWSTEEL.NS", "BAJAJFINSV.NS"]

def check_signal(stock):
    df = yf.download(stock, period="2d", interval="5m")
    if len(df) < 2:
        return None
    last_close = df["Close"].iloc[-1]
    prev_close = df["Close"].iloc[-2]

    if last_close > prev_close * 1.02:
        return {"stock": stock.split(".")[0], "entry": round(prev_close, 2), "target": round(last_close, 2), "type": "TP"}
    elif last_close < prev_close * 0.98:
        return {"stock": stock.split(".")[0], "entry": round(prev_close, 2), "target": round(last_close, 2), "type": "SL"}
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
    last_no_signal_time = time.time() - 3600  # So it sends on first run if needed

    while True:
        found_signal = False
        for stock in stocks:
            signal = check_signal(stock)
            if signal:
                found_signal = True
                time_now = get_ist_time()
                msg = f"[{signal['type']} HIT - {signal['stock']}]\nTarget reached: ₹{signal['target']}\nEntry: ₹{signal['entry']}\nSignal time: {time_now}\nTime: {time_now} (IST)"
                send_to_telegram(msg)

        # No signal logic
        if not found_signal:
            current_time = time.time()
            if current_time - last_no_signal_time >= 3600:
                time_now = get_ist_time()
                send_to_telegram(f"[NO SIGNAL]\nKono stock e TP/SL hit koreni.\nTime: {time_now} (IST)")
                last_no_signal_time = current_time

        time.sleep(300)  # Wait 5 mins before next scan

if __name__ == "__main__":
    run_bot()

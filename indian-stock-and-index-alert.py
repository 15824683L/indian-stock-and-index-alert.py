import yfinance as yf
import pytz
import datetime
import time
import requests
import talib as ta
import numpy as np

TOKEN = "8100205821:AAE0sGJhnA8ySkuSusEXSf9bYU5OU6sFzVg"
CHANNEL_ID = "@swingtreadingSmartbot"

stocks = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "LT.NS", "KOTAKBANK.NS", "SBIN.NS",
          "AXISBANK.NS", "ITC.NS", "BHARTIARTL.NS", "ASIANPAINT.NS", "HINDUNILVR.NS", "BAJFINANCE.NS", "WIPRO.NS",
          "ULTRACEMCO.NS", "HCLTECH.NS", "MARUTI.NS", "TECHM.NS", "SUNPHARMA.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS",
          "TITAN.NS", "GRASIM.NS", "BPCL.NS", "DIVISLAB.NS", "NESTLEIND.NS", "JSWSTEEL.NS", "BAJAJFINSV.NS"]

# Define Supertrend function
def calculate_supertrend(df, period=14, multiplier=3):
    hl2 = (df['High'] + df['Low']) / 2
    atr = ta.ATR(df['High'], df['Low'], df['Close'], timeperiod=period)
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)
    
    supertrend = np.zeros(len(df))
    for i in range(1, len(df)):
        if df['Close'][i] > upperband[i-1]:
            supertrend[i] = upperband[i]
        elif df['Close'][i] < lowerband[i-1]:
            supertrend[i] = lowerband[i]
        else:
            supertrend[i] = supertrend[i-1]
    
    return supertrend

# Define MACD function
def calculate_macd(df, fastperiod=12, slowperiod=26, signalperiod=9):
    macd, macdsignal, macdhist = ta.MACD(df['Close'], fastperiod=fastperiod, slowperiod=slowperiod, signalperiod=signalperiod)
    return macd, macdsignal

# Define VWAP function
def calculate_vwap(df):
    vwap = (df['Volume'] * (df['High'] + df['Low'] + df['Close']) / 3).cumsum() / df['Volume'].cumsum()
    return vwap

# Volume Breakout Strategy
def calculate_volume_breakout(df, period=20):
    avg_volume = df['Volume'].rolling(window=period).mean()
    volume_breakout = df['Volume'] > (1.5 * avg_volume)
    return volume_breakout

def check_signal(stock):
    df = yf.download(stock, period="2d", interval="5m")
    if len(df) < 2:
        return None

    supertrend = calculate_supertrend(df)
    macd, macdsignal = calculate_macd(df)
    vwap = calculate_vwap(df)
    volume_breakout = calculate_volume_breakout(df)

    last_close = df["Close"].iloc[-1]
    prev_close = df["Close"].iloc[-2]
    
    # Supertrend condition: If the current price is above the Supertrend, consider it a buy signal
    supertrend_signal = last_close > supertrend[-1]
    
    # MACD condition: MACD line crosses above signal line
    macd_signal = macd[-1] > macdsignal[-1]
    
    # VWAP condition: Price above VWAP indicates an uptrend
    vwap_signal = last_close > vwap[-1]
    
    # Volume breakout condition: Volume is higher than the average
    volume_signal = volume_breakout[-1]
    
    # Combine all signals
    if supertrend_signal and macd_signal and vwap_signal and volume_signal:
        return {"stock": stock.split(".")[0], "entry": round(prev_close, 2), "target": round(last_close * 1.02, 2), "type": "BUY"}
    elif not supertrend_signal and not macd_signal and not vwap_signal and not volume_signal:
        return {"stock": stock.split(".")[0], "entry": round(prev_close, 2), "target": round(last_close * 0.98, 2), "type": "SELL"}
    
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
                msg = f"[{signal['type']} SIGNAL - {signal['stock']}]\nTarget: ₹{signal['target']}\nEntry: ₹{signal['entry']}\nSignal time: {time_now}\nTime: {time_now} (IST)"
                send_to_telegram(msg)

        # No signal logic
        if not found_signal:
            current_time = time.time()
            if current_time - last_no_signal_time >= 3600:
                time_now = get_ist_time()
                send_to_telegram(f"[NO SIGNAL]\nKono stock e signal hit koreni.\nTime: {time_now} (IST)")
                last_no_signal_time = current_time

        time.sleep(300)  # Wait 5 mins before next scan

if __name__ == "__main__":
    run_bot()

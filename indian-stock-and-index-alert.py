import time  
import yfinance as yf  
import requests  
import logging  
from datetime import datetime  
import pytz  
import ssl  
import certifi  
import os  
from keep_alive import keep_alive  
  
keep_alive()  
  
# SSL cert path set  
os.environ['SSL_CERT_FILE'] = certifi.where()  
  
# Telegram Bot Config  
TELEGRAM_BOT_TOKEN = "8100205821:AAE0sGJhnA8ySkuSusEXSf9bYU5OU6sFzVg"  
TELEGRAM_CHAT_ID = "@swingtreadingnsmartbot"  
  
# Top 45 Indian Stocks (NSE Symbols)  
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
  
ALL_SYMBOLS = INDIAN_STOCKS  
  
timeframes = {  
    "Intraday 15m": "15m",  
    "Intraday 30m": "30m"  
}  
  
active_trades = {}  
last_signal_time = time.time()  
  
logging.basicConfig(filename="trade_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")  
  
def send_telegram_message(message, chat_id):  
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"  
    data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}  
    try:  
        response = requests.post(url, data=data)  
        if response.status_code != 200:  
            print(f"Telegram error: {response.text}")  
    except Exception as e:  
        print(f"Telegram send failed: {e}")  
  
def fetch_data(symbol, tf):  
    try:  
        df = yf.download(tickers=symbol, period="2d", interval=tf)  
        df.reset_index(inplace=True)  
        df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)  
        df = df[['Datetime' if 'Datetime' in df.columns else 'Date', 'open', 'high', 'low', 'close', 'volume']]  
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']  
        return df  
    except Exception as e:  
        logging.error(f"Error fetching {symbol} - {e}")  
        return None  
  
def calculate_vwap(df):  
    df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()  
    return df  
  
def liquidity_grab_with_vwap(df):  
    df = calculate_vwap(df)  
    df['high_shift'] = df['high'].shift(1)  
    df['low_shift'] = df['low'].shift(1)  
      
    liquidity_grab = (df['high'] > df['high_shift']) & (df['low'] < df['low_shift'])  
      
    close_above_vwap = df['close'] > df['vwap']  
    close_below_vwap = df['close'] < df['vwap']  
  
    if liquidity_grab.iloc[-1] and close_above_vwap.iloc[-1]:  
        entry = round(df['close'].iloc[-1], 2)  
        sl = round(df['low'].iloc[-2], 2)  
        tp = round(entry + (entry - sl) * 2, 2)  
        tsl = round(entry + (entry - sl) * 1.5, 2)  
        return "BUY", entry, sl, tp, tsl, "\U0001F7E2"  
    elif liquidity_grab.iloc[-1] and close_below_vwap.iloc[-1]:  
        entry = round(df['close'].iloc[-1], 2)  
        sl = round(df['high'].iloc[-2], 2)  
        tp = round(entry - (sl - entry) * 2, 2)  
        tsl = round(entry - (sl - entry) * 1.5, 2)  
        return "SELL", entry, sl, tp, tsl, "\U0001F534"  
      
    return "NO SIGNAL", None, None, None, None, None  
  
kolkata_tz = pytz.timezone("Asia/Kolkata")  
  
while True:  
    signal_found = False  
  
    for stock in ALL_SYMBOLS:  
        if stock in active_trades:  
            df = fetch_data(stock, "15m")  
            if df is not None and not df.empty:  
                last_price = df['close'].iloc[-1]  
                trade = active_trades[stock]  
                now_time = datetime.now(kolkata_tz).strftime('%Y-%m-%d %H:%M')  
  
                if trade['direction'] == "BUY" and last_price >= trade['tp']:  
                    send_telegram_message(f"✅ *TP HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`\nSignal: BUY", TELEGRAM_CHAT_ID)  
                    del active_trades[stock]  
                elif trade['direction'] == "BUY" and last_price <= trade['sl']:  
                    send_telegram_message(f"🛑 *SL HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`\nSignal: BUY", TELEGRAM_CHAT_ID)  
                    del active_trades[stock]  
                elif trade['direction'] == "SELL" and last_price <= trade['tp']:  
                    send_telegram_message(f"✅ *TP HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`\nSignal: SELL", TELEGRAM_CHAT_ID)  
                    del active_trades[stock]  
                elif trade['direction'] == "SELL" and last_price >= trade['sl']:  
                    send_telegram_message(f"🛑 *SL HIT for {stock}*\nTime: `{now_time}`\nPrice: `{last_price}`\nSignal: SELL", TELEGRAM_CHAT_ID)  
                    del active_trades[stock]  
            continue  
  
        for label, tf in timeframes.items():  
            df = fetch_data(stock, tf)  
            if df is not None and not df.empty:  
                signal, entry, sl, tp, tsl, emoji = liquidity_grab_with_vwap(df)  
                if signal != "NO SIGNAL":  
                    signal_time = datetime.now(kolkata_tz).strftime('%Y-%m-%d %H:%M:%S')  
                    msg = (  
                        f"{emoji} *{signal} Signal for {stock}*\n"  
                        f"Type: {label}\nTimeframe: {tf}\nTime: `{signal_time}`\n"  
                        f"Entry: `{entry}`\nSL: `{sl}`\nTP: `{tp}`\nTSL: `{tsl}`"  
                    )  
                    send_telegram_message(msg, TELEGRAM_CHAT_ID)  
  
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
        send_telegram_message("⚠️ No Signal in the Last 1 Hour (Indian Stocks)", TELEGRAM_CHAT_ID)  
        last_signal_time = time.time()  
  
    time.sleep(60)  
    print("Bot is running 24/7!") 

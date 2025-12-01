import time
from datetime import datetime, timezone
import requests
import pandas as pd
import yfinance as yf
import math
from typing import Optional, Dict
# Flask ইমপোর্ট করুন
from flask import Flask
import threading

# =========================
# --- ১. ডাইরেক্ট টেলিগ্রাম সেটিংস (পরিবর্তন করুন) ---
# =========================
# IMPORTANT: আপনার আসল টোকেন এবং আইডি ব্যবহার করুন
TELEGRAM_BOT_TOKEN = "8537811183:AAF4DWeA5Sks86mBISJvS1iNvLRpkY_FgnA"
TELEGRAM_CHAT_ID = "8191014589"

SEND_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# কয়েন এবং সেটিংস
COINS = [
    "BTC-USD","ETH-USD","SOL-USD","BNB-USD",
    "XRP-USD","DOGE-USD","AVAX-USD","LINK-USD"
]

TF_DIR = "1h"      # HTF (আগে 1h ছিল, এটি 1h/15m সেটআপের জন্য ব্যবহৃত হবে)
TF_ENTRY = "15m"   # LTF
EMA_PERIOD = 200
ATR_PERIOD = 14
TP_PERCENT = [1.5, 3.0, 5.0]  # TP1, TP2, TP3
MAX_SL = 5.0                  # Max SL fallback 
CHECK_INTERVAL_MIN = 15       # 15m ক্যান্ডেলের জন্য উপযুক্ত সাইকেল টাইম

# ট্র্যাকিং ভেরিয়েবল
LAST_ALERT_TIME: Dict[str, Optional[float]] = {} # শেষ এন্ট্রি প্রাইস ট্র্যাক করার জন্য

# ===============================
# --- ২. টেলিগ্রাম সেন্ডার ---
# ===============================
def send_telegram(msg):
    """HTML ফরম্যাটে টেলিগ্রামে মেসেজ পাঠায়"""
    try:
        r = requests.post(
            SEND_URL,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        )
        if r.status_code != 200:
            print("Telegram error:", r.text)
    except Exception as e:
        print("Telegram exception:", e)


# ===============================
# --- ৩. ডেটা ফেচ (আপনার কার্যকরী ফাংশন) ---
# ===============================
def get_data(ticker, interval, period):
    """নিরাপদে yfinance থেকে ডেটা ডাউনলোড করে কলামগুলিকে ছোট করে"""
    try:
        df = yf.download(ticker, interval=interval, period=period, auto_adjust=False, progress=False)
        if df is None or df.empty:
            return None
        # শুধুমাত্র প্রয়োজনীয় কলামগুলি নেওয়া এবং কলাম নাম ছোট করা
        df = df[['Open','High','Low','Close','Volume']]
        df.columns = ['open','high','low','close','volume']
        df = df.dropna()
        df.index = pd.to_datetime(df.index, utc=True)
        return df
    except Exception as e:
        # print("Data fetch error:", ticker, e) # অতিরিক্ত প্রিন্ট এড়াতে কমেন্ট আউট
        return None

# ===============================
# --- ৪. SMC ইন্ডিকেটর এবং লজিক (পূর্বের কোড থেকে) ---
# ===============================

def add_indicators(df):
    df["ema200"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = (df['high'] - df['close'].shift()).abs()
    df['tr3'] = (df['low'] - df['close'].shift()).abs()
    df['TR'] = df[['tr1','tr2','tr3']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=ATR_PERIOD, min_periods=1).mean()
    df['body'] = (df['close'] - df['open'])
    df['range'] = (df['high'] - df['low']).abs().replace(0, 0.0000001)
    return df

def round_price(p):
    # দাম রাউন্ড করার সঠিক ফাংশন
    if p >= 10: return round(p, 3)
    elif p >= 1: return round(p, 4)
    else: return round(p, 6)
    
def find_recent_impulse_and_ob(df_htf):
    d = df_htf.tail(40).copy()
    if len(d) < 2: return None, None
    if 'body' not in d.columns: return None, None
    d['abs_body'] = d['body'].abs()
    imp_idx = d['abs_body'].idxmax()
    try:
        imp = d.loc[imp_idx]
        pos = d.index.get_loc(imp_idx)
        if pos == 0: return None, None
        ob = d.iloc[pos - 1]
        return ob, imp
    except Exception:
        return None, None

def detect_fvg(df_htf):
    arr = df_htf.tail(50)
    arr_idx = arr.index.tolist()
    for i in range(len(arr_idx) - 2):
        c1 = arr.iloc[i]
        c3 = arr.iloc[i+2]
        if c1['high'] < c3['low']:
            return 'bull', (c1['high'], c3['low'])
        if c1['low'] > c3['high']:
            return 'bear', (c3['high'], c1['low'])
    return None, None

def market_structure_shift(df_htf):
    s = df_htf['close'].tail(8)
    if len(s) < 4: return None
    highs = df_htf['high'].tail(8)
    lows = df_htf['low'].tail(8)
    if lows.iloc[-1] > lows.iloc[-3] and highs.iloc[-1] > highs.iloc[-3]:
        return 'bull'
    if highs.iloc[-1] < highs.iloc[-3] and lows.iloc[-1] < lows.iloc[-3]:
        return 'bear'
    return None

# ===============================
# --- ৫. ডিটেকশন লজিক (SMC) ---
# ===============================
def detect_signal(df_dir, df_entry, coin_name):

    df_dir = add_indicators(df_dir)
    df_entry = add_indicators(df_entry)
    
    if df_dir.empty or df_entry.empty: return None

    # ১. ট্রেন্ড (EMA 200)
    trend = "bull" if df_dir["close"].iloc[-1] > df_dir["ema200"].iloc[-1] else "bear"
    
    # ২. OB এবং FVG ডিটেকশন
    ob_candle, imp_candle = find_recent_impulse_and_ob(df_dir)
    fvg_side, fvg_zone = detect_fvg(df_dir)
    ms = market_structure_shift(df_dir)
    
    if ob_candle is None or imp_candle is None: return None
    
    ob_top = max(ob_candle['open'], ob_candle['high'], ob_candle['close'])
    ob_bottom = min(ob_candle['open'], ob_candle['low'], ob_candle['close'])
    ob_zone = (ob_bottom, ob_top)

    cur = df_entry.iloc[-1]
    price = cur['close']
    atr = df_entry['ATR'].iloc[-1] if 'ATR' in df_entry.columns and not math.isnan(df_entry['ATR'].iloc[-1]) and df_entry['ATR'].iloc[-1] > 0 else None
    
    entry, side, sl, reason = None, None, None, []
    
    # ৩. এন্ট্রি লজিক: OB Retest/Rejection
    recent = df_entry.tail(2) 
    for idx in reversed(recent.index.tolist()):
        row = df_entry.loc[idx]
        touched = (row['low'] <= ob_zone[1] and row['high'] >= ob_zone[0])
        if not touched: continue
        
        lower_wick = (row['open'] - row['low']) if row['open'] > row['close'] else (row['close'] - row['low'])
        upper_wick = (row['high'] - row['open']) if row['open'] > row['close'] else (row['high'] - row['close'])
        
        if trend == 'bull' and lower_wick > 0.45 * row['range'] and price > ob_zone[0]:
            entry = price
            side = 'long'
            sl = ob_zone[0] - 0.2 * atr if atr else entry * 0.995
            reason.append("OB Retest + Bullish Rejection")
            break
        
        if trend == 'bear' and upper_wick > 0.45 * row['range'] and price < ob_zone[1]:
            entry = price
            side = 'short'
            sl = ob_zone[1] + 0.2 * atr if atr else entry * 1.005
            reason.append("OB Retest + Bearish Rejection")
            break

    # ৪. এন্ট্রি লজিক: FVG Fill
    if entry is None and fvg_side and ms:
        if fvg_side == 'bull' and trend == 'bull' and (fvg_zone[0] <= price <= fvg_zone[1]):
            entry = price
            side = 'long'
            sl = ob_zone[0] - 0.25 * atr if atr else entry * 0.995
            reason.append("FVG Fill + HTF Bull")
        if fvg_side == 'bear' and trend == 'bear' and (fvg_zone[0] <= price <= fvg_zone[1]):
            entry = price
            side = 'short'
            sl = ob_zone[1] + 0.25 * atr if atr else entry * 1.005
            reason.append("FVG Fill + HTF Bear")

    if entry is None: return None
    if ms is not None and ((ms=='bull' and side=='long') or (ms=='bear' and side=='short')):
        reason.append("MS Shift")
        
    # ৫. SL এবং TP ক্যালকুলেশন
    sl_pct = abs((entry - sl) / entry * 100)
    if sl_pct > MAX_SL or sl_pct < 0.2: return None

    # TPs
    tps = []
    for p in TP_PERCENT:
        if side == "long":
            tps.append(round_price(entry * (1 + p/100)))
        else:
            tps.append(round_price(entry * (1 - p/100)))

    rr1 = abs((tps[0] - entry) / (entry - sl)) if entry != sl else None
    if rr1 is None or rr1 < 1.5: return None 

    return {
        "side": side.upper(),
        "entry": round_price(entry),
        "sl": round_price(sl),
        "tps": tps,
        "trend": trend.upper(),
        "reason": ", ".join(reason)
    }


# ===============================
# --- ৬. ফরম্যাট অ্যালার্ট ---
# ===============================
def format_alert(ticker, sig):
    """HTML ফরম্যাটে অ্যালার্ট মেসেজ তৈরি করে"""
    emoji = "🔵 LONG" if sig["side"]=="LONG" else "🔴 SHORT"
    
    # entry প্রাইসকে ট্র্যাকিং কী হিসাবে ব্যবহার করা হবে
    entry_price_key = sig["entry"]
    
    msg = f"""
<b>🔥 SMC INTRADAY SIGNAL DETECTED 🔥</b>

PAIR: <b>{ticker}</b> ({TF_DIR}/{TF_ENTRY})
SIDE: {emoji}
TREND: {sig['trend']}
REASON: {sig['reason']}

Entry: <b>{entry_price_key}</b>
SL: <b>{sig['sl']}</b> (Max {MAX_SL}%)

TP1 ({TP_PERCENT[0]}%): {sig['tps'][0]}
TP2 ({TP_PERCENT[1]}%): {sig['tps'][1]}
TP3 ({TP_PERCENT[2]}%): {sig['tps'][2]}

⏳ Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""
    return msg, entry_price_key


# ===============================
# --- ৭. TRADING MAIN লুপ ---
# ===============================
def main():
    global LAST_ALERT_TIME
    
    # LAST_ALERT_TIME ইনিশিয়ালাইজ করা
    for coin in COINS:
        LAST_ALERT_TIME[coin] = 0.0

    send_telegram(f"🚀 SMC Intraday Bot Started. Checking {len(COINS)} coins every {CHECK_INTERVAL_MIN} min.")

    while True:
        cycle_start = time.time()

        for coin in COINS:
            try:
                # ডেটা ফেচ (long period for direction, short period for entry)
                df_dir = get_data(coin, TF_DIR, "90d")
                df_entry = get_data(coin, TF_ENTRY, "30d")

                if df_dir is None or df_entry is None or df_dir.empty or df_entry.empty:
                    # print(f"No valid data for {coin}") # ডিবাগিং এর জন্য কমেন্ট আউট
                    continue

                sig = detect_signal(df_dir, df_entry, coin)
                
                if sig:
                    entry_price = sig['entry']
                    
                    # ডুপ্লিকেট সিগন্যাল চেক: যদি এন্ট্রি প্রাইস প্রায় একই হয় (0.01% এর কম পার্থক্য)
                    if abs(entry_price - LAST_ALERT_TIME.get(coin, 0.0)) / entry_price * 100 < 0.01:
                        # print(f"Duplicate signal detected for {coin} at {entry_price}. Skipping.")
                        continue

                    # নতুন সিগন্যাল
                    msg, entry_key = format_alert(coin, sig)
                    send_telegram(msg)
                    LAST_ALERT_TIME[coin] = entry_price
                    print(f"Sent NEW signal for {coin} at {entry_price}")

            except Exception as e:
                print("Error processing", coin, e)

        # স্লিভ টাইম গণনা
        sleep_time = max(60, CHECK_INTERVAL_MIN*60 - (time.time() - cycle_start))
        print("Sleeping", int(sleep_time), "sec")
        time.sleep(sleep_time)


# ===============================
# --- ৮. KEEP-ALIVE WEB SERVER (Flask) ---
# ===============================

# Flask অ্যাপ তৈরি করুন
app = Flask(__name__)

# রুট (route) তৈরি করুন যা Replit চেক করবে
@app.route('/')
def home():
    """স্বাস্থ্য পরীক্ষা (Health Check) এর জন্য একটি সাধারণ উত্তর দেয়"""
    return "SMC Bot is running!", 200

# থ্রেড ব্যবহার করে Flask সার্ভারটি চালু করার ফাংশন
def run_flask_server():
    # Replit এ চালানোর জন্য '0.0.0.0' ব্যবহার করা প্রয়োজন
    # PORT টি Replit স্বয়ংক্রিয়ভাবে পরিবেশ ভেরিয়েবল (Environment Variable) থেকে সেট করে, 
    # তাই এটি 8080 বা os.environ.get('PORT') হওয়া উচিত। 
    # Replit সাধারণত PORT Environment Variable ব্যবহার করে।
    app.run(host='0.0.0.0', port=8080, debug=False)


# ===============================
# --- ৯. স্টার্টিং পয়েন্ট ---
# ===============================
if __name__ == "__main__":
    # ১. Flask সার্ভারটি একটি নতুন থ্রেডে চালু করুন
    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.start()
    print("Flask Keep-Alive server started.")

    # ২. প্রধান ট্রেডিং লুপটি চালু করুন
    main()


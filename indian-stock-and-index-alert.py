import time
from datetime import datetime, timezone
import requests
import pandas as pd
import yfinance as yf
import math
from typing import Optional, Dict
import numpy as np # numpy ইমপোর্ট করা হয়েছে ATR ক্যালকুলেশনের জন্য
from flask import Flask
import threading

# =========================
# --- ১. ডাইরেক্ট টেলিগ্রাম সেটিংস (পরিবর্তন করুন) ---
# =========================
TELEGRAM_BOT_TOKEN = "8537811183:AAF4DWeA5Sks86mBISJvS1iNvLRpkY_FgnA"
TELEGRAM_CHAT_ID = "8191014589"

SEND_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# কয়েন এবং সেটিংস
COINS = [
    "BTC-USD","ETH-USD","SOL-USD","BNB-USD",
    "XRP-USD","DOGE-USD","AVAX-USD","LINK-USD"
]

TF_DIR = "1h"      # HTF (Higher Timeframe)
TF_ENTRY = "15m"   # LTF (Lower Timeframe)
EMA_PERIOD = 200
ATR_PERIOD = 14
TP_PERCENT = [1.5, 3.0, 5.0]  # TP1, TP2, TP3 (R:R 1.5 এর বেশি নিশ্চিত করার জন্য)
MAX_SL = 5.0                  # Max SL fallback 
CHECK_INTERVAL_MIN = 15       # 15m ক্যান্ডেলের জন্য উপযুক্ত সাইকেল টাইম

# ট্র্যাকিং ভেরিয়েবল
# শেষ এন্ট্রি প্রাইস ট্র্যাক করার জন্য (ডুপ্লিকেট এড়াতে)
LAST_ENTRY_PRICE: Dict[str, float] = {} 

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
# --- ৩. ডেটা ফেচ ---
# ===============================
def get_data(ticker, interval, period):
    """নিরাপদে yfinance থেকে ডেটা ডাউনলোড করে কলামগুলিকে ছোট করে"""
    try:
        df = yf.download(ticker, interval=interval, period=period, auto_adjust=False, progress=False)
        if df is None or df.empty:
            return None
        df = df[['Open','High','Low','Close','Volume']]
        df.columns = ['open','high','low','close','volume']
        df = df.dropna()
        df.index = pd.to_datetime(df.index, utc=True)
        return df
    except Exception as e:
        return None

# ===============================
# --- ৪. SMC ইন্ডিকেটর এবং ইউটিলিটি ফাংশন ---
# ===============================

def add_indicators(df):
    """EMA, ATR, এবং বডি/রেঞ্জ যোগ করে"""
    df["ema200"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    
    # ATR ক্যালকুলেশন
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(span=ATR_PERIOD, adjust=False).mean()

    df['body'] = (df['close'] - df['open'])
    df['range'] = (df['high'] - df['low']).abs().replace(0, 0.0000001)
    return df

def round_price(p):
    """দামকে তার মানের উপর ভিত্তি করে রাউন্ড করে"""
    if p >= 1000: return round(p, 2)
    elif p >= 10: return round(p, 3)
    elif p >= 1: return round(p, 4)
    else: return round(p, 6)
    
def find_recent_impulse_and_ob(df_htf):
    """সাম্প্রতিকতম অর্ডার ব্লক (OB) এবং ইমপালস ক্যান্ডেল খুঁজে বের করে"""
    d = df_htf.tail(40).copy()
    if len(d) < 2: return None, None
    d['abs_body'] = d['body'].abs()
    
    # শেষ 5টি ক্যান্ডেলের মধ্যে সবচেয়ে বড় বডি খুঁজে বের করা
    imp_idx = d.iloc[-5:]['abs_body'].idxmax()
    
    try:
        imp = d.loc[imp_idx]
        pos = d.index.get_loc(imp_idx)
        # OB টি অবশ্যই ইমপালস ক্যান্ডেলের ঠিক আগেরটি হতে হবে
        if pos == 0: return None, None
        ob = d.iloc[pos - 1]
        return ob, imp
    except Exception:
        return None, None

# --- সংশোধিত FVG লজিক ---
def detect_fvg(df_htf):
    """শুধুমাত্র সর্বশেষ 3টি ক্যান্ডেলের FVG সনাক্ত করে (C1 H < C3 L)"""
    arr = df_htf.tail(3) 
    if len(arr) < 3: return None, None
    
    c1 = arr.iloc[0] # ক্যান্ডেল 1
    c3 = arr.iloc[2] # ক্যান্ডেল 3
    
    # Bullish FVG: C1 High < C3 Low
    if c1['high'] < c3['low']:
        # FVG এর জোন: C1 হাই থেকে C3 লো
        return 'bull', (c1['high'], c3['low']) 
    
    # Bearish FVG: C1 Low > C3 High
    if c1['low'] > c3['high']:
        # FVG এর জোন: C3 হাই থেকে C1 লো
        return 'bear', (c3['high'], c1['low']) 

    return None, None

# --- সংশোধিত MSS লজিক ---
def market_structure_shift(df_htf):
    """সর্বশেষ সুইং হাই/লো ভাঙা হয়েছে কিনা তা পরীক্ষা করে"""
    df = df_htf.tail(8) 
    if len(df) < 8: return None
    
    # শেষ 6টি ক্যান্ডেলের মধ্যে সুইং হাই এবং লো সনাক্ত করা 
    recent_high = df.iloc[-6:-1]['high'].max()
    recent_low = df.iloc[-6:-1]['low'].min()

    cur = df.iloc[-1] 

    # Bullish MSS: যদি কারেন্ট ক্লোজ সাম্প্রতিক হাই ভেঙ্গে যায়
    if cur['close'] > recent_high and df.iloc[-2]['close'] < recent_high:
        return 'bull'
    
    # Bearish MSS: যদি কারেন্ট ক্লোজ সাম্প্রতিক লো ভেঙ্গে যায়
    if cur['close'] < recent_low and df.iloc[-2]['close'] > recent_low:
        return 'bear'
        
    return None

# ===============================
# --- ৫. ডিটেকশন লজিক (SMC) ---
# ===============================
def detect_signal(df_dir, df_entry, coin_name):

    df_dir = add_indicators(df_dir)
    df_entry = add_indicators(df_entry)
    
    if df_dir.empty or df_entry.empty: return None

    # ১. ট্রেন্ড (EMA 200 - HTF)
    trend = "bull" if df_dir["close"].iloc[-1] > df_dir["ema200"].iloc[-1] else "bear"
    
    # ২. OB, FVG, MSS ডিটেকশন (HTF)
    ob_candle, imp_candle = find_recent_impulse_and_ob(df_dir)
    fvg_side, fvg_zone = detect_fvg(df_dir)
    ms = market_structure_shift(df_dir)
    
    if ob_candle is None or imp_candle is None: return None
    
    ob_top = max(ob_candle['open'], ob_candle['high'], ob_candle['close'])
    ob_bottom = min(ob_candle['open'], ob_candle['low'], ob_candle['close'])
    ob_zone = (ob_bottom, ob_top)

    cur = df_entry.iloc[-1]
    price = cur['close']
    atr = df_entry['ATR'].iloc[-1] if 'ATR' in df_entry.columns and not math.isnan(df_entry['ATR'].iloc[-1]) and df_entry['ATR'].iloc[-1] > 0 else 0.0
    
    entry, side, sl, reason = None, None, None, []
    
    # ৩. এন্ট্রি লজিক: OB Retest/Rejection (LTF)
    # শেষ 2টি LTF ক্যান্ডেল চেক
    recent = df_entry.tail(2) 
    for idx in reversed(recent.index.tolist()):
        row = df_entry.loc[idx]
        # যদি LTF ক্যান্ডেলটি HTF OB জোনকে স্পর্শ করে
        touched = (row['low'] <= ob_zone[1] and row['high'] >= ob_zone[0])
        if not touched: continue
        
        # রিজেকশন ক্যান্ডেল সনাক্তকরণ (উইক বডির চেয়ে বড়)
        lower_wick = (row['open'] - row['low']) if row['open'] > row['close'] else (row['close'] - row['low'])
        upper_wick = (row['high'] - row['open']) if row['open'] > row['close'] else (row['high'] - row['close'])
        
        # লং এন্ট্রি: বুলিশ ট্রেন্ড, OB Rejection (নিচের উইক বড়) এবং দাম OB এর উপরে
        if trend == 'bull' and lower_wick > 0.4 * row['range'] and price > ob_zone[0]:
            entry = price
            side = 'long'
            sl = ob_zone[0] - 0.5 * atr if atr > 0 else entry * 0.995 # ATR ব্যবহার
            reason.append("OB Retest/Rej")
            break
        
        # শর্ট এন্ট্রি: বিয়ারিশ ট্রেন্ড, OB Rejection (উপরের উইক বড়) এবং দাম OB এর নিচে
        if trend == 'bear' and upper_wick > 0.4 * row['range'] and price < ob_zone[1]:
            entry = price
            side = 'short'
            sl = ob_zone[1] + 0.5 * atr if atr > 0 else entry * 1.005 # ATR ব্যবহার
            reason.append("OB Retest/Rej")
            break

    # ৪. এন্ট্রি লজিক: FVG Fill (যদি OB Retest না পাওয়া যায়)
    if entry is None and fvg_side and ms:
        # FVG জোন এবং বর্তমান দাম যদি ওভারল্যাপ করে
        fvg_touched = (fvg_zone[0] <= price <= fvg_zone[1])
        
        # লং এন্ট্রি: FVG বুলিশ, HTF ট্রেন্ড বুলিশ, MSS বুলিশ, এবং FVG টাচ
        if fvg_side == 'bull' and trend == 'bull' and ms == 'bull' and fvg_touched:
            entry = price
            side = 'long'
            sl = fvg_zone[0] - 0.75 * atr if atr > 0 else entry * 0.995
            reason.append("FVG Fill + MSS")
        
        # শর্ট এন্ট্রি: FVG বিয়ারিশ, HTF ট্রেন্ড বিয়ারিশ, MSS বিয়ারিশ, এবং FVG টাচ
        if fvg_side == 'bear' and trend == 'bear' and ms == 'bear' and fvg_touched:
            entry = price
            side = 'short'
            sl = fvg_zone[1] + 0.75 * atr if atr > 0 else entry * 1.005
            reason.append("FVG Fill + MSS")

    if entry is None: return None
        
    # ৫. SL এবং TP ক্যালকুলেশন
    sl_pct = abs((entry - sl) / entry * 100)
    # SL খুব বড় বা খুব ছোট হলে বাদ
    if sl_pct > MAX_SL or sl_pct < 0.1: return None

    # TPs (R:R ভিত্তিতে নয়, ফিক্সড পার্সেন্টেজ, যেহেতু আপনি কোডে TP_PERCENT ব্যবহার করেছেন)
    tps = []
    for p in TP_PERCENT:
        if side == "long":
            tps.append(round_price(entry * (1 + p/100)))
        else:
            tps.append(round_price(entry * (1 - p/100)))

    # নিশ্চিত করুন TP1 কমপক্ষে 1.5 R:R দিচ্ছে (R:R = TP1 দূরত্ব / SL দূরত্ব)
    risk_distance = abs(entry - sl)
    reward1_distance = abs(tps[0] - entry)
    rr1 = reward1_distance / risk_distance if risk_distance > 0 else 0
    
    if rr1 < 1.5: return None 

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
    
    # SL শতাংশ গণনা
    risk_pct = round(abs(sig['entry'] - sig['sl']) / sig['entry'] * 100, 2)
    
    # R:R গণনা
    risk = abs(sig['entry'] - sig['sl'])
    reward1 = abs(sig['tps'][0] - sig['entry'])
    rr1 = round(reward1 / risk, 2) if risk > 0 else "N/A"
    
    msg = f"""
<b>🔥 SMC INTRADAY SIGNAL DETECTED 🔥</b>

PAIR: <b>{ticker}</b> ({TF_DIR}/{TF_ENTRY})
SIDE: {emoji}
TREND: {sig['trend']}
REASON: <b>{sig['reason']}</b>

Entry: <b>{sig['entry']}</b>
SL: <b>{sig['sl']}</b> (Risk: {risk_pct}%)

TP1 ({TP_PERCENT[0]}%): {sig['tps'][0]} (R:R ~{rr1})
TP2 ({TP_PERCENT[1]}%): {sig['tps'][1]}
TP3 ({TP_PERCENT[2]}%): {sig['tps'][2]}

⏳ Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""
    return msg, sig['entry']


# ===============================
# --- ৭. TRADING MAIN লুপ ---
# ===============================
def main():
    global LAST_ENTRY_PRICE
    
    # LAST_ENTRY_PRICE ইনিশিয়ালাইজ করা
    for coin in COINS:
        LAST_ENTRY_PRICE[coin] = 0.0

    send_telegram(f"🚀 SMC Intraday Bot Started. Checking {len(COINS)} coins every {CHECK_INTERVAL_MIN} min.")

    while True:
        cycle_start = time.time()

        for coin in COINS:
            try:
                # ডেটা ফেচ
                df_dir = get_data(coin, TF_DIR, "90d")
                df_entry = get_data(coin, TF_ENTRY, "30d")

                if df_dir is None or df_entry is None or df_dir.empty or df_entry.empty:
                    continue

                sig = detect_signal(df_dir, df_entry, coin)
                
                if sig:
                    entry_price = sig['entry']
                    
                    # ডুপ্লিকেট সিগন্যাল চেক: যদি এন্ট্রি প্রাইস প্রায় একই হয় (0.01% এর কম পার্থক্য)
                    if abs(entry_price - LAST_ENTRY_PRICE.get(coin, 0.0)) / entry_price * 100 < 0.01:
                        continue

                    # নতুন সিগন্যাল
                    msg, entry_key = format_alert(coin, sig)
                    send_telegram(msg)
                    LAST_ENTRY_PRICE[coin] = entry_price
                    print(f"Sent NEW signal for {coin} at {entry_price}. Reason: {sig['reason']}")

            except Exception as e:
                print("Error processing", coin, e)

        # স্লিভ টাইম গণনা
        cycle_duration = time.time() - cycle_start
        sleep_time = max(60, CHECK_INTERVAL_MIN*60 - cycle_duration)
        print(f"Cycle finished in {round(cycle_duration, 2)}s. Sleeping {int(sleep_time)} sec.")
        time.sleep(sleep_time)


# ===============================
# --- ৮. KEEP-ALIVE WEB SERVER (Flask) ---
# ===============================

app = Flask(__name__)

@app.route('/')
def home():
    """স্বাস্থ্য পরীক্ষা (Health Check) এর জন্য একটি সাধারণ উত্তর দেয়"""
    return "SMC Bot is running!", 200

def run_flask_server():
    app.run(host='0.0.0.0', port=8080, debug=False)


# ===============================
# --- ৯. স্টার্টিং পয়েন্ট ---
# ===============================
if __name__ == "__main__":
    # ১. Flask সার্ভারটি একটি নতুন থ্রেডে চালু করুন
    flask_thread = threading.Thread(target=run_flask_server, daemon=True)
    flask_thread.start()
    print("Flask Keep-Alive server started.")

    # ২. প্রধান ট্রেডিং লুপটি চালু করুন
    main()
    

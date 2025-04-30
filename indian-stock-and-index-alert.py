# প্রয়োজনীয় লাইব্রেরি ইমপোর্ট করো
import yfinance as yf
import pandas as pd
import requests

# Telegram Bot এর Token আর Chat ID বসাও
TELEGRAM_TOKEN = 'তোমার_বট_টোকেন'
TELEGRAM_CHAT_ID = 'তোমার_চ্যাট_আইডি'

# Telegram এ মেসেজ পাঠানোর ফাংশন
def send_telegram(msg):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram Error: {e}")

# টপ ১০ NSE স্টকের তালিকা
TOP_10_STOCKS = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS',
                 'SBIN.NS', 'ITC.NS', 'LT.NS', 'KOTAKBANK.NS', 'AXISBANK.NS']

# টাইমফ্রেম সেটিং
INTERVAL = '15m'
HIGHER_INTERVAL = '1h'
LOOKBACK = '2d'
RR = 2  # Risk Reward 1:2

# ডুপ্লিকেট সিগনাল আটকানোর জন্য ট্র্যাকার
active_signals = {}

# ডেটা আনো
def fetch_data(symbol, interval, period):
    try:
        data = yf.download(tickers=symbol, interval=interval, period=period, auto_adjust=False, progress=False)
        data.dropna(inplace=True)
        return data
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()

# ট্রেন্ড চেক করো (Simple MA Structure Filter)
def get_trend(df):
    ma20 = df['Close'].rolling(20).mean()
    if ma20.dropna().empty:
        return 'UNKNOWN'
    try:
        if df['Close'].iloc[-1] > ma20.iloc[-1]:
            return 'BULLISH'
        else:
            return 'BEARISH'
    except:
        return 'UNKNOWN'

# মূল স্ট্র্যাটেজি + ফিল্টার
def liquidity_grab_with_filters(df, trend):
    signal = None
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    recent_highs = df['High'][-12:-2]
    recent_lows = df['Low'][-12:-2]
    avg_volume = df['Volume'][-12:-2].mean()

    # BUY Signal
    if (prev['Low'] < recent_lows.min() and 
        latest['Close'] > prev['High'] and
        prev['Volume'] > avg_volume and
        trend == 'BULLISH'):

        signal = 'BUY'
        entry = latest['Close']
        sl = prev['Low']
        tp = entry + (entry - sl) * RR

    # SELL Signal
    elif (prev['High'] > recent_highs.max() and 
          latest['Close'] < prev['Low'] and
          prev['Volume'] > avg_volume and
          trend == 'BEARISH'):

        signal = 'SELL'
        entry = latest['Close']
        sl = prev['High']
        tp = entry - (sl - entry) * RR

    else:
        return None

    return {'signal': signal, 'entry': entry, 'sl': sl, 'tp': tp}

# স্ক্যান চালাও
for stock in TOP_10_STOCKS:
    df_15m = fetch_data(stock, INTERVAL, LOOKBACK)
    df_1h = fetch_data(stock, HIGHER_INTERVAL, LOOKBACK)

    if df_15m.empty or df_1h.empty:
        continue

    trend = get_trend(df_1h)

    if trend == 'UNKNOWN':
        continue

    if stock in active_signals:
        continue  # পুরনো সিগনাল হলে স্কিপ করো

    result = liquidity_grab_with_filters(df_15m, trend)

    if result:
        msg = f"{stock} - {result['signal']} Signal\nTrend: {trend}\nEntry: {result['entry']:.2f}\nSL: {result['sl']:.2f}\nTP: {result['tp']:.2f}"
        send_telegram(msg)
        active_signals[stock] = result

print("Scan complete. Signals sent to Telegram if any matched.")

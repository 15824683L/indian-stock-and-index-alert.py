import yfinance as yf
import pandas as pd
import logging
import time

def fetch_data(symbol, tf):
    try:
        df = yf.download(tickers=symbol, period="2d", interval=tf, progress=False)
        if df.empty:
            logging.warning(f"No data found for {symbol} with tf {tf}")
            return None
        df.reset_index(inplace=True)
        df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
        # যদি 'Datetime' না থাকে তাহলে 'Date' ধরে নাও
        time_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
        df = df[[time_col, 'open', 'high', 'low', 'close', 'volume']]
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        return df
    except Exception as e:
        logging.error(f"Error fetching {symbol} - {e}")
        return None

def main_loop():
    symbols = ['BTC-USD', 'ETH-USD', 'BNB-USD']  # চাইলে এখানে আরও যোগ করো
    timeframes = ['1h', '4h']

    while True:
        for symbol in symbols:
            for tf in timeframes:
                df = fetch_data(symbol, tf)
                if df is not None:
                    print(f"Data for {symbol} ({tf}):")
                    print(df.tail(2))  # শুধু শেষ ২টি ক্যান্ডেল দেখাও
                else:
                    print(f"Could not fetch data for {symbol} ({tf})")
        print("Waiting for next cycle...\n", flush=True)
        time.sleep(60)  # প্রতি ১ মিনিট পরপর আবার ডেটা চেক করবে

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Bot is running 24/7!", flush=True)
    main_loop()

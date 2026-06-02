import os
import time
import ccxt
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

st.set_page_config(page_title="Crypto AI Signal Analyzer", layout="wide")

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
exchange = ccxt.binance({"enableRateLimit": True})


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10
        )
    except Exception as e:
        st.warning(f"Telegram hiba: {e}")


def get_data(symbol, timeframe, limit=250):
    data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df


def analyze_coin(symbol, timeframe, account_size, risk_percent, max_position_size):
    df = get_data(symbol, timeframe)

    df["rsi"] = RSIIndicator(df["close"], window=14).rsi()
    df["ema20"] = EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema50"] = EMAIndicator(df["close"], window=50).ema_indicator()
    df["ema200"] = EMAIndicator(df["close"], window=200).ema_indicator()

    macd = MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()

    atr = AverageTrueRange(df["high"], df["low"], df["close"], window=14)
    df["atr"] = atr.average_true_range()

    df = df.dropna()
    last = df.iloc[-1]

    price = float(last["close"])
    rsi = float(last["rsi"])
    ema20 = float(last["ema20"])
    ema50 = float(last["ema50"])
    ema200 = float(last["ema200"])
    macd_value = float(last["macd"])
    macd_signal = float(last["macd_signal"])
    atr_value = float(last["atr"])

    score = 0
    score += 25 if price > ema200 else -25
    score += 25 if ema20 > ema50 else -25
    score += 20 if macd_value > macd_signal else -20

    if 45 <= rsi <= 65:
        score += 15
    elif rsi > 70:
        score -= 20
    elif rsi < 30:
        score -= 10

    if score >= 35:
        signal = "LONG"
        stop_loss = price - atr_value * 1.5
        tp1 = price + atr_value * 2
        tp2 = price + atr_value * 3
    elif score <= -35:
        signal = "SHORT"
        stop_loss = price + atr_value * 1.5
        tp1 = price - atr_value * 2
        tp2 = price - atr_value * 3
    else:
        signal = "WAIT"
        stop_loss = 0
        tp1 = 0
        tp2 = 0

    max_loss = account_size * (risk_percent / 100)

    if signal != "WAIT":
        risk_per_coin = abs(price - stop_loss)
        position_size = (max_loss / risk_per_coin) * price
        position_size = min(position_size, max_position_size)
    else:
        position_size = 0

    return {
        "Coin": symbol,
        "Timeframe": timeframe,
        "Price": round(price, 4),
        "RSI": round(rsi, 2),
        "Score": score,
        "Signal": signal,
        "Stop Loss": round(stop_loss, 4),
        "TP1": round(tp1, 4),
        "TP2": round(tp2, 4),
        "Max Loss USDT": round(max_loss, 2),
        "Position Size USDT": round(position_size, 2),
    }


st.title("🚀 Crypto AI Signal Analyzer")
st.write("BTC / ETH / SOL / BNB elemző rendszer Telegram jelzésekkel. Automatikus trade nincs.")

with st.sidebar:
    st.header("Beállítások")

    timeframe = st.selectbox("Idősík", ["5m", "15m", "30m", "1h", "2h", "4h"], index=1)

    account_size = st.number_input("Számla mérete USDT", min_value=10.0, value=200.0, step=10.0)

    risk_percent = st.slider("Kockázat trade-enként %", min_value=0.5, max_value=5.0, value=1.0, step=0.5)

    max_position_size = st.number_input("Max pozíció méret USDT", min_value=10.0, value=50.0, step=10.0)

    auto_refresh = st.checkbox("Automatikus frissítés", value=False)

    refresh_seconds = st.selectbox("Frissítés gyakorisága", [30, 60, 120, 300], index=1)

    telegram_enabled = st.checkbox("Telegram signal küldés bekapcsolása", value=True)


if "last_signals" not in st.session_state:
    st.session_state.last_signals = {}

if st.button("Frissítés / Elemzés indítása") or auto_refresh:
    results = []

    with st.spinner("Adatok lekérése és elemzés..."):
        for coin in COINS:
            try:
                result = analyze_coin(
                    coin,
                    timeframe,
                    account_size,
                    risk_percent,
                    max_position_size
                )

                results.append(result)

                signal = result["Signal"]
                signal_key = f"{coin}_{timeframe}"
                previous_signal = st.session_state.last_signals.get(signal_key)

                if telegram_enabled and signal in ["LONG", "SHORT"] and previous_signal != signal:
                    emoji = "🟢" if signal == "LONG" else "🔴"

                    message = (
                        f"{emoji} {signal} SIGNAL\n\n"
                        f"Coin: {result['Coin']}\n"
                        f"Timeframe: {result['Timeframe']}\n"
                        f"Price: {result['Price']}\n"
                        f"RSI: {result['RSI']}\n"
                        f"Score: {result['Score']}\n\n"
                        f"Stop Loss: {result['Stop Loss']}\n"
                        f"TP1: {result['TP1']}\n"
                        f"TP2: {result['TP2']}\n\n"
                        f"Max Loss: {result['Max Loss USDT']} USDT\n"
                        f"Suggested Position: {result['Position Size USDT']} USDT\n\n"
                        f"⚠️ Ez csak jelzés, nem automatikus trade."
                    )

                    send_telegram(message)
                    st.session_state.last_signals[signal_key] = signal

            except Exception as e:
                results.append({
                    "Coin": coin,
                    "Timeframe": timeframe,
                    "Price": 0,
                    "RSI": 0,
                    "Score": 0,
                    "Signal": f"HIBA: {e}",
                    "Stop Loss": 0,
                    "TP1": 0,
                    "TP2": 0,
                    "Max Loss USDT": 0,
                    "Position Size USDT": 0,
                })

    st.dataframe(pd.DataFrame(results).astype(str), use_container_width=True)

    if auto_refresh:
        st.info(f"Automatikus frissítés {refresh_seconds} másodperc múlva...")
        time.sleep(refresh_seconds)
        st.rerun()

else:
    st.info("Kattints a Frissítés / Elemzés indítása gombra.")
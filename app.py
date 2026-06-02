import os
import time
import ccxt
import pandas as pd
import requests
import streamlit as st
from PIL import Image
from dotenv import load_dotenv
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange

load_dotenv()


def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name)


TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

st.set_page_config(
    page_title="Crypto Edge AI",
    page_icon="⚡",
    layout="wide"
)

st.markdown("""
<style>
.main {
    background-color: #0b0f19;
}
.header-box {
    text-align: center;
    padding: 25px;
}
.big-title {
    font-size: 62px;
    font-weight: 900;
    color: #ffffff;
    margin-bottom: 5px;
}
.subtitle {
    font-size: 22px;
    color: #b6c2d9;
}
.card {
    padding: 20px;
    border-radius: 18px;
    background: linear-gradient(135deg, #111827, #1f2937);
    border: 1px solid #334155;
    margin-bottom: 15px;
}
.green-card {
    padding: 18px;
    border-radius: 15px;
    background-color: #123d2a;
    border: 1px solid #22c55e;
    color: #bbf7d0;
    font-size: 18px;
}
.red-card {
    padding: 18px;
    border-radius: 15px;
    background-color: #3d1212;
    border: 1px solid #ef4444;
    color: #fecaca;
    font-size: 18px;
}
.wait-card {
    padding: 18px;
    border-radius: 15px;
    background-color: #3b3312;
    border: 1px solid #eab308;
    color: #fef3c7;
    font-size: 18px;
}
</style>
""", unsafe_allow_html=True)


TEXT = {
    "Magyar": {
        "title": "Crypto Edge AI",
        "subtitle": "Professzionális BTC / ETH / SOL / BNB jelzésfigyelő Telegram értesítéssel. Automatikus trade nincs.",
        "settings": "Beállítások",
        "timeframe": "Idősík",
        "account": "Számla mérete USDT",
        "risk": "Kockázat trade-enként %",
        "maxpos": "Max pozíció méret USDT",
        "auto": "Automatikus frissítés",
        "refresh": "Frissítés gyakorisága",
        "telegram": "Telegram signal küldés bekapcsolása",
        "button": "Frissítés / Elemzés indítása",
        "info": "Kattints a Frissítés / Elemzés indítása gombra.",
        "loading": "Adatok lekérése és elemzés...",
        "strong": "🏆 Erős jelzések",
        "full": "📊 Teljes elemzés",
    },
    "English": {
        "title": "Crypto Edge AI",
        "subtitle": "Professional BTC / ETH / SOL / BNB signal scanner with Telegram alerts. No automatic trading.",
        "settings": "Settings",
        "timeframe": "Timeframe",
        "account": "Account size USDT",
        "risk": "Risk per trade %",
        "maxpos": "Max position size USDT",
        "auto": "Auto refresh",
        "refresh": "Refresh interval",
        "telegram": "Enable Telegram signals",
        "button": "Start Refresh / Analysis",
        "info": "Click the Start Refresh / Analysis button.",
        "loading": "Fetching market data and analysing...",
        "strong": "🏆 Strong Signals",
        "full": "📊 Full Analysis",
    }
}


COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

exchange = ccxt.binanceus({
    "enableRateLimit": True
})


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
    score += 25 if macd_value > macd_signal else -25

    if 45 <= rsi <= 65:
        score += 10
    elif rsi > 70:
        score -= 15
    elif rsi < 30:
        score += 15

    if score >= 60:
        signal = "STRONG LONG"
        stop_loss = price - atr_value * 1.5
        tp1 = price + atr_value * 2
        tp2 = price + atr_value * 3
    elif score >= 35:
        signal = "LONG"
        stop_loss = price - atr_value * 1.5
        tp1 = price + atr_value * 2
        tp2 = price + atr_value * 3
    elif score <= -60:
        signal = "STRONG SHORT"
        stop_loss = price + atr_value * 1.5
        tp1 = price - atr_value * 2
        tp2 = price - atr_value * 3
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
        "EMA20": round(ema20, 4),
        "EMA50": round(ema50, 4),
        "EMA200": round(ema200, 4),
        "MACD": round(macd_value, 4),
        "MACD Signal": round(macd_signal, 4),
        "Score": score,
        "Signal": signal,
        "Stop Loss": round(stop_loss, 4),
        "TP1": round(tp1, 4),
        "TP2": round(tp2, 4),
        "Max Loss USDT": round(max_loss, 2),
        "Position Size USDT": round(position_size, 2),
    }


with st.sidebar:
    language = st.selectbox("Language / Nyelv", ["Magyar", "English"])
    t = TEXT[language]

    st.header(t["settings"])

    timeframe = st.selectbox(t["timeframe"], ["5m", "15m", "30m", "1h", "2h", "4h"], index=1)
    account_size = st.number_input(t["account"], min_value=10.0, value=200.0, step=10.0)
    risk_percent = st.slider(t["risk"], min_value=0.5, max_value=5.0, value=1.0, step=0.5)
    max_position_size = st.number_input(t["maxpos"], min_value=10.0, value=50.0, step=10.0)
    auto_refresh = st.checkbox(t["auto"], value=False)
    refresh_seconds = st.selectbox(t["refresh"], [30, 60, 120, 300], index=1)
    telegram_enabled = st.checkbox(t["telegram"], value=True)


try:
    logo = Image.open("logo.png")
    st.markdown("<div class='header-box'>", unsafe_allow_html=True)
    st.image(logo, width=320)
    st.markdown(
        f"""
        <div class="big-title">{t['title']}</div>
        <div class="subtitle">{t['subtitle']}</div>
        </div>
        """,
        unsafe_allow_html=True
    )
except Exception:
    st.markdown(
        f"""
        <div class="card">
            <div class="big-title">⚡ {t['title']}</div>
            <div class="subtitle">{t['subtitle']}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


if "last_signals" not in st.session_state:
    st.session_state.last_signals = {}


if st.button(t["button"]) or auto_refresh:
    results = []

    with st.spinner(t["loading"]):
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

                if (
                    telegram_enabled
                    and signal in ["STRONG LONG", "STRONG SHORT"]
                    and previous_signal != signal
                ):
                    emoji = "🟢" if signal == "STRONG LONG" else "🔴"

                    message = (
                        f"{emoji} {signal}\n\n"
                        f"Coin: {result['Coin']}\n"
                        f"Timeframe: {result['Timeframe']}\n"
                        f"Price: {result['Price']}\n"
                        f"RSI: {result['RSI']}\n"
                        f"Score: {result['Score']}\n\n"
                        f"SL: {result['Stop Loss']}\n"
                        f"TP1: {result['TP1']}\n"
                        f"TP2: {result['TP2']}\n\n"
                        f"Max Loss: {result['Max Loss USDT']} USDT\n"
                        f"Position: {result['Position Size USDT']} USDT\n\n"
                        f"⚠️ Signal only. No automatic trade."
                    )

                    send_telegram(message)
                    st.session_state.last_signals[signal_key] = signal

            except Exception as e:
                results.append({
                    "Coin": coin,
                    "Timeframe": timeframe,
                    "Price": 0,
                    "RSI": 0,
                    "EMA20": 0,
                    "EMA50": 0,
                    "EMA200": 0,
                    "MACD": 0,
                    "MACD Signal": 0,
                    "Score": 0,
                    "Signal": f"HIBA: {e}",
                    "Stop Loss": 0,
                    "TP1": 0,
                    "TP2": 0,
                    "Max Loss USDT": 0,
                    "Position Size USDT": 0,
                })

    cols = st.columns(4)

    for idx, r in enumerate(results):
        with cols[idx]:
            if "LONG" in r["Signal"]:
                color = "green-card"
            elif "SHORT" in r["Signal"]:
                color = "red-card"
            else:
                color = "wait-card"

            st.markdown(
                f"""
                <div class="{color}">
                    <b>{r['Coin']}</b><br>
                    {r['Signal']}<br>
                    Score: {r['Score']}<br>
                    Price: {r['Price']}
                </div>
                """,
                unsafe_allow_html=True
            )

    strong_results = [
        r for r in results
        if r["Signal"] in ["STRONG LONG", "STRONG SHORT"]
    ]

    if strong_results:
        st.subheader(t["strong"])
        for r in strong_results:
            st.success(
                f"{r['Coin']} | {r['Signal']} | Score: {r['Score']} | "
                f"Price: {r['Price']} | SL: {r['Stop Loss']} | "
                f"TP1: {r['TP1']} | TP2: {r['TP2']}"
            )

    st.subheader(t["full"])
    st.dataframe(pd.DataFrame(results).astype(str), use_container_width=True)

    if auto_refresh:
        st.info(f"Automatikus frissítés {refresh_seconds} másodperc múlva...")
        time.sleep(refresh_seconds)
        st.rerun()

else:
    st.info(t["info"])

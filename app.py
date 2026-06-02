import os
import time
from datetime import datetime

import ccxt
import pandas as pd
import requests
import streamlit as st
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

DISCORD_WEBHOOK = get_secret("DISCORD_WEBHOOK") or get_secret("DISCORD_WEBHOOK_URL")

st.set_page_config(page_title="Crypto Edge AI V2", page_icon="⚡", layout="wide")

OPEN_FILE = "paper_open_trades.csv"
CLOSED_FILE = "paper_closed_trades.csv"

PAPER_ACCOUNT_DEFAULT = 200.0
TRADE_MARGIN_DEFAULT = 50.0
LEVERAGE_DEFAULT = 10

COINS = {
    "BTC": ["BTC/USD", "XBT/USD", "BTC/USDT", "XBT/USDT"],
    "ETH": ["ETH/USD", "ETH/USDT"],
    "SOL": ["SOL/USD", "SOL/USDT"],
    "BNB": ["BNB/USD", "BNB/USDT"],
}

exchange = ccxt.kraken({"enableRateLimit": True})
exchange.load_markets()

st.markdown("""
<style>
.stApp { background-color: #0b0f19; color: white; }
section[data-testid="stSidebar"] { background-color: #1a1d29; }
.big-title { font-size: 54px; font-weight: 900; color: white; }
.subtitle { font-size: 20px; color: #b6c2d9; }
.green-card {
    padding: 18px; border-radius: 15px; background-color: #123d2a;
    border: 1px solid #22c55e; color: #bbf7d0; font-size: 18px;
}
.red-card {
    padding: 18px; border-radius: 15px; background-color: #3d1212;
    border: 1px solid #ef4444; color: #fecaca; font-size: 18px;
}
.wait-card {
    padding: 18px; border-radius: 15px; background-color: #3b3312;
    border: 1px solid #eab308; color: #fef3c7; font-size: 18px;
}
</style>
""", unsafe_allow_html=True)


OPEN_COLS = [
    "opened_at", "label", "coin", "timeframe", "signal", "entry",
    "stop_loss", "tp1", "tp2", "score", "margin", "leverage", "notional"
]

CLOSED_COLS = OPEN_COLS + ["closed_at", "exit_price", "result", "pnl_usdt", "equity"]


def read_csv(path, cols):
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame(columns=cols)
    return pd.DataFrame(columns=cols)


def save_csv(df, path):
    df.to_csv(path, index=False)


def resolve_market(candidates):
    for symbol in candidates:
        if symbol in exchange.markets:
            return symbol
    return None


def send_discord_signal(result):
    if not DISCORD_WEBHOOK:
        return

    emoji = "🟢" if result["Signal"] == "STRONG LONG" else "🔴"

    message = (
        f"{emoji} **{result['Signal']} - PAPER SIGNAL**\n\n"
        f"Coin: **{result['Coin']}**\n"
        f"Timeframe: {result['Timeframe']}\n"
        f"Entry: {result['Price']}\n"
        f"Stop Loss: {result['Stop Loss']}\n"
        f"TP1: {result['TP1']}\n"
        f"TP2: {result['TP2']}\n"
        f"Score: {result['Score']}\n"
        f"Margin: {result['Margin USDT']} USDT\n"
        f"Leverage: {result['Leverage']}x\n"
        f"Notional: {result['Notional USDT']} USDT\n\n"
        f"⚠️ Paper trade only. No real trade opened."
    )

    try:
        requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10)
    except Exception as e:
        st.warning(f"Discord hiba: {e}")


def get_data(symbol, timeframe, limit=250):
    data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df


def analyze_coin(label, symbol, timeframe, paper_account, risk_percent, margin, leverage):
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
    if df.empty:
        raise ValueError("Not enough data")

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
    elif score <= -60:
        signal = "STRONG SHORT"
        stop_loss = price + atr_value * 1.5
        tp1 = price - atr_value * 2
        tp2 = price - atr_value * 3
    else:
        signal = "WAIT"
        stop_loss = 0
        tp1 = 0
        tp2 = 0

    return {
        "Label": label,
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
        "Max Loss USDT": round(paper_account * (risk_percent / 100), 2),
        "Margin USDT": round(margin, 2),
        "Leverage": leverage,
        "Notional USDT": round(margin * leverage, 2),
    }


def open_trade(result, discord_enabled):
    open_df = read_csv(OPEN_FILE, OPEN_COLS)

    if not open_df.empty:
        duplicate = open_df[
            (open_df["label"] == result["Label"]) &
            (open_df["timeframe"] == result["Timeframe"])
        ]
        if not duplicate.empty:
            return

    new_trade = {
        "opened_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "label": result["Label"],
        "coin": result["Coin"],
        "timeframe": result["Timeframe"],
        "signal": result["Signal"],
        "entry": result["Price"],
        "stop_loss": result["Stop Loss"],
        "tp1": result["TP1"],
        "tp2": result["TP2"],
        "score": result["Score"],
        "margin": result["Margin USDT"],
        "leverage": result["Leverage"],
        "notional": result["Notional USDT"],
    }

    open_df = pd.concat([open_df, pd.DataFrame([new_trade])], ignore_index=True)
    save_csv(open_df, OPEN_FILE)

    if discord_enabled:
        send_discord_signal(result)


def update_trades(start_equity):
    open_df = read_csv(OPEN_FILE, OPEN_COLS)
    closed_df = read_csv(CLOSED_FILE, CLOSED_COLS)

    if open_df.empty:
        return open_df, closed_df

    remaining = []

    current_equity = start_equity
    if not closed_df.empty and "equity" in closed_df.columns:
        current_equity = pd.to_numeric(closed_df["equity"], errors="coerce").dropna()
        current_equity = float(current_equity.iloc[-1]) if not current_equity.empty else start_equity

    for _, trade in open_df.iterrows():
        try:
            ticker = exchange.fetch_ticker(trade["coin"])
            current_price = float(ticker["last"])

            entry = float(trade["entry"])
            stop_loss = float(trade["stop_loss"])
            tp1 = float(trade["tp1"])
            margin = float(trade["margin"])
            leverage = float(trade["leverage"])
            signal = str(trade["signal"])

            closed = False
            result = ""
            exit_price = current_price

            if signal == "STRONG LONG":
                if current_price >= tp1:
                    closed = True
                    result = "WIN_TP1"
                    exit_price = tp1
                elif current_price <= stop_loss:
                    closed = True
                    result = "LOSS_SL"
                    exit_price = stop_loss

                pnl = margin * leverage * ((exit_price - entry) / entry)

            elif signal == "STRONG SHORT":
                if current_price <= tp1:
                    closed = True
                    result = "WIN_TP1"
                    exit_price = tp1
                elif current_price >= stop_loss:
                    closed = True
                    result = "LOSS_SL"
                    exit_price = stop_loss

                pnl = margin * leverage * ((entry - exit_price) / entry)

            else:
                pnl = 0

            if closed:
                current_equity += pnl

                closed_trade = trade.to_dict()
                closed_trade["closed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                closed_trade["exit_price"] = round(exit_price, 4)
                closed_trade["result"] = result
                closed_trade["pnl_usdt"] = round(pnl, 4)
                closed_trade["equity"] = round(current_equity, 4)

                closed_df = pd.concat([closed_df, pd.DataFrame([closed_trade])], ignore_index=True)
            else:
                remaining.append(trade.to_dict())

        except Exception:
            remaining.append(trade.to_dict())

    new_open_df = pd.DataFrame(remaining, columns=OPEN_COLS)

    save_csv(new_open_df, OPEN_FILE)
    save_csv(closed_df, CLOSED_FILE)

    return new_open_df, closed_df


def show_stats(open_df, closed_df, start_equity):
    total_closed = len(closed_df)
    wins = len(closed_df[closed_df["result"].astype(str).str.contains("WIN")]) if not closed_df.empty else 0
    losses = len(closed_df[closed_df["result"].astype(str).str.contains("LOSS")]) if not closed_df.empty else 0
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0
    pnl = pd.to_numeric(closed_df["pnl_usdt"], errors="coerce").fillna(0).sum() if not closed_df.empty else 0
    equity = start_equity + pnl

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Open", len(open_df))
    c2.metric("Closed", total_closed)
    c3.metric("Wins", wins)
    c4.metric("Losses", losses)
    c5.metric("Win Rate", f"{win_rate:.1f}%")
    c6.metric("P/L", f"{pnl:.2f} USDT")

    st.metric("Paper Equity", f"{equity:.2f} USDT")


with st.sidebar:
    st.header("Beállítások")

    timeframe = st.selectbox("Idősík", ["5m", "15m", "30m", "1h", "2h", "4h"], index=1)
    paper_account = st.number_input("Virtuális tőke USDT", min_value=10.0, value=PAPER_ACCOUNT_DEFAULT, step=10.0)
    risk_percent = st.slider("Kockázat trade-enként %", min_value=0.5, max_value=5.0, value=1.0, step=0.5)
    margin = st.number_input("Trade méret / margin USDT", min_value=5.0, value=TRADE_MARGIN_DEFAULT, step=5.0)
    leverage = st.slider("Paper leverage", min_value=1, max_value=20, value=LEVERAGE_DEFAULT, step=1)
    auto_refresh = st.checkbox("Automatikus frissítés", value=False)
    refresh_seconds = st.selectbox("Frissítés gyakorisága", [30, 60, 120, 300], index=1)
    discord_enabled = st.checkbox("Discord STRONG jelzés küldése", value=True)

st.markdown("<div class='big-title'>⚡ Crypto Edge AI V2</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='subtitle'>Kraken adatok + paper trading + Discord jelzések. Automatikus élő trade nincs.</div>",
    unsafe_allow_html=True
)
st.divider()

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📈 Elemzés", "📜 Trade History"])

run = False

with tab1:
    if st.button("Frissítés / Elemzés indítása"):
        run = True

with tab2:
    if st.button("Elemzés indítása"):
        run = True

if auto_refresh:
    run = True

if run:
    open_df, closed_df = update_trades(paper_account)

    results = []

    with st.spinner("Kraken adatok lekérése és elemzés..."):
        for label, candidates in COINS.items():
            symbol = resolve_market(candidates)

            if not symbol:
                results.append({
                    "Label": label,
                    "Coin": "N/A",
                    "Price": 0,
                    "Score": 0,
                    "Signal": "NOT AVAILABLE ON KRAKEN",
                })
                continue

            try:
                result = analyze_coin(label, symbol, timeframe, paper_account, risk_percent, margin, leverage)
                results.append(result)

                if result["Signal"] in ["STRONG LONG", "STRONG SHORT"]:
                    open_trade(result, discord_enabled)

            except Exception as e:
                results.append({
                    "Label": label,
                    "Coin": symbol,
                    "Price": 0,
                    "Score": 0,
                    "Signal": f"HIBA: {e}",
                })

    open_df, closed_df = update_trades(paper_account)

    st.session_state["results"] = results

else:
    open_df = read_csv(OPEN_FILE, OPEN_COLS)
    closed_df = read_csv(CLOSED_FILE, CLOSED_COLS)
    results = st.session_state.get("results", [])

with tab1:
    st.subheader("📊 Paper Trading Dashboard")
    show_stats(open_df, closed_df, paper_account)

    if not closed_df.empty and "equity" in closed_df.columns:
        curve = closed_df[["closed_at", "equity"]].copy()
        curve["closed_at"] = pd.to_datetime(curve["closed_at"])
        curve = curve.sort_values("closed_at")
        curve = curve.set_index("closed_at")
        st.subheader("📈 Equity Curve")
        st.line_chart(curve["equity"])
    else:
        st.info("Equity Curve akkor jelenik meg, ha lesz legalább egy lezárt paper trade.")

    if results:
        cols = st.columns(4)

        for idx, r in enumerate(results):
            with cols[idx]:
                signal = r.get("Signal", "WAIT")

                if "LONG" in signal:
                    color = "green-card"
                elif "SHORT" in signal:
                    color = "red-card"
                else:
                    color = "wait-card"

                st.markdown(
                    f"""
                    <div class="{color}">
                        <b>{r.get('Label', '')} - {r.get('Coin', '')}</b><br>
                        {signal}<br>
                        Score: {r.get('Score', 0)}<br>
                        Price: {r.get('Price', 0)}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

with tab2:
    st.subheader("📈 Elemzés")

    if results:
        strong = [r for r in results if r.get("Signal") in ["STRONG LONG", "STRONG SHORT"]]

        if strong:
            st.subheader("🏆 Erős jelzések")
            for r in strong:
                st.success(
                    f"{r['Coin']} | {r['Signal']} | Score: {r['Score']} | "
                    f"Price: {r['Price']} | SL: {r['Stop Loss']} | TP1: {r['TP1']} | TP2: {r['TP2']}"
                )

        st.subheader("📊 Teljes elemzés")
        st.dataframe(pd.DataFrame(results).astype(str), use_container_width=True)
    else:
        st.info("Még nincs elemzés. Kattints az Elemzés indítása gombra.")

with tab3:
    st.subheader("📌 Nyitott paper trade-ek")
    if not open_df.empty:
        st.dataframe(open_df.astype(str), use_container_width=True)
    else:
        st.info("Nincs nyitott paper trade.")

    st.subheader("📜 Lezárt paper trade-ek")
    if not closed_df.empty:
        st.dataframe(closed_df.tail(100).astype(str), use_container_width=True)
    else:
        st.info("Még nincs lezárt paper trade.")

if auto_refresh:
    st.info(f"Automatikus frissítés {refresh_seconds} másodperc múlva...")
    time.sleep(refresh_seconds)
    st.rerun()

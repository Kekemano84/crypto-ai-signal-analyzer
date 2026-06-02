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


DISCORD_WEBHOOK = get_secret("DISCORD_WEBHOOK")

st.set_page_config(
    page_title="Crypto Edge AI V2",
    page_icon="⚡",
    layout="wide"
)

COIN_CANDIDATES = {
    "BTC": ["BTC/USDT", "BTC/USD"],
    "ETH": ["ETH/USDT", "ETH/USD"],
    "SOL": ["SOL/USDT", "SOL/USD"],
    "BNB": ["BNB/USDT", "BNB/USD"],
}

OPEN_TRADES_FILE = "paper_open_trades.csv"
CLOSED_TRADES_FILE = "paper_closed_trades.csv"

exchange = ccxt.kraken({"enableRateLimit": True})
exchange.load_markets()

st.markdown("""
<style>
.big-title {
    font-size: 58px;
    font-weight: 900;
    color: #ffffff;
}
.subtitle {
    font-size: 21px;
    color: #b6c2d9;
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
        "subtitle": "Kraken adatok + paper trading + Discord jelzések. Automatikus élő trade nincs.",
        "settings": "Beállítások",
        "timeframe": "Idősík",
        "account": "Paper számla mérete USDT",
        "risk": "Kockázat trade-enként %",
        "margin": "Trade margin USDT",
        "leverage": "Paper leverage",
        "auto": "Automatikus frissítés",
        "refresh": "Frissítés gyakorisága",
        "discord": "Discord jelzés bekapcsolása",
        "button": "Frissítés / Elemzés indítása",
        "loading": "Kraken adatok lekérése és elemzés...",
        "strong": "🏆 Erős jelzések",
        "full": "📊 Teljes elemzés",
        "open": "📌 Nyitott paper trade-ek",
        "closed": "📜 Lezárt paper trade-ek",
        "no_open": "Nincs nyitott paper trade.",
        "no_closed": "Még nincs lezárt paper trade.",
        "start": "Kattints a Frissítés / Elemzés indítása gombra.",
    },
    "English": {
        "subtitle": "Kraken data + paper trading + Discord alerts. No live automatic trading.",
        "settings": "Settings",
        "timeframe": "Timeframe",
        "account": "Paper account size USDT",
        "risk": "Risk per trade %",
        "margin": "Trade margin USDT",
        "leverage": "Paper leverage",
        "auto": "Auto refresh",
        "refresh": "Refresh interval",
        "discord": "Enable Discord alerts",
        "button": "Refresh / Start Analysis",
        "loading": "Fetching Kraken data and analysing...",
        "strong": "🏆 Strong Signals",
        "full": "📊 Full Analysis",
        "open": "📌 Open paper trades",
        "closed": "📜 Closed paper trades",
        "no_open": "No open paper trades.",
        "no_closed": "No closed paper trades yet.",
        "start": "Click the Refresh / Start Analysis button.",
    }
}


def resolve_market(candidates):
    for symbol in candidates:
        if symbol in exchange.markets:
            return symbol
    return None


def send_discord(content):
    if not DISCORD_WEBHOOK:
        return

    try:
        requests.post(
            DISCORD_WEBHOOK,
            json={"content": content},
            timeout=10
        )
    except Exception as e:
        st.warning(f"Discord hiba: {e}")


def read_csv_safe(path, columns):
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame(columns=columns)

    return pd.DataFrame(columns=columns)


def save_csv(df, path):
    df.to_csv(path, index=False)


def get_data(symbol, timeframe, limit=250):
    data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    df = pd.DataFrame(
        data,
        columns=["time", "open", "high", "low", "close", "volume"]
    )

    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df


def analyze_coin(label, symbol, timeframe, paper_account, risk_percent, trade_margin, leverage):
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
        raise ValueError("Not enough market data.")

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
        sl = price - atr_value * 1.5
        tp1 = price + atr_value * 2
        tp2 = price + atr_value * 3
    elif score >= 35:
        signal = "LONG"
        sl = price - atr_value * 1.5
        tp1 = price + atr_value * 2
        tp2 = price + atr_value * 3
    elif score <= -60:
        signal = "STRONG SHORT"
        sl = price + atr_value * 1.5
        tp1 = price - atr_value * 2
        tp2 = price - atr_value * 3
    elif score <= -35:
        signal = "SHORT"
        sl = price + atr_value * 1.5
        tp1 = price - atr_value * 2
        tp2 = price - atr_value * 3
    else:
        signal = "WAIT"
        sl = 0
        tp1 = 0
        tp2 = 0

    max_loss = paper_account * (risk_percent / 100)
    notional = trade_margin * leverage

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
        "Stop Loss": round(sl, 4),
        "TP1": round(tp1, 4),
        "TP2": round(tp2, 4),
        "Max Loss USDT": round(max_loss, 2),
        "Margin USDT": round(trade_margin, 2),
        "Leverage": leverage,
        "Notional USDT": round(notional, 2),
    }


def open_paper_trade(result, discord_enabled):
    open_cols = [
        "opened_at", "label", "coin", "timeframe", "signal", "entry",
        "stop_loss", "tp1", "tp2", "score", "margin", "leverage", "notional"
    ]

    open_df = read_csv_safe(OPEN_TRADES_FILE, open_cols)

    if not open_df.empty:
        existing = open_df[
            (open_df["label"] == result["Label"]) &
            (open_df["timeframe"] == result["Timeframe"])
        ]

        if not existing.empty:
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
    save_csv(open_df, OPEN_TRADES_FILE)

    if discord_enabled:
        emoji = "🟢" if "LONG" in result["Signal"] else "🔴"

        send_discord(
            f"{emoji} **NEW PAPER TRADE**\n\n"
            f"Signal: **{result['Signal']}**\n"
            f"Coin: **{result['Coin']}**\n"
            f"Timeframe: {result['Timeframe']}\n"
            f"Entry: {result['Price']}\n"
            f"SL: {result['Stop Loss']}\n"
            f"TP1: {result['TP1']}\n"
            f"TP2: {result['TP2']}\n"
            f"Margin: {result['Margin USDT']} USDT\n"
            f"Leverage: {result['Leverage']}x\n"
            f"Notional: {result['Notional USDT']} USDT"
        )


def update_paper_trades(discord_enabled):
    open_cols = [
        "opened_at", "label", "coin", "timeframe", "signal", "entry",
        "stop_loss", "tp1", "tp2", "score", "margin", "leverage", "notional"
    ]

    closed_cols = open_cols + [
        "closed_at", "exit_price", "result", "pnl_usdt"
    ]

    open_df = read_csv_safe(OPEN_TRADES_FILE, open_cols)
    closed_df = read_csv_safe(CLOSED_TRADES_FILE, closed_cols)

    if open_df.empty:
        return open_df, closed_df

    remaining = []

    for _, trade in open_df.iterrows():
        try:
            ticker = exchange.fetch_ticker(trade["coin"])
            current_price = float(ticker["last"])

            entry = float(trade["entry"])
            sl = float(trade["stop_loss"])
            tp1 = float(trade["tp1"])
            margin = float(trade["margin"])
            leverage = float(trade["leverage"])
            signal = str(trade["signal"])

            closed = False
            result = None
            exit_price = current_price
            pnl = 0

            if "LONG" in signal:
                if current_price >= tp1:
                    closed = True
                    result = "WIN_TP1"
                    exit_price = tp1
                elif current_price <= sl:
                    closed = True
                    result = "LOSS_SL"
                    exit_price = sl

                pnl = margin * leverage * ((exit_price - entry) / entry)

            elif "SHORT" in signal:
                if current_price <= tp1:
                    closed = True
                    result = "WIN_TP1"
                    exit_price = tp1
                elif current_price >= sl:
                    closed = True
                    result = "LOSS_SL"
                    exit_price = sl

                pnl = margin * leverage * ((entry - exit_price) / entry)

            if closed:
                closed_trade = trade.to_dict()
                closed_trade["closed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                closed_trade["exit_price"] = round(exit_price, 4)
                closed_trade["result"] = result
                closed_trade["pnl_usdt"] = round(pnl, 4)

                closed_df = pd.concat(
                    [closed_df, pd.DataFrame([closed_trade])],
                    ignore_index=True
                )

                if discord_enabled:
                    icon = "✅" if pnl > 0 else "❌"

                    send_discord(
                        f"{icon} **PAPER TRADE CLOSED**\n\n"
                        f"Coin: **{trade['coin']}**\n"
                        f"Signal: {signal}\n"
                        f"Entry: {entry}\n"
                        f"Exit: {round(exit_price, 4)}\n"
                        f"Result: {result}\n"
                        f"PnL: **{round(pnl, 4)} USDT**"
                    )
            else:
                remaining.append(trade.to_dict())

        except Exception:
            remaining.append(trade.to_dict())

    new_open_df = pd.DataFrame(remaining, columns=open_cols)

    save_csv(new_open_df, OPEN_TRADES_FILE)
    save_csv(closed_df, CLOSED_TRADES_FILE)

    return new_open_df, closed_df


def show_stats(closed_df):
    if closed_df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Closed", 0)
        c2.metric("Wins", 0)
        c3.metric("Losses", 0)
        c4.metric("Paper PnL", "0 USDT")
        return

    total = len(closed_df)
    wins = len(closed_df[closed_df["result"].astype(str).str.contains("WIN")])
    losses = len(closed_df[closed_df["result"].astype(str).str.contains("LOSS")])
    pnl = pd.to_numeric(closed_df["pnl_usdt"], errors="coerce").fillna(0).sum()
    win_rate = (wins / total) * 100 if total else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Closed", total)
    c2.metric("Wins", wins)
    c3.metric("Losses", losses)
    c4.metric("Win Rate", f"{win_rate:.1f}%")
    c5.metric("Paper PnL", f"{pnl:.2f} USDT")


with st.sidebar:
    language = st.selectbox("Language / Nyelv", ["Magyar", "English"])
    t = TEXT[language]

    st.header(t["settings"])

    timeframe = st.selectbox(
        t["timeframe"],
        ["5m", "15m", "30m", "1h", "2h", "4h"],
        index=1
    )

    paper_account = st.number_input(
        t["account"],
        min_value=10.0,
        value=200.0,
        step=10.0
    )

    risk_percent = st.slider(
        t["risk"],
        min_value=0.5,
        max_value=5.0,
        value=1.0,
        step=0.5
    )

    trade_margin = st.number_input(
        t["margin"],
        min_value=5.0,
        value=50.0,
        step=5.0
    )

    leverage = st.slider(
        t["leverage"],
        min_value=1,
        max_value=20,
        value=10,
        step=1
    )

    auto_refresh = st.checkbox(t["auto"], value=False)

    refresh_seconds = st.selectbox(
        t["refresh"],
        [30, 60, 120, 300],
        index=1
    )

    discord_enabled = st.checkbox(t["discord"], value=True)


st.markdown("<div class='big-title'>⚡ Crypto Edge AI V2</div>", unsafe_allow_html=True)
st.markdown(f"<div class='subtitle'>{t['subtitle']}</div>", unsafe_allow_html=True)
st.divider()


if st.button(t["button"]) or auto_refresh:
    results = []

    open_df, closed_df = update_paper_trades(discord_enabled)

    with st.spinner(t["loading"]):
        for label, candidates in COIN_CANDIDATES.items():
            symbol = resolve_market(candidates)

            if symbol is None:
                results.append({
                    "Label": label,
                    "Coin": "N/A",
                    "Timeframe": timeframe,
                    "Price": 0,
                    "RSI": 0,
                    "Score": 0,
                    "Signal": "NOT AVAILABLE ON KRAKEN",
                    "Stop Loss": 0,
                    "TP1": 0,
                    "TP2": 0,
                })
                continue

            try:
                result = analyze_coin(
                    label,
                    symbol,
                    timeframe,
                    paper_account,
                    risk_percent,
                    trade_margin,
                    leverage
                )

                results.append(result)

                if result["Signal"] in ["STRONG LONG", "STRONG SHORT"]:
                    open_paper_trade(result, discord_enabled)

            except Exception as e:
                results.append({
                    "Label": label,
                    "Coin": symbol,
                    "Timeframe": timeframe,
                    "Price": 0,
                    "RSI": 0,
                    "Score": 0,
                    "Signal": f"HIBA: {e}",
                    "Stop Loss": 0,
                    "TP1": 0,
                    "TP2": 0,
                })

    open_df = read_csv_safe(OPEN_TRADES_FILE, [])
    closed_df = read_csv_safe(CLOSED_TRADES_FILE, [])

    show_stats(closed_df)

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
                    <b>{r.get('Label', '')} - {r.get('Coin', '')}</b><br>
                    {r['Signal']}<br>
                    Score: {r.get('Score', 0)}<br>
                    Price: {r.get('Price', 0)}
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

    st.subheader(t["open"])

    if not open_df.empty:
        st.dataframe(open_df.astype(str), use_container_width=True)
    else:
        st.info(t["no_open"])

    st.subheader(t["closed"])

    if not closed_df.empty:
        st.dataframe(closed_df.tail(50).astype(str), use_container_width=True)
    else:
        st.info(t["no_closed"])

    if auto_refresh:
        st.info(f"Automatikus frissítés {refresh_seconds} másodperc múlva...")
        time.sleep(refresh_seconds)
        st.rerun()

else:
    st.info(t["start"])

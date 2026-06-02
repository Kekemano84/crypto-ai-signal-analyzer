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

st.set_page_config(
    page_title="Crypto Edge AI V2",
    page_icon="⚡",
    layout="wide"
)

OPEN_FILE = "paper_open_trades.csv"
CLOSED_FILE = "paper_closed_trades.csv"

OPEN_COLS = [
    "opened_at", "label", "coin", "timeframe", "signal", "entry",
    "stop_loss", "tp1", "tp2", "score", "margin", "leverage", "notional"
]

CLOSED_COLS = OPEN_COLS + [
    "closed_at", "exit_price", "result", "pnl_usdt", "equity"
]

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
.stApp {
    background:
        radial-gradient(circle at top, rgba(0,255,90,0.12), transparent 35%),
        linear-gradient(180deg, #020403 0%, #06120b 45%, #020403 100%);
    color: #eaffea;
}

.stApp::before {
    content: "010101 101010 001100 111000 010101 101010 001100 111000 010101 101010 001100 111000";
    position: fixed;
    top: -20%;
    left: 0;
    width: 100%;
    height: 140%;
    color: rgba(0, 255, 80, 0.13);
    font-family: monospace;
    font-size: 22px;
    line-height: 34px;
    white-space: pre-wrap;
    word-spacing: 18px;
    z-index: 0;
    animation: matrixRain 18s linear infinite;
    pointer-events: none;
}

@keyframes matrixRain {
    from { transform: translateY(-120px); }
    to { transform: translateY(120px); }
}

.block-container {
    position: relative;
    z-index: 2;
    padding-top: 2rem;
}

section[data-testid="stSidebar"] {
    background: rgba(5, 15, 10, 0.94);
    border-right: 1px solid rgba(0,255,100,0.25);
}

.big-title {
    font-size: 56px;
    font-weight: 900;
    color: #ffffff;
    text-shadow: 0 0 18px rgba(0,255,100,0.55);
}

.subtitle {
    font-size: 20px;
    color: #9dffb3;
    margin-bottom: 22px;
}

.green-card {
    padding: 18px;
    border-radius: 15px;
    background: rgba(0, 80, 35, 0.75);
    border: 1px solid #22c55e;
    color: #bbf7d0;
    font-size: 18px;
    box-shadow: 0 0 18px rgba(34,197,94,0.25);
}

.red-card {
    padding: 18px;
    border-radius: 15px;
    background: rgba(90, 12, 20, 0.75);
    border: 1px solid #ef4444;
    color: #fecaca;
    font-size: 18px;
    box-shadow: 0 0 18px rgba(239,68,68,0.25);
}

.wait-card {
    padding: 18px;
    border-radius: 15px;
    background: rgba(70, 60, 10, 0.72);
    border: 1px solid #eab308;
    color: #fef3c7;
    font-size: 18px;
    box-shadow: 0 0 18px rgba(234,179,8,0.18);
}

h1, h2, h3, h4, p, label, div, span {
    color: #eaffea;
}

[data-testid="stMetricValue"] {
    color: #22ff66;
    text-shadow: 0 0 12px rgba(0,255,90,0.45);
}

.stButton > button {
    background: linear-gradient(90deg, #16a34a, #22c55e);
    color: white;
    border: none;
    border-radius: 12px;
    font-weight: 800;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 10px;
}

.stTabs [data-baseweb="tab"] {
    background: rgba(0, 30, 15, 0.65);
    border-radius: 12px;
    color: #d9ffe3;
    border: 1px solid rgba(0,255,100,0.2);
}

.stTabs [aria-selected="true"] {
    background: rgba(0, 120, 45, 0.45);
    border: 1px solid rgba(0,255,100,0.55);
}
</style>
""", unsafe_allow_html=True)


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


def send_discord(message):
    if not DISCORD_WEBHOOK:
        return

    try:
        requests.post(
            DISCORD_WEBHOOK,
            json={"content": message},
            timeout=10
        )
    except Exception as e:
        st.warning(f"Discord hiba: {e}")


def get_data(symbol, timeframe, limit=250):
    data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    df = pd.DataFrame(
        data,
        columns=["time", "open", "high", "low", "close", "volume"]
    )

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

    max_loss = paper_account * (risk_percent / 100)
    notional = margin * leverage

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
        "Max Loss USDT": round(max_loss, 2),
        "Margin USDT": round(margin, 2),
        "Leverage": leverage,
        "Notional USDT": round(notional, 2),
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

    trade = {
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

    open_df = pd.concat(
        [open_df, pd.DataFrame([trade])],
        ignore_index=True
    )

    save_csv(open_df, OPEN_FILE)

    if discord_enabled:
        emoji = "🟢" if result["Signal"] == "STRONG LONG" else "🔴"

        send_discord(
            f"{emoji} **NEW PAPER TRADE**\n\n"
            f"Signal: **{result['Signal']}**\n"
            f"Coin: **{result['Coin']}**\n"
            f"Timeframe: {result['Timeframe']}\n"
            f"Entry: {result['Price']}\n"
            f"SL: {result['Stop Loss']}\n"
            f"TP1: {result['TP1']}\n"
            f"TP2: {result['TP2']}\n"
            f"Score: {result['Score']}\n"
            f"Margin: {result['Margin USDT']} USDT\n"
            f"Leverage: {result['Leverage']}x\n"
            f"Notional: {result['Notional USDT']} USDT\n\n"
            f"⚠️ Paper trade only. No real trade opened."
        )


def update_trades(start_equity, discord_enabled):
    open_df = read_csv(OPEN_FILE, OPEN_COLS)
    closed_df = read_csv(CLOSED_FILE, CLOSED_COLS)

    if open_df.empty:
        return open_df, closed_df

    current_equity = start_equity

    if not closed_df.empty and "equity" in closed_df.columns:
        equity_series = pd.to_numeric(
            closed_df["equity"],
            errors="coerce"
        ).dropna()

        if not equity_series.empty:
            current_equity = float(equity_series.iloc[-1])

    remaining = []

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
                        f"Result: **{result}**\n"
                        f"PnL: **{round(pnl, 4)} USDT**\n"
                        f"Equity: **{round(current_equity, 4)} USDT**"
                    )
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

    if closed_df.empty:
        wins = 0
        losses = 0
        pnl = 0
        win_rate = 0
        equity = start_equity
    else:
        wins = len(closed_df[closed_df["result"].astype(str).str.contains("WIN")])
        losses = len(closed_df[closed_df["result"].astype(str).str.contains("LOSS")])
        pnl = pd.to_numeric(
            closed_df["pnl_usdt"],
            errors="coerce"
        ).fillna(0).sum()

        win_rate = (wins / total_closed * 100) if total_closed else 0
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
    st.header("⚙️ Beállítások")

    timeframe = st.selectbox(
        "Idősík",
        ["5m", "15m", "30m", "1h", "2h", "4h"],
        index=1
    )

    paper_account = st.number_input(
        "Virtuális tőke USDT",
        min_value=10.0,
        value=200.0,
        step=10.0
    )

    risk_percent = st.slider(
        "Kockázat trade-enként %",
        min_value=0.5,
        max_value=5.0,
        value=1.0,
        step=0.5
    )

    margin = st.number_input(
        "Trade méret / margin USDT",
        min_value=5.0,
        value=50.0,
        step=5.0
    )

    leverage = st.slider(
        "Paper leverage",
        min_value=1,
        max_value=100,
        value=10,
        step=1
    )

    if leverage >= 50:
        st.warning(
            "⚠️ Magas leverage kockázat! 50x felett egy kisebb rossz irányú mozgás is gyors veszteséget okozhat."
        )

    if leverage >= 75:
        st.error(
            "🚨 Extrém kockázat! 75x+ leverage mellett nagyon könnyen elveszítheted a teljes marginodat."
        )

    auto_refresh = st.checkbox(
        "Automatikus frissítés",
        value=False
    )

    if timeframe == "5m":
        refresh_seconds = 30
    elif timeframe == "15m":
        refresh_seconds = 60
    elif timeframe == "30m":
        refresh_seconds = 120
    elif timeframe == "1h":
        refresh_seconds = 300
    else:
        refresh_seconds = 600

    st.info(f"Frissítés gyakorisága: {refresh_seconds} másodperc")

    discord_enabled = st.checkbox(
        "Discord értesítés",
        value=True
    )


st.markdown(
    "<div class='big-title'>⚡ Crypto Edge AI V2</div>",
    unsafe_allow_html=True
)

st.markdown(
    "<div class='subtitle'>Kraken adatok + paper trading + Discord jelzések. Automatikus élő trade nincs.</div>",
    unsafe_allow_html=True
)

st.success(
    f"🟢 Bot Active | Last Refresh: {datetime.now().strftime('%H:%M:%S')}"
)

st.divider()

tab1, tab2, tab3 = st.tabs(
    ["📊 Dashboard", "📈 Elemzés", "📜 Trade History"]
)

run = False

with tab1:
    if st.button("🚀 Frissítés / Elemzés indítása"):
        run = True

with tab2:
    if st.button("📈 Elemzés indítása"):
        run = True

if auto_refresh:
    run = True

if run:
    open_df, closed_df = update_trades(
        paper_account,
        discord_enabled
    )

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
                result = analyze_coin(
                    label,
                    symbol,
                    timeframe,
                    paper_account,
                    risk_percent,
                    margin,
                    leverage
                )

                results.append(result)

                if result["Signal"] in ["STRONG LONG", "STRONG SHORT"]:
                    open_trade(
                        result,
                        discord_enabled
                    )

            except Exception as e:
                results.append({
                    "Label": label,
                    "Coin": symbol,
                    "Price": 0,
                    "Score": 0,
                    "Signal": f"HIBA: {e}",
                })

    open_df, closed_df = update_trades(
        paper_account,
        discord_enabled
    )

    st.session_state["results"] = results

else:
    open_df = read_csv(OPEN_FILE, OPEN_COLS)
    closed_df = read_csv(CLOSED_FILE, CLOSED_COLS)
    results = st.session_state.get("results", [])


with tab1:
    st.subheader("📊 Paper Trading Dashboard")

    show_stats(
        open_df,
        closed_df,
        paper_account
    )

    if not closed_df.empty and "equity" in closed_df.columns:
        curve = closed_df[["closed_at", "equity"]].copy()
        curve["closed_at"] = pd.to_datetime(curve["closed_at"])
        curve = curve.sort_values("closed_at").set_index("closed_at")

        st.subheader("📈 Equity Curve")
        st.line_chart(curve["equity"])
    else:
        st.info(
            "Equity Curve akkor jelenik meg, ha lesz legalább egy lezárt paper trade."
        )

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
        strong = [
            r for r in results
            if r.get("Signal") in ["STRONG LONG", "STRONG SHORT"]
        ]

        if strong:
            st.subheader("🏆 Erős jelzések")

            for r in strong:
                st.success(
                    f"{r['Coin']} | {r['Signal']} | Score: {r['Score']} | "
                    f"Price: {r['Price']} | SL: {r['Stop Loss']} | "
                    f"TP1: {r['TP1']} | TP2: {r['TP2']}"
                )

        st.subheader("📊 Teljes elemzés")
        st.dataframe(
            pd.DataFrame(results).astype(str),
            use_container_width=True
        )
    else:
        st.info(
            "Még nincs elemzés. Kattints az Elemzés indítása gombra."
        )


with tab3:
    st.subheader("📌 Nyitott paper trade-ek")

    if not open_df.empty:
        st.dataframe(
            open_df.astype(str),
            use_container_width=True
        )
    else:
        st.info("Nincs nyitott paper trade.")

    st.subheader("📜 Lezárt paper trade-ek")

    if not closed_df.empty:
        st.dataframe(
            closed_df.tail(100).astype(str),
            use_container_width=True
        )
    else:
        st.info("Még nincs lezárt paper trade.")


if auto_refresh:
    st.info(
        f"Automatikus frissítés {refresh_seconds} másodperc múlva..."
    )

    time.sleep(refresh_seconds)
    st.rerun()

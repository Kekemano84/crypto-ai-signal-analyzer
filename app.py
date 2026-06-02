import os
import time
import base64
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

st.set_page_config(page_title="Crypto Edge AI V3", page_icon="⚡", layout="wide")

OPEN_FILE = "paper_open_trades.csv"
CLOSED_FILE = "paper_closed_trades.csv"

OPEN_COLS = [
    "opened_at", "group", "label", "coin", "timeframe", "signal", "entry",
    "stop_loss", "tp1", "tp2", "score", "confidence", "rr_ratio",
    "volume_spike", "margin", "leverage", "notional"
]

CLOSED_COLS = OPEN_COLS + ["closed_at", "exit_price", "result", "pnl_usdt", "equity"]

TOP4_COINS = {
    "BTC": ["BTC/USD", "XBT/USD", "BTC/USDT", "XBT/USDT"],
    "ETH": ["ETH/USD", "ETH/USDT"],
    "SOL": ["SOL/USD", "SOL/USDT"],
    "BNB": ["BNB/USD", "BNB/USDT"],
}

ALTCOINS = {
    "XRP": ["XRP/USD", "XRP/USDT"],
    "ADA": ["ADA/USD", "ADA/USDT"],
    "DOGE": ["DOGE/USD", "DOGE/USDT"],
    "LINK": ["LINK/USD", "LINK/USDT"],
    "LTC": ["LTC/USD", "LTC/USDT"],
    "DOT": ["DOT/USD", "DOT/USDT"],
    "AVAX": ["AVAX/USD", "AVAX/USDT"],
    "XLM": ["XLM/USD", "XLM/USDT"],
    "ATOM": ["ATOM/USD", "ATOM/USDT"],
    "BCH": ["BCH/USD", "BCH/USDT"],
}

exchange = ccxt.kraken({"enableRateLimit": True})
exchange.load_markets()


def find_matrix_gif():
    possible_paths = [
        "matrix-code.gif",
        "./matrix-code.gif",
        "assets/matrix-code.gif",
        "static/matrix-code.gif",
        "images/matrix-code.gif",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None


def matrix_background_css():
    gif_path = find_matrix_gif()
    if gif_path:
        try:
            with open(gif_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            return f'''
            background-image:
                linear-gradient(rgba(0,0,0,0.66), rgba(0,0,0,0.90)),
                url("data:image/gif;base64,{data}");
            background-size: cover;
            background-attachment: fixed;
            background-position: center;
            '''
        except Exception:
            pass
    return '''
    background:
        radial-gradient(circle at top, rgba(0,255,90,0.16), transparent 35%),
        linear-gradient(180deg, #020403 0%, #06120b 45%, #020403 100%);
    '''


st.markdown(f'''
<style>
.stApp {{
    {matrix_background_css()}
    color: #eaffea;
}}
.block-container {{ position: relative; z-index: 2; padding-top: 2rem; }}
section[data-testid="stSidebar"] {{ background: rgba(5, 15, 10, 0.96); border-right: 1px solid rgba(0,255,100,0.25); }}
.big-title {{ font-size: 56px; font-weight: 900; color: #ffffff; text-shadow: 0 0 22px rgba(0,255,100,0.75); }}
.subtitle {{ font-size: 20px; color: #9dffb3; margin-bottom: 22px; }}
.green-card {{ padding: 18px; border-radius: 15px; background: rgba(0, 80, 35, 0.80); border: 1px solid #22c55e; color: #bbf7d0; font-size: 18px; box-shadow: 0 0 18px rgba(34,197,94,0.35); }}
.red-card {{ padding: 18px; border-radius: 15px; background: rgba(90, 12, 20, 0.80); border: 1px solid #ef4444; color: #fecaca; font-size: 18px; box-shadow: 0 0 18px rgba(239,68,68,0.35); }}
.wait-card {{ padding: 18px; border-radius: 15px; background: rgba(70, 60, 10, 0.78); border: 1px solid #eab308; color: #fef3c7; font-size: 18px; box-shadow: 0 0 18px rgba(234,179,8,0.22); }}
.elite-box {{ padding: 20px; border-radius: 18px; background: rgba(0, 90, 45, 0.86); border: 1px solid rgba(0,255,100,0.78); box-shadow: 0 0 25px rgba(0,255,100,0.30); margin-bottom: 18px; }}
h1, h2, h3, h4, p, label, div, span {{ color: #eaffea; }}
[data-testid="stMetricValue"] {{ color: #22ff66; text-shadow: 0 0 12px rgba(0,255,90,0.55); }}
.stButton > button {{ background: linear-gradient(90deg, #16a34a, #22c55e); color: white; border: none; border-radius: 12px; font-weight: 800; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 10px; }}
.stTabs [data-baseweb="tab"] {{ background: rgba(0, 30, 15, 0.72); border-radius: 12px; color: #d9ffe3; border: 1px solid rgba(0,255,100,0.24); }}
.stTabs [aria-selected="true"] {{ background: rgba(0, 120, 45, 0.50); border: 1px solid rgba(0,255,100,0.60); }}
</style>
''', unsafe_allow_html=True)


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
        return False, "Discord webhook nincs beállítva."
    try:
        response = requests.post(DISCORD_WEBHOOK, json={"content": message}, timeout=10)
        if response.status_code in [200, 204]:
            st.session_state["last_discord_message"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return True, "Discord üzenet elküldve."
        return False, f"Discord hiba: {response.status_code}"
    except Exception as e:
        return False, f"Discord hiba: {e}"


def get_data(symbol, timeframe, limit=250):
    data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(data, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df


def calculate_confidence(score, volume_spike):
    base = min(100, max(0, abs(score)))
    if volume_spike >= 2:
        base += 8
    elif volume_spike >= 1.5:
        base += 4
    return min(100, round(base, 1))


def calculate_rr(entry, stop_loss, tp1):
    if not stop_loss or not tp1:
        return 0
    risk = abs(entry - stop_loss)
    reward = abs(tp1 - entry)
    if risk == 0:
        return 0
    return round(reward / risk, 2)


def analyze_coin(group_name, label, symbol, timeframe, paper_account, risk_percent, margin, leverage):
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
    df["volume_avg_20"] = df["volume"].rolling(window=20).mean()
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
    volume = float(last["volume"])
    volume_avg_20 = float(last["volume_avg_20"])
    volume_spike = round(volume / volume_avg_20, 2) if volume_avg_20 > 0 else 0

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
    if volume_spike >= 2:
        score += 10 if score > 0 else -10 if score < 0 else 0

    if score >= 80:
        signal = "ELITE LONG"
        stop_loss = price - atr_value * 1.5
        tp1 = price + atr_value * 2
        tp2 = price + atr_value * 3
    elif score >= 60:
        signal = "STRONG LONG"
        stop_loss = price - atr_value * 1.5
        tp1 = price + atr_value * 2
        tp2 = price + atr_value * 3
    elif score <= -80:
        signal = "ELITE SHORT"
        stop_loss = price + atr_value * 1.5
        tp1 = price - atr_value * 2
        tp2 = price - atr_value * 3
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

    rr_ratio = calculate_rr(price, stop_loss, tp1)
    confidence = calculate_confidence(score, volume_spike)

    return {
        "Group": group_name,
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
        "Volume Spike": volume_spike,
        "Score": score,
        "Confidence %": confidence,
        "Signal": signal,
        "Stop Loss": round(stop_loss, 4),
        "TP1": round(tp1, 4),
        "TP2": round(tp2, 4),
        "RR Ratio": rr_ratio,
        "Max Loss USDT": round(paper_account * (risk_percent / 100), 2),
        "Margin USDT": round(margin, 2),
        "Leverage": leverage,
        "Notional USDT": round(margin * leverage, 2),
    }


def is_trade_signal(signal):
    return signal in ["STRONG LONG", "STRONG SHORT", "ELITE LONG", "ELITE SHORT"]


def open_trade(result, discord_enabled, send_longs, send_shorts):
    open_df = read_csv(OPEN_FILE, OPEN_COLS)
    if not open_df.empty:
        duplicate = open_df[(open_df["group"] == result["Group"]) & (open_df["label"] == result["Label"]) & (open_df["timeframe"] == result["Timeframe"])]
        if not duplicate.empty:
            return
    trade = {
        "opened_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "group": result["Group"], "label": result["Label"], "coin": result["Coin"],
        "timeframe": result["Timeframe"], "signal": result["Signal"], "entry": result["Price"],
        "stop_loss": result["Stop Loss"], "tp1": result["TP1"], "tp2": result["TP2"],
        "score": result["Score"], "confidence": result["Confidence %"], "rr_ratio": result["RR Ratio"],
        "volume_spike": result["Volume Spike"], "margin": result["Margin USDT"],
        "leverage": result["Leverage"], "notional": result["Notional USDT"],
    }
    open_df = pd.concat([open_df, pd.DataFrame([trade])], ignore_index=True)
    save_csv(open_df, OPEN_FILE)

    signal = result["Signal"]
    should_send = discord_enabled and (("LONG" in signal and send_longs) or ("SHORT" in signal and send_shorts))
    if should_send:
        emoji = "🟢" if "LONG" in signal else "🔴"
        whale_text = "🐋 Volume spike detected!" if result["Volume Spike"] >= 2 else ""
        send_discord(
            f"{emoji} **NEW PAPER TRADE**\n\n"
            f"Group: **{result['Group']}**\nSignal: **{result['Signal']}**\nCoin: **{result['Coin']}**\n"
            f"Timeframe: {result['Timeframe']}\nEntry: {result['Price']}\nSL: {result['Stop Loss']}\n"
            f"TP1: {result['TP1']}\nTP2: {result['TP2']}\nScore: {result['Score']}\n"
            f"Confidence: {result['Confidence %']}%\nRR Ratio: 1:{result['RR Ratio']}\n"
            f"Volume Spike: {result['Volume Spike']}x {whale_text}\nMargin: {result['Margin USDT']} USDT\n"
            f"Leverage: {result['Leverage']}x\nNotional: {result['Notional USDT']} USDT\n\n"
            f"⚠️ Paper trade only. No real trade opened."
        )


def update_trades(start_equity, discord_enabled, send_trade_close):
    open_df = read_csv(OPEN_FILE, OPEN_COLS)
    closed_df = read_csv(CLOSED_FILE, CLOSED_COLS)
    if open_df.empty:
        return open_df, closed_df
    current_equity = start_equity
    if not closed_df.empty and "equity" in closed_df.columns:
        equity_series = pd.to_numeric(closed_df["equity"], errors="coerce").dropna()
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
            if "LONG" in signal:
                if current_price >= tp1:
                    closed = True; result = "WIN_TP1"; exit_price = tp1
                elif current_price <= stop_loss:
                    closed = True; result = "LOSS_SL"; exit_price = stop_loss
                pnl = margin * leverage * ((exit_price - entry) / entry)
            elif "SHORT" in signal:
                if current_price <= tp1:
                    closed = True; result = "WIN_TP1"; exit_price = tp1
                elif current_price >= stop_loss:
                    closed = True; result = "LOSS_SL"; exit_price = stop_loss
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
                if discord_enabled and send_trade_close:
                    icon = "✅" if pnl > 0 else "❌"
                    send_discord(
                        f"{icon} **PAPER TRADE CLOSED**\n\nGroup: **{trade.get('group', '')}**\n"
                        f"Coin: **{trade['coin']}**\nSignal: {signal}\nEntry: {entry}\nExit: {round(exit_price, 4)}\n"
                        f"Result: **{result}**\nPnL: **{round(pnl, 4)} USDT**\nEquity: **{round(current_equity, 4)} USDT**"
                    )
            else:
                remaining.append(trade.to_dict())
        except Exception:
            remaining.append(trade.to_dict())
    new_open_df = pd.DataFrame(remaining, columns=OPEN_COLS)
    save_csv(new_open_df, OPEN_FILE)
    save_csv(closed_df, CLOSED_FILE)
    return new_open_df, closed_df


def analyze_group(group_name, coin_dict, timeframe, paper_account, risk_percent, margin, leverage, discord_enabled, send_longs, send_shorts):
    results = []
    with st.spinner(f"{group_name} adatok lekérése és elemzés..."):
        for label, candidates in coin_dict.items():
            symbol = resolve_market(candidates)
            if not symbol:
                results.append({"Group": group_name, "Label": label, "Coin": "N/A", "Timeframe": timeframe, "Price": 0, "Score": 0, "Confidence %": 0, "Volume Spike": 0, "RR Ratio": 0, "Signal": "NOT AVAILABLE ON KRAKEN"})
                continue
            try:
                result = analyze_coin(group_name, label, symbol, timeframe, paper_account, risk_percent, margin, leverage)
                results.append(result)
                if is_trade_signal(result["Signal"]):
                    open_trade(result, discord_enabled, send_longs, send_shorts)
            except Exception as e:
                results.append({"Group": group_name, "Label": label, "Coin": symbol, "Timeframe": timeframe, "Price": 0, "Score": 0, "Confidence %": 0, "Volume Spike": 0, "RR Ratio": 0, "Signal": f"HIBA: {e}"})
    return results


def show_coin_cards(results):
    if not results:
        st.info("Még nincs elemzés.")
        return
    columns_per_row = 4
    for start in range(0, len(results), columns_per_row):
        cols = st.columns(columns_per_row)
        row = results[start:start + columns_per_row]
        for idx, r in enumerate(row):
            with cols[idx]:
                signal = r.get("Signal", "WAIT")
                color = "green-card" if "LONG" in signal else "red-card" if "SHORT" in signal else "wait-card"
                st.markdown(f"""
                <div class="{color}">
                    <b>{r.get('Label', '')} - {r.get('Coin', '')}</b><br>
                    {signal}<br>
                    Score: {r.get('Score', 0)}<br>
                    Confidence: {r.get('Confidence %', 0)}%<br>
                    Vol: {r.get('Volume Spike', 0)}x<br>
                    RR: 1:{r.get('RR Ratio', 0)}<br>
                    Price: {r.get('Price', 0)}
                </div>
                """, unsafe_allow_html=True)


def show_stats(open_df, closed_df, start_equity):
    total_closed = len(closed_df)
    if closed_df.empty:
        wins = losses = pnl = win_rate = growth = average_win = profit_factor = 0
        equity = start_equity
    else:
        wins_df = closed_df[closed_df["result"].astype(str).str.contains("WIN")]
        losses_df = closed_df[closed_df["result"].astype(str).str.contains("LOSS")]
        wins = len(wins_df)
        losses = len(losses_df)
        pnl_series = pd.to_numeric(closed_df["pnl_usdt"], errors="coerce").fillna(0)
        pnl = pnl_series.sum()
        win_rate = (wins / total_closed * 100) if total_closed else 0
        equity = start_equity + pnl
        growth = ((equity - start_equity) / start_equity * 100) if start_equity else 0
        win_pnl = pd.to_numeric(wins_df["pnl_usdt"], errors="coerce").fillna(0)
        loss_pnl = pd.to_numeric(losses_df["pnl_usdt"], errors="coerce").fillna(0)
        average_win = win_pnl.mean() if not win_pnl.empty else 0
        gross_profit = win_pnl.sum()
        gross_loss = abs(loss_pnl.sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Open", len(open_df))
    c2.metric("Closed", total_closed)
    c3.metric("Wins", wins)
    c4.metric("Losses", losses)
    c5.metric("Win Rate", f"{win_rate:.1f}%")
    c6.metric("P/L", f"{pnl:.2f} USDT")
    c7, c8, c9, c10 = st.columns(4)
    c7.metric("Paper Equity", f"{equity:.2f} USDT")
    c8.metric("Growth", f"{growth:.2f}%")
    c9.metric("Avg Win", f"{average_win:.2f} USDT")
    c10.metric("Profit Factor", f"{profit_factor:.2f}")


def best_setup(results):
    trade_results = [r for r in results if is_trade_signal(r.get("Signal", ""))]
    if not trade_results:
        return None
    return sorted(trade_results, key=lambda x: (abs(x.get("Score", 0)), x.get("Confidence %", 0), x.get("RR Ratio", 0)), reverse=True)[0]


def show_best_setup(top4_results, alt_results):
    best = best_setup(top4_results + alt_results)
    if not best:
        st.info("🏆 Best Setup még nincs. Várj STRONG vagy ELITE jelzésre.")
        return
    st.markdown(f"""
    <div class="elite-box">
        <h3>🏆 BEST SETUP RIGHT NOW</h3>
        <b>{best['Coin']}</b><br>
        Signal: <b>{best['Signal']}</b><br>
        Score: <b>{best['Score']}</b><br>
        Confidence: <b>{best['Confidence %']}%</b><br>
        Entry: <b>{best['Price']}</b><br>
        SL: <b>{best['Stop Loss']}</b><br>
        TP1: <b>{best['TP1']}</b><br>
        TP2: <b>{best['TP2']}</b><br>
        RR: <b>1:{best['RR Ratio']}</b><br>
        Volume Spike: <b>{best['Volume Spike']}x</b>
    </div>
    """, unsafe_allow_html=True)


def send_daily_summary(open_df, closed_df, start_equity):
    total_closed = len(closed_df)
    if closed_df.empty:
        wins = losses = pnl = win_rate = 0
        equity = start_equity
    else:
        wins = len(closed_df[closed_df["result"].astype(str).str.contains("WIN")])
        losses = len(closed_df[closed_df["result"].astype(str).str.contains("LOSS")])
        pnl = pd.to_numeric(closed_df["pnl_usdt"], errors="coerce").fillna(0).sum()
        win_rate = (wins / total_closed * 100) if total_closed else 0
        equity = start_equity + pnl
    return send_discord(
        f"📊 **Crypto Edge AI V3 Summary**\n\nOpen Trades: **{len(open_df)}**\nClosed Trades: **{total_closed}**\nWins: **{wins}**\nLosses: **{losses}**\nWin Rate: **{win_rate:.1f}%**\nProfit/Loss: **{pnl:.2f} USDT**\nPaper Equity: **{equity:.2f} USDT**"
    )


# SIDEBAR
with st.sidebar:
    st.header("⚙️ Beállítások")
    timeframe = st.selectbox("Idősík", ["5m", "15m", "30m", "1h", "2h", "4h"], index=1)
    paper_account = st.number_input("Virtuális tőke USDT", min_value=10.0, value=200.0, step=10.0)
    risk_percent = st.slider("Kockázat trade-enként %", min_value=0.5, max_value=5.0, value=1.0, step=0.5)
    margin = st.number_input("Trade méret / margin USDT", min_value=5.0, value=50.0, step=5.0)
    leverage = st.slider("Paper leverage", min_value=1, max_value=100, value=10, step=1)
    if leverage >= 50:
        st.warning("⚠️ Magas leverage kockázat! 50x felett egy kisebb rossz irányú mozgás is gyors veszteséget okozhat.")
    if leverage >= 75:
        st.error("🚨 Extrém kockázat! 75x+ leverage mellett nagyon könnyen elveszítheted a teljes marginodat.")
    auto_refresh = st.checkbox("Automatikus frissítés és figyelés", value=False)
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
    discord_enabled = st.checkbox("Discord értesítés", value=True)
    send_longs = st.checkbox("Discord: LONG/ELITE LONG", value=True)
    send_shorts = st.checkbox("Discord: SHORT/ELITE SHORT", value=True)
    send_trade_close = st.checkbox("Discord: trade lezárás", value=True)


# HEADER
st.markdown("<div class='big-title'>⚡ Crypto Edge AI V3</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Kraken adatok + paper trading + Discord jelzések + Matrix háttér. Automatikus élő trade nincs.</div>", unsafe_allow_html=True)
st.success(f"🟢 Bot Active | Last Refresh: {datetime.now().strftime('%H:%M:%S')}")
st.divider()


# TABS
tab_dashboard, tab_top4, tab_altcoins, tab_history, tab_discord = st.tabs(["📊 Dashboard", "₿ TOP 4", "🚀 ALTCOINS", "📜 Trade History", "🔔 Discord"])

open_df = read_csv(OPEN_FILE, OPEN_COLS)
closed_df = read_csv(CLOSED_FILE, CLOSED_COLS)

if "top4_results" not in st.session_state:
    st.session_state["top4_results"] = []
if "altcoin_results" not in st.session_state:
    st.session_state["altcoin_results"] = []
if "last_discord_message" not in st.session_state:
    st.session_state["last_discord_message"] = "Még nem volt Discord üzenet."

run_dashboard_refresh = False
run_top4 = False
run_altcoins = False

with tab_dashboard:
    if st.button("🔄 Frissítés"):
        run_dashboard_refresh = True
with tab_top4:
    if st.button("₿ TOP 4 elemzés indítása"):
        run_top4 = True
with tab_altcoins:
    if st.button("🚀 ALTCOINS elemzés indítása"):
        run_altcoins = True

if auto_refresh:
    run_dashboard_refresh = True
    run_top4 = True
    run_altcoins = True

if run_dashboard_refresh or run_top4 or run_altcoins:
    open_df, closed_df = update_trades(paper_account, discord_enabled, send_trade_close)

if run_top4:
    st.session_state["top4_results"] = analyze_group("TOP 4", TOP4_COINS, timeframe, paper_account, risk_percent, margin, leverage, discord_enabled, send_longs, send_shorts)
    open_df, closed_df = update_trades(paper_account, discord_enabled, send_trade_close)

if run_altcoins:
    st.session_state["altcoin_results"] = analyze_group("ALTCOINS", ALTCOINS, timeframe, paper_account, risk_percent, margin, leverage, discord_enabled, send_longs, send_shorts)
    open_df, closed_df = update_trades(paper_account, discord_enabled, send_trade_close)


# DASHBOARD
with tab_dashboard:
    st.subheader("📊 Paper Trading Dashboard")
    show_stats(open_df, closed_df, paper_account)
    show_best_setup(st.session_state["top4_results"], st.session_state["altcoin_results"])
    if not closed_df.empty and "equity" in closed_df.columns:
        curve = closed_df[["closed_at", "equity"]].copy()
        curve["closed_at"] = pd.to_datetime(curve["closed_at"])
        curve = curve.sort_values("closed_at").set_index("closed_at")
        st.subheader("📈 Equity Curve")
        st.line_chart(curve["equity"])
    else:
        st.info("Equity Curve akkor jelenik meg, ha lesz legalább egy lezárt paper trade.")
    st.subheader("Aktuális TOP 4 jelek")
    show_coin_cards(st.session_state["top4_results"])
    st.subheader("Aktuális ALTCOIN jelek")
    show_coin_cards(st.session_state["altcoin_results"])


# TOP 4
with tab_top4:
    st.subheader("₿ TOP 4 elemzés")
    top4_results = st.session_state["top4_results"]
    show_coin_cards(top4_results)
    if top4_results:
        strong = [r for r in top4_results if is_trade_signal(r.get("Signal", ""))]
        if strong:
            st.subheader("🏆 TOP 4 erős jelzések")
            for r in strong:
                st.success(f"{r['Coin']} | {r['Signal']} | Score: {r['Score']} | Confidence: {r['Confidence %']}% | Vol: {r['Volume Spike']}x | RR: 1:{r['RR Ratio']} | Price: {r['Price']} | SL: {r['Stop Loss']} | TP1: {r['TP1']} | TP2: {r['TP2']}")
        st.subheader("📊 TOP 4 teljes elemzés")
        st.dataframe(pd.DataFrame(top4_results).astype(str), use_container_width=True)
    else:
        st.info("Még nincs TOP 4 elemzés. Kattints a TOP 4 elemzés indítása gombra.")


# ALTCOINS
with tab_altcoins:
    st.subheader("🚀 ALTCOINS elemzés")
    alt_results = st.session_state["altcoin_results"]
    show_coin_cards(alt_results)
    if alt_results:
        strong = [r for r in alt_results if is_trade_signal(r.get("Signal", ""))]
        if strong:
            st.subheader("🏆 ALTCOIN erős jelzések")
            for r in strong:
                st.success(f"{r['Coin']} | {r['Signal']} | Score: {r['Score']} | Confidence: {r['Confidence %']}% | Vol: {r['Volume Spike']}x | RR: 1:{r['RR Ratio']} | Price: {r['Price']} | SL: {r['Stop Loss']} | TP1: {r['TP1']} | TP2: {r['TP2']}")
        st.subheader("📊 ALTCOINS teljes elemzés")
        st.dataframe(pd.DataFrame(alt_results).astype(str), use_container_width=True)
    else:
        st.info("Még nincs ALTCOINS elemzés. Kattints az ALTCOINS elemzés indítása gombra.")


# HISTORY
with tab_history:
    st.subheader("📌 Nyitott paper trade-ek")
    if not open_df.empty:
        st.dataframe(open_df.astype(str), use_container_width=True)
    else:
        st.info("Nincs nyitott paper trade.")
    st.subheader("📜 Lezárt paper trade-ek")
    if not closed_df.empty:
        def color_trade_rows(row):
    result = str(row["result"])

    if "WIN" in result:
        return ['background-color: rgba(0,180,0,0.25); color: #90EE90'] * len(row)

    elif "LOSS" in result:
        return ['background-color: rgba(180,0,0,0.25); color: #FF9999'] * len(row)

    return [''] * len(row)


styled_closed = (
    closed_df.tail(100)
    .style
    .apply(color_trade_rows, axis=1)
)

st.dataframe(
    styled_closed,
    use_container_width=True
)
    else:
        st.info("Még nincs lezárt paper trade.")


# DISCORD
with tab_discord:
    st.subheader("🔔 Discord vezérlőpult")
    if DISCORD_WEBHOOK:
        st.success("✅ Discord webhook csatlakoztatva.")
    else:
        st.error("❌ Discord webhook nincs beállítva.")
    st.write("Webhook változó neve:")
    st.code("DISCORD_WEBHOOK", language="text")
    st.write("Aktív Discord beállítások:")
    st.write(f"LONG / ELITE LONG küldése: **{send_longs}**")
    st.write(f"SHORT / ELITE SHORT küldése: **{send_shorts}**")
    st.write(f"Trade lezárás küldése: **{send_trade_close}**")
    st.metric("Utolsó Discord üzenet", st.session_state["last_discord_message"])
    if st.button("📨 Teszt Discord üzenet"):
        ok, msg = send_discord("✅ Crypto Edge AI V3 Discord kapcsolat sikeres. A webhook működik.")
        st.success(msg) if ok else st.error(msg)
    if st.button("📊 Daily Summary küldése Discordra"):
        ok, msg = send_daily_summary(open_df, closed_df, paper_account)
        st.success(msg) if ok else st.error(msg)


# AUTO REFRESH
if auto_refresh:
    st.info(f"Automatikus frissítés {refresh_seconds} másodperc múlva...")
    time.sleep(refresh_seconds)
    st.rerun()

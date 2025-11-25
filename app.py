import streamlit as st
import subprocess
import json
from pathlib import Path
from datetime import datetime
import time
import ccxt
import pandas as pd

# =========================
# CONFIGURAÇÕES INICIAIS
# =========================
USERDIR = Path("user_data")
CONFIG_PATH = USERDIR / "config.json"
DATA_DIR = USERDIR / "data" / "gateio"
EXPORT_BT = USERDIR / "backtest_trades.json"
EXPORT_HO = USERDIR / "hyperopt_results.json"

USERDIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Freqtrade Trading App", layout="wide")
st.title("🤖 Freqtrade + GateIO + Streamlit — Backtest & Hyperopt")


# =========================
# FUNÇÃO: BAIXAR DADOS GATEIO
# =========================
def baixar_gateio(pair="BTC/USDT", timeframe="15m", since="2022-01-01"):
    st.info(f"Baixando dados de {pair} ({timeframe}) desde {since}...")

    exchange = ccxt.gateio({"enableRateLimit": True, "timeout": 20000})
    since_ms = int(pd.Timestamp(since).timestamp() * 1000)
    all_candles = []
    progress = st.progress(0)
    steps = 0

    while True:
        try:
            candles = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=since_ms, limit=1000)
        except Exception as e:
            st.warning(f"Erro: {e}")
            time.sleep(2)
            continue

        if not candles:
            break

        all_candles.extend(candles)
        since_ms = candles[-1][0] + 1
        steps += 1
        progress.progress(min(steps / 50, 1.0))

        if len(candles) < 1000:
            break

        time.sleep(exchange.rateLimit / 1000)

    if not all_candles:
        st.error("Nenhum dado retornado.")
        return

    df = pd.DataFrame(all_candles, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"], unit="ms")

    path = DATA_DIR / f"{pair.replace('/', '_')}-{timeframe}.feather"
    df.to_feather(path)

    st.success(f"Dados salvos em: {path}")
    st.write("Amostra:")
    st.dataframe(df.tail(20))


# =========================
# SIDEBAR
# =========================
st.sidebar.header("⚙️ Parâmetros")

pair = st.sidebar.text_input("Par", "BTC/USDT")
timeframe = st.sidebar.selectbox("Timeframe", ["15m", "1h"], index=0)
since_date = st.sidebar.text_input("Download desde", "2022-01-01")

strategy_name = st.sidebar.text_input("Estratégia", "AtrStochBreakout15m")

bt_start = st.sidebar.text_input("Início do backtest (YYYYMMDD)", "20220101")
bt_end = st.sidebar.text_input("Fim do backtest (YYYYMMDD)", "20241231")

timerange = f"{bt_start}-{bt_end}"

st.sidebar.write("---")
btn_download = st.sidebar.button("📥 Baixar dados")
btn_backtest = st.sidebar.button("📈 Rodar Backtest")
btn_hyperopt = st.sidebar.button("🔧 Otimizar (Hyperopt)")


# =========================
# AÇÃO: BAIXAR DADOS
# =========================
if btn_download:
    baixar_gateio(pair, timeframe, since_date)


# =========================
# FUNÇÃO: EXECUTAR BACKTEST
# =========================
def rodar_backtest():
    cmd = [
        "freqtrade", "backtesting",
        "--config", str(CONFIG_PATH),
        "--strategy", strategy_name,
        "--timerange", timerange,
        "--userdir", str(USERDIR),
        "--export", "trades",
        "--export-filename", str(EXPORT_BT),
        "--data-format-ohlcv", "feather"
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


# =========================
# AÇÃO: BACKTEST
# =========================
if btn_backtest:
    st.info("Executando backtest...")
    result = rodar_backtest()

    st.code(result.stdout + "\n" + result.stderr)

    if result.returncode == 0:
        st.success("Backtest concluído!")

        if EXPORT_BT.exists():
            df = pd.read_json(EXPORT_BT)
            st.dataframe(df)

            if "profit_abs" in df.columns:
                df["cum_profit"] = df["profit_abs"].cumsum()
                st.line_chart(df["cum_profit"])
    else:
        st.error("Erro ao rodar backtest.")


# =========================
# FUNÇÃO: HYPEROPT
# =========================
def rodar_hyperopt():
    cmd = [
        "freqtrade", "hyperopt",
        "--config", str(CONFIG_PATH),
        "--strategy", strategy_name,
        "--timerange", timerange,
        "--spaces", "all",
        "--epochs", "50",
        "--userdir", str(USERDIR),
        "--hyperopt-loss", "SharpeHyperOptLossDaily"
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


# =========================
# AÇÃO: HYPEROPT
# =========================
if btn_hyperopt:
    st.info("Rodando HYPEROPT... aguarde (pode demorar).")
    result = rodar_hyperopt()
    st.code(result.stdout + "\n" + result.stderr)

    if result.returncode == 0:
        st.success("Hyperopt concluído!")
    else:
        st.error("Erro no Hyperopt.")

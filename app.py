import streamlit as st
import subprocess
import json
from pathlib import Path
from datetime import datetime
import time

import ccxt
import pandas as pd


# =========================
# CONFIGURAÇÕES BÁSICAS
# =========================
USERDIR = Path("user_data")
CONFIG_PATH = USERDIR / "config.json"
DATA_DIR = USERDIR / "data" / "gateio"
EXPORT_PATH = USERDIR / "backtest_trades.json"

USERDIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Freqtrade Backtest App", layout="wide")
st.title("🤖 Freqtrade + GateIO + Streamlit (Backtest em 15m)")


# =========================
# FUNÇÃO: BAIXAR DADOS DA GATEIO (CCXT)
# =========================
def baixar_gateio(pair: str = "BTC/USDT", timeframe: str = "15m", since: str = "2022-01-01"):
    """
    Baixa dados OHLCV da GateIO usando CCXT e salva no formato Feather
    no caminho esperado pelo Freqtrade.
    """
    st.info(f"Baixando dados de {pair} {timeframe} a partir de {since} pela GateIO...")

    exchange = ccxt.gateio({
        "enableRateLimit": True,
        "timeout": 20000,
    })

    since_ms = int(pd.Timestamp(since).timestamp() * 1000)
    all_candles = []

    progress = st.progress(0)
    steps = 0

    while True:
        try:
            candles = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=since_ms, limit=1000)
        except Exception as e:
            st.warning(f"Erro ao buscar dados, tentando novamente em 2s...\n{e}")
            time.sleep(2)
            continue

        if not candles:
            break

        all_candles.extend(candles)
        since_ms = candles[-1][0] + 1

        steps += 1
        progress.progress(min(steps / 50, 1.0))  # barra "fake", só pra feedback visual

        # Pequena pausa para respeitar rate limit
        time.sleep(exchange.rateLimit / 1000)

        if len(candles) < 1000:
            # Não tem mais dados suficientes, encerra
            break

    if not all_candles:
        st.error("Nenhum dado retornado pela GateIO.")
        return None

    df = pd.DataFrame(
        all_candles,
        columns=["date", "open", "high", "low", "close", "volume"],
    )
    df["date"] = pd.to_datetime(df["date"], unit="ms")

    filename = f"{pair.replace('/', '_')}-{timeframe}.feather"
    path = DATA_DIR / filename
    df.to_feather(path)

    st.success(f"Dados salvos em: {path}")
    st.write(f"Total de candles: {len(df)}")

    return df


# =========================
# SIDEBAR – CONTROLES
# =========================
st.sidebar.header("⚙️ Parâmetros")

pair = st.sidebar.text_input("Par (GateIO)", "BTC/USDT")
timeframe = st.sidebar.selectbox("Timeframe", ["15m", "1h", "4h"], index=0)
since_date = st.sidebar.text_input("Data inicial p/ download (YYYY-MM-DD)", "2022-01-01")

bt_start = st.sidebar.text_input("Backtest - Data inicial (YYYYMMDD)", "20251026")
bt_end = st.sidebar.text_input("Backtest - Data final (YYYYMMDD, opcional)", "20251125")

timerange = f"{bt_start}-{bt_end}" if bt_end else f"{bt_start}-"

strategy_name = st.sidebar.text_input("Nome da Estratégia (classe)", "AtrStochBreakout15m")

st.sidebar.write("---")
btn_download = st.sidebar.button("📥 Baixar dados GateIO")
btn_backtest = st.sidebar.button("📈 Rodar Backtest")


# =========================
# AÇÃO: BAIXAR DADOS
# =========================
if btn_download:
    df = baixar_gateio(pair=pair, timeframe=timeframe, since=since_date)
    if df is not None:
        st.subheader("Amostra dos dados baixados")
        st.dataframe(df.tail(20))


# =========================
# AÇÃO: RODAR BACKTEST (FREQTRADE)
# =========================
if btn_backtest:
    st.info("Executando Freqtrade backtesting... aguarde.")

    # Verifica se o arquivo de dados existe
    data_file = DATA_DIR / f"{pair.replace('/', '_')}-{timeframe}.feather"
    if not data_file.exists():
        st.error(f"Arquivo de dados não encontrado: {data_file}. Baixe os dados primeiro.")
    else:
        st.write(f"Usando arquivo de dados: `{data_file}`")
        st.write(f"Timerange: `{timerange}`")
        st.write(f"Estratégia: `{strategy_name}`")

        # Comando de backtest (via subprocess)
        cmd = [
            "freqtrade",
            "backtesting",
            "--config", str(CONFIG_PATH),
            "--strategy", strategy_name,
            "--timerange", timerange,
            "--userdir", str(USERDIR),
            "--export", "trades",
            "--export-filename", str(EXPORT_PATH),
            "--data-format-ohlcv", "feather",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        st.subheader("Log do Freqtrade")
        st.code(result.stdout + "\n" + result.stderr)

        if result.returncode != 0:
            st.error("Erro ao executar o backtest. Veja o log acima.")
        else:
            if not EXPORT_PATH.exists():
                st.warning("Backtest rodou, mas não foi encontrado arquivo de trades exportado.")
            else:
                with open(EXPORT_PATH) as f:
                    trades_data = json.load(f)

                if not trades_data:
                    st.warning("Backtest concluído, porém nenhum trade foi gerado nesse período.")
                else:
                    df_trades = pd.DataFrame(trades_data)

                    st.subheader("📋 Trades gerados")
                    st.dataframe(df_trades)

                    # Curva de lucro acumulado
                    if "profit_abs" in df_trades.columns:
                        df_trades["cum_profit"] = df_trades["profit_abs"].cumsum()
                        st.subheader("📊 Curva de lucro acumulado (profit_abs)")
                        st.line_chart(df_trades["cum_profit"])
                    else:
                        st.warning("Coluna 'profit_abs' não encontrada no export do Freqtrade.")

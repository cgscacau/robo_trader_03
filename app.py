import streamlit as st
import subprocess
import json
from pathlib import Path
import pandas as pd

USERDIR = Path("user_data")
CONFIG_PATH = USERDIR / "config.json"
EXPORT_PATH = USERDIR / "backtest_trades.json"

st.set_page_config(page_title="Backtest Freqtrade", layout="wide")

st.title("📈 Backtest – AtrStochBreakout15m (Freqtrade + Streamlit)")

st.sidebar.header("Parâmetros do backtest")

# Período
start_date = st.sidebar.text_input("Data inicial (YYYYMMDD)", "20251026")
end_date = st.sidebar.text_input("Data final (YYYYMMDD, opcional)", "20251125")

timerange = f"{start_date}-{end_date}" if end_date else f"{start_date}-"

st.sidebar.write(f"Timerange usado: `{timerange}`")

run_bt = st.sidebar.button("🚀 Rodar backtest")

if run_bt:
    st.info("Executando Freqtrade backtesting... aguarde.")

    # Monta o comando de backtest
    cmd = [
        "freqtrade",
        "backtesting",
        "--config", str(CONFIG_PATH),
        "--strategy", "AtrStochBreakout15m",
        "--timerange", timerange,
        "--userdir", str(USERDIR),
        "--export", "trades",
        "--export-filename", str(EXPORT_PATH),
        "--data-format-ohlcv", "feather",
    ]

    # Executa o comando e captura saída
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    st.subheader("Log do Freqtrade")
    st.code(result.stdout + "\n" + result.stderr)

    if result.returncode != 0:
        st.error("Erro ao executar backtest. Veja o log acima.")
    else:
        if not EXPORT_PATH.exists():
            st.warning("Backtest rodou, mas não encontrou arquivo de trades exportado.")
        else:
            # Carregar trades exportados
            with open(EXPORT_PATH) as f:
                trades_data = json.load(f)

            if not trades_data:
                st.warning("Backtest concluído, mas não houve nenhum trade nesse período.")
            else:
                df = pd.DataFrame(trades_data)
                st.subheader("Trades gerados")
                st.dataframe(df)

                # Curva de equity simples
                df["cum_profit_pct"] = df["profit_abs"].cumsum()
                st.subheader("Curva de lucro acumulado")
                st.line_chart(df["cum_profit_pct"])

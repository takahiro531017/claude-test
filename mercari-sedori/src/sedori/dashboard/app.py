"""Streamlit ダッシュボード。起動: streamlit run src/sedori/dashboard/app.py"""
import pandas as pd
import streamlit as st

from sedori import db
from sedori.config import load_config
from sedori.inventory import store

cfg = load_config("config.yaml")
conn = db.connect(cfg.db_path)

st.title("せどり 損益ダッシュボード")

rep = store.monthly_report(conn)
if rep:
    df = pd.DataFrame(rep).set_index("month")
    c1, c2, c3 = st.columns(3)
    c1.metric("累計売上", f"{int(df['revenue'].sum()):,}円")
    c2.metric("累計利益", f"{int(df['profit'].sum()):,}円")
    c3.metric("平均回転日数", f"{df['avg_turnover_days'].dropna().mean():.1f}日")
    st.subheader("月次")
    st.dataframe(df.rename(columns={"count": "件数", "revenue": "売上", "profit": "利益",
                                    "avg_turnover_days": "平均回転日数"}))
    st.bar_chart(df[["revenue", "profit"]])
else:
    st.info("売却済みのデータがまだありません。`sedori inventory sold` で記録してください。")

days = st.slider("滞留とみなす日数", 7, 120, 30)
stag = store.stagnant_stock(conn, days)
st.subheader(f"滞留在庫({len(stag)}件)")
st.dataframe(pd.DataFrame(stag))

st.subheader("確定申告用CSV")
year = st.number_input("対象年", 2020, 2100, pd.Timestamp.now().year)
if st.button("CSVを生成"):
    path = f"data/export_{int(year)}.csv"
    n = store.export_csv(conn, path, int(year))
    st.success(f"{n}件を {path} に出力しました")
    with open(path, "rb") as f:
        st.download_button("ダウンロード", f, file_name=f"export_{int(year)}.csv")

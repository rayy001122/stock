import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import urllib.parse
import requests
from bs4 import BeautifulSoup
import feedparser

# --- 1. 頁面配置 ---
st.set_page_config(page_title="台股全方位診斷系統", layout="wide")
st.title("📈 台股專業投資工作站")

# --- 2. 自選股邏輯 (Session State) ---
if 'fav_stocks' not in st.session_state:
    st.session_state.fav_stocks = {
        "2330.TW": "台積電 (2330)",
        "2317.TW": "鴻海 (2317)",
        "2454.TW": "聯發科 (2454)",
        "2603.TW": "長榮 (2603)",
        "0050.TW": "元大台灣50"
    }

# --- 3. 側邊欄設定 ---
st.sidebar.header("📊 分析參數")

# 立即刷新按鈕
if st.sidebar.button("🔄 立即重新整理數據"):
    st.cache_data.clear()
    st.rerun()

# 股票代碼輸入（與自選股連動）
st.sidebar.subheader("⭐ 自選股快捷鍵")
# 建立一個標籤與代碼的對照表
label_to_ticker = {v: k for k, v in st.session_state.fav_stocks.items()}
selected_label = st.sidebar.selectbox("選取我的自選股", ["-- 請選擇 --"] + list(st.session_state.fav_stocks.values()))

# 如果用戶選了快捷鍵，預設值就變快捷鍵，否則手動輸入
default_ticker = label_to_ticker[selected_label] if selected_label != "-- 請選擇 --" else "2330.TW"
ticker = st.sidebar.text_input("輸入台股代碼", default_ticker).upper()

# 管理自選股功能
with st.sidebar.expander("➕ 新增/管理自選股"):
    new_ticker = st.text_input("新增代碼 (例: 2881.TW)").upper()
    new_name = st.text_input("輸入名稱 (例: 富邦金)")
    if st.button("新增至清單"):
        if new_ticker and new_name:
            st.session_state.fav_stocks[new_ticker] = f"{new_name} ({new_ticker.split('.')[0]})"
            st.rerun()
        else:
            st.error("請輸入代碼與名稱")

    st.divider()
    target_del = st.selectbox("選擇要刪除的股票", ["-- 請選擇 --"] + list(st.session_state.fav_stocks.values()))
    if st.button("❌ 刪除所選"):
        if target_del != "-- 請選擇 --":
            for k, v in list(st.session_state.fav_stocks.items()):
                if v == target_del:
                    del st.session_state.fav_stocks[k]
                    st.rerun()

st.sidebar.divider()
time_frame = st.sidebar.selectbox("K線頻率", ["1d", "1wk", "1mo"], 
                                 format_func=lambda x: {"1d":"每日", "1wk":"每週", "1mo":"每月"}[x])
period = st.sidebar.selectbox("資料回溯長度", ["1y", "2y", "5y", "max"], index=1)
display_count = st.sidebar.slider("圖表顯示最近筆數", 20, 300, 80)

# --- 4. 功能函式定義 ---

@st.cache_data(ttl=600)
def get_taiwan_news_robust(ticker_symbol):
    stock_no = ticker_symbol.split('.')[0]
    query_encoded = urllib.parse.quote(f"{stock_no} 股市")
    news_items = []
    
    # 方案 1: RSS
    try:
        rss_url = f"https://news.google.com/rss/search?q={query_encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:8]:
            news_items.append({
                'title': entry.title.split(' - ')[0],
                'link': entry.link,
                'source': entry.source.get('title', '媒體'),
                'time': entry.published
            })
        if news_items: return news_items
    except: pass

    # 方案 2: Crawler 備援
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(f"https://www.google.com/search?q={query_encoded}&tbm=nws&hl=zh-TW&gl=TW", headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for h in soup.find_all('div', role='heading')[:8]:
            parent_a = h.find_parent('a')
            if parent_a:
                news_items.append({
                    'title': h.text,
                    'link': parent_a['href'] if parent_a['href'].startswith('http') else "https://www.google.com" + parent_a['href'],
                    'source': "即時新聞", 'time': "今日"
                })
    except: pass
    return news_items

@st.cache_data(ttl=300)
def load_data(symbol, p, i):
    try:
        t_obj = yf.Ticker(symbol)
        data = t_obj.history(period=p, interval=i)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data, t_obj.info
    except:
        return pd.DataFrame(), {}

# --- 5. 數據下載與繪圖 ---
df, info = load_data(ticker, period, time_frame)

if not df.empty:
    df = df.copy()
    # 指標計算
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['HIST'] = df['MACD'] - df['SIGNAL']
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    plot_df = df.tail(display_count)

    st.subheader(f"🏢 {info.get('longName', ticker)} 基本面概況")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("本益比 (P/E)", f"{info.get('trailingPE', 'N/A')}")
    with c2: st.metric("股利殖利率", f"{info.get('dividendYield', 0)*100:.2f} %")
    with c3: st.metric("市值 (兆)", f"{info.get('marketCap', 0)/1e12:.2f}")
    with c4: st.metric("52週高/低", f"{info.get('fiftyTwoWeekHigh', 0)} / {info.get('fiftyTwoWeekLow', 0)}")

    # Plotly 圖表
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.35])
    fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="K線"), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], name="MA5", line=dict(color='orange', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name="MA20", line=dict(color='blue', width=1.5)), row=1, col=1)
    
    vol_colors = ['red' if plot_df['Close'].iloc[i] >= plot_df['Open'].iloc[i] else 'green' for i in range(len(plot_df))]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="成交量", marker_color=vol_colors), row=2, col=1)
    
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD'], name="MACD", line=dict(color='black')), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['SIGNAL'], name="Signal", line=dict(color='red')), row=3, col=1)
    hist_colors = ['#FF4B4B' if val >= 0 else '#008000' for val in plot_df['HIST']]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['HIST'], name="MACD柱", marker_color=hist_colors), row=3, col=1)

    fig.update_layout(height=800, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(t=10, b=10))
    st.plotly_chart(fig, width='stretch')

    # 診斷與新聞
    st.divider()
    st.subheader("🤖 價量與動能診斷建議")
    dc1, dc2 = st.columns(2)
    curr_close, prev_close = plot_df['Close'].iloc[-1], plot_df['Close'].iloc[-2]
    curr_vol, curr_vma5 = plot_df['Volume'].iloc[-1], plot_df['Vol_MA5'].iloc[-1]
    
    with dc1:
        if curr_close > prev_close and curr_vol > curr_vma5: st.success("✅ 量增價揚：買盤積極")
        elif curr_close < prev_close and curr_vol > curr_vma5: st.error("🚨 放量下跌：賣壓沉重")
        else: st.info("😴 量縮整理中")
        
    with dc2:
        if plot_df['MACD'].iloc[-1] > plot_df['SIGNAL'].iloc[-1]: st.success("🌟 MACD 金叉：多頭佔優")
        else: st.error("📉 MACD 死叉：偏空整理")

    st.divider()
    st.subheader("🇹🇼 台灣即時中文新聞")
    final_news = get_taiwan_news_robust(ticker)
    if final_news:
        for n in final_news:
            with st.expander(f"📰 {n['title']}"):
                st.write(f"**來源：** {n['source']} | **時間：** {n['time']}")
                st.link_button("閱讀全文", n['link'])
    else:
        st.info("目前暫無相關新聞資訊。")
else:
    st.error("無法下載資料，請檢查代碼格式。")

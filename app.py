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
import json
import os

# --- 0. 檔案存取邏輯 (確保重新整理不遺失) ---
DB_FILE = "favorites.json"

def load_favorites():
    """從檔案讀取自選股，若無檔案則提供預設清單"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "2330.TW": "台積電 (2330)",
        "2317.TW": "鴻海 (2317)",
        "2454.TW": "聯發科 (2454)",
        "2603.TW": "長榮 (2603)",
        "0050.TW": "元大台灣50"
    }

def save_favorites(data):
    """將目前的自選股清單永久存入檔案"""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 初始化 Session State (僅在啟動時執行一次)
if 'fav_stocks' not in st.session_state:
    st.session_state.fav_stocks = load_favorites()

# --- 1. 頁面配置 ---
st.set_page_config(page_title="台股全方位診斷系統", layout="wide")
st.title("📈 台股專業投資工作站")

# --- 2. 側邊欄：功能與參數 ---
st.sidebar.header("📊 分析參數")

# 立即刷新按鈕
if st.sidebar.button("🔄 立即重新整理數據"):
    st.cache_data.clear()
    st.rerun()

# 股票選取與輸入
st.sidebar.subheader("⭐ 自選股快捷鍵")
label_to_ticker = {v: k for k, v in st.session_state.fav_stocks.items()}
selected_label = st.sidebar.selectbox("選取我的自選股", ["-- 請選擇 --"] + list(st.session_state.fav_stocks.values()))

default_ticker = label_to_ticker[selected_label] if selected_label != "-- 請選擇 --" else "2330.TW"
ticker = st.sidebar.text_input("輸入台股代碼 (手動輸入)", default_ticker).upper()

# 管理自選股
with st.sidebar.expander("➕ 新增/管理自選股"):
    new_ticker = st.text_input("新增代碼 (例: 2881.TW)").upper()
    new_name = st.text_input("輸入名稱 (例: 富邦金)")
    if st.button("確認新增"):
        if new_ticker and new_name:
            st.session_state.fav_stocks[new_ticker] = f"{new_name} ({new_ticker.split('.')[0]})"
            save_favorites(st.session_state.fav_stocks)
            st.success(f"已加入 {new_name}")
            st.rerun()
        else:
            st.error("請輸入完整代碼與名稱")

    st.divider()
    target_del = st.selectbox("刪除自選股", ["-- 請選擇 --"] + list(st.session_state.fav_stocks.values()))
    if st.button("❌ 執行刪除"):
        if target_del != "-- 請選擇 --":
            for k, v in list(st.session_state.fav_stocks.items()):
                if v == target_del:
                    del st.session_state.fav_stocks[k]
                    save_favorites(st.session_state.fav_stocks)
                    st.rerun()

st.sidebar.divider()
time_frame = st.sidebar.selectbox("K線頻率", ["1d", "1wk", "1mo"], 
                                 format_func=lambda x: {"1d":"每日", "1wk":"每週", "1mo":"每月"}[x])
period = st.sidebar.selectbox("資料回溯長度", ["1y", "2y", "5y", "max"], index=1)
display_count = st.sidebar.slider("圖表顯示最近筆數", 20, 300, 80)

# --- 3. 核心功能函式 ---

@st.cache_data(ttl=600)
def get_news(ticker_symbol):
    """新聞抓取：RSS 優先 + Crawler 備援"""
    stock_no = ticker_symbol.split('.')[0]
    query = urllib.parse.quote(f"{stock_no} 股市")
    news_items = []
    
    # 方案 A: Google RSS
    try:
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)
        for entry in feed.entries[:8]:
            news_items.append({
                'title': entry.title.split(' - ')[0],
                'link': entry.link,
                'source': entry.source.get('title', '財經媒體'),
                'time': entry.published[:16]
            })
        if news_items: return news_items
    except: pass

    # 方案 B: Crawler
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(f"https://www.google.com/search?q={query}&tbm=nws&hl=zh-TW&gl=TW", headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, "html.parser")
        for h in soup.find_all('div', role='heading')[:8]:
            a = h.find_parent('a')
            if a:
                news_items.append({
                    'title': h.text, 'link': a['href'], 'source': '即時新聞', 'time': '今日'
                })
    except: pass
    return news_items

@st.cache_data(ttl=300)
def load_data(symbol, p, i):
    """股價資料下載"""
    try:
        t_obj = yf.Ticker(symbol)
        data = t_obj.history(period=p, interval=i)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data, t_obj.info
    except:
        return pd.DataFrame(), {}

# --- 4. 資料處理與繪圖 ---
df, info = load_data(ticker, period, time_frame)

if not df.empty:
    df = df.copy()
    # 技術指標
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['HIST'] = df['MACD'] - df['SIGNAL']
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    plot_df = df.tail(display_count)

    # 基本面概況
    st.subheader(f"🏢 {info.get('longName', ticker)} 基本面概況")
    cols = st.columns(4)
    cols[0].metric("本益比 (P/E)", f"{info.get('trailingPE', 'N/A')}")
    cols[1].metric("股利殖利率", f"{info.get('dividendYield', 0)*100:.2f} %")
    cols[2].metric("市值 (兆)", f"{info.get('marketCap', 0)/1e12:.2f}")
    cols[3].metric("52週高/低", f"{info.get('fiftyTwoWeekHigh', 0)} / {info.get('fiftyTwoWeekLow', 0)}")

    # Plotly 專業三層圖表
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.35])
    
    # 1. K線與均線
    fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], 
                                low=plot_df['Low'], close=plot_df['Close'], name="K線",
                                increasing_line_color='#FF0000', decreasing_line_color='#00AA00'), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], name="MA5", line=dict(color='orange', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name="MA20", line=dict(color='blue', width=1.5)), row=1, col=1)
    
    # 2. 成交量 (依漲跌變色)
    vol_colors = ['#FF0000' if plot_df['Close'].iloc[i] >= plot_df['Open'].iloc[i] else '#00AA00' for i in range(len(plot_df))]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="成交量", marker_color=vol_colors, opacity=0.8), row=2, col=1)
    
    # 3. MACD
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD'], name="MACD", line=dict(color='black')), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['SIGNAL'], name="Signal", line=dict(color='red')), row=3, col=1)
    hist_colors = ['#FF4B4B' if val >= 0 else '#008000' for val in plot_df['HIST']]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['HIST'], name="MACD柱", marker_color=hist_colors), row=3, col=1)

    fig.update_layout(height=800, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(t=10, b=10))
    st.plotly_chart(fig, width='stretch')

    # 診斷區
    st.divider()
    st.subheader("🤖 價量與動能診斷建議")
    dc1, dc2 = st.columns(2)
    c_close, p_close = plot_df['Close'].iloc[-1], plot_df['Close'].iloc[-2]
    c_vol, c_vma5 = plot_df['Volume'].iloc[-1], plot_df['Vol_MA5'].iloc[-1]
    
    with dc1:
        if c_close > p_close and c_vol > c_vma5: st.success("✅ **量增價揚**：買盤積極，攻擊力道強。")
        elif c_close < p_close and c_vol > c_vma5: st.error("🚨 **放量下跌**：賣壓沉重，注意回檔風險。")
        else: st.info("😴 **縮量整理**：目前交投冷清，等待方向確立。")
        
    with dc2:
        if plot_df['MACD'].iloc[-1] > plot_df['SIGNAL'].iloc[-1]:
            st.success("🌟 **MACD 金叉**：短期動能偏多。")
        else:
            st.error("📉 **MACD 死叉**：短期動能轉弱。")

    # 新聞區
    st.divider()
    st.subheader("🇹🇼 台灣即時中文新聞")
    news_list = get_news(ticker)
    if news_list:
        for n in news_list:
            with st.expander(f"📰 {n['title']}"):
                st.write(f"**來源：** {n['source']} | **時間：** {n['time']}")
                st.link_button("閱讀全文", n['link'])
    else:
        st.info("目前暫無即時新聞。")
else:
    st.error("無法下載資料，請確認代碼（例如 2330.TW）。")

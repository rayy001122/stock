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
import re

# --- 1. 頁面配置 ---
st.set_page_config(page_title="台股全方位診斷系統", layout="wide")
st.title("📈 台股專業投資工作站")

# --- 2. 快捷選單邏輯 (支援新增/刪除) ---
if 'fav_stocks' not in st.session_state:
    st.session_state.fav_stocks = {
        "2330.TW": "台積電 (2330)",
        "2317.TW": "鴻海 (2317)",
        "2454.TW": "聯發科 (2454)",
        "2603.TW": "長榮 (2603)",
        "0050.TW": "元大台灣50"
    }

st.sidebar.header("⭐ 自選股快捷鍵")

with st.sidebar.expander("➕ 新增/管理自選股"):
    new_ticker = st.text_input("輸入代碼 (例: 2881.TW)").upper()
    new_name = st.text_input("輸入名稱 (例: 富邦金)")
    if st.button("新增至清單"):
        if new_ticker and new_name:
            st.session_state.fav_stocks[new_ticker] = f"{new_name} ({new_ticker.split('.')[0]})"
            st.rerun()
        else:
            st.error("請輸入完整代碼與名稱")

    target_del = st.selectbox("選擇要刪除的股票", ["-- 請選擇 --"] + list(st.session_state.fav_stocks.values()))
    if st.button("❌ 刪除所選"):
        if target_del != "-- 請選擇 --":
            for k, v in list(st.session_state.fav_stocks.items()):
                if v == target_del:
                    del st.session_state.fav_stocks[k]
                    st.rerun()

st.sidebar.divider()

fav_options = {v: k for k, v in st.session_state.fav_stocks.items()}
selected_label = st.sidebar.selectbox("快速切換標的", list(fav_options.keys()))
ticker = fav_options[selected_label]

# --- 3. 分析參數設定 ---
st.sidebar.header("📊 分析參數")
time_frame = st.sidebar.selectbox("K線頻率", ["1d", "1wk", "1mo"], 
                                 format_func=lambda x: {"1d":"每日", "1wk":"每週", "1mo":"每月"}[x])
period = st.sidebar.selectbox("資料回溯長度", ["1y", "2y", "5y", "max"], index=1)
display_count = st.sidebar.slider("圖表顯示最近筆數", 20, 300, 80)

# --- 4. 功能函式定義 ---

@st.cache_data(ttl=600)
def get_taiwan_news_robust(ticker_symbol):
    stock_no = ticker_symbol.split('.')[0]
    query_str = f"{stock_no} 股價 新聞"
    query_encoded = urllib.parse.quote(query_str)
    news_items = []
    
    # 方案 1: RSS (最穩定)
    try:
        rss_url = f"https://news.google.com/rss/search?q={query_encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        if feed.entries:
            for entry in feed.entries[:8]:
                clean_title = entry.title.split(' - ')[0]
                news_items.append({
                    'title': clean_title,
                    'link': entry.link,
                    'source': entry.source.get('title', '財經媒體'),
                    'time': entry.published[:16] if 'published' in entry else "近期"
                })
            if news_items: return news_items
    except Exception:
        pass
    
    # 方案 2: 直接網頁解析 (備援)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    try:
        search_url = f"https://www.google.com/search?q={query_encoded}&tbm=nws&hl=zh-TW&gl=TW"
        resp = requests.get(search_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # 針對 Google 新聞搜尋頁面的多種可能標籤進行抓取
            articles = soup.find_all(['div', 'a'], {'role': re.compile(r'heading|main')}) or soup.find_all('div', class_='SoR6p')
            for item in articles[:10]:
                title = item.get_text()
                link_tag = item.find_parent('a') or (item if item.name == 'a' else None)
                if link_tag and link_tag.get('href') and len(title) > 5:
                    news_items.append({
                        'title': title,
                        'link': link_tag['href'] if link_tag['href'].startswith('http') else "https://www.google.com" + link_tag['href'],
                        'source': "即時新聞",
                        'time': "今日"
                    })
                if len(news_items) >= 8: break
    except Exception:
        pass
    return news_items

@st.cache_data
def load_data(symbol, p, i):
    try:
        t_obj = yf.Ticker(symbol)
        data = t_obj.history(period=p, interval=i)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data, t_obj.info
    except:
        return pd.DataFrame(), {}

# --- 5. 執行資料下載 ---
df, info = load_data(ticker, period, time_frame)

if not df.empty:
    df = df.copy()
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['HIST'] = df['MACD'] - df['SIGNAL']
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    plot_df = df.tail(display_count)

    # --- 6. 基本面資訊欄 ---
    st.subheader(f"🏢 {info.get('longName', ticker)} 基本面概況")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("本益比 (P/E)", f"{info.get('trailingPE', 'N/A')}")
    with c2: 
        dy = info.get('dividendYield', 0)
        st.metric("股利殖利率", f"{dy*100:.2f} %" if dy else "N/A")
    with c3: st.metric("市值 (兆)", f"{info.get('marketCap', 0)/1e12:.2f}")
    with c4: st.metric("52週高/低", f"{info.get('fiftyTwoWeekHigh', 0)} / {info.get('fiftyTwoWeekLow', 0)}")

    # --- 7. Plotly 三層圖表 ---
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.35])

    fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'],
                                 low=plot_df['Low'], close=plot_df['Close'], name="K線",
                                 increasing_line_color='#FF0000', decreasing_line_color='#00AA00'), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], name="MA5", line=dict(color='orange', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name="MA20", line=dict(color='blue', width=1.5)), row=1, col=1)

    vol_colors = ['red' if plot_df['Close'].iloc[i] >= plot_df['Open'].iloc[i] else 'green' for i in range(len(plot_df))]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="成交量", marker_color=vol_colors, opacity=0.7), row=2, col=1)

    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD'], name="MACD(黑線)", line=dict(color='black', width=1.2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['SIGNAL'], name="Signal(紅線)", line=dict(color='red', width=1.2)), row=3, col=1)
    hist_colors = ['#FF4B4B' if val >= 0 else '#008000' for val in plot_df['HIST']]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['HIST'], name="MACD柱", marker_color=hist_colors), row=3, col=1)

    fig.update_layout(height=800, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(t=10, b=10))
    st.plotly_chart(fig, width='stretch')

    # --- 8. 診斷區 ---
    st.divider()
    curr_close = plot_df['Close'].iloc[-1]
    curr_vol = plot_df['Volume'].iloc[-1]
    curr_vma5 = plot_df['Vol_MA5'].iloc[-1]
    curr_macd = plot_df['MACD'].iloc[-1]
    curr_sig = plot_df['SIGNAL'].iloc[-1]
    prev_macd = plot_df['MACD'].iloc[-2]

    st.subheader("🤖 價量與動能診斷建議")
    dc1, dc2 = st.columns(2)
    with dc1:
        if curr_close > plot_df['Close'].iloc[-2] and curr_vol > curr_vma5:
            st.success("✅ **量增價揚**：買盤積極，趨勢有撐。")
        elif curr_close > plot_df['Close'].iloc[-2] and curr_vol < curr_vma5:
            st.warning("⚠️ **量價背離**：動力枯竭，小心追高。")
        elif curr_close < plot_df['Close'].iloc[-2] and curr_vol > curr_vma5:
            st.error("🚨 **放量下跌**：賣壓沉重，注意風險。")
        else:
            st.info("😴 **量縮整理**：觀望中，等待方向。")
    with dc2:
        if curr_macd > curr_sig:
            st.success("🌟 **MACD 金叉**：多頭動能轉強。") if curr_macd > prev_macd else st.warning("⚖️ **動能減弱**。")
        else:
            st.error("📉 **MACD 死叉**：動能偏弱。")

    # --- 9. 新聞區 ---
    st.divider()
    st.subheader("🇹🇼 台灣即時中文新聞")
    with st.spinner('獲取最新情報中...'):
        final_news = get_taiwan_news_robust(ticker)
        if final_news:
            for n in final_news:
                with st.expander(f"📰 {n['title']}"):
                    st.write(f"**來源：** {n['source']} | **時間：** {n['time']}")
                    st.link_button("閱讀全文", n['link'])
        else:
            st.info("目前該標的暫無即時新聞。")
else:
    st.error("無法下載資料，請檢查代碼格式（需含 .TW）。")

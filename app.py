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

# --- 2. 側邊欄設定 ---
st.sidebar.header("📊 分析參數")
ticker = st.sidebar.text_input("輸入台股代碼 (例: 2330.TW)", "2330.TW").upper()
time_frame = st.sidebar.selectbox("K線頻率", ["1d", "1wk", "1mo"], 
                                 format_func=lambda x: {"1d":"每日", "1wk":"每週", "1mo":"每月"}[x])
period = st.sidebar.selectbox("資料回溯長度", ["1y", "2y", "5y", "max"], index=1)
display_count = st.sidebar.slider("圖表顯示最近筆數", 20, 300, 80)

# --- 3. 功能函式定義 ---

@st.cache_data(ttl=600)
def get_taiwan_news_robust(ticker_symbol):
    """雙重保險版新聞抓取：RSS 優先 + Role-Based 爬蟲"""
    stock_no = ticker_symbol.split('.')[0]
    query_str = f"{stock_no} 股市"
    query_encoded = urllib.parse.quote(query_str)
    
    news_items = []

    # --- 方案 1: RSS 解析 (標題最整齊) ---
    try:
        rss_url = f"https://news.google.com/rss/search?q={query_encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        if feed.entries:
            for entry in feed.entries[:8]:
                news_items.append({
                    'title': entry.title.split(' - ')[0], # 去除標題後方的媒體名
                    'link': entry.link,
                    'source': entry.source.get('title', '台灣財經媒體'),
                    'time': entry.published
                })
            return news_items
    except:
        pass

    # --- 方案 2: 強效網頁爬蟲 (當 RSS 被阻擋時) ---
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    search_url = f"https://www.google.com/search?q={query_encoded}&tbm=nws&hl=zh-TW&gl=TW"
    
    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # 使用 role="heading" 抓取新聞標題區塊，這比 class name 更穩定
            headings = soup.find_all('div', role='heading')
            for h in headings:
                # 往上找最近的 <a> 標籤
                parent_a = h.find_parent('a')
                if parent_a and parent_a.get('href'):
                    news_items.append({
                        'title': h.text,
                        'link': parent_a['href'] if parent_a['href'].startswith('http') else "https://www.google.com" + parent_a['href'],
                        'source': "即時財經",
                        'time': "今日"
                    })
                if len(news_items) >= 8: break
    except Exception as e:
        print(f"Crawler Error: {e}")

    return news_items

@st.cache_data
def load_data(symbol, p, i):
    """下載股價與基本面資料"""
    try:
        t_obj = yf.Ticker(symbol)
        data = t_obj.history(period=p, interval=i)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data, t_obj.info
    except:
        return pd.DataFrame(), {}

# --- 4. 執行資料下載 ---
df, info = load_data(ticker, period, time_frame)

if not df.empty:
    df = df.copy()
    # 技術指標計算
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['HIST'] = df['MACD'] - df['SIGNAL']
    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    
    plot_df = df.tail(display_count)

    # --- 5. 基本面資訊欄 ---
    st.subheader(f"🏢 {info.get('longName', ticker)} 基本面概況")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("本益比 (P/E)", f"{info.get('trailingPE', 'N/A')}")
    with c2:
        st.metric("股利殖利率", f"{info.get('dividendYield', 0)*100:.2f} %")
    with c3:
        st.metric("市值 (兆)", f"{info.get('marketCap', 0)/1e12:.2f}")
    with c4:
        st.metric("52週高/低", f"{info.get('fiftyTwoWeekHigh', 0)} / {info.get('fiftyTwoWeekLow', 0)}")

    # --- 6. Plotly 三層專業圖表 ---
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.35])

    # K線
    fig.add_trace(go.Candlestick(
        x=plot_df.index, open=plot_df['Open'], high=plot_df['High'],
        low=plot_df['Low'], close=plot_df['Close'], name="K線",
        increasing_line_color='#FF0000', decreasing_line_color='#00AA00'
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA5'], name="MA5", line=dict(color='orange', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], name="MA20", line=dict(color='blue', width=1.5)), row=1, col=1)

    # 成交量
    vol_colors = ['red' if plot_df['Close'].iloc[i] >= plot_df['Open'].iloc[i] else 'green' for i in range(len(plot_df))]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name="成交量", marker_color=vol_colors, opacity=0.7), row=2, col=1)

    # MACD
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD'], name="MACD (黑線)", line=dict(color='black', width=1)), row=3, col=1)
    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['SIGNAL'], name="Signal (紅線)", line=dict(color='red', width=1)), row=3, col=1)
    hist_colors = ['#FF4B4B' if val >= 0 else '#008000' for val in plot_df['HIST']]
    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['HIST'], name="MACD柱", marker_color=hist_colors), row=3, col=1)

    fig.update_layout(height=800, xaxis_rangeslider_visible=False, template="plotly_white", margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # --- 7. 診斷區 ---
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
            st.success("🌟 **MACD 金叉**：多頭動能轉強。") if curr_macd > prev_macd else st.warning("⚖️ **動能減弱**：金叉但斜率轉平。")
        else:
            st.error("📉 **MACD 死叉**：動能偏弱。")

    # --- 8. 台灣中文新聞區 (雙重保險版) ---
    st.divider()
    st.subheader("🇹🇼 台灣即時中文新聞")
    final_news = get_taiwan_news_robust(ticker)
    
    if final_news:
        for n in final_news:
            with st.expander(f"📰 {n['title']}"):
                st.write(f"**來源：** {n['source']} | **時間：** {n['time']}")
                st.link_button("閱讀全文", n['link'])
    else:
        st.info("暫無即時中文新聞，請確認網路連線。")

else:
    st.error("無法下載資料，請檢查代碼格式（需含 .TW）。")

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime, date, timedelta
import json
import re
import concurrent.futures
import hashlib
import base64
from cryptography.fernet import Fernet
from supabase import create_client, Client

st.set_page_config(page_title="個人加密資產金庫", page_icon="🔐", layout="wide")

# ========================================================
# ⚡ 效能優化：引入局部渲染技術
# ========================================================
if hasattr(st, "fragment"):
    st_fragment = st.fragment
elif hasattr(st, "experimental_fragment"):
    st_fragment = st.experimental_fragment
else:
    def st_fragment(func): return func

# ========================================================
# 🚀 零知識加密與 Supabase 連線核心
# ========================================================
@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"⚠️ Supabase 連線失敗，請確認 secrets.toml 設定。錯誤：{e}")
    st.stop()

def get_encryption_key(password: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(password.encode('utf-8')).digest())

def encrypt_data(data, password: str) -> str:
    f = Fernet(get_encryption_key(password))
    return f.encrypt(json.dumps(data, ensure_ascii=False).encode('utf-8')).decode('utf-8')

def decrypt_data(encrypted_str: str, password: str):
    try: return json.loads(Fernet(get_encryption_key(password)).decrypt(encrypted_str.encode('utf-8')).decode('utf-8'))
    except Exception: return None

def save_data(category, data):
    try:
        enc_payload = encrypt_data(data, st.session_state.password)
        res = supabase.table("encrypted_vault").select("id").eq("user_id", st.session_state.user.id).eq("category", category).execute()
        if res.data:
            supabase.table("encrypted_vault").update({"encrypted_payload": enc_payload}).eq("id", res.data[0]["id"]).execute()
        else:
            supabase.table("encrypted_vault").insert({"user_id": st.session_state.user.id, "category": category, "encrypted_payload": enc_payload}).execute()
    except Exception as e:
        st.error(f"儲存 {category} 失敗: {e}")

def load_data(category, default_val):
    try:
        res = supabase.table("encrypted_vault").select("encrypted_payload").eq("user_id", st.session_state.user.id).eq("category", category).execute()
        if res.data: return decrypt_data(res.data[0]["encrypted_payload"], st.session_state.password) or default_val
    except Exception: pass
    return default_val

# ========================================================
# 🔐 登入與註冊介面
# ========================================================
if "user" not in st.session_state: st.session_state.user = None
if "password" not in st.session_state: st.session_state.password = None

if st.session_state.user is None:
    st.markdown("<h2 style='text-align: center; margin-top: 50px;'>🔐 端到端加密資產金庫</h2>", unsafe_allow_html=True)
    st.caption("<div style='text-align: center;'>你的資料在離開此設備前即被加密。連系統管理員也無法讀取。</div>", unsafe_allow_html=True)
    st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_reg = st.tabs(["登入", "註冊新帳號"])
        with tab_login:
            login_email = st.text_input("Email", key="l_email")
            login_pwd = st.text_input("密碼", type="password", key="l_pwd")
            if st.button("登入金庫", use_container_width=True, type="primary"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": login_email, "password": login_pwd})
                    st.session_state.user, st.session_state.password = res.user, login_pwd
                    st.rerun()
                except Exception: st.error("登入失敗，請確認帳號密碼是否正確。")
        with tab_reg:
            reg_email = st.text_input("Email", key="r_email")
            reg_pwd = st.text_input("密碼 (請牢記！作為加密鑰匙，遺失將永遠無法解密資料)", type="password", key="r_pwd")
            if st.button("註冊帳號", use_container_width=True):
                try:
                    supabase.auth.sign_up({"email": reg_email, "password": reg_pwd})
                    st.success("註冊成功！如果 Supabase 預設開啟信箱驗證，請先去收信驗證後登入。")
                except Exception as e: st.error(f"註冊失敗: {e}")
    st.stop()

# ========================================================
# 📊 正式 App 初始化與狀態管理
# ========================================================
st.markdown("""<style>section[data-testid="stSidebar"] > div:first-child { overflow-y: auto; } div[data-testid="collapsedControl"], button[data-testid="stSidebarCollapseButton"] { position: fixed !important; top: 10px !important; z-index: 999999; } div[data-testid="stTextInput"] div { padding-top: 0px; padding-bottom: 0px; } .js-plotly-plot .plotly .nsewdrag, .js-plotly-plot .plotly .ewdrag, .js-plotly-plot .plotly .nsdrag, .js-plotly-plot .plotly .cursor-crosshair, .js-plotly-plot .plotly .cursor-move { cursor: default !important; }</style>""", unsafe_allow_html=True)

for k, def_val in [("transactions", []), ("manual_prices", {}), ("cash_accounts", []), ("liabilities_accounts", []), ("history_snapshots", {})]:
    if k not in st.session_state: st.session_state[k] = load_data(k, def_val)

for k, def_val in [("selected_category", None), ("editing_id", None), ("edit_cash_id", None), ("edit_liability_id", None), ("display_currency", "TWD"), ("selected_extras", []), ("visible_items", set()), ("clear_form", False), ("privacy_mode", False), ("prev_ticker", ""), ("prev_type", "台股"), ("prev_name_input", ""), ("prev_ticker_input", "")]:
    if k not in st.session_state: st.session_state[k] = def_val

@st.cache_data(ttl=300, show_spinner=False)
def get_rate(symbol: str):
    try:
        t = yf.Ticker(symbol)
        rate = t.fast_info.get("last_price")
        if rate: return round(float(rate), 4)
        hist = t.history(period="5d")
        if not hist.empty: return round(float(hist["Close"].dropna().iloc[-1]), 4)
    except Exception: pass
    return None

usd_twd = get_rate("USDTWD=X") or 32.4
btc_usd = get_rate("BTC-USD") or 95000.0
EXTRA_RATES = {"EUR/TWD": "EURTWD=X", "JPY/TWD": "JPYTWD=X", "GBP/TWD": "GBPTWD=X", "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD"}

def get_latest_price(ticker: str):
    if not ticker: return None
    t = ticker.strip().upper()
    cl = t.replace(".TW", "").replace(".TWO", "")
    is_tw = cl.isdigit() or (len(cl) > 1 and cl[:-1].isdigit() and cl[-1] in ["B", "L", "R"])
    cands = [f"{cl}.TW", f"{cl}.TWO"] if is_tw else [t] + ([f"{t}.TW", f"{t}.TWO"] if not t.endswith((".TW", ".TWO")) and t.isalnum() and not t.isalpha() else [])

    for sym in cands:
        try:
            stock = yf.Ticker(sym)
            price = stock.fast_info.get("last_price")
            if price is not None and not pd.isna(price) and price > 0: return round(float(price), 4)
            hist = stock.history(period="1mo", auto_adjust=False)
            if not hist.empty: return round(float(hist["Close"].dropna().iloc[-1]), 4)
        except Exception: continue
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_historical_prices_for_chart(ticker: str, start_date: pd.Timestamp):
    if not ticker: return pd.DataFrame()
    t = ticker.strip().upper()
    cl = t.replace(".TW", "").replace(".TWO", "")
    is_tw = cl.isdigit() or (len(cl) > 1 and cl[:-1].isdigit() and cl[-1] in ["B", "L", "R"])
    cands = [f"{cl}.TW", f"{cl}.TWO"] if is_tw else [t] + ([f"{t}.TW", f"{t}.TWO"] if not t.endswith((".TW", ".TWO")) and t.isalnum() and not t.isalpha() else [])

    for sym in cands:
        try:
            hist = yf.Ticker(sym).history(start=start_date, auto_adjust=False)
            if not hist.empty:
                hist.index = hist.index.tz_localize(None).normalize()
                return hist
        except: continue
    return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_prices(tickers: tuple):
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        f2t = {executor.submit(get_latest_price, t): t for t in tickers}
        for future in concurrent.futures.as_completed(f2t):
            t = f2t[future]
            try: results[t] = future.result()
            except Exception: results[t] = None
    return results

# ========================================================
# ⚡ 效能優化：Plotly 圖表建構快取
# ========================================================
@st.cache_data(show_spinner=False)
def _build_cash_trend_fig(dates, values, unit_str, privacy: bool):
    fig = go.Figure()
    hover_temp = "%{x|%Y-%m-%d}<br>" + unit_str + " %{y:,.0f}<extra></extra>" if not privacy else "%{x|%Y-%m-%d}<br>＊＊＊＊<extra></extra>"
    fig.add_trace(go.Scatter(
        x=dates, y=values, mode='lines', name='現金總額',
        line=dict(color='#00CC96', width=3, shape='linear'),
        fill='tozeroy', fillcolor='rgba(0, 204, 150, 0.1)', hovertemplate=hover_temp
    ))
    if dates:
        dtick_val = 86400000 if len(dates) <= 40 else None
        today_dt = pd.to_datetime(date.today())
        start_date = today_dt - pd.DateOffset(months=1) if len(dates) <= 30 else pd.to_datetime(min(dates)) - pd.Timedelta(days=3)
        fig.update_layout(
            margin=dict(t=10, b=20, l=10, r=10), height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(range=[start_date, today_dt + pd.Timedelta(days=1)], showgrid=False, tickfont=dict(color="#e2e8f0"), tickformat="%Y-%m-%d", type="date", dtick=dtick_val),
            yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not privacy),
            hovermode="x unified", dragmode="pan"
        )
    return fig

@st.cache_data(show_spinner=False)
def _build_pie_fig(labels, values, colors, unit_str, privacy: bool, height=300):
    hover = "%{label}<br>%{percent}<br>" + unit_str + " %{value:,.0f}<extra></extra>" if not privacy else "%{label}<br>%{percent}<extra></extra>"
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, pull=[0.03]*len(labels),
        textinfo="label+percent", textfont=dict(size=14, color="#ffffff"),
        marker=dict(colors=colors, line=dict(color="#111111", width=1.5)),
        sort=False, hovertemplate=hover
    )])
    fig.update_layout(margin=dict(t=10, b=50, l=10, r=10), height=height, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

@st.cache_data(show_spinner=False)
def _build_lib_trend_fig(dates, values, unit_str, privacy: bool):
    fig = go.Figure()
    hover_temp = "%{x|%Y-%m-%d}<br>" + unit_str + " %{y:,.0f}<extra></extra>" if not privacy else "%{x|%Y-%m-%d}<br>＊＊＊＊<extra></extra>"
    fig.add_trace(go.Scatter(
        x=dates, y=values, mode='lines', name='負債總額',
        line=dict(color='#EF553B', width=3, shape='linear'),
        fill='tozeroy', fillcolor='rgba(239, 85, 59, 0.1)', hovertemplate=hover_temp
    ))
    if dates:
        dtick_val = 86400000 if len(dates) <= 40 else None
        today_dt = pd.to_datetime(date.today())
        start_date = today_dt - pd.DateOffset(months=1) if len(dates) <= 30 else pd.to_datetime(min(dates)) - pd.Timedelta(days=3)
        fig.update_layout(
            margin=dict(t=10, b=20, l=10, r=10), height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(range=[start_date, today_dt + pd.Timedelta(days=1)], showgrid=False, tickfont=dict(color="#e2e8f0"), tickformat="%Y-%m-%d", type="date", dtick=dtick_val),
            yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not privacy),
            hovermode="x unified", dragmode="pan"
        )
    return fig

@st.cache_data(show_spinner=False)
def _build_overall_trend_fig(dates, values, costs, pnl_val_texts, pnl_pct_texts, unit_str, privacy: bool, val_name: str):
    fdf_dates = pd.to_datetime(dates)
    fdf_value, fdf_cost = list(values), list(costs)
    value_gain = [max(v, c) for v, c in zip(fdf_value, fdf_cost)]
    value_loss = [min(v, c) for v, c in zip(fdf_value, fdf_cost)]
    y_max, y_min = max(max(fdf_value or [0]), max(fdf_cost or [0])), min(min(fdf_value or [0]), min(fdf_cost or [0]))
    y_range = y_max - y_min if y_max != y_min else 1.0
    pnl_y = [min(v, c) - (y_range * 0.005) for v, c in zip(fdf_value, fdf_cost)]
    pct_y = [min(v, c) - (y_range * 0.010) for v, c in zip(fdf_value, fdf_cost)]

    fig = go.Figure()
    if privacy:
        hover_temp_val = "＊＊＊＊<extra>" + val_name + "</extra>"
        hover_temp_cost = "＊＊＊＊<extra>成本</extra>"
        hover_temp_pnl = "＊＊＊＊<extra>損益</extra>"
        hover_temp_pct = "＊＊＊＊<extra>$$ %</extra>"
    else:
        hover_temp_val = " : " + unit_str + " %{y:,.0f}<extra>" + val_name + "</extra>"
        hover_temp_cost = " : " + unit_str + " %{y:,.0f}<extra>成本</extra>"
        hover_temp_pnl = " : %{customdata}<extra>損益</extra>"
        hover_temp_pct = " : %{customdata}<extra>$$ %</extra>"

    fig.add_trace(go.Scatter(x=fdf_dates, y=pct_y, mode='lines', name='百分比', line=dict(color='rgba(0,0,0,0)', width=0), customdata=pnl_pct_texts if not privacy else None, hovertemplate=hover_temp_pct, showlegend=False, connectgaps=False))
    fig.add_trace(go.Scatter(x=fdf_dates, y=pnl_y, mode='lines', name='損益', line=dict(color='rgba(0,0,0,0)', width=0), customdata=pnl_val_texts if not privacy else None, hovertemplate=hover_temp_pnl, showlegend=False, connectgaps=False))
    fig.add_trace(go.Scatter(x=fdf_dates, y=fdf_cost, mode='lines', name='成本', line=dict(color='#3b82f6', width=3), hovertemplate=hover_temp_cost))
    fig.add_trace(go.Scatter(x=fdf_dates, y=fdf_value, mode='lines', name=val_name, line=dict(color='#00CC96', width=3), hovertemplate=hover_temp_val))
    fig.add_trace(go.Scatter(x=fdf_dates, y=fdf_cost, mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=fdf_dates, y=value_gain, mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(255, 193, 7, 0.2)', hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=fdf_dates, y=fdf_cost, mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=fdf_dates, y=value_loss, mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(239, 68, 68, 0.2)', hoverinfo='skip', showlegend=False))
    
    dtick_val = 86400000 if len(fdf_dates) <= 40 else None
    fig.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False, tickformat="%Y-%m-%d", dtick=dtick_val), yaxis=dict(showgrid=True, showticklabels=not privacy), hovermode="x unified", dragmode="pan")
    return fig

@st.cache_data(show_spinner=False)
def _build_holdings_bar_fig(labels, values_display, bar_text_labels, bar_pie_colors, privacy: bool, bar_font_size: int):
    fig = go.Figure(data=[go.Bar(
        x=labels, y=values_display, text=bar_text_labels, textposition="outside",
        textfont=dict(size=bar_font_size, color="#e2e8f0"), marker_color=bar_pie_colors,
        hovertemplate="%{x}<br>%{text}<extra></extra>" if privacy else "%{x}<br>%{text}<br>%{y:,.2f}<extra></extra>"
    )])
    fig.update_layout(
        margin=dict(t=40, b=40, l=40, r=40), height=650, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, tickfont=dict(size=16, color="#e2e8f0")), yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not privacy)
    )
    return fig

@st.cache_data(show_spinner=False)
def _build_holdings_pie_fig(labels, values_abs, pie_text_labels, bar_pie_colors, privacy: bool):
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values_abs, pull=[0.03]*len(labels), text=pie_text_labels, textinfo="text", textposition="auto",
        insidetextfont=dict(size=22, color="#ffffff"), outsidetextfont=dict(size=16, color="#e2e8f0"),
        hovertemplate="%{label}<br>%{percent}<extra></extra>" if privacy else "%{label}<br>%{percent}<br>%{value:,.2f}<extra></extra>",
        marker=dict(colors=bar_pie_colors, line=dict(color="#111111", width=1.5)), sort=False, direction="clockwise"
    )])
    fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=750, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_traces(domain=dict(x=[0.15, 0.85], y=[0.15, 0.85]))
    return fig

@st.cache_data(show_spinner=False)
def _prepare_trend_hist_data(history_json: str, selected_cat, display_currency: str):
    try: history_snapshots = json.loads(history_json)
    except: return []
    hist_d = []
    for d_str, v in history_snapshots.items():
        if isinstance(v, dict) and v.get("version") == "v2":
            d_data = v.get(display_currency, v.get("TWD"))
            val, cost, liab = d_data.get("value", 0), d_data.get("cost", 0), d_data.get("liability", 0.0)
            if selected_cat is None: vc, cc = val - liab, cost - liab
            else:
                cat_data = d_data.get("categories", {}).get(selected_cat, {})
                vc, cc = cat_data.get("value", 0), cat_data.get("cost", 0)
            hist_d.append({'Date': d_str, 'Value': vc, 'Cost': cc})
        else:
            val = v.get("value", 0) if isinstance(v, dict) else 0
            liab = v.get("liability", 0) if isinstance(v, dict) else 0
            hist_d.append({'Date': d_str, 'Value': val - liab, 'Cost': 0})
    return hist_d

# ========================================================
# 🚀 做空與多頭會計核心引擎
# ========================================================
def calculate_holdings(transactions):
    holdings = {}
    for t in transactions:
        key = t.get("ticker") or t.get("name")
        if not key: continue
        if key not in holdings:
            holdings[key] = {"名稱": t.get("name", key), "代號": t.get("ticker", ""), "幣別": t.get("currency", "TWD"), "類型": t.get("type_category", "其他"), "數量": 0.0, "avg_cost": 0.0, "CC權利金": 0.0, "SP權利金": 0.0, "股息": 0.0, "已實現損益": 0.0, "歷史買進數量": 0.0, "歷史賣出數量": 0.0}
        
        h, qty, price, action = holdings[key], float(t.get("quantity", 0)), float(t.get("price", 0)), t["type"]
        
        if action in ["Sell Put", "Covered Call", "配息"]:
            amount = price if qty == 0 else qty * price
            if action == "Covered Call": h["CC權利金"] += amount; h["已實現損益"] += amount
            elif action == "Sell Put": h["SP權利金"] += amount; h["已實現損益"] += amount
            elif action == "配息": h["股息"] += amount; h["已實現損益"] += amount
            continue

        if action == "買進":
            h["歷史買進數量"] += qty
            if h["數量"] >= 0: 
                new_qty = h["數量"] + qty
                h["avg_cost"] = (h["數量"] * h["avg_cost"] + qty * price) / new_qty if new_qty > 0 else 0
                h["數量"] = new_qty
            else: 
                cover_qty = min(qty, abs(h["數量"]))
                h["已實現損益"] += (h["avg_cost"] - price) * cover_qty 
                h["數量"] += cover_qty
                remaining_buy = qty - cover_qty
                if remaining_buy > 0: 
                    h["數量"] = remaining_buy
                    h["avg_cost"] = price
                elif abs(h["數量"]) < 1e-5:
                    h["數量"] = 0.0
                    h["avg_cost"] = 0.0
                    
        elif action == "賣出":
            h["歷史賣出數量"] += qty
            if h["數量"] <= 0: 
                new_qty_abs = abs(h["數量"]) + qty
                h["avg_cost"] = (abs(h["數量"]) * h["avg_cost"] + qty * price) / new_qty_abs if new_qty_abs > 0 else 0
                h["數量"] -= qty
            else: 
                sell_qty = min(qty, h["數量"])
                h["已實現損益"] += (price - h["avg_cost"]) * sell_qty 
                h["數量"] -= sell_qty
                remaining_sell = qty - sell_qty
                if remaining_sell > 0: 
                    h["數量"] = -remaining_sell
                    h["avg_cost"] = price
                elif abs(h["數量"]) < 1e-5:
                    h["數量"] = 0.0
                    h["avg_cost"] = 0.0

    result = []
    for key, h in holdings.items():
        h["原始總成本"] = h["數量"] * h["avg_cost"] 
        if abs(h["數量"]) > 0.0001 or h["CC權利金"] > 0 or h["SP權利金"] > 0 or h["股息"] > 0 or h["已實現損益"] != 0 or h["歷史買進數量"] > 0 or h["歷史賣出數量"] > 0:
            result.append({
                "名稱": h["名稱"], "代號": h["代號"], "幣別": h["幣別"], "類型": h["類型"],
                "數量": h["數量"], "原始總成本": h["原始總成本"], "平均價格": h["avg_cost"],
                "CC權利金": h["CC權利金"], "SP權利金": h["SP權利金"], "股息": h["股息"],
                "已實現損益": h["已實現損益"], "歷史買進數量": h["歷史買進數量"], "歷史賣出數量": h["歷史賣出數量"], "is_cash": False
            })
    return result

def safe_float(text):
    try: return float(text) if str(text).strip() else None
    except Exception: return None

def mask_val(val_str): return "＊＊＊＊" if st.session_state.privacy_mode else val_str

def format_dynamic_qty(qty, price, currency):
    if pd.isna(qty) or qty is None: return "—"
    try: qty_val = float(qty)
    except: return str(qty)
    try: price_val = float(price)
    except: price_val = 0.0
    
    if currency == "TWD": price_usd = price_val / usd_twd
    elif currency == "BTC": price_usd = price_val * (btc_usd if btc_usd else 95000.0)
    else: price_usd = price_val
    
    if price_usd >= 10000: decimals = 4
    elif price_usd >= 5000: decimals = 3
    elif price_usd >= 1500: decimals = 2
    elif price_usd >= 500: decimals = 1
    else:
        if qty_val % 1 != 0: decimals = 2
        else: decimals = 0
    return f"{qty_val:,.{decimals}f}"

def fmt(num, decimals=2):
    if pd.isna(num) or num is None: return "—"
    if isinstance(num, (int, float)) and 0 < num < 1: return f"{num:,.4f}"
    return f"{num:,.{decimals}f}"

# ========================================================
# 🚀 核心資料與數值預先計算區 (⚡極速向量化優化)
# ========================================================
display_currency = st.session_state.display_currency
privacy = st.session_state.privacy_mode
unit = "NT&#36;" if display_currency == "TWD" else "US&#36;" if display_currency == "USD" else "BTC"

def convert(val, cur):
    u = val / usd_twd if cur == "TWD" else val
    return u * usd_twd if display_currency == "TWD" else u if display_currency == "USD" else u / btc_usd if btc_usd else u

holdings = calculate_holdings(st.session_state.transactions)
for acc in st.session_state.cash_accounts:
    holdings.append({"名稱": acc["name"], "代號": "", "幣別": acc["currency"], "類型": "現金", "數量": acc["balance"], "原始總成本": acc["balance"], "CC權利金": 0.0, "SP權利金": 0.0, "股息": 0.0, "已實現損益": 0.0, "歷史買進數量": 0.0, "歷史賣出數量": 0.0, "is_cash": True})

for h in holdings:
    if h.get("is_cash"): 
        h["總成本"], h["調整後價格"], h["歷史總均價"] = h["原始總成本"], 1.0, 1.0
    else:
        eff = h["原始總成本"] - h["CC權利金"] - h["SP權利金"] - h["股息"] if st.session_state.get("include_premium", False) else h["原始總成本"]
        h["總成本"] = eff
        h["調整後價格"] = (h["原始總成本"] - h["CC權利金"] - h["SP權利金"] - h["股息"]) / h["數量"] if abs(h["數量"]) > 0 else 0
        # 🟢 修正：已實現損益內部已經包含權利金與股息，直接扣除即可，避免重複扣除
        h["歷史總均價"] = (h["原始總成本"] - h["已實現損益"]) / h["數量"] if abs(h["數量"]) > 0 else 0

df = pd.DataFrame(holdings) if holdings else pd.DataFrame(columns=["名稱", "代號", "幣別", "類型", "數量", "原始總成本", "平均價格", "CC權利金", "SP權利金", "股息", "已實現損益", "歷史買進數量", "歷史賣出數量", "is_cash", "總成本", "調整後價格", "歷史總均價"])
if not df.empty:
    df["類型"] = df["類型"].replace({"股票": "台股", "ETF": "台股"})
    cp = fetch_all_prices(tuple(set(r["代號"] for _, r in df.iterrows() if r.get("代號") and not r.get("is_cash"))))
    df["現價"] = df.apply(lambda r: 1.0 if r.get("is_cash") else (st.session_state.manual_prices.get(r["代號"] or r["名稱"]) or cp.get(r["代號"])), axis=1)
    df["現值"] = df.apply(lambda r: r["數量"] * r["現價"] if r["現價"] is not None else r["總成本"], axis=1)
    df["未實現損益"] = df["現值"] - df["總成本"]
    
    rates_to_twd = {"TWD": 1.0, "USD": usd_twd, "BTC": btc_usd * usd_twd if btc_usd else 1.0}
    df["rate_to_twd"] = df["幣別"].map(rates_to_twd).fillna(1.0)
    df["現值_TWD"] = df["現值"] * df["rate_to_twd"]
    df["總成本_TWD"] = df["總成本"] * df["rate_to_twd"]
    
    disp_rate = 1.0 if display_currency == "TWD" else (1.0 / usd_twd) if display_currency == "USD" else (1.0 / (btc_usd * usd_twd) if btc_usd else 1.0)
    df["顯示現值"] = df["現值_TWD"] * disp_rate
    df["顯示總成本"] = df["總成本_TWD"] * disp_rate
    df["顯示損益"] = df["顯示現值"] - df["顯示總成本"]

tv = df["顯示現值"].sum() if not df.empty else 0.0
tc = df["顯示總成本"].sum() if not df.empty else 0.0

tl_twd = sum((l["balance"] if l["currency"] == "TWD" else l["balance"] * usd_twd) for l in st.session_state.liabilities_accounts)
disp_rate_glob = 1.0 if display_currency == "TWD" else (1.0 / usd_twd) if display_currency == "USD" else (1.0 / (btc_usd * usd_twd) if btc_usd else 1.0)
tl_disp = tl_twd * disp_rate_glob

nv, nc = tv - tl_disp, tc - tl_disp
n_pnl = nv - nc
n_pnl_pct = (n_pnl / abs(nc) * 100) if abs(nc) > 0 else 0

new_snap = {"version": "v2"}
for d_cur in ["TWD", "USD", "BTC"]:
    factor = 1.0 if d_cur == "TWD" else (1.0 / usd_twd) if d_cur == "USD" else (1.0 / (btc_usd * usd_twd) if btc_usd else 1.0)
    cv = (df["現值_TWD"].sum() * factor) if not df.empty else 0
    cc = (df["總成本_TWD"].sum() * factor) if not df.empty else 0
    cl = tl_twd * factor
    
    cs = {}
    if not df.empty:
        gp = df.groupby("類型")[["現值_TWD", "總成本_TWD"]].sum()
        for cat, r in gp.iterrows():
            cs[cat] = {"value": round(r["現值_TWD"] * factor, 2), "cost": round(r["總成本_TWD"] * factor, 2)}
            
    new_snap[d_cur] = {"value": round(cv, 2), "cost": round(cc, 2), "liability": round(cl, 2), "categories": cs}

today_s = date.today().isoformat()
if today_s not in st.session_state.history_snapshots or st.session_state.history_snapshots[today_s] != new_snap:
    st.session_state.history_snapshots[today_s] = new_snap
    save_data("history_snapshots", st.session_state.history_snapshots)

# ========================================================
# 📊 UI 渲染區段開始
# ========================================================
col_rate, col_select, col_empty = st.columns([1.2, 0.7, 3.1])
with col_rate: st.markdown(f"<span style='font-size:18px; font-weight:600'>USD / TWD {usd_twd:.3f}</span>", unsafe_allow_html=True)
with col_select:
    avail = [k for k in EXTRA_RATES.keys() if k not in st.session_state.selected_extras]
    if avail:
        ch = st.selectbox("新增匯率", ["+ 匯率"] + avail, label_visibility="collapsed", key="rate_sel")
        if ch != "+ 匯率": st.session_state.selected_extras.append(ch); st.rerun()
if st.session_state.selected_extras:
    for n in st.session_state.selected_extras[:]:
        r = get_rate(EXTRA_RATES[n])
        c1, c2, _ = st.columns([1.2, 0.7, 3.1])
        c1.markdown(f"**{n} {r:.3f}**" if r else f"**{n} N/A**")
        if c2.button("×", key=f"rm_{n}"): st.session_state.selected_extras.remove(n); st.rerun()

st.divider()

# 側邊欄
with st.sidebar:
    st.title("📊 個人資產儀表板")
    st.markdown(f"<div style='color: #4ade80; font-size: 14px; font-weight: bold; margin-bottom: 5px;'>🔓 已登入：{st.session_state.user.email}</div>", unsafe_allow_html=True)
    if st.button("登出金庫", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state.user, st.session_state.password = None, None
        st.cache_data.clear(); st.rerun()
    st.divider()
    
    st.header("新增交易")
    
    if st.session_state.clear_form:
        for k in ["name_input", "ticker_input", "qty_input", "price_input", "note_input", "prev_name_input", "prev_ticker_input"]: 
            if k in st.session_state: st.session_state[k] = ""
        st.session_state.clear_form = False

    action = st.selectbox("交易類型", ["買進", "賣出", "Sell Put", "Covered Call", "配息"])

    TW_MAP = {"元大台灣50":"0050", "元大高股息":"0056", "富邦台50":"006208", "國泰永續高股息":"00878", "群益台灣精選高息":"00919", "復華台灣科技優息":"00929", "元大台灣價值高息":"00940", "元大美債20年":"00679B", "國泰20年美債":"00687B", "群益ESG投等債20+":"00937B", "台積電":"2330", "鴻海":"2317", "聯發科":"2454", "廣達":"2382", "富邦金":"2881", "國泰金":"2882"}
    
    user_name_to_ticker = {}
    user_ticker_to_name = {}
    user_ticker_to_type = {}
    user_ticker_to_curr = {}
    for t in st.session_state.transactions:
        nm = t.get("name", "").strip()
        tk = t.get("ticker", "").strip().upper()
        ty = t.get("type_category", "其他")
        cu = t.get("currency", "TWD")
        if nm and tk:
            user_name_to_ticker[nm] = tk
            user_ticker_to_name[tk] = nm
            if tk not in user_ticker_to_type:
                user_ticker_to_type[tk] = ty
                user_ticker_to_curr[tk] = cu
    
    COMBINED_MAP = {**TW_MAP, **user_name_to_ticker}
    REV_MAP = {v:k for k,v in TW_MAP.items()}
    COMBINED_REV_MAP = {**REV_MAP, **user_ticker_to_name}

    cn, ct = st.session_state.get("name_input", ""), st.session_state.get("ticker_input", "")
    if cn != st.session_state.get("prev_name_input", ""):
        cln = cn.strip()
        at = COMBINED_MAP.get(cln) or (cln.upper() if re.fullmatch(r"[A-Z0-9.\-]{1,15}", cln.upper()) else None)
        if at: 
            st.session_state["ticker_input"] = {"BTC":"BTC-USD", "ETH":"ETH-USD"}.get(at, at)
            if at in user_ticker_to_type:
                st.session_state["type_select"] = user_ticker_to_type[at]
                st.session_state["currency_select"] = user_ticker_to_curr[at]
        st.session_state["prev_name_input"], st.session_state["prev_ticker_input"] = cn, st.session_state.get("ticker_input", "")
    elif ct != st.session_state.get("prev_ticker_input", ""):
        clt = ct.strip().upper()
        if clt in COMBINED_REV_MAP: 
            st.session_state["name_input"] = COMBINED_REV_MAP[clt]
        if clt in user_ticker_to_type:
            st.session_state["type_select"] = user_ticker_to_type[clt]
            st.session_state["currency_select"] = user_ticker_to_curr[clt]
        st.session_state["prev_ticker_input"], st.session_state["prev_name_input"] = ct, st.session_state.get("name_input", "")

    name = st.text_input("資產名稱", key="name_input")
    ticker = st.text_input("代號", key="ticker_input")
    tv_str = str(ticker).strip().upper()
    
    if tv_str != st.session_state.prev_ticker:
        clt = tv_str.replace(".TW", "").replace(".TWO", "")
        st.session_state["type_select"] = "債券" if clt.endswith("B") and len(clt)>1 and clt[:-1].isdigit() else "台股" if clt.isdigit() or (len(clt)>1 and clt[:-1].isdigit() and clt[-1] in ["L","R"]) else "加密貨幣" if "-USD" in tv_str else "美股" if tv_str.isalpha() else "其他"
        st.session_state["currency_select"] = "USD" if st.session_state["type_select"] in ["美股", "加密貨幣"] else "TWD"
        st.session_state.prev_ticker = tv_str
        st.session_state["price_input"] = str(get_latest_price(tv_str) or "") if len(tv_str)>=2 else ""

    asset_type = st.selectbox("類型", ["台股", "美股", "期貨", "加密貨幣", "債券", "其他"], key="type_select")
    if asset_type != st.session_state.prev_type:
        st.session_state["currency_select"] = "USD" if asset_type in ["美股", "加密貨幣"] else "TWD"
        st.session_state.prev_type = asset_type

    currency = st.selectbox("幣別", ["TWD", "USD"], key="currency_select")
    qty_str = st.text_input("數量", placeholder="SP/CC/配息 可為 0", key="qty_input")
    price_str = st.text_input(f"價格（{currency}）", placeholder="留白自動抓價", key="price_input")
    tr_date = st.date_input("交易日期", value=date.today())
    note = st.text_input("備註", key="note_input")

    if st.button("儲存", type="primary", use_container_width=True):
        q, p = safe_float(qty_str), safe_float(price_str)
        if p is None and ticker and len(str(ticker).strip())>=2: p = get_latest_price(str(ticker))
        is_prem = action in ["Sell Put", "Covered Call", "配息"]
        vq, vp = (q is not None and q>=0) if is_prem else (q is not None and q>0), (p is not None) if is_prem else (p is not None and p>=0)
        
        if name and vq and vp:
            st.session_state.transactions.append({
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"), "date": tr_date.strftime("%Y-%m-%d"), "type": action, "name": name, "ticker": str(ticker).strip().upper(), "type_category": asset_type, "currency": currency, "quantity": q, "price": p, "fee": 0, "note": note, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            st.session_state.clear_form = True
            save_data("transactions", st.session_state.transactions)
            fetch_all_prices.clear(); st.rerun()
        else: st.warning("請正確填寫數量與價格。")

c_t, c_tg, c_r, _, c_tdc = st.columns([1.5, 1.0, 1.0, 2.5, 4.0])
with c_t: st.markdown("<h3 style='margin: 0; padding-top: 5px; white-space: nowrap;'>資產總覽</h3>", unsafe_allow_html=True)
with c_tg:
    if st.button("顯示金額" if privacy else "隱藏金額", use_container_width=True):
        st.session_state.privacy_mode = not privacy; st.rerun()
with c_r:
    if st.button("重新整理", use_container_width=True): st.cache_data.clear(); st.rerun()
        
with c_tdc:
    hds = sorted([d for d in st.session_state.history_snapshots.keys() if d < today_s])
    pnv = nv
    if hds:
        pd_data = st.session_state.history_snapshots[hds[-1]]
        if isinstance(pd_data, dict) and pd_data.get("version") == "v2":
            pnv = pd_data.get(display_currency, pd_data.get("TWD")).get("value", 0) - pd_data.get(display_currency, pd_data.get("TWD")).get("liability", 0)
        else:
            v, l = pd_data.get("value", 0) if isinstance(pd_data, dict) else pd_data, pd_data.get("liability", 0) if isinstance(pd_data, dict) else 0
            div = 1 if display_currency == "TWD" else usd_twd if display_currency == "USD" else (btc_usd * usd_twd if btc_usd else 1)
            pnv = (v - l) / div
    
    tc_val = nv - pnv
    tc_pct_str = "∞%" if abs(pnv)<1e-5 and tc_val>0 else "0.00%" if abs(pnv)<1e-5 and tc_val<=0 else f"{(tc_val/abs(pnv)*100):.2f}%"
    su = unit.replace('$', '&#36;')
    if privacy: st.markdown("<div style='text-align:right; margin-top:-5px;'><span style='font-size:14px; color:#94a3b8;'>當日淨值變化</span><br><span style='font-size:30px; font-weight:bold;'>＊＊＊＊</span></div>", unsafe_allow_html=True)
    else:
        color = "#4ade80" if tc_val>0 else "#ef4444" if tc_val<0 else "#94a3b8"
        sign = "+" if tc_val>0 else ""
        def format_cv_val(val, dc): return f"{val:,.0f}" if dc != "BTC" else f"{val:,.4f}"
        vs = f"{sign}{su} {format_cv_val(abs(tc_val), display_currency)}"
        st.markdown(f"<div style='text-align:right; line-height:1.2; margin-top:-5px;'><span style='font-size:14px; color:#94a3b8;'>當日淨值變化</span><br><span style='font-size:30px; font-weight:bold; color:{color};'>{vs} ({sign}{tc_pct_str})</span></div>", unsafe_allow_html=True)

opts = ["TWD", "USD", "BTC"]
idx = opts.index(display_currency) if display_currency in opts else 0
nc = st.radio("顯示幣別", opts, horizontal=True, index=idx)
if nc != display_currency: st.session_state.display_currency = nc; st.rerun()
st.checkbox("損益含權利金/配息", key="include_premium")

m1, m2, m3, m4 = st.columns(4)
m1.metric("淨資產現值", mask_val(f"{unit.replace('&#36;', '$')} {nv:,.0f}" if display_currency!="BTC" else f"{unit.replace('&#36;', '$')} {nv:,.3f}"))
m2.metric("總資產現值", mask_val(f"{unit.replace('&#36;', '$')} {tv:,.0f}" if display_currency!="BTC" else f"{unit.replace('&#36;', '$')} {tv:,.3f}"))
m3.metric("負債總額", mask_val(f"{unit.replace('&#36;', '$')} {tl_disp:,.0f}" if display_currency!="BTC" else f"{unit.replace('&#36;', '$')} {tl_disp:,.3f}"))
m4.metric("未實現損益", mask_val(f"{unit.replace('&#36;', '$')} {n_pnl:,.0f}" if display_currency!="BTC" else f"{unit.replace('&#36;', '$')} {n_pnl:,.3f}"), delta=f"{n_pnl_pct:.1f}%")

def render_cash_manager(unit, display_currency, btc_usd, usd_twd):
    with st.expander("💵 現金總覽", expanded=False):
        cash_total_display = 0
        cash_df_list = []
        if st.session_state.cash_accounts:
            for acc in st.session_state.cash_accounts:
                twd_bal = acc["balance"] if acc["currency"] == "TWD" else acc["balance"] * usd_twd
                disp_bal = twd_bal if display_currency == "TWD" else twd_bal / usd_twd if display_currency == "USD" else (twd_bal / usd_twd) / btc_usd if btc_usd else twd_bal
                cash_df_list.append({"id": acc["id"], "名稱": acc["name"], "幣別": acc["currency"], "餘額": acc["balance"], "顯示金額": disp_bal})
            
            cash_df = pd.DataFrame(cash_df_list)
            cash_df = cash_df.sort_values(by="顯示金額", ascending=False)
            cash_total_display = cash_df["顯示金額"].sum()
        else:
            cash_df = pd.DataFrame()

        safe_unit = unit.replace("$", "&#36;")
        cash_str = f"{safe_unit} {cash_total_display:,.0f}" if display_currency != "BTC" else f"{safe_unit} {cash_total_display:,.4f}"
        
        st.markdown(f"<div style='font-size: 22px; font-weight: bold; margin-bottom: 15px;'>現金總額： {mask_val(cash_str)}</div>", unsafe_allow_html=True)
        
        with st.form("cash_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([2, 1, 2, 1])
            with c1: new_cash_name = st.text_input("帳戶名稱 (如: 富邦交割戶)")
            with c2: new_cash_curr = st.selectbox("幣別", ["TWD", "USD"], key="cash_curr_box")
            with c3: new_cash_bal = st.text_input("目前餘額")
            with c4:
                st.write("")
                if st.form_submit_button("新增帳戶", use_container_width=True):
                    if new_cash_name and safe_float(new_cash_bal) is not None:
                        st.session_state.cash_accounts.append({
                            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"), 
                            "name": new_cash_name.strip(), 
                            "currency": new_cash_curr, 
                            "balance": safe_float(new_cash_bal)
                        })
                        save_data("cash_accounts", st.session_state.cash_accounts)
                        st.success("已成功新增現金帳戶！")
                        st.rerun()
                    else: st.warning("請輸入有效的餘額數字。")
                    
        if st.session_state.cash_accounts:
            sorted_cash_accounts = sorted(
                st.session_state.cash_accounts,
                key=lambda x: x["balance"] if x["currency"] == "TWD" else x["balance"] * usd_twd,
                reverse=True
            )
            for acc in sorted_cash_accounts:
                if st.session_state.edit_cash_id == acc["id"]:
                    c1, c2, c3, c4, c5 = st.columns([2, 1, 2, 1, 1])
                    new_name = c1.text_input("名稱", acc["name"], key=f"c_name_{acc['id']}", label_visibility="collapsed")
                    new_curr = c2.selectbox("幣別", ["TWD", "USD"], index=0 if acc["currency"]=="TWD" else 1, key=f"c_curr_{acc['id']}", label_visibility="collapsed")
                    new_bal = c3.text_input("餘額", str(acc["balance"]), key=f"c_bal_{acc['id']}", label_visibility="collapsed")
                    if c4.button("儲存", key=f"save_c_{acc['id']}", type="primary", use_container_width=True):
                        acc["name"], acc["currency"] = new_name.strip() if new_name.strip() else acc["name"], new_curr
                        if safe_float(new_bal) is not None: acc["balance"] = safe_float(new_bal)
                        save_data("cash_accounts", st.session_state.cash_accounts)
                        st.session_state.edit_cash_id = None
                        st.rerun()
                    if c5.button("取消", key=f"cancel_c_{acc['id']}", use_container_width=True):
                        st.session_state.edit_cash_id = None
                        st.rerun()
                else:
                    c1, c2, c3, c4 = st.columns([3.5, 5.0, 0.8, 0.8])
                    c1.markdown(f"<div style='font-size:19px; font-weight:bold; margin-top:4px;'>{acc['name']}</div>", unsafe_allow_html=True)
                    bal_str = f"{acc['balance']:,.0f}" if acc['currency'] == "TWD" else f"{acc['balance']:,.2f}"
                    c2.markdown(f"<div style='font-size:19px; margin-top:4px;'>{acc['currency']} {mask_val(bal_str)}</div>", unsafe_allow_html=True)
                    if c3.button("編輯", key=f"edit_c_{acc['id']}", use_container_width=True):
                        st.session_state.edit_cash_id = acc["id"]
                        st.rerun()
                    if c4.button("刪除", key=f"del_c_{acc['id']}", use_container_width=True):
                        st.session_state.cash_accounts = [a for a in st.session_state.cash_accounts if a["id"] != acc["id"]]
                        save_data("cash_accounts", st.session_state.cash_accounts)
                        st.rerun()

            st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
            if not cash_df.empty and cash_total_display > 0:
                c_chart_left, c_chart_right = st.columns([1.5, 1.0])
                with c_chart_left:
                    st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>📉 現金變化趨勢</div>", unsafe_allow_html=True)
                    history_data = st.session_state.history_snapshots
                    if len(history_data) > 0:
                        cash_hist = []
                        for d_str, data_val in history_data.items():
                            if isinstance(data_val, dict) and data_val.get("version") == "v2":
                                c_val = data_val.get(display_currency, data_val.get("TWD")).get("categories", {}).get("現金", {}).get("value", 0.0)
                                cash_hist.append({'Date': d_str, 'Value': c_val})
                            else:
                                c_val = data_val.get("categories", {}).get("現金", {}).get("value", 0.0) if isinstance(data_val, dict) else 0.0
                                div = 1 if display_currency == "TWD" else usd_twd if display_currency == "USD" else (btc_usd * usd_twd if btc_usd else 1)
                                cash_hist.append({'Date': d_str, 'Value': c_val / div})
                                
                        cash_hist_df = pd.DataFrame(cash_hist)
                        if not cash_hist_df.empty:
                            cash_hist_df['Date'] = pd.to_datetime(cash_hist_df['Date'])
                            cash_hist_df = cash_hist_df.sort_values('Date').set_index('Date').resample('D').ffill().reset_index()
                            if cash_hist_df['Value'].sum() > 0:
                                fig_cash_line = _build_cash_trend_fig(
                                    tuple(cash_hist_df['Date'].astype(str).tolist()),
                                    tuple(cash_hist_df['Value'].tolist()),
                                    safe_unit,
                                    st.session_state.privacy_mode
                                )
                                st.plotly_chart(fig_cash_line, use_container_width=True, config={'scrollZoom': True})
                            else:
                                st.caption("尚無足夠的歷史資料繪製趨勢圖。")
                        else:
                            st.caption("尚無足夠的歷史資料繪製趨勢圖。")
                    else:
                        st.caption("尚無歷史資料。")
                with c_chart_right:
                    st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>📊 現金分佈佔比</div>", unsafe_allow_html=True)
                    fig_cash = _build_pie_fig(
                        tuple(cash_df["名稱"].tolist()),
                        tuple(cash_df["顯示金額"].tolist()),
                        ("#00CC96", "#AB63FA", "#FFA15A", "#636EFA", "#EF553B"),
                        safe_unit,
                        st.session_state.privacy_mode,
                        300
                    )
                    st.plotly_chart(fig_cash, use_container_width=True)

def render_liability_manager(unit, display_currency, total_value, net_value, btc_usd, usd_twd):
    with st.expander("💳 負債總覽", expanded=False):
        lib_total_display = 0
        lib_df = pd.DataFrame()
        if st.session_state.liabilities_accounts:
            lib_items = [{"id": lib["id"], "名稱": lib["name"], "幣別": lib["currency"], "原始金額": lib["balance"], "TWD金額": lib["balance"] if lib["currency"] == "TWD" else lib["balance"] * usd_twd} for lib in st.session_state.liabilities_accounts]
            lib_df = pd.DataFrame(lib_items)
            
            lib_df["顯示金額"] = lib_df["TWD金額"] if display_currency == "TWD" else lib_df["TWD金額"] / usd_twd if display_currency == "USD" else (lib_df["TWD金額"] / usd_twd) / btc_usd if btc_usd else lib_df["TWD金額"]
            
            lib_df = lib_df.sort_values(by="顯示金額", ascending=False)
            lib_total_display = lib_df["顯示金額"].sum()

        safe_unit = unit.replace("$", "&#36;")
        lib_str = f"{safe_unit} {lib_total_display:,.0f}" if display_currency != "BTC" else f"{safe_unit} {lib_total_display:,.4f}"
        lev_str = f"{total_value / net_value:.2f} 倍" if net_value > 0 else 'N/A'
        st.markdown(f"<div style='font-size: 22px; font-weight: bold; margin-bottom: 15px;'>負債總額： {mask_val(lib_str)} <span style='font-size: 18px; color: #94a3b8; font-weight: normal;'>｜ 槓桿比率： {mask_val(lev_str)}</span></div>", unsafe_allow_html=True)
        
        with st.form("liability_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([2, 1, 2, 1])
            with c1: new_lib_name = st.text_input("負債名稱 (如: 股票質借 / 房貸)")
            with c2: new_lib_curr = st.selectbox("幣別", ["TWD", "USD"], key="lib_curr_box")
            with c3: new_lib_bal = st.text_input("目前金額")
            with c4:
                st.write("")
                if st.form_submit_button("新增負債", use_container_width=True):
                    if new_lib_name and safe_float(new_lib_bal) is not None:
                        st.session_state.liabilities_accounts.append({"id": datetime.now().strftime("%Y%m%d%H%M%S%f"), "name": new_lib_name.strip(), "currency": new_lib_curr, "balance": safe_float(new_lib_bal)})
                        save_data("liabilities_accounts", st.session_state.liabilities_accounts)
                        st.success("已成功新增負債！")
                        st.rerun()
                    else: st.warning("請輸入有效的金額數字。")
                        
        if st.session_state.liabilities_accounts:
            sorted_liabilities = sorted(
                st.session_state.liabilities_accounts,
                key=lambda acc: acc["balance"] if acc["currency"] == "TWD" else acc["balance"] * usd_twd,
                reverse=True
            )
            for acc in sorted_liabilities:
                if st.session_state.edit_liability_id == acc["id"]:
                    c1, c2, c3, c4, c5 = st.columns([2, 1, 2, 1, 1])
                    new_name = c1.text_input("名稱", acc["name"], key=f"lib_name_{acc['id']}", label_visibility="collapsed")
                    new_curr = c2.selectbox("幣別", ["TWD", "USD"], index=0 if acc["currency"]=="TWD" else 1, key=f"lib_curr_{acc['id']}", label_visibility="collapsed")
                    new_bal = c3.text_input("金額", str(acc["balance"]), key=f"lib_bal_{acc['id']}", label_visibility="collapsed")
                    if c4.button("儲存", key=f"save_lib_{acc['id']}", type="primary", use_container_width=True):
                        acc["name"], acc["currency"] = new_name.strip() if new_name.strip() else acc["name"], new_curr
                        if safe_float(new_bal) is not None: acc["balance"] = safe_float(new_bal)
                        save_data("liabilities_accounts", st.session_state.liabilities_accounts)
                        st.session_state.edit_liability_id = None
                        st.rerun()
                    if c5.button("取消", key=f"cancel_lib_{acc['id']}", use_container_width=True):
                        st.session_state.edit_liability_id = None
                        st.rerun()
                else:
                    c1, c2, c3, c4 = st.columns([3.5, 5.0, 0.8, 0.8])
                    c1.markdown(f"<div style='font-size:19px; font-weight:bold; margin-top:4px;'>{acc['name']}</div>", unsafe_allow_html=True)
                    bal_str = f"{acc['balance']:,.0f}" if acc['currency'] == "TWD" else f"{acc['balance']:,.2f}"
                    c2.markdown(f"<div style='font-size:19px; margin-top:4px;'>{acc['currency']} {mask_val(bal_str)}</div>", unsafe_allow_html=True)
                    if c3.button("編輯", key=f"edit_lib_{acc['id']}", use_container_width=True):
                        st.session_state.edit_liability_id = acc["id"]
                        st.rerun()
                    if c4.button("刪除", key=f"del_lib_{acc['id']}", use_container_width=True):
                        st.session_state.liabilities_accounts = [a for a in st.session_state.liabilities_accounts if a["id"] != acc["id"]]
                        save_data("liabilities_accounts", st.session_state.liabilities_accounts)
                        st.rerun()

            st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
            c_chart_left, c_chart_right = st.columns([1.5, 1.0])
            with c_chart_left:
                st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>📉 負債變化趨勢</div>", unsafe_allow_html=True)
                history_data = st.session_state.history_snapshots
                if len(history_data) > 0:
                    lib_hist = []
                    for d_str, data_val in history_data.items():
                        if isinstance(data_val, dict) and data_val.get("version") == "v2":
                            liab_val = data_val.get(display_currency, data_val.get("TWD")).get("liability", 0.0)
                            lib_hist.append({'Date': d_str, 'Value': liab_val})
                        else:
                            liab = data_val.get("liability", 0.0) if isinstance(data_val, dict) else 0.0
                            div = 1 if display_currency == "TWD" else usd_twd if display_currency == "USD" else (btc_usd * usd_twd if btc_usd else 1)
                            lib_hist.append({'Date': d_str, 'Value': liab / div})
                            
                    lib_hist_df = pd.DataFrame(lib_hist)
                    if not lib_hist_df.empty:
                        lib_hist_df['Date'] = pd.to_datetime(lib_hist_df['Date'])
                        lib_hist_df = lib_hist_df.sort_values('Date').set_index('Date').resample('D').ffill().reset_index()
                        fig_lib_line = _build_lib_trend_fig(
                            tuple(lib_hist_df['Date'].astype(str).tolist()),
                            tuple(lib_hist_df['Value'].tolist()),
                            safe_unit,
                            st.session_state.privacy_mode
                        )
                        st.plotly_chart(fig_lib_line, use_container_width=True, config={'scrollZoom': True})
            with c_chart_right:
                st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>📊 負債分佈佔比</div>", unsafe_allow_html=True)
                if not lib_df.empty:
                    fig_lib = _build_pie_fig(
                        tuple(lib_df["名稱"].tolist()),
                        tuple(lib_df["顯示金額"].tolist()),
                        ("#EF553B", "#FFA15A", "#AB63FA", "#636EFA", "#00CC96"),
                        safe_unit,
                        st.session_state.privacy_mode,
                        300
                    )
                    st.plotly_chart(fig_lib, use_container_width=True)
        else: st.caption("目前無負債紀錄。")

render_cash_manager(unit, display_currency, btc_usd, usd_twd)
render_liability_manager(unit, display_currency, tv, nv, btc_usd, usd_twd)

# ========================================================
# 📊 目前持倉配置 (圓餅圖與長條圖)
# ========================================================
if not df.empty:
    st.subheader("目前持倉配置")
    df_chart = df[df["數量"] != 0].copy()
    cats = df_chart.groupby("類型")[["顯示現值", "顯示損益", "顯示總成本"]].sum().reset_index().sort_values("顯示現值", ascending=False)
    order_list = [c for c in cats['類型'] if c not in ['期貨', '現金']] + ([c for c in ['期貨', '現金'] if c in cats['類型'].values])
    cats = cats.set_index('類型').loc[order_list].reset_index()
    
    n_cols = min(len(cats), 6)
    if n_cols > 0:
        cs = st.columns(n_cols)
        for i, (_, r) in enumerate(cats.iterrows()):
            c, a, p, cst = r["類型"], r["顯示現值"], r["顯示損益"], r["顯示總成本"]
            pct = "∞%" if abs(cst)<=1e-5 and p>0 else "0.0%" if abs(cst)<=1e-5 and p<=0 else f"{abs(p/abs(cst)*100):.1f}%"
            sgn = "+" if p>0 else "-" if p<0 else ""
            clr = "#ef4444" if p<0 else "#4ade80"
            amt_s = mask_val(f"{unit.replace('$', '&#36;')} {a:,.0f}" if display_currency != "BTC" else f"{unit.replace('$', '&#36;')} {a:,.3f}")
            pnl_s = mask_val(f"{unit.replace('$', '&#36;')} {abs(p):,.0f}" if display_currency != "BTC" else f"{unit.replace('$', '&#36;')} {abs(p):,.3f}")
            pd_ui = f"<div style='font-size:16px; font-weight:600; color:{clr}; margin-top:4px;'>({sgn}{pnl_s} ｜ {sgn}{pct})</div>" if c != "現金" else "<div style='font-size:16px; margin-top:4px; visibility:hidden;'>-</div>"
            cs[i % n_cols].markdown(f"<div style='padding: 5px 0 15px 0;'><div style='font-size:18px; font-weight:600; color:#e2e8f0'>{c}：{amt_s}</div>{pd_ui}</div>", unsafe_allow_html=True)

    is_category_view = st.session_state.selected_category is not None
    if is_category_view:
        view_df = df_chart[df_chart["類型"] == st.session_state.selected_category].copy()
        cat_total_val = view_df['顯示現值'].sum()
        cat_total_str = f"{unit.replace('$', '&#36;')} {cat_total_val:,.0f}" if display_currency != "BTC" else f"{unit.replace('$', '&#36;')} {cat_total_val:,.3f}"
        st.markdown(f"目前顯示：**{st.session_state.selected_category}** 分類總額 {mask_val(cat_total_str)}", unsafe_allow_html=True)
    else:
        view_df = df_chart.groupby("類型", as_index=False)["顯示現值"].sum().rename(columns={"類型": "名稱"})

    if not view_df.empty:
        all_l = view_df["名稱"].tolist()
        if not st.session_state.visible_items or not st.session_state.visible_items.intersection(set(all_l)): st.session_state.visible_items = set(all_l)

        plot_df = view_df[view_df["名稱"].isin(st.session_state.visible_items)].copy().sort_values(by="顯示現值", ascending=False).reset_index(drop=True)
        view_total_abs = view_df["顯示現值"].abs().sum()
        plot_total_abs = plot_df["顯示現值"].abs().sum()
        global_total_abs = df_chart["顯示現值"].abs().sum() 
        
        colors = ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52"]

        st.markdown("**圖例**（點擊可顯示/隱藏）")
        n_cols_leg = 7
        view_df_sorted = view_df.sort_values("顯示現值", ascending=False).reset_index(drop=True)
        items = list(view_df_sorted.iterrows())
        
        for i in range(0, len(items), n_cols_leg):
            cols_leg = st.columns(n_cols_leg)
            for j, (idx, row) in enumerate(items[i:i+n_cols_leg]):
                lab, val = row["名稱"], row["顯示現值"]
                pct = (abs(val) / view_total_abs * 100) if view_total_abs > 0 else 0
                color = colors[list(view_df["名稱"]).index(lab) % len(colors)]
                is_visible = lab in st.session_state.visible_items
                
                with cols_leg[j]:
                    label_text = f"{lab} | {pct:.1f}%" if is_visible else f"~~{lab}~~"
                    st.markdown(f"<div style='width:100%; height:6px; background-color:{color}; border-radius:4px; margin-bottom:-14px; position:relative; z-index:1;'></div>", unsafe_allow_html=True)
                    if st.button(label_text, key=f"leg_all_{lab}", use_container_width=True):
                        st.session_state.visible_items.discard(lab) if is_visible else st.session_state.visible_items.add(lab)
                        st.rerun()

        col_pie, col_nav = st.columns([0.88, 0.12])
        
        with col_pie:
            try:
                with st.popover("⚙️ 圖表設定"):
                    chart_type_choice = st.selectbox("圖表類型", ["自動 (預設)", "圓餅圖", "長條圖"], index=0, key="chart_type_select")
                    threshold = st.slider("合併佔比小於多少為「其他」？", 0.0, 5.0, 1.0, 0.5, "%.1f%%")
            except AttributeError:
                chart_type_choice = st.selectbox("圖表類型", ["自動 (預設)", "圓餅圖", "長條圖"], index=0, key="chart_type_select")
                threshold = st.slider("合併佔比小於多少為「其他」？", 0.0, 5.0, 1.0, 0.5, "%.1f%%")

            if plot_df.empty: st.info("請至少選擇一個項目")
            else:
                if threshold > 0 and plot_total_abs > 0:
                    mask = (plot_df["顯示現值"].abs() / plot_total_abs * 100) < threshold
                    small_df, large_df = plot_df[mask], plot_df[~mask]
                    if not small_df.empty:
                        plot_df = pd.concat([large_df, pd.DataFrame([{"名稱": f"其他小部位 ({len(small_df)} 檔)", "顯示現值": small_df["顯示現值"].sum()}])], ignore_index=True)
                
                labels = plot_df["名稱"].tolist()
                values_display = plot_df["顯示現值"].tolist()
                values_abs = plot_df["顯示現值"].abs().tolist()
                bar_pie_colors = ["#808080" if lab.startswith("其他小部位") else colors[list(view_df["名稱"]).index(lab) % len(colors)] for lab in labels]
                
                pie_text_labels, bar_text_labels = [], []
                for lab, val in zip(labels, values_display):
                    abs_val = abs(val)
                    pct_in_view = (abs_val / plot_total_abs * 100) if plot_total_abs > 0 else 0
                    pct_of_total = (abs_val / global_total_abs * 100) if global_total_abs > 0 else 0
                    bar_text_labels.append(f"<b>{pct_in_view:.1f}%<br>({pct_of_total:.1f}%)</b>" if is_category_view else f"<b>{pct_in_view:.1f}%</b>")
                    pie_text_labels.append(f"<b>{lab}</b><br>{pct_in_view:.1f}%<br>({pct_of_total:.1f}%)" if pct_in_view >= 1.0 and is_category_view else f"<b>{lab}</b><br>{pct_in_view:.1f}%" if pct_in_view >= 1.0 else "")
                
                show_bar_chart = (chart_type_choice == "長條圖") or (chart_type_choice == "自動 (預設)" and len(labels) > 10)

                if show_bar_chart:
                    bar_font_size = 24 if len(labels) <= 12 else 20 if len(labels) <= 15 else 16 if len(labels) <= 20 else 14 if len(labels) <= 30 else 12
                    fig = _build_holdings_bar_fig(
                        tuple(labels),
                        tuple(values_display),
                        tuple(bar_text_labels),
                        tuple(bar_pie_colors),
                        privacy,
                        bar_font_size
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    fig = _build_holdings_pie_fig(
                        tuple(labels),
                        tuple(values_abs),
                        tuple(pie_text_labels),
                        tuple(bar_pie_colors),
                        privacy
                    )
                    st.plotly_chart(fig, use_container_width=True)

        with col_nav:
            st.markdown("<div style='margin-top: 60px;'></div>", unsafe_allow_html=True)
            st.caption("切換分類檢視：")
            for cat in ["全部"] + order_list:
                if st.button(cat, use_container_width=True, key=f"nav_cat_{cat}", type="primary" if ((cat == st.session_state.selected_category) or (cat == "全部" and st.session_state.selected_category is None)) else "secondary"):
                    st.session_state.selected_category = None if cat == "全部" else cat
                    st.session_state.visible_items = set()
                    st.rerun()

# ========================================================
# ⚡ 局部渲染 Fragment: 趨勢圖 
# ========================================================
@st_fragment
def render_overall_trend_section(history_snapshots, selected_cat, display_currency, usd_twd, btc_usd, unit, privacy):
    st.divider()
    st.subheader(f"📈 {'全部淨資產' if selected_cat is None else selected_cat} 變化趨勢")
    if len(history_snapshots) > 0:
        history_json = json.dumps(history_snapshots, sort_keys=True, default=str)
        hist_d = _prepare_trend_hist_data(history_json, selected_cat, display_currency)
        
        hdf = pd.DataFrame(hist_d)
        if not hdf.empty:
            hdf['Date'] = pd.to_datetime(hdf['Date'])
            hdf = hdf.sort_values('Date').set_index('Date').resample('D').ffill().reset_index()

            cr, cp = st.columns([2.5, 1.5])
            with cr:
                tr = st.radio("選擇時間區間", ["1週", "1個月", "3個月", "半年", "1年", "全部"], index=1, horizontal=True, label_visibility="collapsed")
            tdy = pd.to_datetime(date.today())
            sd = tdy - pd.DateOffset(weeks=1) if tr == "1週" else tdy - pd.DateOffset(months=1) if tr == "1個月" else tdy - pd.DateOffset(months=3) if tr == "3個月" else tdy - pd.DateOffset(months=6) if tr == "半年" else tdy - pd.DateOffset(years=1) if tr == "1年" else hdf['Date'].min() - pd.Timedelta(days=3)
            
            fdf = hdf[hdf['Date'] >= sd].copy()
            with cp:
                if not fdf.empty:
                    sv, ev = fdf['Value'].iloc[0], fdf['Value'].iloc[-1]
                    cv = ev - sv
                    cp_str = "∞%" if abs(sv)<1e-5 and cv>0 else "0.00%" if abs(sv)<1e-5 and cv<=0 else f"{(cv/abs(sv)*100):.2f}%"
                    if privacy: st.markdown("<div style='text-align:right; margin-top:-10px;'><span style='font-size:16px; color:#94a3b8;'>區間淨值變化</span><br><span style='font-size:30px; font-weight:bold;'>＊＊＊＊</span></div>", unsafe_allow_html=True)
                    else:
                        c_clr = "#4ade80" if cv>0 else "#ef4444" if cv<0 else "#94a3b8"
                        sgn = "+" if cv>0 else ""
                        def format_cv_val(val, dc): return f"{val:,.0f}" if dc != "BTC" else f"{val:,.4f}"
                        vs = f"{sgn}{unit.replace('$', '&#36;')} {format_cv_val(abs(cv), display_currency)}"
                        st.markdown(f"<div style='text-align:right; line-height:1.2; margin-top:-10px;'><span style='font-size:16px; color:#94a3b8;'>區間淨值變化</span><br><span style='font-size:30px; font-weight:bold; color:{c_clr};'>{vs} ({sgn}{cp_str})</span></div>", unsafe_allow_html=True)
            
            if not fdf.empty:
                fdf['PnL'] = fdf['Value'] - fdf['Cost']
                unit_str = unit.replace("$", "&#36;")
                
                def get_val_text_global(x):
                    if x < 0: return f"<span style='color:#ef4444'>-{unit_str} {abs(x):,.0f}</span>"
                    elif x > 0: return f"<span style='color:#4ade80'>+{unit_str} {x:,.0f}</span>"
                    else: return f"{unit_str} 0"

                def get_pct_text_global(row):
                    pnl, cost = row['PnL'], row['Cost']
                    if abs(cost) <= 1e-5 and pnl > 0: return "<span style='color:#4ade80'>+∞%</span>"
                    elif abs(cost) <= 1e-5 and pnl <= 0: return "0.00%"
                    pct = (pnl / abs(cost) * 100) if abs(cost) > 0 else 0
                    if pnl < 0: return f"<span style='color:#ef4444'>-{abs(pct):.2f}%</span>"
                    elif pnl > 0: return f"<span style='color:#4ade80'>+{pct:.2f}%</span>"
                    else: return "0.00%"

                fdf['pnl_val_text'] = fdf['PnL'].apply(get_val_text_global)
                fdf['pnl_pct_text'] = fdf.apply(get_pct_text_global, axis=1)

                fig = _build_overall_trend_fig(
                    tuple(fdf['Date'].astype(str).tolist()),
                    tuple(fdf['Value'].tolist()),
                    tuple(fdf['Cost'].tolist()),
                    tuple(fdf['pnl_val_text'].tolist()),
                    tuple(fdf['pnl_pct_text'].tolist()),
                    unit_str,
                    privacy,
                    '淨值'
                )
                st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

render_overall_trend_section(st.session_state.history_snapshots, st.session_state.selected_category, display_currency, usd_twd, btc_usd, unit.replace('$', '&#36;'), privacy)

# ========================================================
# 📝 持倉明細表
# ========================================================
st.divider()
st.subheader(f"持倉明細 ({st.session_state.selected_category if st.session_state.selected_category else '全部'})")
with st.expander("點此展開 / 收合明細表", expanded=False):
    if not df.empty:
        def det_stat(r):
            if r.get("is_cash"): return "現金"
            if r["數量"] > 0.0001: return "持有中(做多)"
            if r["數量"] < -0.0001: return "持有中(做空)"
            if r.get("歷史買進數量", 0) > 0 or r.get("歷史賣出數量", 0) > 0: return "已清倉"
            return "未建倉 (純收租)"

        df["持倉狀態"] = df.apply(det_stat, axis=1)
        
        show_df = pd.DataFrame({
            "持倉狀態": df["持倉狀態"],
            "名稱": df["名稱"], "代號": df["代號"], "類型": df["類型"], "幣別": df["幣別"], 
            "數量": df["數量"],
            "平均價格": df.apply(lambda r: None if r.get("is_cash") else abs(r["平均價格"]), axis=1),
            "調整後價格": df.apply(lambda r: None if r.get("is_cash") else abs(r["調整後價格"]), axis=1),
            "歷史總均價": df.apply(lambda r: None if r.get("is_cash") else r["歷史總均價"], axis=1),
            "現價": df.apply(lambda r: None if r.get("is_cash") else r["現價"], axis=1),
            "原幣現值": df["現值"], 
            f"約當現值({display_currency})": df["顯示現值"],
            "未實現損益": df.apply(lambda r: None if r.get("is_cash") else r["未實現損益"], axis=1),
            "已實現損益": df.apply(lambda r: None if r.get("is_cash") else r["已實現損益"], axis=1),
            "SP權利金": df.apply(lambda r: None if r.get("is_cash") else r["SP權利金"], axis=1),
            "CC權利金": df.apply(lambda r: None if r.get("is_cash") else r["CC權利金"], axis=1),
            "股息": df.apply(lambda r: None if r.get("is_cash") else r["股息"], axis=1)
        })

        cols = ["名稱", "代號", "類型", "幣別", "數量", "平均價格", "調整後價格", "歷史總均價", "現價", "原幣現值", f"約當現值({display_currency})", "未實現損益", "已實現損益", "SP權利金", "CC權利金", "股息"]
        
        col_cfg = {
            "數量": st.column_config.NumberColumn("數量"), 
            "平均價格": st.column_config.NumberColumn("平均價格", format="%,.4f"),
            "調整後價格": st.column_config.NumberColumn("調整後價格", format="%,.4f"),
            "歷史總均價": st.column_config.NumberColumn("歷史總均價", format="%,.4f"),
            "現價": st.column_config.NumberColumn("現價", format="%,.4f"), 
            "原幣現值": st.column_config.NumberColumn("原幣現值", format="%,.0f"), 
            f"約當現值({display_currency})": st.column_config.NumberColumn(f"約當現值({display_currency})", format="%,.0f"),
            "未實現損益": st.column_config.NumberColumn("未實現損益", format="%,.0f"),
            "已實現損益": st.column_config.NumberColumn("已實現損益", format="%,.0f"),
            "SP權利金": st.column_config.NumberColumn("SP權利金", format="%,.0f"),
            "CC權利金": st.column_config.NumberColumn("CC權利金", format="%,.0f"),
            "股息": st.column_config.NumberColumn("股息", format="%,.0f")
        }

        if st.session_state.selected_category:
            show_df = show_df[show_df["類型"] == st.session_state.selected_category]

        d_long = show_df[(show_df["持倉狀態"] == "持有中(做多)") & (show_df["類型"] != "現金")][cols]
        d_short = show_df[show_df["持倉狀態"] == "持有中(做空)"][cols]
        d_closed = show_df[show_df["持倉狀態"] == "已清倉"][cols]
        d_prem = show_df[show_df["持倉狀態"] == "未建倉 (純收租)"][cols]

        st.markdown("<h5 style='color:#4ade80; margin-bottom:5px;'>🟢 持有中部位 (做多)</h5>", unsafe_allow_html=True)
        if not d_long.empty:
            if privacy:
                m_df = d_long.copy()
                for c in cols:
                    if c not in ["名稱", "代號", "類型", "幣別"]: m_df[c] = "＊＊＊＊"
                st.dataframe(m_df, use_container_width=True, hide_index=True)
            else: st.dataframe(d_long, use_container_width=True, hide_index=True, column_config=col_cfg)
        else: st.caption("目前無做多部位。")

        if not d_short.empty:
            st.markdown("<h5 style='color:#ef4444; margin-bottom:5px; margin-top:20px;'>🔴 持有中部位 (做空)</h5>", unsafe_allow_html=True)
            if privacy:
                m_df = d_short.copy()
                for c in cols:
                    if c not in ["名稱", "代號", "類型", "幣別"]: m_df[c] = "＊＊＊＊"
                st.dataframe(m_df, use_container_width=True, hide_index=True)
            else: st.dataframe(d_short, use_container_width=True, hide_index=True, column_config=col_cfg)

        if not d_closed.empty:
            st.markdown("<h5 style='color:#94a3b8; margin-bottom:5px; margin-top:20px;'>⚪ 已清倉部位</h5>", unsafe_allow_html=True)
            if privacy:
                m_df = d_closed.copy()
                for c in cols:
                    if c not in ["名稱", "代號", "類型", "幣別"]: m_df[c] = "＊＊＊＊"
                st.dataframe(m_df, use_container_width=True, hide_index=True)
            else: st.dataframe(d_closed, use_container_width=True, hide_index=True, column_config=col_cfg)

        if not d_prem.empty:
            st.markdown("<h5 style='color:#c084fc; margin-bottom:5px; margin-top:20px;'>🟣 未建倉 (純收權利金 / 配息)</h5>", unsafe_allow_html=True)
            if privacy:
                m_df = d_prem.copy()
                for c in cols:
                    if c not in ["名稱", "代號", "類型", "幣別"]: m_df[c] = "＊＊＊＊"
                st.dataframe(m_df, use_container_width=True, hide_index=True)
            else: st.dataframe(d_prem, use_container_width=True, hide_index=True, column_config=col_cfg)

# ========================================================
# ⚡ 局部渲染 Fragment: 個別標的分析 
# ========================================================
@st_fragment
def render_individual_analysis(transactions, privacy, display_currency, usd_twd, btc_usd):
    st.divider()
    st.subheader("🔍 個別標的進階分析")
    if transactions:
        tdf = pd.DataFrame(transactions)
        tdf["date_obj"] = pd.to_datetime(tdf["date"])
        tdf["target_label"] = tdf.apply(lambda r: f"{r['name']} ({r['ticker']})" if r['ticker'] else r['name'], axis=1)
        sel_t = st.selectbox("選擇標的", sorted(tdf["target_label"].unique()), index=None, placeholder="🔍 搜尋...", label_visibility="collapsed")
        
        if sel_t:
            inc_prem = st.checkbox("圖表計算包含權利金/配息降本", value=st.session_state.get("include_premium", False))
            with st.spinner("載入歷史資料中..."):
                atx = tdf[tdf["target_label"] == sel_t].sort_values("date_obj").copy()
                tkr = atx.iloc[0]["ticker"]
                asset_currency = atx.iloc[0]["currency"]
                
                hdf = pd.DataFrame()
                if tkr: hdf = get_historical_prices_for_chart(tkr, atx["date_obj"].min() - pd.Timedelta(days=7))
                
                cal = pd.date_range(start=atx["date_obj"].min(), end=pd.to_datetime(date.today()))
                cs, cac = 0.0, 0.0
                d_recs = []
                
                for d, dt in atx.groupby("date_obj"):
                    for _, tx in dt.iterrows():
                        q, p, a = float(tx["quantity"]), float(tx["price"]), tx["type"]
                        if a == "買進":
                            if cs >= 0:
                                ns = cs + q
                                cac = (cs * cac + q * p) / ns if ns > 0 else 0
                                cs = ns
                            else:
                                cq = min(q, abs(cs))
                                cs += cq
                                rem = q - cq
                                if rem > 0: cs, cac = rem, p
                                elif abs(cs) < 1e-5: cs, cac = 0.0, 0.0
                        elif a == "賣出":
                            if cs <= 0:
                                ns = abs(cs) + q
                                cac = (abs(cs) * cac + q * p) / ns if ns > 0 else 0
                                cs -= q
                            else:
                                sq = min(q, cs)
                                cs -= sq
                                rem = q - sq
                                if rem > 0: cs, cac = -rem, p
                                elif abs(cs) < 1e-5: cs, cac = 0.0, 0.0
                        elif a in ["Sell Put", "Covered Call", "配息"]:
                            if inc_prem and abs(cs) > 1e-5:
                                cac = (cs * cac - p) / cs
                    d_recs.append({"date": d, "shares": cs, "cost": cs * cac, "avg_cost": cac})
                
                ddf = pd.DataFrame(index=cal).join(pd.DataFrame(d_recs).set_index("date"), how="left").ffill().fillna(0)
                if not hdf.empty:
                    ddf = ddf.join(hdf["Close"])
                    ddf["Close"] = ddf["Close"].ffill()
                    ddf["Value"] = ddf["shares"] * ddf["Close"]
                else:
                    ddf["Close"], ddf["Value"] = None, ddf["cost"]
                
                ddf['pnl'] = ddf['Value'] - ddf['cost']
                currency_symbols = {"TWD": "NT&#36;", "USD": "US&#36;", "BTC": "BTC"}
                asset_unit_str = currency_symbols.get(asset_currency, asset_currency)

                def get_val_text_ind(x):
                    if x < 0: return f"<span style='color:#ef4444'>-{asset_unit_str} {abs(x):,.0f}</span>"
                    elif x > 0: return f"<span style='color:#4ade80'>+{asset_unit_str} {x:,.0f}</span>"
                    else: return f"{asset_unit_str} 0"

                def get_pct_text_ind(row):
                    pnl, cost = row['pnl'], row['cost']
                    if abs(cost) <= 1e-5 and pnl > 0: return "<span style='color:#4ade80'>+∞%</span>"
                    elif abs(cost) <= 1e-5 and pnl <= 0: return "0.00%"
                    pct = (pnl / abs(cost) * 100) if abs(cost) > 0 else 0
                    if pnl < 0: return f"<span style='color:#ef4444'>-{abs(pct):.2f}%</span>"
                    elif pnl > 0: return f"<span style='color:#4ade80'>+{pct:.2f}%</span>"
                    else: return "0.00%"

                ddf['pnl_val_text'] = ddf['pnl'].apply(get_val_text_ind)
                ddf['pnl_pct_text'] = ddf.apply(get_pct_text_ind, axis=1)

                ddf['Value_Gain'] = ddf[['Value', 'cost']].max(axis=1)
                ddf['Value_Loss'] = ddf[['Value', 'cost']].min(axis=1)
                
                y_max_ind = ddf[['Value', 'cost']].max().max()
                y_min_ind = ddf[['Value', 'cost']].min().min()
                y_range_ind = y_max_ind - y_min_ind
                if y_range_ind == 0: y_range_ind = 1
                
                ddf['pnl_y'] = ddf[['Value', 'cost']].min(axis=1) - (y_range_ind * 0.005)
                ddf['pct_y'] = ddf[['Value', 'cost']].min(axis=1) - (y_range_ind * 0.010)

                st.markdown(f"*(註: 圖表以標的原始計價幣別呈現)*")
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>📊 持倉現值與成本變化</div>", unsafe_allow_html=True)
                    fig1 = go.Figure()
                    
                    val_name_ind = '淨值'
                    if privacy:
                        hover_val = " : ＊＊＊＊<extra>" + val_name_ind + "</extra>"
                        hover_cost = " : ＊＊＊＊<extra>成本</extra>"
                        hover_pnl = " : ＊＊＊＊<extra>損益</extra>"
                        hover_pct = " : ＊＊＊＊<extra>$$ %</extra>"
                    else:
                        hover_val = " : " + asset_unit_str + " %{y:,.0f}<extra>" + val_name_ind + "</extra>"
                        hover_cost = " : " + asset_unit_str + " %{y:,.0f}<extra>成本</extra>"
                        hover_pnl = " : %{customdata}<extra>損益</extra>"
                        hover_pct = " : %{customdata}<extra>$$ %</extra>"

                    fig1.add_trace(go.Scatter(x=ddf.index, y=ddf['pct_y'], mode='lines', name='百分比', line=dict(color='rgba(0,0,0,0)', width=0), customdata=ddf['pnl_pct_text'] if not privacy else None, hovertemplate=hover_pct, showlegend=False))
                    fig1.add_trace(go.Scatter(x=ddf.index, y=ddf['pnl_y'], mode='lines', name='損益', line=dict(color='rgba(0,0,0,0)', width=0), customdata=ddf['pnl_val_text'] if not privacy else None, hovertemplate=hover_pnl, showlegend=False))
                    
                    fig1.add_trace(go.Scatter(x=ddf.index, y=ddf['cost'], mode='lines', name='成本', line=dict(color='#3b82f6', width=2), hovertemplate=hover_cost))
                    fig1.add_trace(go.Scatter(x=ddf.index, y=ddf['Value'], mode='lines', name=val_name_ind, line=dict(color='#00CC96', width=2), hovertemplate=hover_val))
                    
                    fig1.add_trace(go.Scatter(x=ddf.index, y=ddf['cost'], mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False))
                    fig1.add_trace(go.Scatter(x=ddf.index, y=ddf['Value_Gain'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(255, 193, 7, 0.2)', hoverinfo='skip', showlegend=False))
                    fig1.add_trace(go.Scatter(x=ddf.index, y=ddf['cost'], mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False))
                    fig1.add_trace(go.Scatter(x=ddf.index, y=ddf['Value_Loss'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(239, 68, 68, 0.2)', hoverinfo='skip', showlegend=False))
                    
                    fig1.update_layout(margin=dict(t=10, b=20, l=10, r=10), height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, showticklabels=not privacy), hovermode="x unified", dragmode="pan")
                    st.plotly_chart(fig1, use_container_width=True, config={'scrollZoom': True})
                
                with c2:
                    st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>🎯 價格走勢</div>", unsafe_allow_html=True)
                    if not hdf.empty:
                        fig2 = go.Figure()
                        fig2.add_trace(go.Scatter(x=hdf.index, y=hdf['Close'], mode='lines', name='收盤價', line=dict(color='#94a3b8', width=2)))
                        fig2.add_trace(go.Scatter(x=ddf.index, y=ddf['avg_cost'].abs(), mode='lines', name='平均成本', line=dict(color='#FFA15A', width=2, dash='dash')))
                        
                        buys = atx[atx['type'] == '買進'].copy()
                        sells = atx[atx['type'] == '賣出'].copy()
                        max_q = atx[atx['type'].isin(['買進', '賣出'])]['quantity'].max()
                        if pd.isna(max_q) or max_q <= 0: max_q = 1
                        
                        def mk_hover(r): return "＊＊＊＊" if privacy else f"日期: {r['date']}<br>動作: {r['type']}<br>價格: {r['price']}<br>數量: {r['quantity']}<br>備註: {r.get('note', '')}"
                        
                        if not buys.empty:
                            buys['hover'] = buys.apply(mk_hover, axis=1)
                            sizes = [max(8, min(25, (q / max_q) * 25)) for q in buys['quantity']]
                            fig2.add_trace(go.Scatter(x=buys['date_obj'], y=buys['price'], mode='markers', name='買進', marker=dict(color='#4ade80', size=sizes, line=dict(width=1, color='white')), customdata=buys['hover'], hovertemplate="<br>%{customdata}<extra></extra>"))
                            
                        if not sells.empty:
                            sells['hover'] = sells.apply(mk_hover, axis=1)
                            sizes = [max(8, min(25, (q / max_q) * 25)) for q in sells['quantity']]
                            fig2.add_trace(go.Scatter(x=sells['date_obj'], y=sells['price'], mode='markers', name='賣出', marker=dict(color='#ef4444', size=sizes, line=dict(width=1, color='white')), customdata=sells['hover'], hovertemplate="<br>%{customdata}<extra></extra>"))

                        fig2.update_layout(margin=dict(t=10, b=20, l=10, r=10), height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, showticklabels=not privacy), hovermode="closest", dragmode="pan")
                        st.plotly_chart(fig2, use_container_width=True, config={'scrollZoom': True})

render_individual_analysis(st.session_state.transactions, privacy, display_currency, usd_twd, btc_usd)

# ========================================================
# 📝 交易紀錄管理
# ========================================================
st.divider()
st.subheader("交易紀錄管理")
if st.session_state.transactions:
    tx_df = pd.DataFrame(st.session_state.transactions)
    tx_df["date_obj"] = pd.to_datetime(tx_df["date"]).dt.date
    tx_df = tx_df.sort_values("date", ascending=False).reset_index(drop=True)
    min_d, max_d, today_d = tx_df["date_obj"].min(), tx_df["date_obj"].max(), date.today()
    
    tx_df["target_label"] = tx_df.apply(lambda row: f"{row['name']} ({row['ticker']})" if row['ticker'] else row['name'], axis=1)
    target_options = ["全部"] + sorted(tx_df["target_label"].unique().tolist())

    f_c1, f_c2, f_c3 = st.columns(3)
    with f_c1:
        date_preset = st.selectbox("篩選時間範圍", ["全部", "本月", "半年", "一年", "自訂區間"])
        date_range = st.date_input("選擇日期", value=(min_d, max_d), min_value=min_d, max_value=max_d) if date_preset == "自訂區間" else (min_d, max_d) if date_preset == "全部" else (today_d.replace(day=1), today_d) if date_preset == "本月" else (today_d - timedelta(days=183), today_d) if date_preset == "半年" else (today_d - timedelta(days=365), today_d)
    with f_c2: selected_target = st.selectbox("篩選標的", target_options)
    with f_c3: action_filter = st.selectbox("篩選動作", ["全部", "買進", "賣出", "Sell Put", "Covered Call", "配息"])

    if isinstance(date_range, tuple):
        if len(date_range) == 2: tx_df = tx_df[(tx_df["date_obj"] >= date_range[0]) & (tx_df["date_obj"] <= date_range[1])]
        elif len(date_range) == 1: tx_df = tx_df[tx_df["date_obj"] == date_range[0]]
    if selected_target != "全部": tx_df = tx_df[tx_df["target_label"] == selected_target]
    if action_filter != "全部": tx_df = tx_df[tx_df["type"] == action_filter]
    st.caption(f"共找到 {len(tx_df)} 筆紀錄")

    def render_tx_rows(df_to_render):
        for i, row in df_to_render.iterrows():
            if st.session_state.editing_id == row["id"]:
                c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([0.9, 0.6, 1.3, 1.2, 0.5, 1.0, 0.9, 1.1])
                with c1: new_date = st.date_input("日期", value=date.fromisoformat(row["date"]), key=f"ed_d_{row['id']}", label_visibility="collapsed")
                with c2: 
                    type_options_list = ["買進", "賣出", "Sell Put", "Covered Call", "配息"]
                    current_type_idx = type_options_list.index(row["type"]) if row["type"] in type_options_list else 0
                    new_type = st.selectbox("動作", type_options_list, index=current_type_idx, key=f"ed_t_{row['id']}", label_visibility="collapsed")
                with c3:
                    cc1, cc2 = st.columns([1.5, 1])
                    new_name = cc1.text_input("名稱", value=row["name"], key=f"ed_n_{row['id']}", label_visibility="collapsed")
                    new_ticker = cc2.text_input("代號", value=row["ticker"], key=f"ed_tk_{row['id']}", label_visibility="collapsed")
                with c4:
                    cc1, cc2 = st.columns(2)
                    new_qty = cc1.text_input("數量", value=str(row["quantity"]), key=f"ed_q_{row['id']}", label_visibility="collapsed")
                    new_price = cc2.text_input("價格", value=str(row["price"]), key=f"ed_p_{row['id']}", label_visibility="collapsed")
                with c5: new_curr = st.selectbox("幣別", ["TWD", "USD"], index=0 if row["currency"]=="TWD" else 1, key=f"ed_c_{row['id']}", label_visibility="collapsed")
                with c6: new_note = st.text_input("備註", value=row.get("note", ""), key=f"ed_nt_{row['id']}", label_visibility="collapsed")
                
                created_at_str = str(row.get('created_at', ''))[:10] if row.get('created_at') else ''
                with c7: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{created_at_str}</div>", unsafe_allow_html=True)
                
                with c8:
                    b1, b2 = st.columns([0.9, 0.9])
                    if b1.button("儲存", key=f"save_tx_{row['id']}", type="primary", use_container_width=True):
                        for idx, t in enumerate(st.session_state.transactions):
                            if t["id"] == row["id"]:
                                st.session_state.transactions[idx].update({"date": new_date.strftime("%Y-%m-%d"), "type": new_type, "name": new_name.strip(), "ticker": new_ticker.strip().upper(), "quantity": safe_float(new_qty) or row["quantity"], "price": safe_float(new_price) if safe_float(new_price) is not None else row["price"], "currency": new_curr, "note": new_note})
                                break
                        save_data("transactions", st.session_state.transactions)
                        st.session_state.editing_id = None
                        fetch_all_prices.clear()
                        st.rerun()
                    if b2.button("取消", key=f"cancel_tx_{row['id']}", use_container_width=True):
                        st.session_state.editing_id = None
                        st.rerun()
            else:
                c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([0.9, 0.6, 1.3, 1.2, 0.5, 1.0, 0.9, 1.1])
                if st.session_state.privacy_mode:
                    qty_display, price_display = "＊＊＊＊", "＊＊＊＊"
                else:
                    qty_display = format_dynamic_qty(row['quantity'], row['price'], row['currency'])
                    price_display = fmt(row['price'])
                    
                with c1: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{row['date']}</div>", unsafe_allow_html=True)
                with c2: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{row['type']}</div>", unsafe_allow_html=True)
                with c3: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{row['name']}（{row['ticker']}）</div>", unsafe_allow_html=True)
                with c4: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{qty_display} × {price_display}</div>", unsafe_allow_html=True)
                with c5: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{row['currency']}</div>", unsafe_allow_html=True)
                with c6: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{row.get('note', '')}</div>", unsafe_allow_html=True)
                
                created_at_str = str(row.get('created_at', ''))[:10] if row.get('created_at') else ''
                with c7: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px; color:#94a3b8; font-size:13px;'>{created_at_str}</div>", unsafe_allow_html=True)
                
                with c8:
                    b1, b2 = st.columns([0.9, 0.9])
                    if b1.button("編輯", key=f"edit_{row['id']}"):
                        st.session_state.editing_id = row["id"]
                        st.rerun()
                    if b2.button("刪除", key=f"del_{row['id']}"):
                        st.session_state.transactions = [t for t in st.session_state.transactions if t["id"] != row["id"]]
                        save_data("transactions", st.session_state.transactions)
                        st.success("已刪除")
                        fetch_all_prices.clear()
                        st.rerun()

    if not tx_df.empty:
        h1, h2, h3, h4, h5, h6, h7, h8 = st.columns([0.9, 0.6, 1.3, 1.2, 0.5, 1.0, 0.9, 1.1])
        h1.markdown("<div style='text-align:center'><b>交易日期</b></div>", unsafe_allow_html=True)
        h2.markdown("<div style='text-align:center'><b>動作</b></div>", unsafe_allow_html=True)
        h3.markdown("<div style='text-align:center'><b>標的</b></div>", unsafe_allow_html=True)
        h4.markdown("<div style='text-align:center'><b>明細</b></div>", unsafe_allow_html=True)
        h5.markdown("<div style='text-align:center'><b>幣別</b></div>", unsafe_allow_html=True)
        h6.markdown("<div style='text-align:center'><b>備註</b></div>", unsafe_allow_html=True)
        h7.markdown("<div style='text-align:center'><b>登錄日期</b></div>", unsafe_allow_html=True)
        h8.markdown("")
        render_tx_rows(tx_df.head(20))
        if len(tx_df) > 20:
            with st.expander(f"展開顯示其餘 {len(tx_df) - 20} 筆紀錄..."): render_tx_rows(tx_df.iloc[20:])
    else: st.info("沒有符合條件的紀錄。")
else: st.caption("尚無交易紀錄")

st.divider()
c1, c2 = st.columns(2)
with c1:
    if not df.empty: st.download_button("下載持倉 CSV", df.to_csv(index=False).encode("utf-8-sig"), f"holdings.csv", "text/csv")
with c2: st.download_button("下載交易紀錄 CSV", pd.DataFrame(st.session_state.transactions).to_csv(index=False).encode("utf-8-sig"), f"tx.csv", "text/csv")

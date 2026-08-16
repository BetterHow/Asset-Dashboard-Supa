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
# ⚡ 效能優化：引入局部渲染技術，讓圖表切換瞬間完成
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
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error(f"⚠️ Supabase 連線失敗，請確認 secrets.toml 設定。錯誤：{e}")
    st.stop()

def get_encryption_key(password: str) -> bytes:
    digest = hashlib.sha256(password.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)

def encrypt_data(data, password: str) -> str:
    f = Fernet(get_encryption_key(password))
    json_str = json.dumps(data, ensure_ascii=False)
    return f.encrypt(json_str.encode('utf-8')).decode('utf-8')

def decrypt_data(encrypted_str: str, password: str):
    try:
        f = Fernet(get_encryption_key(password))
        decrypted_bytes = f.decrypt(encrypted_str.encode('utf-8'))
        return json.loads(decrypted_bytes.decode('utf-8'))
    except Exception:
        return None

def save_data(category, data):
    """上傳加密資料到 Supabase (純雲端安全版)"""
    try:
        enc_payload = encrypt_data(data, st.session_state.password)
        res = supabase.table("encrypted_vault").select("id").eq("user_id", st.session_state.user.id).eq("category", category).execute()
        if res.data:
            row_id = res.data[0]["id"]
            supabase.table("encrypted_vault").update({"encrypted_payload": enc_payload}).eq("id", row_id).execute()
        else:
            supabase.table("encrypted_vault").insert({
                "user_id": st.session_state.user.id,
                "category": category,
                "encrypted_payload": enc_payload
            }).execute()
    except Exception as e:
        st.error(f"儲存 {category} 失敗: {e}")

def load_data(category, default_val):
    try:
        res = supabase.table("encrypted_vault").select("encrypted_payload").eq("user_id", st.session_state.user.id).eq("category", category).execute()
        if res.data:
            enc_payload = res.data[0]["encrypted_payload"]
            decrypted = decrypt_data(enc_payload, st.session_state.password)
            return decrypted if decrypted is not None else default_val
    except Exception:
        pass
    return default_val

# ========================================================
# 🔐 登入與註冊介面
# ========================================================
if "user" not in st.session_state:
    st.session_state.user = None
if "password" not in st.session_state:
    st.session_state.password = None

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
                    st.session_state.user = res.user
                    st.session_state.password = login_pwd
                    st.rerun()
                except Exception:
                    st.error("登入失敗，請確認帳號密碼是否正確。")
                    
        with tab_reg:
            reg_email = st.text_input("Email", key="r_email")
            reg_pwd = st.text_input("密碼 (請牢記！作為加密鑰匙，遺失將永遠無法解密資料)", type="password", key="r_pwd")
            if st.button("註冊帳號", use_container_width=True):
                try:
                    res = supabase.auth.sign_up({"email": reg_email, "password": reg_pwd})
                    st.success("註冊成功！如果 Supabase 預設開啟信箱驗證，請先去收信驗證後，切換回登入頁面登入。")
                except Exception as e:
                    st.error(f"註冊失敗: {e}")
    st.stop()

# ========================================================
# 📊 正式 App 儀表板
# ========================================================
st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] > div:first-child { overflow-y: auto; }
    div[data-testid="collapsedControl"], button[data-testid="stSidebarCollapseButton"] { position: fixed !important; top: 10px !important; z-index: 999999; }
    div[data-testid="stButton"] button p { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    div[data-testid="stTextInput"] div { padding-top: 0px; padding-bottom: 0px; }
    </style>
    """, unsafe_allow_html=True
)

st.title("📊 個人資產儀表板（端到端加密版）")
st.caption("支援買進 / 賣出 / SP / CC / 配息｜動態現金管理｜負債追蹤｜單一標的分析｜隱私保護")

if "transactions" not in st.session_state: st.session_state.transactions = load_data("transactions", [])
if "manual_prices" not in st.session_state: st.session_state.manual_prices = load_data("manual_prices", {})
if "cash_accounts" not in st.session_state: st.session_state.cash_accounts = load_data("cash_accounts", [])
if "liabilities_accounts" not in st.session_state: st.session_state.liabilities_accounts = load_data("liabilities_accounts", [])
if "history_snapshots" not in st.session_state: st.session_state.history_snapshots = load_data("history_snapshots", {})

if "selected_category" not in st.session_state: st.session_state.selected_category = None
if "editing_id" not in st.session_state: st.session_state.editing_id = None
if "edit_cash_id" not in st.session_state: st.session_state.edit_cash_id = None
if "edit_liability_id" not in st.session_state: st.session_state.edit_liability_id = None
if "display_currency" not in st.session_state: st.session_state.display_currency = "TWD"
if "selected_extras" not in st.session_state: st.session_state.selected_extras = []
if "visible_items" not in st.session_state: st.session_state.visible_items = set()
if "clear_form" not in st.session_state: st.session_state.clear_form = False
if "privacy_mode" not in st.session_state: st.session_state.privacy_mode = False
if "prev_ticker" not in st.session_state: st.session_state.prev_ticker = ""
if "prev_type" not in st.session_state: st.session_state.prev_type = "台股"
if "prev_name_input" not in st.session_state: st.session_state.prev_name_input = ""
if "prev_ticker_input" not in st.session_state: st.session_state.prev_ticker_input = ""

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
    ticker = ticker.strip().upper()
    clean_t = ticker.replace(".TW", "").replace(".TWO", "")
    is_tw_symbol = clean_t.isdigit() or (len(clean_t) > 1 and clean_t[:-1].isdigit() and clean_t[-1] in ["B", "L", "R"])
    if is_tw_symbol: candidates = [f"{clean_t}.TW", f"{clean_t}.TWO"]
    else: candidates = [ticker] + ([f"{ticker}.TW", f"{ticker}.TWO"] if not ticker.endswith((".TW", ".TWO")) and ticker.isalnum() and not ticker.isalpha() else [])

    for sym in candidates:
        try:
            stock = yf.Ticker(sym)
            try:
                price = stock.fast_info.get("last_price")
                if price is not None and not pd.isna(price) and price > 0: return round(float(price), 4)
            except Exception: pass
            try:
                hist = stock.history(period="1mo", auto_adjust=False)
                if not hist.empty: return round(float(hist["Close"].dropna().iloc[-1]), 4)
            except Exception: pass
        except Exception: continue
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_historical_prices_for_chart(ticker: str, start_date: pd.Timestamp):
    if not ticker: return pd.DataFrame()
    ticker = ticker.strip().upper()
    clean_t = ticker.replace(".TW", "").replace(".TWO", "")
    is_tw_symbol = clean_t.isdigit() or (len(clean_t) > 1 and clean_t[:-1].isdigit() and clean_t[-1] in ["B", "L", "R"])
    if is_tw_symbol: candidates = [f"{clean_t}.TW", f"{clean_t}.TWO"]
    else: candidates = [ticker] + ([f"{ticker}.TW", f"{ticker}.TWO"] if not ticker.endswith((".TW", ".TWO")) and ticker.isalnum() and not ticker.isalpha() else [])

    for sym in candidates:
        try:
            stock = yf.Ticker(sym)
            hist = stock.history(start=start_date, auto_adjust=False)
            if not hist.empty:
                hist.index = hist.index.tz_localize(None).normalize()
                return hist
        except: continue
    return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_prices(tickers: tuple):
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_ticker = {executor.submit(get_latest_price, t): t for t in tickers}
        for future in concurrent.futures.as_completed(future_to_ticker):
            t = future_to_ticker[future]
            try: results[t] = future.result()
            except Exception: results[t] = None
    return results

# ========================================================
# 🚀 做空與多頭會計核心引擎
# ========================================================
def calculate_holdings(transactions):
    holdings = {}
    for t in transactions:
        key = t.get("ticker") or t.get("name")
        if not key: continue
        if key not in holdings:
            holdings[key] = {
                "名稱": t.get("name", key), "代號": t.get("ticker", ""), "幣別": t.get("currency", "TWD"),
                "類型": t.get("type_category", "其他"), "數量": 0.0, "avg_cost": 0.0,
                "CC權利金": 0.0, "SP權利金": 0.0, "股息": 0.0, "已實現損益": 0.0,
                "歷史買進數量": 0.0, "歷史賣出數量": 0.0
            }
        
        h = holdings[key]
        qty = float(t.get("quantity", 0))
        price = float(t.get("price", 0))
        action = t["type"]
        
        if action in ["Sell Put", "Covered Call", "配息"]:
            amount = price if qty == 0 else qty * price
            if action == "Covered Call":
                h["CC權利金"] += amount
                h["已實現損益"] += amount
            elif action == "Sell Put":
                h["SP權利金"] += amount
                h["已實現損益"] += amount
            elif action == "配息":
                h["股息"] += amount
                h["已實現損益"] += amount
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
                "數量": h["數量"], "原始總成本": h["原始總成本"], "平均成本": h["avg_cost"],
                "CC權利金": h["CC權利金"], "SP權利金": h["SP權利金"], "股息": h["股息"],
                "已實現損益": h["已實現損益"], "歷史買進數量": h["歷史買進數量"], "歷史賣出數量": h["歷史賣出數量"], "is_cash": False
            })
    return result

def safe_float(text):
    try: return float(text) if str(text).strip() else None
    except Exception: return None

def fmt(num, decimals=2):
    if pd.isna(num) or num is None: return "—"
    if isinstance(num, (int, float)) and 0 < num < 1: return f"{num:,.4f}"
    return f"{num:,.{decimals}f}"

def fmt_total(num, currency):
    if pd.isna(num) or num is None: return "—"
    if currency == "BTC": return f"{num:,.3f}"
    return f"{num:,.0f}"

def looks_like_ticker(text: str) -> bool:
    if not text: return False
    return bool(re.fullmatch(r"[A-Z0-9.\-]{1,15}", text.strip().upper()))

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

# ========================================================
# 💳 UI: 現金與負債管理區塊
# ========================================================
def render_cash_manager(unit, display_currency):
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
        cash_str = f"{safe_unit} {fmt_total(cash_total_display, display_currency)}"
        
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
                    c2.markdown(f"<div style='font-size:19px; margin-top:4px;'>{acc['currency']} {mask_val(fmt(acc['balance']))}</div>", unsafe_allow_html=True)
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
                                
                        cash_hist_df = pd.DataFrame(cash_hist).sort_values('Date')
                        if not cash_hist_df.empty and cash_hist_df['Value'].sum() > 0:
                            fig_cash_line = go.Figure()
                            hover_temp = "%{x|%Y-%m-%d}<br>" + safe_unit + " %{y:,.0f}<extra></extra>" if not st.session_state.privacy_mode else "%{x|%Y-%m-%d}<br>＊＊＊＊<extra></extra>"
                            fig_cash_line.add_trace(go.Scatter(x=cash_hist_df['Date'], y=cash_hist_df['Value'], mode='lines', name='現金總額', line=dict(color='#00CC96', width=3, shape='linear'), fill='tozeroy', fillcolor='rgba(0, 204, 150, 0.1)', hovertemplate=hover_temp))
                            today_dt = pd.to_datetime(date.today())
                            start_date = today_dt - pd.DateOffset(months=1) if len(cash_hist_df) <= 30 else cash_hist_df['Date'].min() - pd.Timedelta(days=3)
                            fig_cash_line.update_layout(margin=dict(t=10, b=20, l=10, r=10), height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(range=[start_date, today_dt + pd.Timedelta(days=1)], showgrid=False, tickfont=dict(color="#e2e8f0"), tickformat="%Y-%m-%d", type="date"), yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not st.session_state.privacy_mode), hovermode="x unified", dragmode="pan")
                            st.plotly_chart(fig_cash_line, use_container_width=True, config={'scrollZoom': True})
                        else:
                            st.caption("尚無足夠的歷史資料繪製趨勢圖。")
                    else:
                        st.caption("尚無歷史資料。")
                with c_chart_right:
                    st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>📊 現金分佈佔比</div>", unsafe_allow_html=True)
                    fig_cash = go.Figure(data=[go.Pie(labels=cash_df["名稱"], values=cash_df["顯示金額"], pull=[0.03]*len(cash_df), textinfo="label+percent", textfont=dict(size=14, color="#ffffff"), marker=dict(colors=["#00CC96", "#AB63FA", "#FFA15A", "#636EFA", "#EF553B"], line=dict(color="#111111", width=1.5)), sort=False, hovertemplate="%{label}<br>%{percent}<br>" + safe_unit + " %{value:,.0f}<extra></extra>" if not st.session_state.privacy_mode else "%{label}<br>%{percent}<extra></extra>")])
                    fig_cash.update_layout(margin=dict(t=10, b=50, l=10, r=10), height=300, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_cash, use_container_width=True)

def render_liability_manager(unit, display_currency, total_value, net_value):
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
        lib_str = f"{safe_unit} {fmt_total(lib_total_display, display_currency)}"
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
                    c2.markdown(f"<div style='font-size:19px; margin-top:4px;'>{acc['currency']} {mask_val(fmt(acc['balance']))}</div>", unsafe_allow_html=True)
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
                            
                    lib_hist_df = pd.DataFrame(lib_hist).sort_values('Date')
                    if not lib_hist_df.empty:
                        fig_lib_line = go.Figure()
                        hover_temp = "%{x|%Y-%m-%d}<br>" + safe_unit + " %{y:,.0f}<extra></extra>" if not st.session_state.privacy_mode else "%{x|%Y-%m-%d}<br>＊＊＊＊<extra></extra>"
                        fig_lib_line.add_trace(go.Scatter(x=lib_hist_df['Date'], y=lib_hist_df['Value'], mode='lines', name='負債總額', line=dict(color='#EF553B', width=3, shape='linear'), fill='tozeroy', fillcolor='rgba(239, 85, 59, 0.1)', hovertemplate=hover_temp))
                        today_dt = pd.to_datetime(date.today())
                        start_date = today_dt - pd.DateOffset(months=1) if len(lib_hist_df) <= 30 else lib_hist_df['Date'].min() - pd.Timedelta(days=3)
                        fig_lib_line.update_layout(margin=dict(t=10, b=20, l=10, r=10), height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(range=[start_date, today_dt + pd.Timedelta(days=1)], showgrid=False, tickfont=dict(color="#e2e8f0"), tickformat="%Y-%m-%d", type="date"), yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not st.session_state.privacy_mode), hovermode="x unified", dragmode="pan")
                        st.plotly_chart(fig_lib_line, use_container_width=True, config={'scrollZoom': True})
            with c_chart_right:
                st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>📊 負債分佈佔比</div>", unsafe_allow_html=True)
                if not lib_df.empty:
                    fig_lib = go.Figure(data=[go.Pie(labels=lib_df["名稱"], values=lib_df["顯示金額"], pull=[0.03]*len(lib_df), textinfo="label+percent", textfont=dict(size=14, color="#ffffff"), marker=dict(colors=["#EF553B", "#FFA15A", "#AB63FA", "#636EFA", "#00CC96"], line=dict(color="#111111", width=1.5)), sort=False, hovertemplate="%{label}<br>%{percent}<br>" + safe_unit + " %{value:,.0f}<extra></extra>" if not st.session_state.privacy_mode else "%{label}<br>%{percent}<extra></extra>")])
                    fig_lib.update_layout(margin=dict(t=10, b=50, l=10, r=10), height=300, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_lib, use_container_width=True)
        else: st.caption("目前無負債紀錄。")

# ========================================================
# ⚡ 獨立抽出的渲染模組 (@st_fragment) 解決效能問題
# ========================================================
@st_fragment
def render_overall_trend_section(history_snapshots, selected_cat, display_currency, usd_twd, btc_usd, unit, privacy):
    st.divider()
    st.subheader(f"📈 {'全部淨資產' if selected_cat is None else selected_cat} 變化趨勢")
    
    if len(history_snapshots) > 0:
        processed_history = []
        for d_str, data_val in history_snapshots.items():
            if isinstance(data_val, dict) and data_val.get("version") == "v2":
                d_data = data_val.get(display_currency, data_val.get("TWD"))
                val = d_data.get("value", 0)
                cost = d_data.get("cost", 0)
                liability = d_data.get("liability", 0.0)
                cats = d_data.get("categories", {})
                v = val - liability if selected_cat is None else cats.get(selected_cat, {}).get("value", 0)
                c = cost - liability if selected_cat is None else cats.get(selected_cat, {}).get("cost", 0)
            else:
                val = data_val.get("value", 0) if isinstance(data_val, dict) else data_val
                cost = data_val.get("cost", 0) if isinstance(data_val, dict) else data_val
                liability = data_val.get("liability", 0.0) if isinstance(data_val, dict) else 0.0
                cats = data_val.get("categories", {}) if isinstance(data_val, dict) else {}
                twd_v = val - liability if selected_cat is None else cats.get(selected_cat, {}).get("value", 0)
                twd_c = cost - liability if selected_cat is None else cats.get(selected_cat, {}).get("cost", 0)
                div = 1 if display_currency == "TWD" else usd_twd if display_currency == "USD" else (btc_usd * usd_twd if btc_usd else 1)
                v, c = twd_v / div, twd_c / div
            processed_history.append({'Date': d_str, 'Value': v, 'Cost': c})

        hist_df = pd.DataFrame(processed_history)
        hist_df['Date'] = pd.to_datetime(hist_df['Date'])
        hist_df = hist_df.sort_values('Date')

        col_radio, col_period_change = st.columns([2.5, 1.5])
        with col_radio:
            time_range = st.radio("選擇時間區間", ["1週", "1個月", "3個月", "半年", "1年", "全部"], index=1, horizontal=True, label_visibility="collapsed", key="trend_time_range")
            
        today_dt = pd.to_datetime(date.today())
        if time_range == "1週": start_date = today_dt - pd.DateOffset(weeks=1)
        elif time_range == "1個月": start_date = today_dt - pd.DateOffset(months=1)
        elif time_range == "3個月": start_date = today_dt - pd.DateOffset(months=3)
        elif time_range == "半年": start_date = today_dt - pd.DateOffset(months=6)
        elif time_range == "1年": start_date = today_dt - pd.DateOffset(years=1)
        else: start_date = hist_df['Date'].min() - pd.Timedelta(days=3)
        
        end_date = today_dt + pd.Timedelta(days=1)
        filtered_df = hist_df[hist_df['Date'] >= start_date].copy()
        
        with col_period_change:
            if not filtered_df.empty:
                start_val = filtered_df['Value'].iloc[0]
                end_val = filtered_df['Value'].iloc[-1]
                chg_val = end_val - start_val
                
                if abs(start_val) < 1e-5 and chg_val > 0: chg_pct_str = "∞%"
                elif abs(start_val) < 1e-5 and chg_val <= 0: chg_pct_str = "0.00%"
                else: chg_pct_str = f"{(chg_val / abs(start_val) * 100):.2f}%"
                
                safe_u = unit.replace('$', '&#36;')
                if privacy:
                    p_html = "<div style='text-align:right; margin-top:-10px;'><span style='font-size:14px; color:#94a3b8;'>區間淨值變化</span><br><span style='font-size:30px; font-weight:bold;'>＊＊＊＊</span></div>"
                else:
                    c_color = "#4ade80" if chg_val > 0 else "#ef4444" if chg_val < 0 else "#94a3b8"
                    c_sign = "+" if chg_val > 0 else ""
                    v_str = f"{c_sign}{safe_u} {abs(chg_val):,.0f}" if display_currency != "BTC" else f"{c_sign}BTC {abs(chg_val):,.4f}"
                    p_html = f"<div style='text-align:right; line-height:1.2; margin-top:-10px;'><span style='font-size:14px; color:#94a3b8;'>區間淨值變化</span><br><span style='font-size:30px; font-weight:bold; color:{c_color};'>{v_str} ({c_sign}{chg_pct_str})</span></div>"
                st.markdown(p_html, unsafe_allow_html=True)
            else:
                st.markdown("<div style='text-align:right; margin-top:-10px;'><span style='font-size:14px; color:#94a3b8;'>區間淨值變化</span><br><span style='font-size:30px; font-weight:bold; color:#94a3b8;'>無資料</span></div>", unsafe_allow_html=True)

        filtered_df['PnL'] = filtered_df['Value'] - filtered_df['Cost']
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

        filtered_df['pnl_val_text'] = filtered_df['PnL'].apply(get_val_text_global)
        filtered_df['pnl_pct_text'] = filtered_df.apply(get_pct_text_global, axis=1)

        filtered_df['Value_Gain'] = filtered_df[['Value', 'Cost']].max(axis=1)
        filtered_df['Value_Loss'] = filtered_df[['Value', 'Cost']].min(axis=1)
        
        y_max = filtered_df[['Value', 'Cost']].max().max()
        y_min = filtered_df[['Value', 'Cost']].min().min()
        y_range = y_max - y_min
        if y_range == 0: y_range = 1
        offset1 = y_range * 0.005
        offset2 = y_range * 0.010
        
        filtered_df['pnl_y'] = filtered_df[['Value', 'Cost']].min(axis=1) - offset1
        filtered_df['pct_y'] = filtered_df[['Value', 'Cost']].min(axis=1) - offset2
        
        if not filtered_df.empty:
            fig_line = go.Figure()
            val_name = '淨值' 
            
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

            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['pct_y'], mode='lines', name='百分比', line=dict(color='rgba(0,0,0,0)', width=0), customdata=filtered_df['pnl_pct_text'] if not privacy else None, hovertemplate=hover_temp_pct, showlegend=False, connectgaps=False))
            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['pnl_y'], mode='lines', name='損益', line=dict(color='rgba(0,0,0,0)', width=0), customdata=filtered_df['pnl_val_text'] if not privacy else None, hovertemplate=hover_temp_pnl, showlegend=False, connectgaps=False))
            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['Cost'], mode='lines', name='成本', line=dict(color='#3b82f6', width=3, shape='linear'), hovertemplate=hover_temp_cost))
            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['Value'], mode='lines', name=val_name, line=dict(color='#00CC96', width=3, shape='linear'), hovertemplate=hover_temp_val))

            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['Cost'], mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False))
            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['Value_Gain'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(255, 193, 7, 0.2)', hoverinfo='skip', showlegend=False))
            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['Cost'], mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False))
            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['Value_Loss'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(239, 68, 68, 0.2)', hoverinfo='skip', showlegend=False))

            fig_line.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(range=[start_date, end_date], showgrid=False, tickfont=dict(color="#e2e8f0"), tickformat="%Y-%m-%d", type="date"), yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not privacy, autorange=True), hovermode="x unified", dragmode="pan")
            st.plotly_chart(fig_line, use_container_width=True, config={'scrollZoom': True})
        else: st.info("所選時間區間內尚無歷史快照資料。")
    else: st.info("尚無足夠的歷史快照資料以繪製圖表。")

@st_fragment
def render_individual_analysis(transactions, privacy, display_currency, usd_twd, btc_usd):
    st.divider()
    st.subheader("🔍 個別標的進階分析")
    
    if transactions:
        tx_df_analysis = pd.DataFrame(transactions)
        tx_df_analysis["date_obj"] = pd.to_datetime(tx_df_analysis["date"])
        tx_df_analysis["target_label"] = tx_df_analysis.apply(lambda row: f"{row['name']} ({row['ticker']})" if row['ticker'] else row['name'], axis=1)
        
        target_options_analysis = sorted(tx_df_analysis["target_label"].unique().tolist())
        selected_analysis_target = st.selectbox("選擇要分析的標的", target_options_analysis, index=None, placeholder="🔍 點擊此處並直接鍵盤輸入代號或名稱搜尋...", label_visibility="collapsed")
        
        if selected_analysis_target:
            include_premium_individual = st.checkbox("此標的圖表計算包含權利金/配息降本", value=st.session_state.get("include_premium", False), key="include_premium_ind")

            with st.spinner(f"正在載入 {selected_analysis_target} 的歷史資料並回推圖表..."):
                asset_tx = tx_df_analysis[tx_df_analysis["target_label"] == selected_analysis_target].sort_values("date_obj").copy()
                ticker_to_fetch = asset_tx.iloc[0]["ticker"]
                asset_currency = asset_tx.iloc[0]["currency"]
                
                hist_df = pd.DataFrame()
                if ticker_to_fetch:
                    start_dt = asset_tx["date_obj"].min() - pd.Timedelta(days=7)
                    hist_df = get_historical_prices_for_chart(ticker_to_fetch, start_dt)
                
                first_trade_date = asset_tx["date_obj"].min()
                calendar = pd.date_range(start=first_trade_date, end=pd.to_datetime(date.today()))
                
                current_shares = 0.0
                current_avg_cost = 0.0
                daily_records = []
                
                for d, day_txs in asset_tx.groupby("date_obj"):
                    for _, tx in day_txs.iterrows():
                        qty = float(tx["quantity"])
                        price = float(tx["price"])
                        action = tx["type"]
                        
                        if action == "買進":
                            if current_shares >= 0:
                                new_shares = current_shares + qty
                                current_avg_cost = (current_shares * current_avg_cost + qty * price) / new_shares if new_shares > 0 else 0
                                current_shares = new_shares
                            else:
                                cover_qty = min(qty, abs(current_shares))
                                current_shares += cover_qty
                                remaining = qty - cover_qty
                                if remaining > 0:
                                    current_shares = remaining
                                    current_avg_cost = price
                                elif abs(current_shares) < 1e-5:
                                    current_shares = 0.0
                                    current_avg_cost = 0.0
                        elif action == "賣出":
                            if current_shares <= 0:
                                new_shares_abs = abs(current_shares) + qty
                                current_avg_cost = (abs(current_shares) * current_avg_cost + qty * price) / new_shares_abs if new_shares_abs > 0 else 0
                                current_shares -= qty
                            else:
                                sell_qty = min(qty, current_shares)
                                current_shares -= sell_qty
                                remaining = qty - sell_qty
                                if remaining > 0:
                                    current_shares = -remaining
                                    current_avg_cost = price
                                elif abs(current_shares) < 1e-5:
                                    current_shares = 0.0
                                    current_avg_cost = 0.0
                        elif action in ["Sell Put", "Covered Call", "配息"]:
                            if include_premium_individual:
                                if abs(current_shares) > 1e-5:
                                    total_cost = current_shares * current_avg_cost - price
                                    current_avg_cost = total_cost / current_shares

                    current_cost = current_shares * current_avg_cost
                    daily_records.append({"date": d, "shares": current_shares, "cost": current_cost, "avg_cost": current_avg_cost})
                
                records_df = pd.DataFrame(daily_records).set_index("date")
                daily_data = pd.DataFrame(index=calendar)
                daily_data = daily_data.join(records_df, how="left").ffill().fillna(0)

                if not hist_df.empty:
                    daily_data = daily_data.join(hist_df["Close"])
                    daily_data["Close"] = daily_data["Close"].ffill()
                    daily_data["Value"] = daily_data["shares"] * daily_data["Close"]
                else:
                    daily_data["Close"] = None
                    daily_data["Value"] = daily_data["cost"] 
                
                daily_data["pnl"] = daily_data["Value"] - daily_data["cost"]
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

                daily_data['pnl_val_text'] = daily_data['pnl'].apply(get_val_text_ind)
                daily_data['pnl_pct_text'] = daily_data.apply(get_pct_text_ind, axis=1)

                daily_data['Value_Gain'] = daily_data[['Value', 'cost']].max(axis=1)
                daily_data['Value_Loss'] = daily_data[['Value', 'cost']].min(axis=1)
                
                y_max_ind = daily_data[['Value', 'cost']].max().max()
                y_min_ind = daily_data[['Value', 'cost']].min().min()
                y_range_ind = y_max_ind - y_min_ind
                if y_range_ind == 0: y_range_ind = 1
                offset1_ind = y_range_ind * 0.005
                offset2_ind = y_range_ind * 0.010

                daily_data['pnl_y'] = daily_data[['Value', 'cost']].min(axis=1) - offset1_ind
                daily_data['pct_y'] = daily_data[['Value', 'cost']].min(axis=1) - offset2_ind

                st.markdown(f"*(註: 以下圖表皆以該標的原始計價幣別 **{asset_currency}** 呈現，不受匯率波動影響)*")
                
                c_chart1, c_chart2 = st.columns(2)
                
                with c_chart1:
                    st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>📊 持倉現值與成本變化</div>", unsafe_allow_html=True)
                    fig1 = go.Figure()
                    
                    val_name_ind = '淨值'
                    if privacy:
                        hover_val = " : ＊＊＊＊<extra>" + val_name_ind + "</extra>"
                        hover_cost = " : ＊＊＊＊<extra>成本</extra>"
                        hover_pnl = " : ＊＊＊＊<extra>損益</extra>"
                        hover_pct = " : ＊＊＊＊<extra>$$ %</extra>"
                    else:
                        hover_val = " : " + asset_unit_str + f" %{{y:,.0f}}<extra>{val_name_ind}</extra>"
                        hover_cost = " : " + asset_unit_str + " %{y:,.0f}<extra>成本</extra>"
                        hover_pnl = " : %{customdata}<extra>損益</extra>"
                        hover_pct = " : %{customdata}<extra>$$ %</extra>"
                    
                    fig1.add_trace(go.Scatter(x=daily_data.index, y=daily_data['pct_y'], mode='lines', name='百分比', line=dict(color='rgba(0,0,0,0)', width=0), customdata=daily_data['pnl_pct_text'] if not privacy else None, hovertemplate=hover_pct, showlegend=False))
                    fig1.add_trace(go.Scatter(x=daily_data.index, y=daily_data['pnl_y'], mode='lines', name='損益', line=dict(color='rgba(0,0,0,0)', width=0), customdata=daily_data['pnl_val_text'] if not privacy else None, hovertemplate=hover_pnl, showlegend=False))
                    fig1.add_trace(go.Scatter(x=daily_data.index, y=daily_data['cost'], mode='lines', name='成本', line=dict(color='#3b82f6', width=2), hovertemplate=hover_cost))
                    fig1.add_trace(go.Scatter(x=daily_data.index, y=daily_data['Value'], mode='lines', name=val_name_ind, line=dict(color='#00CC96', width=2), hovertemplate=hover_val))
                    fig1.add_trace(go.Scatter(x=daily_data.index, y=daily_data['cost'], mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False))
                    fig1.add_trace(go.Scatter(x=daily_data.index, y=daily_data['Value_Gain'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(255, 193, 7, 0.2)', hoverinfo='skip', showlegend=False))
                    fig1.add_trace(go.Scatter(x=daily_data.index, y=daily_data['cost'], mode='lines', line=dict(width=0), hoverinfo='skip', showlegend=False))
                    fig1.add_trace(go.Scatter(x=daily_data.index, y=daily_data['Value_Loss'], mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(239, 68, 68, 0.2)', hoverinfo='skip', showlegend=False))
                    
                    fig1.update_layout(margin=dict(t=10, b=20, l=10, r=10), height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False, tickfont=dict(color="#e2e8f0"), tickformat="%Y-%m-%d"), yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not privacy), hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0), dragmode="pan")
                    st.plotly_chart(fig1, use_container_width=True, config={'scrollZoom': True})
                
                with c_chart2:
                    st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>🎯 價格走勢與交易點位</div>", unsafe_allow_html=True)
                    if hist_df.empty:
                        st.warning("無法取得此標的之歷史報價，僅能繪製成本變化圖。")
                    else:
                        fig2 = go.Figure()
                        hover_temp2 = " : %{y:,.2f}<extra></extra>" if not privacy else " : ＊＊＊＊<extra></extra>"
                        fig2.add_trace(go.Scatter(x=hist_df.index, y=hist_df['Close'], mode='lines', name='收盤價', line=dict(color='#94a3b8', width=2), hovertemplate=hover_temp2))
                        
                        hover_temp_avg = " : %{y:,.2f}<extra></extra>" if not privacy else " : ＊＊＊＊<extra></extra>"
                        fig2.add_trace(go.Scatter(x=daily_data.index, y=daily_data['avg_cost'].abs(), mode='lines', name='平均成本', line=dict(color='#FFA15A', width=2, dash='dash'), hovertemplate=hover_temp_avg, connectgaps=False))
                        
                        buys = asset_tx[asset_tx['type'] == '買進'].copy()
                        sells = asset_tx[asset_tx['type'] == '賣出'].copy()
                        max_q = asset_tx[asset_tx['type'].isin(['買進', '賣出'])]['quantity'].max()
                        if pd.isna(max_q) or max_q <= 0: max_q = 1
                        
                        def make_hover(row):
                            if privacy: return "＊＊＊＊"
                            return f"日期: {row['date']}<br>動作: {row['type']}<br>價格: {row['price']}<br>數量: {row['quantity']}<br>備註: {row.get('note', '')}"
                        
                        if not buys.empty:
                            buys['hover'] = buys.apply(make_hover, axis=1)
                            sizes = [max(8, min(25, (q / max_q) * 25)) for q in buys['quantity']]
                            fig2.add_trace(go.Scatter(x=buys['date_obj'], y=buys['price'], mode='markers', name='買進', marker=dict(color='#4ade80', size=sizes, line=dict(width=1, color='white')), customdata=buys['hover'], hovertemplate="<br>%{customdata}<extra></extra>"))
                            
                        if not sells.empty:
                            sells['hover'] = sells.apply(make_hover, axis=1)
                            sizes = [max(8, min(25, (q / max_q) * 25)) for q in sells['quantity']]
                            fig2.add_trace(go.Scatter(x=sells['date_obj'], y=sells['price'], mode='markers', name='賣出', marker=dict(color='#ef4444', size=sizes, line=dict(width=1, color='white')), customdata=sells['hover'], hovertemplate="<br>%{customdata}<extra></extra>"))
                            
                        fig2.update_layout(margin=dict(t=10, b=20, l=10, r=10), height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False, tickfont=dict(color="#e2e8f0"), tickformat="%Y-%m-%d"), yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not privacy), hovermode="closest", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0), dragmode="pan")
                        st.plotly_chart(fig2, use_container_width=True, config={'scrollZoom': True})

    # 執行個別標的局部渲染
    render_individual_analysis(st.session_state.transactions, st.session_state.privacy_mode, display_currency, usd_twd, btc_usd)

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
                    c1, c2, c3, c4, c5, c6, c7 = st.columns([1.0, 0.6, 1.4, 1.3, 0.5, 1.2, 1.1])
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
                    with c7:
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
                    c1, c2, c3, c4, c5, c6, c7 = st.columns([1.0, 0.6, 1.4, 1.3, 0.5, 1.2, 1.1])
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
                    with c7:
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
            h1, h2, h3, h4, h5, h6, h7 = st.columns([1.0, 0.6, 1.4, 1.3, 0.5, 1.2, 1.1])
            h1.markdown("<div style='text-align:center'><b>日期</b></div>", unsafe_allow_html=True)
            h2.markdown("<div style='text-align:center'><b>動作</b></div>", unsafe_allow_html=True)
            h3.markdown("<div style='text-align:center'><b>標的</b></div>", unsafe_allow_html=True)
            h4.markdown("<div style='text-align:center'><b>明細</b></div>", unsafe_allow_html=True)
            h5.markdown("<div style='text-align:center'><b>幣別</b></div>", unsafe_allow_html=True)
            h6.markdown("<div style='text-align:center'><b>備註</b></div>", unsafe_allow_html=True)
            h7.markdown("")
            render_tx_rows(tx_df.head(20))
            if len(tx_df) > 20:
                with st.expander(f"展開顯示其餘 {len(tx_df) - 20} 筆紀錄..."): render_tx_rows(tx_df.iloc[20:])
        else: st.info("沒有符合條件的紀錄。")
    else: st.caption("尚無交易紀錄")

    st.divider()
    st.subheader("匯出")
    c1, c2 = st.columns(2)
    with c1: st.download_button("下載持倉 CSV", df.to_csv(index=False).encode("utf-8-sig"), f"holdings_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
    with c2: st.download_button("下載交易紀錄 CSV", pd.DataFrame(st.session_state.transactions).to_csv(index=False).encode("utf-8-sig"), f"transactions_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

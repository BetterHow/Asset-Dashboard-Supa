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
    """用使用者的密碼，轉換成 32-byte 的專屬加密金鑰"""
    digest = hashlib.sha256(password.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)

def encrypt_data(data, password: str) -> str:
    """將明文資料加密成亂碼"""
    f = Fernet(get_encryption_key(password))
    json_str = json.dumps(data, ensure_ascii=False)
    return f.encrypt(json_str.encode('utf-8')).decode('utf-8')

def decrypt_data(encrypted_str: str, password: str):
    """用使用者的密碼解密亂碼"""
    try:
        f = Fernet(get_encryption_key(password))
        decrypted_bytes = f.decrypt(encrypted_str.encode('utf-8'))
        return json.loads(decrypted_bytes.decode('utf-8'))
    except Exception:
        return None

def save_data(category, data):
    """上傳加密後的資料到 Supabase"""
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
    """從 Supabase 下載亂碼並在本地解密"""
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
                except Exception as e:
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
# 📊 以下為正式 App 儀表板
# ========================================================
st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] > div:first-child { overflow-y: auto; }
    button[kind="header"], div[data-testid="collapsedControl"], button[data-testid="stSidebarCollapseButton"] {
        position: fixed !important; top: 10px !important; z-index: 999999;
    }
    div[data-testid="stButton"] button p { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    div[data-testid="stTextInput"] div { padding-top: 0px; padding-bottom: 0px; }
    </style>
    """, unsafe_allow_html=True
)

st.title("📊 個人資產儀表板（交易紀錄版）")
st.caption("支援買進 / 賣出｜動態現金管理｜負債追蹤｜自動快照｜行內編輯｜隱私保護")

# 初始化載入資料 (從 Supabase 解密)
if "transactions" not in st.session_state:
    st.session_state.transactions = load_data("transactions", [])
if "manual_prices" not in st.session_state:
    st.session_state.manual_prices = load_data("manual_prices", {})
if "cash_accounts" not in st.session_state:
    st.session_state.cash_accounts = load_data("cash_accounts", [])
if "liabilities_accounts" not in st.session_state:
    st.session_state.liabilities_accounts = load_data("liabilities_accounts", [])
if "history_snapshots" not in st.session_state:
    st.session_state.history_snapshots = load_data("history_snapshots", {})

# 狀態管理
if "selected_category" not in st.session_state:
    st.session_state.selected_category = None
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
if "edit_cash_id" not in st.session_state:
    st.session_state.edit_cash_id = None
if "edit_liability_id" not in st.session_state:
    st.session_state.edit_liability_id = None
if "display_currency" not in st.session_state:
    st.session_state.display_currency = "TWD"
if "selected_extras" not in st.session_state:
    st.session_state.selected_extras = []
if "visible_items" not in st.session_state:
    st.session_state.visible_items = set()
if "clear_form" not in st.session_state:
    st.session_state.clear_form = False
if "privacy_mode" not in st.session_state:
    st.session_state.privacy_mode = False
if "prev_ticker" not in st.session_state:
    st.session_state.prev_ticker = ""
if "prev_type" not in st.session_state:
    st.session_state.prev_type = "台股"

@st.cache_data(ttl=300, show_spinner=False)
def get_rate(symbol: str):
    try:
        t = yf.Ticker(symbol)
        rate = t.fast_info.get("last_price")
        if rate:
            return round(float(rate), 4)
        hist = t.history(period="5d")
        if not hist.empty:
            return round(float(hist["Close"].dropna().iloc[-1]), 4)
    except Exception:
        pass
    return None

usd_twd = get_rate("USDTWD=X") or 32.4
btc_usd = get_rate("BTC-USD") or 95000.0

EXTRA_RATES = {
    "EUR/TWD": "EURTWD=X",
    "JPY/TWD": "JPYTWD=X",
    "GBP/TWD": "GBPTWD=X",
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
}

def get_latest_price(ticker: str):
    if not ticker: return None
    ticker = ticker.strip().upper()
    candidates = []
    if ticker.isdigit(): candidates = [f"{ticker}.TW", f"{ticker}.TWO"]
    else:
        candidates = [ticker]
        if not ticker.endswith((".TW", ".TWO")) and ticker.isalnum() and not ticker.isalpha():
            candidates += [f"{ticker}.TW", f"{ticker}.TWO"]
    for sym in candidates:
        try:
            stock = yf.Ticker(sym)
            try:
                price = stock.fast_info.get("last_price")
                if price is not None and not pd.isna(price) and price > 0: return round(float(price), 4)
            except Exception: pass
            try:
                hist = stock.history(period="1mo")
                if not hist.empty: return round(float(hist["Close"].dropna().iloc[-1]), 4)
            except Exception: pass
        except Exception: continue
    return None

@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_prices(tickers: tuple):
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_ticker = {executor.submit(get_latest_price, t): t for t in tickers}
        for future in concurrent.futures.as_completed(future_to_ticker):
            t = future_to_ticker[future]
            try:
                price = future.result()
                results[t] = price
            except Exception:
                results[t] = None
    return results

def calculate_holdings(transactions):
    holdings = {}
    for t in transactions:
        key = t.get("ticker") or t.get("name")
        if not key: continue
        if key not in holdings:
            holdings[key] = {"名稱": t.get("name", key), "代號": t.get("ticker", ""), "幣別": t.get("currency", "TWD"), "類型": t.get("type_category", "其他"), "數量": 0.0, "總成本": 0.0}
        qty = float(t["quantity"])
        price = float(t["price"])
        if t["type"] == "買進":
            holdings[key]["數量"] += qty
            holdings[key]["總成本"] += qty * price
        elif t["type"] == "賣出":
            if holdings[key]["數量"] > 0:
                avg_cost = holdings[key]["總成本"] / holdings[key]["數量"] if holdings[key]["數量"] > 0 else 0
                sell_qty = min(qty, holdings[key]["數量"])
                holdings[key]["數量"] -= sell_qty
                holdings[key]["總成本"] -= sell_qty * avg_cost
                if holdings[key]["數量"] < 1e-5:
                    holdings[key]["數量"] = 0.0
                    holdings[key]["總成本"] = 0.0
    result = []
    for key, h in holdings.items():
        if h["數量"] > 0.0001:
            avg_cost = h["總成本"] / h["數量"] if h["數量"] > 0 else 0
            result.append({"名稱": h["名稱"], "代號": h["代號"], "幣別": h["幣別"], "類型": h["類型"], "數量": round(h["數量"], 6), "平均成本": round(avg_cost, 4), "總成本": round(h["總成本"], 2), "is_cash": False})
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

def mask_val(val_str):
    return "＊＊＊＊" if st.session_state.privacy_mode else val_str

def render_cash_manager():
    st.markdown("#### 💵 現金帳戶管理")
    with st.form("cash_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([2, 1, 2, 1])
        with c1: new_cash_name = st.text_input("帳戶名稱 (如: 富邦交割戶)")
        with c2: new_cash_curr = st.selectbox("幣別", ["TWD", "USD"])
        with c3: new_cash_bal = st.text_input("目前餘額")
        with c4:
            st.write("")
            submitted = st.form_submit_button("新增", use_container_width=True)
        if submitted:
            if new_cash_name and new_cash_bal:
                bal = safe_float(new_cash_bal)
                if bal is not None:
                    st.session_state.cash_accounts.append({
                        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"), "name": new_cash_name.strip(), "currency": new_cash_curr, "balance": bal
                    })
                    save_data("cash_accounts", st.session_state.cash_accounts)
                    st.success("已成功新增現金帳戶！")
                    st.rerun()
                else: st.warning("請輸入有效的餘額數字。")
                    
    if st.session_state.cash_accounts:
        st.markdown("##### 目前持有的現金部位")
        for acc in st.session_state.cash_accounts:
            if st.session_state.edit_cash_id == acc["id"]:
                c1, c2, c3, c4, c5 = st.columns([2, 1, 2, 1, 1])
                new_name = c1.text_input("名稱", acc["name"], key=f"name_{acc['id']}", label_visibility="collapsed")
                new_curr = c2.selectbox("幣別", ["TWD", "USD"], index=0 if acc["currency"]=="TWD" else 1, key=f"curr_{acc['id']}", label_visibility="collapsed")
                new_bal = c3.text_input("餘額", str(acc["balance"]), key=f"bal_{acc['id']}", label_visibility="collapsed")
                if c4.button("儲存", key=f"save_{acc['id']}", type="primary", use_container_width=True):
                    acc["name"] = new_name.strip() if new_name.strip() else acc["name"]
                    acc["currency"] = new_curr
                    bal = safe_float(new_bal)
                    if bal is not None: acc["balance"] = bal
                    save_data("cash_accounts", st.session_state.cash_accounts)
                    st.session_state.edit_cash_id = None
                    st.rerun()
                if c5.button("取消", key=f"cancel_{acc['id']}", use_container_width=True):
                    st.session_state.edit_cash_id = None
                    st.rerun()
            else:
                c1, c2, c3, c4 = st.columns([3.5, 5.0, 0.8, 0.8])
                c1.markdown(f"<div style='font-size:19px; font-weight:bold; margin-top:4px;'>{acc['name']}</div>", unsafe_allow_html=True)
                c2.markdown(f"<div style='font-size:19px; margin-top:4px;'>{acc['currency']} {mask_val(fmt(acc['balance']))}</div>", unsafe_allow_html=True)
                if c3.button("編輯", key=f"edit_cash_{acc['id']}", use_container_width=True):
                    st.session_state.edit_cash_id = acc["id"]
                    st.rerun()
                if c4.button("刪除", key=f"del_cash_{acc['id']}", use_container_width=True):
                    st.session_state.cash_accounts = [a for a in st.session_state.cash_accounts if a["id"] != acc["id"]]
                    save_data("cash_accounts", st.session_state.cash_accounts)
                    st.rerun()
    st.divider()

def render_liability_manager(unit, display_currency, total_value, net_value):
    with st.expander("💳 負債總覽", expanded=False):
        lib_total_display = 0
        lib_df = pd.DataFrame()
        if st.session_state.liabilities_accounts:
            lib_items = []
            for lib in st.session_state.liabilities_accounts:
                val_twd = lib["balance"] if lib["currency"] == "TWD" else lib["balance"] * usd_twd
                lib_items.append({"id": lib["id"], "名稱": lib["name"], "幣別": lib["currency"], "原始金額": lib["balance"], "TWD金額": val_twd})
            lib_df = pd.DataFrame(lib_items)
            if display_currency == "TWD": lib_df["顯示金額"] = lib_df["TWD金額"]
            elif display_currency == "USD": lib_df["顯示金額"] = lib_df["TWD金額"] / usd_twd
            elif display_currency == "BTC": lib_df["顯示金額"] = (lib_df["TWD金額"] / usd_twd) / btc_usd if btc_usd else lib_df["TWD金額"]
            lib_total_display = lib_df["顯示金額"].sum()

        safe_unit = unit.replace("$", "&#36;")
        leverage_str = f"{total_value / net_value:.2f} 倍" if net_value > 0 else "N/A"
        st.markdown(f"<div style='font-size: 22px; font-weight: bold; margin-bottom: 15px;'>負債總額： {mask_val(f'{safe_unit} {fmt_total(lib_total_display, display_currency)}')} <span style='font-size: 18px; color: #94a3b8; font-weight: normal;'>｜ 槓桿比率： {mask_val(leverage_str)}</span></div>", unsafe_allow_html=True)
        
        with st.form("liability_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([2, 1, 2, 1])
            with c1: new_lib_name = st.text_input("負債名稱 (如: 股票質借 / 房貸)")
            with c2: new_lib_curr = st.selectbox("幣別", ["TWD", "USD"], key="lib_curr_box")
            with c3: new_lib_bal = st.text_input("目前金額")
            with c4:
                st.write("")
                submitted = st.form_submit_button("新增負債", use_container_width=True)
            if submitted:
                if new_lib_name and new_lib_bal:
                    bal = safe_float(new_lib_bal)
                    if bal is not None:
                        st.session_state.liabilities_accounts.append({
                            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"), "name": new_lib_name.strip(), "currency": new_lib_curr, "balance": bal
                        })
                        save_data("liabilities_accounts", st.session_state.liabilities_accounts)
                        st.success("已成功新增負債！")
                        st.rerun()
                    else: st.warning("請輸入有效的金額數字。")
                        
        if st.session_state.liabilities_accounts:
            for acc in st.session_state.liabilities_accounts:
                if st.session_state.edit_liability_id == acc["id"]:
                    c1, c2, c3, c4, c5 = st.columns([2, 1, 2, 1, 1])
                    new_name = c1.text_input("名稱", acc["name"], key=f"lib_name_{acc['id']}", label_visibility="collapsed")
                    new_curr = c2.selectbox("幣別", ["TWD", "USD"], index=0 if acc["currency"]=="TWD" else 1, key=f"lib_curr_{acc['id']}", label_visibility="collapsed")
                    new_bal = c3.text_input("金額", str(acc["balance"]), key=f"lib_bal_{acc['id']}", label_visibility="collapsed")
                    if c4.button("儲存", key=f"save_lib_{acc['id']}", type="primary", use_container_width=True):
                        acc["name"] = new_name.strip() if new_name.strip() else acc["name"]
                        acc["currency"] = new_curr
                        bal = safe_float(new_bal)
                        if bal is not None: acc["balance"] = bal
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
                            
                    lib_hist_df = pd.DataFrame(lib_hist)
                    lib_hist_df['Date'] = pd.to_datetime(lib_hist_df['Date'])
                    lib_hist_df = lib_hist_df.sort_values('Date')

                    if not lib_hist_df.empty:
                        fig_lib_line = go.Figure()
                        hover_temp = "%{x|%Y-%m-%d}<br>＊＊＊＊<extra></extra>" if st.session_state.privacy_mode else "%{x|%Y-%m-%d}<br>" + safe_unit + " %{y:,.0f}<extra></extra>"
                        fig_lib_line.add_trace(go.Scatter(
                            x=lib_hist_df['Date'], y=lib_hist_df['Value'], mode='lines+markers', name='負債總額',
                            line=dict(color='#EF553B', width=3, shape='linear'), marker=dict(size=6, color='#EF553B'),
                            fill='tozeroy', fillcolor='rgba(239, 85, 59, 0.1)', hovertemplate=hover_temp
                        ))
                        today_dt = pd.to_datetime(date.today())
                        start_date = today_dt - pd.DateOffset(months=1) if len(lib_hist_df) <= 30 else lib_hist_df['Date'].min() - pd.Timedelta(days=3)
                        end_date = today_dt + pd.Timedelta(days=1)
                        fig_lib_line.update_layout(
                            margin=dict(t=10, b=20, l=10, r=10), height=280, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            xaxis=dict(range=[start_date, end_date], showgrid=False, tickfont=dict(color="#e2e8f0"), tickformat="%Y-%m-%d", type="date"),
                            yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not st.session_state.privacy_mode),
                            hovermode="x unified", dragmode="pan"
                        )
                        st.plotly_chart(fig_lib_line, use_container_width=True, config={'scrollZoom': True})
            with c_chart_right:
                st.markdown("<div style='text-align:center; color:#94a3b8; font-size:15px; margin-bottom:10px; font-weight:600;'>📊 負債分佈佔比</div>", unsafe_allow_html=True)
                if not lib_df.empty:
                    fig_lib = go.Figure(data=[go.Pie(
                        labels=lib_df["名稱"], values=lib_df["顯示金額"], pull=[0.03]*len(lib_df),
                        textinfo="label+percent", textfont=dict(size=14, color="#ffffff"),
                        marker=dict(colors=["#EF553B", "#FFA15A", "#AB63FA", "#636EFA", "#00CC96"], line=dict(color="#111111", width=1.5)),
                        sort=False, hovertemplate="%{label}<br>%{percent}<extra></extra>" if st.session_state.privacy_mode else "%{label}<br>%{percent}<br>" + safe_unit + " %{value:,.0f}<extra></extra>"
                    )])
                    fig_lib.update_layout(margin=dict(t=10, b=20, l=10, r=10), height=280, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_lib, use_container_width=True)
        else: st.caption("目前無負債紀錄。")

col_rate, col_select, col_empty = st.columns([1.2, 0.7, 3.1])
with col_rate: st.markdown(f"<span style='font-size:18px; font-weight:600'>USD / TWD {usd_twd:.3f}</span>", unsafe_allow_html=True)
with col_select:
    available = [k for k in EXTRA_RATES.keys() if k not in st.session_state.selected_extras]
    if available:
        choice = st.selectbox("新增匯率", options=["+ 匯率"] + available, index=0, label_visibility="collapsed", key="rate_selector")
        if choice != "+ 匯率":
            st.session_state.selected_extras.append(choice)
            st.rerun()

if st.session_state.selected_extras:
    for name in st.session_state.selected_extras[:]:
        r = get_rate(EXTRA_RATES[name])
        c1, c2, c3 = st.columns([1.2, 0.7, 3.1])
        with c1: st.markdown(f"**{name} {r:.3f}**" if r else f"**{name} N/A**")
        with c2:
            if st.button("×", key=f"rm_{name}"):
                st.session_state.selected_extras.remove(name)
                st.rerun()
st.divider()

with st.sidebar:
    st.markdown(f"<div style='color: #4ade80; font-size: 14px; font-weight: bold; margin-bottom: 5px;'>🔓 已登入：{st.session_state.user.email}</div>", unsafe_allow_html=True)
    if st.button("登出金庫", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.session_state.password = None
        st.cache_data.clear()
        st.rerun()
    st.divider()
    
    st.header("新增交易")
    if st.session_state.clear_form:
        st.session_state["name_input"] = ""
        st.session_state["ticker_input"] = ""
        st.session_state["qty_input"] = ""
        st.session_state["price_input"] = ""
        st.session_state.clear_form = False

    action = st.radio("交易類型", ["買進", "賣出"], horizontal=True, key="action_radio")
    name = st.text_input("資產名稱", key="name_input")
    if name and looks_like_ticker(name):
        auto_ticker = name.strip().upper()
        crypto_map = {"BTC": "BTC-USD", "ETH": "ETH-USD", "ADA": "ADA-USD", "SOL": "SOL-USD", "DOGE": "DOGE-USD", "SUI": "SUI-USD"}
        if auto_ticker in crypto_map: auto_ticker = crypto_map[auto_ticker]
        if st.session_state.get("ticker_input", "") != auto_ticker:
            st.session_state["ticker_input"] = auto_ticker
            
    ticker = st.text_input("代號", key="ticker_input")
    ticker_val = str(ticker).strip().upper()
    if ticker_val != st.session_state.prev_ticker:
        if ticker_val.isdigit() or ticker_val.endswith((".TW", ".TWO")):
            st.session_state["type_select"] = "台股"
            st.session_state["currency_select"] = "TWD"
        elif "-USD" in ticker_val:
            st.session_state["type_select"] = "加密貨幣"
            st.session_state["currency_select"] = "USD"
        elif ticker_val.isalpha():
            st.session_state["type_select"] = "美股"
            st.session_state["currency_select"] = "USD"
        st.session_state.prev_ticker = ticker_val

    type_options = ["台股", "美股", "期貨", "加密貨幣", "債券", "其他"]
    asset_type = st.selectbox("類型", type_options, key="type_select")
    if asset_type != st.session_state.prev_type:
        st.session_state["currency_select"] = "USD" if asset_type in ["美股", "加密貨幣"] else "TWD"
        st.session_state.prev_type = asset_type

    currency = st.selectbox("幣別", ["TWD", "USD"], key="currency_select")
    quantity_str = st.text_input("數量", placeholder="輸入數量 (若是期貨請填1)", key="qty_input")
    price_str = st.text_input(f"價格（{currency}）", value="", placeholder="輸入價格（留白將使用自動抓價）", key="price_input")
    trade_date = st.date_input("交易日期", value=date.today(), key="date_input")
    note = st.text_input("備註", value="", key="note_input")

    if st.button("儲存", type="primary", use_container_width=True, key="save_btn"):
        qty = safe_float(quantity_str)
        price = safe_float(price_str)
        if price is None and ticker and len(str(ticker).strip()) >= 2:
            market_price = get_latest_price(str(ticker))
            if market_price: price = market_price
                
        if name and qty and qty > 0 and price and price > 0:
            new_tx = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"), "date": trade_date.strftime("%Y-%m-%d"),
                "type": action, "name": name, "ticker": str(ticker).strip().upper() if ticker else "",
                "type_category": asset_type, "currency": currency, "quantity": qty, "price": price, "fee": 0, "note": note,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            st.session_state.transactions.append(new_tx)
            st.success(f"已記錄：{action} {name} (價格: {price})")
            st.session_state.clear_form = True
            save_data("transactions", st.session_state.transactions)
            fetch_all_prices.clear()
            st.rerun()
        else: st.warning("請正確填寫名稱、數量。若自動抓價失敗, 請手動輸入價格。")

    st.divider()
    st.caption(f"交易紀錄：{len(st.session_state.transactions)} 筆")
    st.divider()
    st.caption(f"Streamlit 版本: {st.__version__}")

holdings = calculate_holdings(st.session_state.transactions)
for acc in st.session_state.cash_accounts:
    holdings.append({"名稱": acc["name"], "代號": "", "幣別": acc["currency"], "類型": "現金", "數量": acc["balance"], "平均成本": 1.0, "總成本": acc["balance"], "is_cash": True})

if not holdings:
    st.info("目前沒有持倉或現金。請從左側新增第一筆「買進」交易，或在下方新增現金帳戶。")
    render_cash_manager()
else:
    df = pd.DataFrame(holdings)
    df["類型"] = df["類型"].replace({"股票": "台股", "ETF": "台股"})
    unique_tickers = tuple(set(row["代號"] for row in holdings if row.get("代號") and not row.get("is_cash")))
    cached_prices = fetch_all_prices(unique_tickers)

    def get_price_for_row(row):
        if row.get("is_cash"): return 1.0
        key = row["代號"] or row["名稱"]
        if key in st.session_state.manual_prices: return st.session_state.manual_prices[key]
        if row["代號"]: return cached_prices.get(row["代號"])
        return None

    df["現價"] = df.apply(get_price_for_row, axis=1)
    df["現值"] = df.apply(lambda r: r["數量"] * r["現價"] if r["現價"] is not None else r["總成本"], axis=1)
    df["未實現損益"] = df["現值"] - df["總成本"]
    display_currency = st.session_state.display_currency

    def convert(val, cur):
        usd_val = val / usd_twd if cur == "TWD" else val
        if display_currency == "TWD": return usd_val * usd_twd
        elif display_currency == "USD": return usd_val
        elif display_currency == "BTC": return usd_val / btc_usd if btc_usd else usd_val
        return usd_val

    df["顯示現值"] = df.apply(lambda r: convert(r["現值"], r["幣別"]), axis=1)
    df["顯示總成本"] = df.apply(lambda r: convert(r["總成本"], r["幣別"]), axis=1)
    df["顯示損益"] = df["顯示現值"] - df["顯示總成本"]

    total_value = df["顯示現值"].sum()
    total_cost = df["顯示總成本"].sum()

    unit = "NT&#36;" if display_currency == "TWD" else "US&#36;" if display_currency == "USD" else "BTC"

    def get_twd_value(val, cur):
        if cur == "TWD": return val
        if cur == "USD": return val * usd_twd
        if cur == "BTC": return val * (btc_usd * usd_twd) if btc_usd else val
        return val
        
    total_twd_snapshot = sum(get_twd_value(row["現值"], row["幣別"]) for _, row in df.iterrows())
    total_cost_twd_snapshot = sum(get_twd_value(row["總成本"], row["幣別"]) for _, row in df.iterrows())
    
    total_liability_twd = sum(l["balance"] if l["currency"] == "TWD" else l["balance"] * usd_twd for l in st.session_state.liabilities_accounts)
    total_liability_display = convert(total_liability_twd, "TWD")

    net_value = total_value - total_liability_display
    net_cost = total_cost - total_liability_display
    net_pnl = net_value - net_cost
    net_pnl_pct = (net_pnl / net_cost * 100) if net_cost > 0 else 0

    def get_val_in_cur(val, from_cur, to_cur):
        if from_cur == "TWD": usd_val = val / usd_twd
        elif from_cur == "USD": usd_val = val
        elif from_cur == "BTC": usd_val = val * btc_usd if btc_usd else 0
        else: usd_val = val
        if to_cur == "TWD": return usd_val * usd_twd
        elif to_cur == "USD": return usd_val
        elif to_cur == "BTC": return usd_val / btc_usd if btc_usd else 0
        return val

    new_snapshot = {"version": "v2"}
    for d_cur in ["TWD", "USD", "BTC"]:
        cur_val = sum(get_val_in_cur(row["現值"], row["幣別"], d_cur) for _, row in df.iterrows())
        cur_cost = sum(get_val_in_cur(row["總成本"], row["幣別"], d_cur) for _, row in df.iterrows())
        cur_liab = sum(get_val_in_cur(l["balance"], l["currency"], d_cur) for l in st.session_state.liabilities_accounts)
        cat_snaps = {}
        for cat, group in df.groupby("類型"):
            cat_v = sum(get_val_in_cur(r["現值"], r["幣別"], d_cur) for _, r in group.iterrows())
            cat_c = sum(get_val_in_cur(r["總成本"], r["幣別"], d_cur) for _, r in group.iterrows())
            cat_snaps[cat] = {"value": round(cat_v, 2), "cost": round(cat_c, 2)}
        new_snapshot[d_cur] = {"value": round(cur_val, 2), "cost": round(cur_cost, 2), "liability": round(cur_liab, 2), "categories": cat_snaps}

    today_str = date.today().isoformat()
    if today_str not in st.session_state.history_snapshots or st.session_state.history_snapshots[today_str] != new_snapshot:
        st.session_state.history_snapshots[today_str] = new_snapshot
        save_data("history_snapshots", st.session_state.history_snapshots)
        
    col_title, col_toggle, col_refresh, col_empty = st.columns([1.5, 1.0, 1.0, 6.5])
    with col_title: st.markdown("<h3 style='margin: 0; padding-top: 5px; white-space: nowrap;'>資產總覽</h3>", unsafe_allow_html=True)
    with col_toggle:
        if st.button("顯示金額" if st.session_state.privacy_mode else "隱藏金額", key="privacy_toggle", use_container_width=True):
            st.session_state.privacy_mode = not st.session_state.privacy_mode
            st.rerun()
    with col_refresh:
        if st.button("重新整理", key="refresh_cache_btn", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
            
    privacy = st.session_state.privacy_mode
    options = ["TWD", "USD", "BTC"]
    current_idx = options.index(st.session_state.display_currency) if st.session_state.display_currency in options else 0
    new_currency = st.radio("顯示幣別", options, horizontal=True, index=current_idx, key="currency_radio")
    if new_currency != st.session_state.display_currency:
        st.session_state.display_currency = new_currency
        st.rerun()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("淨資產現值", mask_val(f"{unit.replace('&#36;', '$')} {fmt_total(net_value, display_currency)}"))
    m2.metric("總資產現值", mask_val(f"{unit.replace('&#36;', '$')} {fmt_total(total_value, display_currency)}"))
    m3.metric("負債總額", mask_val(f"{unit.replace('&#36;', '$')} {fmt_total(total_liability_display, display_currency)}"))
    m4.metric("未實現損益", mask_val(f"{unit.replace('&#36;', '$')} {fmt_total(net_pnl, display_currency)}"), delta=f"{net_pnl_pct:.1f}%")

    render_liability_manager(unit, display_currency, total_value, net_value)

    st.subheader("目前持倉配置")
    category_summary = df.groupby("類型")[["顯示現值", "顯示損益", "顯示總成本"]].sum().reset_index()
    category_summary = category_summary.sort_values("顯示現值", ascending=False)
    
    order_list = [cat for cat in category_summary['類型'] if cat not in ['期貨', '現金']]
    if '期貨' in category_summary['類型'].values: order_list.append('期貨')
    if '現金' in category_summary['類型'].values: order_list.append('現金')
        
    category_summary = category_summary.set_index('類型').loc[order_list].reset_index()
    
    num_cols = min(len(category_summary), 6)
    if num_cols > 0:
        cols = st.columns(num_cols)
        for i, (_, row) in enumerate(category_summary.iterrows()):
            col = cols[i % num_cols]
            cat, amount, pnl, cost = row["類型"], fmt_total(row["顯示現值"], display_currency), row["顯示損益"], row["顯示總成本"]
            cat_pnl_pct = (pnl / cost * 100) if cost > 0 else 0
            pnl_str, pnl_sign = fmt_total(abs(pnl), display_currency), "+" if pnl > 0 else "-" if pnl < 0 else ""
            pnl_color = "#ef4444" if pnl < 0 else "#4ade80" 
            safe_unit = unit.replace("$", "&#36;")
            
            amount_display, pnl_val_display = mask_val(f"{safe_unit} {amount}"), mask_val(f"{safe_unit} {pnl_str}")
            pnl_display = f"<div style='font-size:16px; font-weight:600; color:{pnl_color}; margin-top:4px;'>({pnl_sign}{pnl_val_display} ｜ {pnl_sign}{abs(cat_pnl_pct):.1f}%)</div>" if cat != "現金" else "<div style='font-size:16px; margin-top:4px; visibility:hidden;'>-</div>"

            col.markdown(f"<div style='padding: 5px 0 15px 0;'><div style='font-size:18px; font-weight:600; color:#e2e8f0'>{cat}：{amount_display}</div>{pnl_display}</div>", unsafe_allow_html=True)

    is_category_view = st.session_state.selected_category is not None
    if is_category_view:
        view_df = df[df["類型"] == st.session_state.selected_category].copy()
        cat_total_val = fmt_total(view_df['顯示現值'].sum(), display_currency)
        st.markdown(f"目前顯示：**{st.session_state.selected_category}** 分類總額 {mask_val(f'{unit.replace('$', '&#36;')} {cat_total_val}')}", unsafe_allow_html=True)
    else:
        view_df = df.groupby("類型", as_index=False)["顯示現值"].sum().rename(columns={"類型": "名稱"})

    if not view_df.empty:
        all_labels = view_df["名稱"].tolist()
        if not st.session_state.visible_items or not st.session_state.visible_items.intersection(set(all_labels)): st.session_state.visible_items = set(all_labels)

        view_total = view_df["顯示現值"].sum()
        colors = ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52"]

        st.markdown("**圖例**（點擊可顯示/隱藏）")
        n_cols = 7
        view_df_sorted = view_df.sort_values("顯示現值", ascending=False).reset_index(drop=True)
        items = list(view_df_sorted.iterrows())
        
        for i in range(0, len(items), n_cols):
            cols = st.columns(n_cols)
            for j, (idx, row) in enumerate(items[i:i+n_cols]):
                lab, val = row["名稱"], row["顯示現值"]
                pct = (val / view_total * 100) if view_total > 0 else 0
                color = colors[list(view_df["名稱"]).index(lab) % len(colors)]
                is_visible = lab in st.session_state.visible_items
                
                with cols[j]:
                    label_text = f"{lab} | {pct:.1f}%" if is_visible else f"~~{lab}~~"
                    st.markdown(f"<div style='width:100%; height:6px; background-color:{color}; border-radius:4px; margin-bottom:-14px; position:relative; z-index:1;'></div>", unsafe_allow_html=True)
                    if st.button(label_text, key=f"leg_all_{lab}", use_container_width=True):
                        st.session_state.visible_items.discard(lab) if is_visible else st.session_state.visible_items.add(lab)
                        st.rerun()

        plot_df = view_df[view_df["名稱"].isin(st.session_state.visible_items)].copy().sort_values(by="顯示現值", ascending=False).reset_index(drop=True)
        col_pie, col_nav = st.columns([0.88, 0.12])
        
        with col_pie:
            try:
                with st.popover("⚙️ 圖表設定"):
                    threshold = st.slider("合併佔比小於多少為「其他」？", 0.0, 5.0, 1.0, 0.5, "%.1f%%")
            except AttributeError:
                threshold = st.slider("合併佔比小於多少為「其他」？", 0.0, 5.0, 1.0, 0.5, "%.1f%%")

            if plot_df.empty: st.info("請至少選擇一個項目")
            else:
                plot_total = plot_df["顯示現值"].sum()
                if threshold > 0 and plot_total > 0:
                    mask = (plot_df["顯示現值"] / plot_total * 100) < threshold
                    small_df, large_df = plot_df[mask], plot_df[~mask]
                    if not small_df.empty:
                        plot_df = pd.concat([large_df, pd.DataFrame([{"名稱": f"其他小部位 ({len(small_df)} 檔)", "顯示現值": small_df["顯示現值"].sum()}])], ignore_index=True)
                
                labels, values = plot_df["名稱"].tolist(), plot_df["顯示現值"].tolist()
                bar_pie_colors = ["#808080" if lab.startswith("其他小部位") else colors[list(view_df["名稱"]).index(lab) % len(colors)] for lab in labels]
                
                pie_text_labels, bar_text_labels = [], []
                for lab, val in zip(labels, values):
                    pct_in_view, pct_of_total = (val / plot_total * 100) if plot_total > 0 else 0, (val / total_value * 100) if total_value > 0 else 0
                    bar_text_labels.append(f"<b>{pct_in_view:.1f}%<br>({pct_of_total:.1f}%)</b>" if is_category_view else f"<b>{pct_in_view:.1f}%</b>")
                    pie_text_labels.append(f"<b>{lab}</b><br>{pct_in_view:.1f}%<br>({pct_of_total:.1f}%)" if pct_in_view >= 1.0 and is_category_view else f"<b>{lab}</b><br>{pct_in_view:.1f}%" if pct_in_view >= 1.0 else "")
                
                if len(labels) > 10:
                    bar_font_size = 24 if len(labels) <= 12 else 20 if len(labels) <= 15 else 16 if len(labels) <= 20 else 14 if len(labels) <= 30 else 12
                    fig = go.Figure(data=[go.Bar(
                        x=labels, y=values, text=bar_text_labels, textposition="outside", textfont=dict(size=bar_font_size, color="#e2e8f0"), marker_color=bar_pie_colors,
                        hovertemplate="%{x}<br>%{text}<extra></extra>" if privacy else "%{x}<br>%{text}<br>%{y:,.2f}<extra></extra>"
                    )])
                    fig.update_layout(
                        margin=dict(t=40, b=40, l=40, r=40), height=650, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(showgrid=False, tickfont=dict(size=16, color="#e2e8f0")), yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not privacy)
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    fig = go.Figure(data=[go.Pie(
                        labels=labels, values=values, pull=[0.03]*len(labels), text=pie_text_labels, textinfo="text", textposition="auto",
                        insidetextfont=dict(size=22, color="#ffffff"), outsidetextfont=dict(size=16, color="#e2e8f0"), 
                        hovertemplate="%{label}<br>%{percent}<extra></extra>" if privacy else "%{label}<br>%{percent}<br>%{value:,.2f}<extra></extra>",
                        marker=dict(colors=bar_pie_colors, line=dict(color="#111111", width=1.5)), sort=False, direction="clockwise"
                    )])
                    fig.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=750, showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    fig.update_traces(domain=dict(x=[0.15, 0.85], y=[0.15, 0.85]))
                    st.plotly_chart(fig, use_container_width=True)

        with col_nav:
            st.markdown("<div style='margin-top: 60px;'></div>", unsafe_allow_html=True)
            st.caption("切換分類檢視：")
            for cat in ["全部"] + order_list:
                if st.button(cat, use_container_width=True, key=f"nav_cat_{cat}", type="primary" if ((cat == st.session_state.selected_category) or (cat == "全部" and st.session_state.selected_category is None)) else "secondary"):
                    st.session_state.selected_category = None if cat == "全部" else cat
                    st.session_state.visible_items = set()
                    st.rerun()

    st.divider()
    st.subheader(f"📈 {'全部淨資產' if st.session_state.selected_category is None else st.session_state.selected_category} 變化趨勢")
    
    history_data = st.session_state.history_snapshots
    if len(history_data) > 0:
        processed_history = []
        for d_str, data_val in history_data.items():
            if isinstance(data_val, dict) and data_val.get("version") == "v2":
                d_data = data_val.get(display_currency, data_val.get("TWD"))
                val = d_data.get("value", 0)
                cost = d_data.get("cost", 0)
                liability = d_data.get("liability", 0.0)
                cats = d_data.get("categories", {})
                v = val - liability if st.session_state.selected_category is None else cats.get(st.session_state.selected_category, {}).get("value", 0)
                c = cost - liability if st.session_state.selected_category is None else cats.get(st.session_state.selected_category, {}).get("cost", 0)
            else:
                val = data_val.get("value", 0) if isinstance(data_val, dict) else data_val
                cost = data_val.get("cost", 0) if isinstance(data_val, dict) else data_val
                liability = data_val.get("liability", 0.0) if isinstance(data_val, dict) else 0.0
                cats = data_val.get("categories", {}) if isinstance(data_val, dict) else {}
                twd_v = val - liability if st.session_state.selected_category is None else cats.get(st.session_state.selected_category, {}).get("value", 0)
                twd_c = cost - liability if st.session_state.selected_category is None else cats.get(st.session_state.selected_category, {}).get("cost", 0)
                div = 1 if display_currency == "TWD" else usd_twd if display_currency == "USD" else (btc_usd * usd_twd if btc_usd else 1)
                v, c = twd_v / div, twd_c / div

            processed_history.append({'Date': d_str, 'Value': v, 'Cost': c})

        hist_df = pd.DataFrame(processed_history)
        hist_df['Date'] = pd.to_datetime(hist_df['Date'])
        hist_df = hist_df.sort_values('Date')

        time_range = st.radio("選擇時間區間", ["1個月", "3個月", "半年", "1年", "全部"], horizontal=True, label_visibility="collapsed", key="trend_time_range")
        today_dt = pd.to_datetime(date.today())
        start_date = today_dt - pd.DateOffset(months=1) if time_range == "1個月" else today_dt - pd.DateOffset(months=3) if time_range == "3個月" else today_dt - pd.DateOffset(months=6) if time_range == "半年" else today_dt - pd.DateOffset(years=1) if time_range == "1年" else hist_df['Date'].min() - pd.Timedelta(days=3)
        end_date = today_dt + pd.Timedelta(days=1)

        filtered_df = hist_df[hist_df['Date'] >= start_date]
        if not filtered_df.empty:
            fig_line = go.Figure()
            hover_temp = "%{x|%Y-%m-%d}<br>＊＊＊＊<extra></extra>" if privacy else "%{x|%Y-%m-%d}<br>" + unit.replace("$", "&#36;") + " %{y:,.0f}<extra></extra>"
            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['Value'], mode='lines+markers', name='淨額' if st.session_state.selected_category is not None else '淨資產', line=dict(color='#00CC96', width=3, shape='linear'), marker=dict(size=6, color='#00CC96'), fill='tozeroy', fillcolor='rgba(0, 204, 150, 0.1)', hovertemplate=hover_temp))
            fig_line.add_trace(go.Scatter(x=filtered_df['Date'], y=filtered_df['Cost'], mode='lines+markers', name='成本', line=dict(color='#3b82f6', width=3, shape='linear'), marker=dict(size=6, color='#3b82f6'), hovertemplate=hover_temp))
            fig_line.update_layout(margin=dict(t=20, b=20, l=10, r=10), height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(range=[start_date, end_date], showgrid=False, tickfont=dict(color="#e2e8f0"), tickformat="%Y-%m-%d", type="date"), yaxis=dict(showgrid=True, gridcolor="#333333", tickfont=dict(color="#e2e8f0"), zeroline=False, showticklabels=not privacy, autorange=True), hovermode="x unified", dragmode="pan")
            st.plotly_chart(fig_line, use_container_width=True, config={'scrollZoom': True})
        else: st.info("所選時間區間內尚無歷史快照資料。")
    else: st.info("尚無足夠的歷史快照資料以繪製圖表。")

    st.divider()
    st.subheader("持倉明細" + (f"（{st.session_state.selected_category}）" if is_category_view else "（全部）"))
    with st.expander("點此展開 / 收合明細表", expanded=False):
        if st.session_state.selected_category == "現金": render_cash_manager()
        detail_df = df[df["類型"] == st.session_state.selected_category] if is_category_view else df
        show_df = pd.DataFrame({
            "名稱": detail_df["名稱"], "代號": detail_df["代號"], "類型": detail_df["類型"], "幣別": detail_df["幣別"], "數量": detail_df["數量"],
            "平均成本": detail_df.apply(lambda r: None if r.get("is_cash") else r["平均成本"], axis=1),
            "現價": detail_df.apply(lambda r: None if r.get("is_cash") else r["現價"], axis=1),
            "現值": detail_df["現值"], "未實現損益": detail_df.apply(lambda r: None if r.get("is_cash") else r["未實現損益"], axis=1)
        })

        if privacy:
            privacy_df = show_df.copy()
            privacy_df[["數量", "平均成本", "現價", "現值", "未實現損益"]] = "＊＊＊＊"
            st.dataframe(privacy_df, use_container_width=True, hide_index=True)
        else:
            st.dataframe(show_df, use_container_width=True, hide_index=True, column_config={
                "數量": st.column_config.NumberColumn("數量", format="%.4f"), "平均成本": st.column_config.NumberColumn("平均成本", format="%.4f"),
                "現價": st.column_config.NumberColumn("現價", format="%.4f"), "現值": st.column_config.NumberColumn("現值", format="%.2f"), "未實現損益": st.column_config.NumberColumn("未實現損益", format="%.2f")
            })

        if st.session_state.selected_category != "現金":
            st.markdown("##### 手動設定現價")
            with st.expander("點此展開手動設定現價"):
                no_price_rows = detail_df[detail_df["現價"].isna() & ~detail_df["is_cash"]]
                if no_price_rows.empty: st.caption("目前所有標的都有價格")
                else:
                    for _, row in no_price_rows.iterrows():
                        key = row["代號"] or row["名稱"]
                        c1, c2, c3 = st.columns([3, 2, 1])
                        with c1: st.write(f"**{row['名稱']}**（{row['代號']}）")
                        with c2: new_p = st.text_input("現價", key=f"mp_{key}", placeholder="輸入市價")
                        with c3:
                            if st.button("儲存", key=f"save_mp_{key}"):
                                val = safe_float(new_p)
                                if val and val > 0:
                                    st.session_state.manual_prices[key] = val
                                    save_data("manual_prices", st.session_state.manual_prices)
                                    st.success("已儲存")
                                    fetch_all_prices.clear()
                                    st.rerun()
                                else: st.warning("請輸入有效數字")

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
        with f_c3: action_filter = st.selectbox("篩選動作", ["全部", "買進", "賣出"])

        if isinstance(date_range, tuple):
            if len(date_range) == 2: tx_df = tx_df[(tx_df["date_obj"] >= date_range[0]) & (tx_df["date_obj"] <= date_range[1])]
            elif len(date_range) == 1: tx_df = tx_df[tx_df["date_obj"] == date_range[0]]
        if selected_target != "全部": tx_df = tx_df[tx_df["target_label"] == selected_target]
        if action_filter != "全部": tx_df = tx_df[tx_df["type"] == action_filter]
        st.caption(f"共找到 {len(tx_df)} 筆紀錄")

        def render_tx_rows(df_to_render):
            for i, row in df_to_render.iterrows():
                if st.session_state.editing_id == row["id"]:
                    c1, c2, c3, c4, c5, c6 = st.columns([1.2, 0.8, 2.0, 1.8, 0.7, 1.3])
                    with c1: new_date = st.date_input("日期", value=date.fromisoformat(row["date"]), key=f"ed_d_{row['id']}", label_visibility="collapsed")
                    with c2: new_type = st.selectbox("動作", ["買進", "賣出"], index=0 if row["type"]=="買進" else 1, key=f"ed_t_{row['id']}", label_visibility="collapsed")
                    with c3:
                        cc1, cc2 = st.columns([1.5, 1])
                        new_name = cc1.text_input("名稱", value=row["name"], key=f"ed_n_{row['id']}", label_visibility="collapsed")
                        new_ticker = cc2.text_input("代號", value=row["ticker"], key=f"ed_tk_{row['id']}", label_visibility="collapsed")
                    with c4:
                        cc1, cc2 = st.columns(2)
                        new_qty = cc1.text_input("數量", value=str(row["quantity"]), key=f"ed_q_{row['id']}", label_visibility="collapsed")
                        new_price = cc2.text_input("價格", value=str(row["price"]), key=f"ed_p_{row['id']}", label_visibility="collapsed")
                    with c5: new_curr = st.selectbox("幣別", ["TWD", "USD"], index=0 if row["currency"]=="TWD" else 1, key=f"ed_c_{row['id']}", label_visibility="collapsed")
                    with c6:
                        b1, b2 = st.columns([0.9, 0.9])
                        if b1.button("儲存", key=f"save_tx_{row['id']}", type="primary", use_container_width=True):
                            for idx, t in enumerate(st.session_state.transactions):
                                if t["id"] == row["id"]:
                                    st.session_state.transactions[idx].update({"date": new_date.strftime("%Y-%m-%d"), "type": new_type, "name": new_name.strip(), "ticker": new_ticker.strip().upper(), "quantity": safe_float(new_qty) or row["quantity"], "price": safe_float(new_price) or row["price"], "currency": new_curr})
                                    break
                            save_data("transactions", st.session_state.transactions)
                            st.session_state.editing_id = None
                            fetch_all_prices.clear()
                            st.rerun()
                        if b2.button("取消", key=f"cancel_tx_{row['id']}", use_container_width=True):
                            st.session_state.editing_id = None
                            st.rerun()
                else:
                    c1, c2, c3, c4, c5, c6 = st.columns([1.0, 0.55, 1.6, 1.5, 0.55, 1.3])
                    qty_display, price_display = ("＊＊＊＊", "＊＊＊＊") if privacy else (fmt(row['quantity']), fmt(row['price']))
                    with c1: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{row['date']}</div>", unsafe_allow_html=True)
                    with c2: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{row['type']}</div>", unsafe_allow_html=True)
                    with c3: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{row['name']}（{row['ticker']}）</div>", unsafe_allow_html=True)
                    with c4: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{qty_display} × {price_display}</div>", unsafe_allow_html=True)
                    with c5: st.markdown(f"<div style='text-align:center; line-height:1.2; margin-top:8px;'>{row['currency']}</div>", unsafe_allow_html=True)
                    with c6:
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
            h1, h2, h3, h4, h5, h6 = st.columns([1.0, 0.55, 1.6, 1.5, 0.55, 1.3])
            h1.markdown("<div style='text-align:center'><b>日期</b></div>", unsafe_allow_html=True)
            h2.markdown("<div style='text-align:center'><b>動作</b></div>", unsafe_allow_html=True)
            h3.markdown("<div style='text-align:center'><b>標的</b></div>", unsafe_allow_html=True)
            h4.markdown("<div style='text-align:center'><b>明細</b></div>", unsafe_allow_html=True)
            h5.markdown("<div style='text-align:center'><b>幣別</b></div>", unsafe_allow_html=True)
            h6.markdown("")
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

import streamlit as st
import pandas as pd
import json
import os
import requests
import warnings
from datetime import datetime, timedelta
import matplotlib
matplotlib.use("Agg") 
import matplotlib.pyplot as plt
import mplfinance as mpf
import uuid
import time

# -------------------------------------------------------------
# ตั้งค่าตัวแปรระบบสมาชิกและลิงก์สำคัญ
# -------------------------------------------------------------
LICENSE_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRjK8ZbtJAI2pqPN1t2NRHmA7gRgleOD8Hz7ZuwvRn-AHCWpW5k1eQfgsV5HdlOyE4CLhlZrsdhK5tB/pub?gid=1340805245&single=true&output=csv"
TRIAL_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbwabFE1GkGnPfIZQzTEnEHvm9Io4Dd5zWJbO-ykNf3EKS20fQjAu0rGn7nqNsJYaI1n_g/exec"
PAYMENT_URL = "https://forms.gle/GbkLPB2SwNVpKN9aA"

# -------------------------------------------------------------
# ตั้งค่าหน้าเว็บ Streamlit
# -------------------------------------------------------------
st.set_page_config(
    page_title="F4 Price & Candle Analytics",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

warnings.filterwarnings("ignore")
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'sans-serif']
plt.rcParams["axes.unicode_minus"] = False

my_style = mpf.make_mpf_style(
    base_mpf_style="yahoo",
    rc={
        "axes.unicode_minus": False,
        "figure.titlesize": 18,
        "axes.titlesize": 14,
    },
)

MASTER_INDEX_URL = "https://docs.google.com/spreadsheets/d/18AANzcT-apOZV40pEoFS1ngvnZ3H4Flx2CpUsycN-UI/export?format=csv"
FALLBACK_URLS = {
    'm1': ['https://docs.google.com/spreadsheets/d/1a0rsD1-QSkZahcl9ygg7T5bm7JD7XE_weoBI0IPfuR0/export?format=csv'],
    'w1': ['https://docs.google.com/spreadsheets/d/1jOhRGKJv6WzJToQ2AAHmla11ceCCMrMethO95KGxOnI/export?format=csv'],
    'd1': ['https://docs.google.com/spreadsheets/d/1_tc8ZtUD2JDdtZVUndcsDKbOq2AaXkxi4dnXFFOIkSo/export?format=csv'],
    'h4': ['https://docs.google.com/spreadsheets/d/1JdLhSEgyUFczkFMKlbNZlwzT-ikrYPfqFpFtsZY3MlU/export?format=csv'],
    'h1': [
        'https://docs.google.com/spreadsheets/d/1AOYN_r4K1oEqZaAOa6GR50h2gJaiwaG9UMjUXmiLj3o/export?format=csv',
        'https://docs.google.com/spreadsheets/d/1TENmP_USrHihqxb2nc_7iH0vs7vCQgXmGdLEsXEENyo/export?format=csv'
    ],
    'm30': [
        'https://docs.google.com/spreadsheets/d/18Cq9FT16EMEfrNk6XcmeHChmaD9TxYMcEY6nZ2OX6O0/export?format=csv',
        'https://docs.google.com/spreadsheets/d/1IEawPRjYnK8amoA3PWGxh5TRRqb2cYnnyRupBMsHy-s/export?format=csv'
    ],
    'm15': [
        'https://docs.google.com/spreadsheets/d/1u83zkeBNaao5rHIeynzxDnO-62GyVaw-SnY3rbADxCE/export?format=csv',
        'https://docs.google.com/spreadsheets/d/1ZH3J6dJ6q8Vo1Bu52Dk4rLTGO4YHcVv_oty_AJWxU6E/export?format=csv',
        'https://docs.google.com/spreadsheets/d/1gj00ORAlz5IxHixwCXb2rOUIlcnKFQN9fVLgohDiXbA/export?format=csv'
    ]
}

TIMEFRAME_MAP = {"h4": "h4", "h1": "h1", "m30": "m30", "m15": "m15", "d1": "d1", "w1": "w1", "m1": "m1"}
TIMEFRAME1_MAP = ["ไส้", "ไส้บน", "ไส้ล่าง", "เนื้อ"]

# -------------------------------------------------------------
# 1. ฟังก์ชันโหลดฐานข้อมูล (ทำความสะอาดชื่อคอลัมน์อัตโนมัติ)
# -------------------------------------------------------------
@st.cache_data(ttl=5)
def get_code_database():
    try:
        separator = "&" if "?" in LICENSE_CSV_URL else "?"
        url = f"{LICENSE_CSV_URL}{separator}t={time.time()}"
        
        df = pd.read_csv(url)
        # แปลงชื่อคอลัมน์ทั้งหมดให้เป็นตัวพิมพ์เล็กและตัดช่องว่าง
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # ค้นหาคอลัมน์ key หรือ access_code
        key_col = 'key' if 'key' in df.columns else ('access_code' if 'access_code' in df.columns else None)
        if key_col and 'status' in df.columns:
            df['key'] = df[key_col].astype(str).str.strip()
            df['status'] = df['status'].astype(str).str.strip().str.lower()
            if 'device_id' in df.columns:
                df['device_id'] = df['device_id'].astype(str).str.strip()
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# -------------------------------------------------------------
# 2. ระบบจัดการ Device ID ถาวรผ่าน Query Params
# -------------------------------------------------------------
query_params = st.query_params
if "did" not in query_params or not query_params["did"]:
    persistent_device_id = str(uuid.uuid4())
    st.query_params["did"] = persistent_device_id
else:
    persistent_device_id = query_params["did"]

st.session_state["device_id"] = persistent_device_id

if "user_code" not in st.session_state:
    st.session_state["user_code"] = None

# -------------------------------------------------------------
# 3. [สำคัญ] ตรวจสอบอัตโนมัติทันทีที่เปิดเว็บ/รีเฟรช (Auto-Login ด้วย Device ID)
# -------------------------------------------------------------
if not st.session_state["user_code"]:
    df_codes = get_code_database()
    if not df_codes.empty and 'device_id' in df_codes.columns:
        matched_row = df_codes[df_codes['device_id'] == str(st.session_state["device_id"])]
        if not matched_row.empty:
            found_key = matched_row['key'].values[0]
            found_status = matched_row['status'].values[0]
            if found_status in ['active', 'trial']:
                # พบรหัสเดิมของเครื่องนี้ในระบบแล้ว ดึงเข้าสู่ระบบให้อัตโนมัติทันที!
                st.session_state["user_code"] = found_key
                st.rerun()

# ตรวจสอบสิทธิ์ปัจจุบัน
is_active_member = False
member_status = ""
if st.session_state["user_code"]:
    df_codes = get_code_database()
    if not df_codes.empty:
        code_row = df_codes[df_codes['key'] == st.session_state["user_code"]]
        if not code_row.empty:
            member_status = code_row['status'].values[0]
            if member_status in ['active', 'trial']:
                is_active_member = True

# -------------------------------------------------------------
# 4. หน้าจอบล็อก (แสดงเฉพาะคนยังไม่มีสิทธิ์หรือยังไม่เคยลงทะเบียน)
# -------------------------------------------------------------
if not is_active_member:
    st.title("🔐 กรุณากรอก Access Code เพื่อเข้าใช้งาน")
    st.warning("ระบบนี้จำกัดการใช้งานเฉพาะผู้ที่มี Access Code ที่ถูกต้องเท่านั้น สามารถทดลองใช้ฟรี 3 วัน หรือติดต่อชำระค่าบริการได้จากด้านล่างนี้ครับ")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🎁 ขอรับสิทธิ์ทดลองใช้ฟรี 3 วัน")
        st.write("ระบบจะสร้างรหัส Trial อัตโนมัติและผูกกับเครื่องของคุณทันที")
        
        if st.button("🚀 กดเพื่อรับสิทธิ์ทดลองฟรี 3 วัน"):
            if TRIAL_WEBHOOK_URL:
                try:
                    expiry_days = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
                    payload = {
                        "action": "create_trial",
                        "device_id": st.session_state["device_id"],
                        "expiry": expiry_days
                    }
                    response = requests.post(TRIAL_WEBHOOK_URL, json=payload, timeout=20)
                    res_data = response.json()
                    
                    if res_data.get("status") == "success":
                        new_key = res_data.get("key")
                        st.session_state["user_code"] = new_key
                        st.success(f"🎉 สร้างรหัสสำเร็จ: {new_key} กำลังเข้าสู่ระบบ...")
                        st.rerun()
                    else:
                        error_msg = res_data.get('message', 'เกิดข้อผิดพลาด')
                        # ถ้า Webhook แจ้งว่าเคยรับสิทธิ์แล้ว ให้เคลียร์แคชแล้วดึงรหัสเดิมจาก CSV มาเข้าแอปทันที
                        if "เคยรับสิทธิ์" in error_msg:
                            st.info("🔄 ตรวจพบข้อมูลในระบบ กำลังดึงรหัสเดิมเข้าสู่ระบบ...")
                            time.sleep(1.5)  # รอให้ชีทบันทึกเสร็จสักครู่
                            get_code_database.clear()
                            df_latest = get_code_database()
                            
                            if not df_latest.empty and 'device_id' in df_latest.columns:
                                df_latest['device_id'] = df_latest['device_id'].astype(str).str.strip()
                                match_row = df_latest[df_latest['device_id'] == str(st.session_state["device_id"])]
                                if not match_row.empty:
                                    saved_key = match_row['key'].values[0]
                                    st.session_state["user_code"] = saved_key
                                    st.success(f"🎉 ดึงรหัสเดิมสำเร็จ: {saved_key} กำลังเข้าสู่ระบบ...")
                                    time.sleep(1)
                                    st.rerun()
                                    
                        st.error(f"❌ {error_msg}")
                except Exception as e:
                    st.error(f"❌ ไม่สามารถเชื่อมต่อกับ Webhook ได้: {e}")
            else:
                st.warning("ยังไม่ได้กำหนดค่า TRIAL_WEBHOOK_URL")
        
        st.markdown("---")
        st.link_button("💳 ชำระค่าบริการ / ติดต่อรับรหัสถาวร", PAYMENT_URL, use_container_width=True)
            
    with col2:
        st.subheader("🔑 มี Access Code อยู่แล้ว?")
        with st.form("code_login_form"):
            input_code = st.text_input("กรอก Access Code ของคุณ:", type="default").strip()
            submit_btn = st.form_submit_button("🚀 ยืนยันรหัสเข้าใช้งาน")
            
            if submit_btn:
                df_codes = get_code_database()
                if not df_codes.empty and input_code in df_codes['key'].values:
                    status_val = df_codes.loc[df_codes['key'] == input_code, 'status'].values[0]
                    if status_val in ['active', 'trial']:
                        st.session_state["user_code"] = input_code
                        st.success("รหัสถูกต้อง! กำลังเข้าสู่ระบบ...")
                        st.rerun()
                    else:
                        st.error("❌ รหัสนี้ถูกระงับการใช้งานหรือหมดอายุแล้ว (Status: {})".format(status_val))
                else:
                    st.error("❌ รหัส Access Code ไม่ถูกต้อง")
    st.stop()

# -------------------------------------------------------------
# ฟังก์ชันหลักและระบบจัดการคอลัมน์ (รองรับทั้งไทยและอังกฤษ)
# -------------------------------------------------------------

# -------------------------------------------------------------
# ฟังก์ชันตรวจสอบชื่อวันจากวันที่
# -------------------------------------------------------------
def หาวันจากวันที่(cc='2013.05.23'):
    # รองรับการส่งค่ามาทั้งแบบ '2013.05.23' และ '2013-05-23'
    date_str = str(cc).strip().replace('.', '-')
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_name = dt.strftime("%A")  # ได้ชื่อวัน เช่น Thursday
        return day_name
    except ValueError:
        st.error("รูปแบบวันที่ไม่ถูกต้อง กรุณาใช้ YYYY.MM.DD หรือ YYYY-MM-DD")
        return None

# -------------------------------------------------------------
# ฟังก์ชันดึงข้อมูล (Cached เพื่อความเร็ว)
# -------------------------------------------------------------
def get_urls_by_tf(tf_column_name: str) -> list:
    try:
        df_master = pd.read_csv(MASTER_INDEX_URL)
        df_master.columns = [str(c).strip().lower() for c in df_master.columns]
        target_col = tf_column_name.strip().lower()
        if target_col in df_master.columns:
            raw_urls = df_master[target_col].dropna().tolist()
            clean_urls = []
            for url in raw_urls:
                url = str(url).strip()
                if not url: continue
                if '/export?format=csv' not in url:
                    if '/edit' in url:
                        url = url.split('/edit')[0] + '/export?format=csv'
                    else:
                        url = url.rstrip('/') + '/export?format=csv'
                clean_urls.append(url)
            return clean_urls
    except Exception:
        pass
    return []

@st.cache_data(ttl=600)
def get_tf_data(tf_key: str) -> pd.DataFrame:
    tf_key = tf_key.lower().strip()
    include_day_time = tf_key in ['h4', 'h1', 'm30', 'm15']
    urls = get_urls_by_tf(f'tf_{tf_key}')
    if not urls:
        urls = FALLBACK_URLS.get(tf_key, [])
    valid_dfs = []
    for url in urls:
        try:
            df = pd.read_csv(url)
            if df is not None and not df.empty and 'วันที่' in df.columns:
                valid_dfs.append(df)
        except:
            continue
    if valid_dfs:
        df_concat = pd.concat(valid_dfs, ignore_index=True)
        def clean_time(val):
            if pd.isna(val) or val is None or str(val).strip() == '': return "00:00"
            s = str(val).strip()
            if ":" in s:
                parts = s.split(":")
                return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
            elif "." in s:
                parts = s.split(".")
                return f"{int(parts[0]):02d}:{int(parts[1].ljust(2, '0')[:2]):02d}"
            else:
                try: return f"{int(s):02d}:00"
                except: return "00:00"
        
        if 'วันที่' in df_concat.columns:
            d_str = pd.to_datetime(df_concat['วันที่'], errors='coerce').dt.strftime('%Y-%m-%d')
            t_str = df_concat['เวลา'].apply(clean_time) if ('เวลา' in df_concat.columns and include_day_time) else "00:00"
            df_concat['_full_dt'] = pd.to_datetime(d_str + " " + t_str, errors='coerce')
            df_concat = df_concat.sort_values('_full_dt', ascending=True).reset_index(drop=True)
            df_concat.drop(columns=['_full_dt'], inplace=True, errors='ignore')
        
        df_concat['ดัชนี'] = df_concat.index
        target_cols = ['วันที่', 'วัน', 'เวลา', 'ไส้', 'ทิศ', 'rsi', 'ไส้บน', 'ไส้ล่าง', 'เนื้อ', 'open', 'high', 'low', 'close', 'ดัชนี']
        available_cols = [col for col in target_cols if col in df_concat.columns]
        return df_concat.loc[:, available_cols]
    return pd.DataFrame()

def parse_time_to_hhmm(val):
    if pd.isna(val) or val is None or str(val).strip() == "": return "00:00"
    s_val = str(val).strip()
    if ":" in s_val:
        p = s_val.split(":")
        return f"{int(p[0]):02d}:{int(p[1]):02d}"
    elif "." in s_val:
        p = s_val.split(".")
        return f"{int(p[0]):02d}:{int(p[1].ljust(2, '0')[:2]):02d}"
    else:
        try: return f"{int(s_val):02d}:00"
        except: return "00:00"

# -------------------------------------------------------------
# Sidebar: เมนูรับค่าพารามิเตอร์
# -------------------------------------------------------------
st.sidebar.success(f"⭐ สถานะ: สมาชิก ({member_status.upper()})\n(รหัส: {st.session_state['user_code']})")
if st.sidebar.button("🚪 ออกจากระบบ"):
    st.session_state["user_code"] = None
    st.rerun()
    
st.sidebar.title("⚙️ ตั้งค่าการค้นหา")
selected_tf = st.sidebar.selectbox("Timeframe", list(TIMEFRAME_MAP.keys()), index=3) # เริ่มต้นที่ h4

with st.sidebar.expander("🔍 ค้นหาราคา (Price)"):
    x_val = st.text_input("ราคาที่ต้องการ (x)", "4077.73")
    tol_val = st.text_input("ช่วงบวกลบ (± tolerance)", "0.0")
    search_price_btn = st.button("ค้นหาราคา")

with st.sidebar.expander("📏 ค้นหาขนาดแท่งเทียน (Size)"):
    tf1_val = st.selectbox("ส่วนแท่งเทียน", TIMEFRAME1_MAP)
    ca_val = st.text_input("ขนาดเริ่มต้น (Start)", "0")
    cb_val = st.text_input("ขนาดสิ้นสุด (End)", "10")
    search_size_btn = st.button("ค้นหาขนาด")

with st.sidebar.expander("📅 ค้นหาตามวันที่ & กราฟ"):
    date_val = st.text_input("ระบุวันที่ (YYYY.MM.DD หรือ YYYY-MM-DD)", "2013.05.23")
    start_time_val = st.text_input("เวลาเริ่มต้น", "04:00")
    end_time_val = st.text_input("เวลาสิ้นสุด", "20:00")
    search_date_btn = st.button("ค้นหารอบวันที่")
    plot_date_btn = st.button("📊 แสดงกราฟจากวันที่")

with st.sidebar.expander("🗓️ ตรวจสอบชื่อวันจากวันที่"):
    check_day_val = st.text_input("ระบุวันที่ต้องการเช็ควัน", "2013.05.23")
    check_day_btn = st.button("🔍 เช็คชื่อวัน")

with st.sidebar.expander("📈 ค้นหาตามดัชนี (Index)"):
    bw_start_val = st.text_input("ดัชนีเริ่มต้น (หรือจุดศูนย์กลาง)", "50")
    bw_end_val = st.text_input("ดัชนีสิ้นสุด (ปล่อยว่างเพื่อดูย้อนหลัง/หน้า 10 แท่ง)", "")
    plot_idx_btn = st.button("📈 แสดงกราฟช่วงดัชนี")

# โหลดข้อมูลตาม Timeframe ที่เลือก
with st.spinner(f'กำลังโหลดข้อมูล Timeframe [{selected_tf}] กรุณารอสักครู่...'):
    df_data = get_tf_data(selected_tf)

# -------------------------------------------------------------
# หน้าจอหลัก (Main Content Area)
# -------------------------------------------------------------
st.title("⚡ F4 Price & Candle Analytics (Mobile Web)")
st.info(f"📌 กำลังใช้งานกรอบเวลา: **{selected_tf.upper()}** (พบข้อมูลทั้งหมด {len(df_data)} แถว)")

# พื้นที่แสดงผลลัพธ์
results_container = st.container()

with results_container:
    # 1. ค้นหาราคา
    if search_price_btn:
        st.subheader(f"ผลการค้นหาราคา: {x_val} (±{tol_val}) [{selected_tf}]")
        try:
            target_p = float(x_val)
            tol = float(tol_val)
            price_cols = [c for c in ['open', 'high', 'low', 'close'] if c in df_data.columns]
            for c in price_cols: df_data[c] = pd.to_numeric(df_data[c], errors='coerce')
            
            if tol == 0:
                cond = df_data[price_cols].isin([target_p]).any(axis=1)
            else:
                cond = df_data[price_cols].apply(lambda col: col.between(target_p - tol, target_p + tol)).any(axis=1)
            res = df_data[cond]
            if not res.empty:
                st.success(f"พบข้อมูลทั้งหมด {len(res)} รายการ")
                st.dataframe(res, use_container_width=True)
            else:
                st.warning("ไม่พบข้อมูลราคาตามเงื่อนไข")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")

    # 2. ค้นหาขนาดแท่งเทียน
    elif search_size_btn:
        st.subheader(f"ผลการค้นหาขนาด {tf1_val} ช่วง {ca_val} ถึง {cb_val} [{selected_tf}]")
        try:
            ca = float(ca_val)
            cb = float(cb_val)
            if tf1_val in df_data.columns:
                df_data[tf1_val] = pd.to_numeric(df_data[tf1_val], errors='coerce')
                res = df_data[(df_data[tf1_val] >= ca) & (df_data[tf1_val] <= cb)]
                st.success(f"พบข้อมูลทั้งหมด {len(res)} รายการ")
                st.dataframe(res, use_container_width=True)
            else:
                st.error(f"ไม่พบคอลัมน์ {tf1_val} ในข้อมูล")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")

    # 3. ค้นหารอบวันที่
    elif search_date_btn:
        st.subheader(f"ผลการค้นหาวันที่: {date_val} [{selected_tf}]")
        try:
            s_date = str(date_val).strip().replace('.', '-')
            df_dt = pd.to_datetime(df_data['วันที่'], errors='coerce').dt.strftime('%Y-%m-%d')
            res = df_data[df_dt == s_date]
            if not res.empty:
                st.success(f"พบข้อมูลทั้งหมด {len(res)} รายการ")
                st.dataframe(res, use_container_width=True)
            else:
                st.warning(f"ไม่พบข้อมูลวันที่ {date_val}")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")

    # 4. เช็คชื่อวันจากฟังก์ชันใหม่
    elif check_day_btn:
        st.subheader(f"🗓️ ผลการตรวจสอบชื่อวันสำหรับ: {check_day_val}")
        day_result = หาวันจากวันที่(check_day_val)
        if day_result:
            st.success(f"วันที่ **{check_day_val}** ตรงกับวัน: **{day_result}**")

    # 5. แสดงกราฟจากวันที่
    elif plot_date_btn:
        st.subheader(f"📊 กราฟแท่งเทียนจากวันที่: {date_val}")
        try:
            s_date = str(date_val).strip().replace('.', '-')
            df_dt = pd.to_datetime(df_data['วันที่'], errors='coerce').dt.strftime('%Y-%m-%d')
            acd1 = df_data[df_dt == s_date].copy()
            
            if acd1.empty:
                st.error(f"ไม่พบข้อมูลสำหรับวันที่ {date_val}")
            else:
                if 'เวลา' in acd1.columns and (start_time_val or end_time_val):
                    acd1['time_norm'] = acd1['เวลา'].apply(parse_time_to_hhmm)
                    if start_time_val: acd1 = acd1[acd1['time_norm'] >= parse_time_to_hhmm(start_time_val)]
                    if end_time_val: acd1 = acd1[acd1['time_norm'] <= parse_time_to_hhmm(end_time_val)]

                acd = acd1.copy()
                acd['time_fixed'] = acd['เวลา'].apply(parse_time_to_hhmm) if 'เวลา' in acd.columns else "00:00"
                acd['datetime'] = pd.to_datetime(acd['วันที่'].astype(str) + " " + acd['time_fixed'], errors='coerce')
                acd = acd.dropna(subset=['datetime']).sort_values('datetime').set_index('datetime')
                for p in ["open", "high", "low", "close"]:
                    if p in acd.columns: acd[p] = pd.to_numeric(acd[p], errors='coerce')

                fig, axlist = mpf.plot(acd, type="candle", style=my_style, figsize=(12, 6), returnfig=True, xrotation=20)
                st.pyplot(fig)
                st.write("📋 **ตารางรายละเอียดข้อมูลแท่งเทียนช่วงนี้:**")
                st.dataframe(acd1, use_container_width=True)
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการสร้างกราฟ: {e}")

    # 6. แสดงกราฟช่วงดัชนี
    elif plot_idx_btn:
        st.subheader(f"📈 กราฟแท่งเทียนช่วงดัชนี: {bw_start_val} ถึง {bw_end_val}")
        try:
            s_idx = int(bw_start_val)
            if bw_end_val.strip().isdigit():
                e_idx = int(bw_end_val)
                acd1 = df_data[(df_data['ดัชนี'] >= s_idx) & (df_data['ดัชนี'] <= e_idx)].copy()
            else:
                matched = df_data.index[df_data['ดัชนี'] == s_idx].tolist()
                if not matched:
                    st.error(f"ไม่พบดัชนี {s_idx}")
                    acd1 = pd.DataFrame()
                else:
                    pos = df_data.index.get_loc(matched[0])
                    acd1 = df_data.iloc[max(0, pos - 10):min(len(df_data), pos + 11)].copy()

            if not acd1.empty:
                acd = acd1.copy()
                acd['time_fixed'] = acd['เวลา'].apply(parse_time_to_hhmm) if 'เวลา' in acd.columns else "00:00"
                acd['datetime'] = pd.to_datetime(acd['วันที่'].astype(str) + " " + acd['time_fixed'], errors='coerce')
                acd = acd.dropna(subset=['datetime']).sort_values('datetime').set_index('datetime')
                for p in ["open", "high", "low", "close"]:
                    if p in acd.columns: acd[p] = pd.to_numeric(acd[p], errors='coerce')

                fig, axlist = mpf.plot(acd, type="candle", style=my_style, figsize=(12, 6), returnfig=True, xrotation=20)
                st.pyplot(fig)
                st.write("📋 **ตารางรายละเอียดข้อมูลแท่งเทียนช่วงนี้:**")
                st.dataframe(acd1, use_container_width=True)
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการสร้างกราฟ: {e}")

    else:
        st.markdown("""
        ### 👋 ยินดีต้อนรับสู่ระบบวิเคราะห์กราฟทองคำ F4 บนเว็บเบราว์เซอร์
        คุณสามารถกดเมนูการค้นหาทาง **แถบด้านข้างซ้าย (Sidebar)** เพื่อ:
        * 🔍 ค้นหาราคาพร้อมกำหนดค่า Tolerance
        * 📏 ค้นหาขนาดของแท่งเทียน (ไส้, เนื้อ, ไส้บน, ไส้ล่าง)
        * 📅 ค้นหารายงานข้อมูลและเช็คชื่อวันตามวันที่ต้องการ
        * 📊 และวาดกราฟแท่งเทียน (Candlestick Chart) พร้อมตารางข้อมูลที่รองรับหน้าจอมือถืออย่างสมบูรณ์แบบ
        """)
        st.dataframe(df_data.head(50), use_container_width=True)
        st.caption("แสดงข้อมูล 50 แถวแรกเป็นตัวอย่าง")
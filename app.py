"""
知識掏金盤 (Knowledge Gold Panning) - Phase 2
核心引擎 + Google Sheets 整合
"""

import streamlit as st
from google import genai
from PIL import Image
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from tenacity import retry, stop_after_attempt, wait_fixed
from datetime import datetime


# ============================================================
# 頁面配置
# ============================================================
st.set_page_config(
    page_title="知識掏金盤",
    page_icon="⛏️",
    layout="centered",
    initial_sidebar_state="collapsed"
)


# ============================================================
# Google Sheets 連線 (Cached)
# ============================================================
@st.cache_resource
def get_google_sheet_client():
    """建立並快取 Google Sheets 連線"""
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except (KeyError, FileNotFoundError):
        return None


def get_worksheet():
    """取得工作表"""
    client = get_google_sheet_client()
    if client is None:
        return None
    try:
        sheet_url = st.secrets["google_sheets"]["sheet_url"]
        spreadsheet = client.open_by_url(sheet_url)
        worksheet = spreadsheet.sheet1
        return worksheet
    except (KeyError, FileNotFoundError):
        return None
    except Exception:
        return None


# ============================================================
# 強健寫入函式 (with Retry)
# ============================================================
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def add_log(role: str, tag: str, content: str):
    """
    寫入對話紀錄至 Google Sheets
    - 自動重試 3 次，每次間隔 2 秒
    - 內容超過 50,000 字元自動截斷
    """
    worksheet = get_worksheet()
    if worksheet is None:
        raise Exception("無法連線至 Google Sheets")

    # 防呆：截斷過長內容
    max_length = 50000
    if len(content) > max_length:
        content = content[:max_length] + "...(truncated)"

    # 準備寫入資料
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [timestamp, role, tag, content]

    # 寫入至最後一行
    worksheet.append_row(row)


# ============================================================
# 讀取歷史紀錄
# ============================================================
def get_logs() -> pd.DataFrame:
    """讀取 Google Sheets 所有紀錄"""
    worksheet = get_worksheet()
    if worksheet is None:
        return pd.DataFrame(columns=["timestamp", "role", "tag", "content"])

    try:
        records = worksheet.get_all_records()
        if not records:
            return pd.DataFrame(columns=["timestamp", "role", "tag", "content"])
        return pd.DataFrame(records)
    except Exception:
        return pd.DataFrame(columns=["timestamp", "role", "tag", "content"])


# ============================================================
# 檢查 Sheets 連線狀態
# ============================================================
def check_sheets_connection() -> bool:
    """檢查 Google Sheets 是否已設定"""
    try:
        _ = st.secrets["gcp_service_account"]
        _ = st.secrets["google_sheets"]["sheet_url"]
        return True
    except (KeyError, FileNotFoundError):
        return False


# ============================================================
# Session State 初始化
# ============================================================
if "user_input" not in st.session_state:
    st.session_state.user_input = ""


# ============================================================
# 標題
# ============================================================
st.title("⛏️ 知識掏金盤")
st.caption("Knowledge Gold Panning - Phase 2")


# ============================================================
# 歷史紀錄區 (Phase 2)
# ============================================================
sheets_connected = check_sheets_connection()

if sheets_connected:
    with st.expander("📜 歷史紀錄 (Phase 2 Test)", expanded=False):
        try:
            logs_df = get_logs()
            if logs_df.empty:
                st.info("目前沒有歷史紀錄")
            else:
                st.dataframe(logs_df, use_container_width=True)
        except Exception as e:
            st.error(f"讀取歷史紀錄失敗: {str(e)}")
else:
    with st.expander("📜 歷史紀錄 (Phase 2 Test)", expanded=False):
        st.warning("Google Sheets 尚未設定。請在 .streamlit/secrets.toml 中設定 [gcp_service_account] 和 [google_sheets] sheet_url")


# ============================================================
# 系統設定區
# ============================================================
with st.expander("⚙️ 系統設定", expanded=False):
    # 模型選擇
    selected_model = st.selectbox(
        "選擇模型",
        options=["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-3-flash-preview", "gemini-3-pro-preview"],
        index=0,
        help="選擇要使用的 Gemini 模型"
    )

    # 顯示 SDK 版本
    st.text(f"Google Gen AI SDK 版本: {genai.__version__}")

    # 顯示 Sheets 連線狀態
    if sheets_connected:
        st.text("📊 Google Sheets: ✅ 已連線")
    else:
        st.text("📊 Google Sheets: ❌ 未設定")


# ============================================================
# 輸入區
# ============================================================
st.divider()

# 文字輸入 - 綁定到 session_state
user_input = st.text_area(
    "輸入您的問題或指令",
    key="user_input",
    height=150,
    placeholder="請在此輸入文字..."
)

# 圖片上傳
uploaded_file = st.file_uploader(
    "上傳圖片（選填）",
    type=["png", "jpg", "jpeg", "webp"],
    help="單次對話用，刷新後需重新上傳"
)

# 顯示上傳的圖片預覽
if uploaded_file is not None:
    st.image(uploaded_file, caption="已上傳的圖片", width=300)

# 送出按鈕
submit_button = st.button("送出測試", type="primary", use_container_width=True)


# ============================================================
# 後端邏輯
# ============================================================
if submit_button:
    # 檢查是否有輸入
    if not user_input.strip() and uploaded_file is None:
        st.warning("請輸入文字或上傳圖片")
    else:
        # 檢查 API Key
        try:
            api_key = st.secrets["gemini"]["api_key"]
            if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                st.error("請先設定 Gemini API Key（在 .streamlit/secrets.toml 中）")
                st.stop()
        except (KeyError, FileNotFoundError):
            st.error("找不到 API Key 設定。請建立 .streamlit/secrets.toml 檔案並設定 [gemini] api_key")
            st.stop()

        # 準備要記錄的使用者輸入
        log_content = user_input.strip() if user_input.strip() else "(圖片輸入)"

        # 寫入使用者紀錄
        if sheets_connected:
            with st.spinner("寫入紀錄中..."):
                try:
                    add_log('user', 'test_q', log_content)
                except Exception as e:
                    st.warning(f"寫入使用者紀錄失敗: {str(e)}")

        # 呼叫 API
        with st.spinner("正在處理中..."):
            try:
                # 初始化 Client
                client = genai.Client(api_key=api_key)

                # 準備內容
                contents = []

                # 處理圖片（如果有）
                if uploaded_file is not None:
                    # 使用 Pillow 開啟圖片
                    image = Image.open(uploaded_file)
                    contents.append(image)

                # 加入文字 Prompt
                if user_input.strip():
                    contents.append(user_input.strip())
                else:
                    # 若只有圖片，給一個預設 prompt
                    contents.append("請用繁體中文詳細描述這張圖片的內容。")

                # 呼叫 API
                response = client.models.generate_content(
                    model=selected_model,
                    contents=contents
                )

                # 寫入 AI 回應紀錄
                if sheets_connected:
                    with st.spinner("寫入紀錄中..."):
                        try:
                            add_log('ai', 'test_a', response.text)
                            st.toast("✅ 對話已儲存！")
                        except Exception as e:
                            st.warning(f"寫入 AI 紀錄失敗: {str(e)}")

                # 顯示結果
                st.divider()
                st.subheader("🤖 AI 回應")
                st.markdown(response.text)

            except Exception as e:
                st.error(f"API 呼叫失敗: {str(e)}")

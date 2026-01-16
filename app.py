"""
知識掏金盤 (Knowledge Gold Panning) - Phase 3
雙區介面與大腦植入 (The UI & Brain)
"""

import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from tenacity import retry, stop_after_attempt, wait_fixed
from datetime import datetime, timezone, timedelta
import time


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

    # 準備寫入資料 (使用台灣時間 UTC+8)
    tw_tz = timezone(timedelta(hours=8))
    timestamp = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    row = [timestamp, role, tag, content]

    # 寫入至最後一行
    worksheet.append_row(row)


# ============================================================
# 讀取歷史紀錄 (Cached)
# ============================================================
@st.cache_data(ttl=5)
def get_logs() -> pd.DataFrame:
    """
    讀取 Google Sheets 所有紀錄
    - 使用 get_all_values() 取代 get_all_records() 避免 Header 問題
    - 依 timestamp 倒序排列（最新在最上面）
    """
    worksheet = get_worksheet()
    default_columns = ["timestamp", "role", "tag", "content"]

    if worksheet is None:
        return pd.DataFrame(columns=default_columns)

    try:
        # 使用 get_all_values() 取得原始資料
        all_values = worksheet.get_all_values()

        # 若資料少於 2 列（只有標題或全空），回傳空 DataFrame
        if len(all_values) < 2:
            return pd.DataFrame(columns=default_columns)

        # 第一列為 Header，第二列之後為 Data
        header = all_values[0]
        data = all_values[1:]

        df = pd.DataFrame(data, columns=header)

        # 依 timestamp 倒序排列（最新的在最上面）
        if "timestamp" in df.columns:
            df = df.sort_values(by="timestamp", ascending=False).reset_index(drop=True)

        return df
    except Exception:
        return pd.DataFrame(columns=default_columns)


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
# System Instruction 輔助函式
# ============================================================
def get_system_instruction(mode: str, depth: str = None) -> str:
    """
    集中管理 System Prompts
    - mode="translate": 翻譯模式
    - mode="explain": 解釋模式 (需指定 depth)
    """
    if mode == "translate":
        return "你是一個學術翻譯。將輸入內容翻譯成流暢的繁體中文，精確保留術語，不要做額外解釋。"

    elif mode == "explain":
        if depth == "摘要":
            return "用一句話解釋這個概念的定義。"
        elif depth == "詳解":
            return "詳細解釋這段內容。如果是概念，說明其原理；如果是論述，分析其邏輯。"
        elif depth == "延伸":
            return "解釋這段內容，並延伸介紹相關聯的學術概念。"
        else:
            return "詳細解釋這段內容。"

    return ""


# ============================================================
# Session State 初始化
# ============================================================
if "input_ai" not in st.session_state:
    st.session_state.input_ai = ""
if "input_note" not in st.session_state:
    st.session_state.input_note = ""


# ============================================================
# 標題
# ============================================================
st.title("⛏️ 知識掏金盤")
st.caption("Knowledge Gold Panning - Phase 3")


# ============================================================
# 系統設定區
# ============================================================
sheets_connected = check_sheets_connection()

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
# 上方顯示區 (Log Zone)
# ============================================================
st.subheader("📜 學習紀錄")

with st.container(height=400):
    if sheets_connected:
        try:
            logs_df = get_logs()
            if logs_df.empty:
                st.info("目前沒有歷史紀錄，開始你的學習之旅吧！")
            else:
                # 渲染 Log
                for _, row in logs_df.iterrows():
                    role = row.get("role", "")
                    tag = row.get("tag", "")
                    content = row.get("content", "")
                    timestamp = row.get("timestamp", "")

                    if role == "ai":
                        with st.chat_message("assistant"):
                            st.markdown(content)
                            st.caption(f"🏷️ {tag} | 🕐 {timestamp}")
                    else:
                        # User message
                        st.markdown(f"**[{tag}]** {content}")
                        st.caption(f"🕐 {timestamp}")
                        st.divider()
        except Exception as e:
            st.error(f"讀取歷史紀錄失敗: {str(e)}")
    else:
        st.warning("Google Sheets 尚未設定。請在 .streamlit/secrets.toml 中設定 [gcp_service_account] 和 [google_sheets] sheet_url")


# ============================================================
# 下方操作區 (Input Zone)
# ============================================================
st.divider()

tab_ai, tab_note = st.tabs(["🤖 AI 助手", "📝 我的筆記"])


# ============================================================
# Tab 1: AI 助手
# ============================================================
with tab_ai:
    # 輸入區
    ai_input = st.text_area(
        "輸入要處理的內容",
        key="input_ai",
        height=120,
        placeholder="貼上要翻譯或解釋的文字..."
    )

    # 深度選擇
    depth_mode = st.pills(
        "解釋深度",
        options=["摘要", "詳解", "延伸"],
        default="詳解",
        key="depth_mode"
    )

    # 按鈕區 (雙欄)
    col1, col2 = st.columns(2)

    with col1:
        btn_translate = st.button("🔤 翻譯", use_container_width=True)

    with col2:
        btn_explain = st.button("🧑‍🏫 解釋", use_container_width=True)

    # 翻譯邏輯
    if btn_translate:
        if not ai_input.strip():
            st.warning("請輸入要翻譯的內容")
        elif not sheets_connected:
            st.error("請先設定 Google Sheets 連線")
        else:
            try:
                api_key = st.secrets["gemini"]["api_key"]
                if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                    st.error("請先設定 Gemini API Key")
                    st.stop()
            except (KeyError, FileNotFoundError):
                st.error("找不到 API Key 設定")
                st.stop()

            with st.spinner("翻譯中..."):
                try:
                    # 寫入 User Log
                    add_log("user", "vocab", ai_input.strip())

                    # 呼叫 API
                    client = genai.Client(api_key=api_key)
                    system_prompt = get_system_instruction("translate")

                    response = client.models.generate_content(
                        model=selected_model,
                        contents=ai_input.strip(),
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt
                        )
                    )

                    # 寫入 AI Log
                    add_log("ai", "vocab", response.text)
                    st.toast("✅ 翻譯完成！")
                    time.sleep(0.5)
                    st.rerun()

                except Exception as e:
                    st.error(f"翻譯失敗: {str(e)}")

    # 解釋邏輯
    if btn_explain:
        if not ai_input.strip():
            st.warning("請輸入要解釋的內容")
        elif not sheets_connected:
            st.error("請先設定 Google Sheets 連線")
        else:
            try:
                api_key = st.secrets["gemini"]["api_key"]
                if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
                    st.error("請先設定 Gemini API Key")
                    st.stop()
            except (KeyError, FileNotFoundError):
                st.error("找不到 API Key 設定")
                st.stop()

            # 根據深度決定 Tag
            depth_tag_map = {
                "摘要": "explain_brief",
                "詳解": "explain_std",
                "延伸": "explain_ext"
            }
            tag = depth_tag_map.get(depth_mode, "explain_std")

            with st.spinner("解釋中..."):
                try:
                    # 寫入 User Log
                    add_log("user", tag, ai_input.strip())

                    # 呼叫 API
                    client = genai.Client(api_key=api_key)
                    system_prompt = get_system_instruction("explain", depth_mode)

                    response = client.models.generate_content(
                        model=selected_model,
                        contents=ai_input.strip(),
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt
                        )
                    )

                    # 寫入 AI Log
                    add_log("ai", tag, response.text)
                    st.toast("✅ 解釋完成！")
                    time.sleep(0.5)
                    st.rerun()

                except Exception as e:
                    st.error(f"解釋失敗: {str(e)}")


# ============================================================
# Tab 2: 我的筆記
# ============================================================
with tab_note:
    # 意圖選擇
    note_tag = st.pills(
        "筆記類型",
        options=["問題", "理解", "洞察"],
        default="理解",
        key="note_tag"
    )

    # 輸入區
    note_input = st.text_area(
        "寫下你的筆記",
        key="input_note",
        height=120,
        placeholder="記錄你的問題、理解或洞察..."
    )

    # 記錄按鈕
    btn_save_note = st.button("💾 記錄", use_container_width=True)

    if btn_save_note:
        if not note_input.strip():
            st.warning("請輸入筆記內容")
        elif not sheets_connected:
            st.error("請先設定 Google Sheets 連線")
        else:
            # 根據意圖決定 Tag
            note_tag_map = {
                "問題": "question",
                "理解": "understand",
                "洞察": "insight"
            }
            tag = note_tag_map.get(note_tag, "understand")

            with st.spinner("儲存中..."):
                try:
                    add_log("user", tag, note_input.strip())
                    st.toast("✅ 筆記已儲存！")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"儲存失敗: {str(e)}")

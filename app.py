"""
知識掏金盤 (Knowledge Gold Panning) - Phase 1
核心引擎與設定介面
"""

import streamlit as st
from google import genai
from PIL import Image
import io


# ============================================================
# 頁面配置
# ============================================================
st.set_page_config(
    page_title="知識掏金盤",
    page_icon="⛏️",
    layout="centered"
)


# ============================================================
# Session State 初始化
# ============================================================
if "user_input" not in st.session_state:
    st.session_state.user_input = ""


# ============================================================
# 標題
# ============================================================
st.title("⛏️ 知識掏金盤")
st.caption("Knowledge Gold Panning - Phase 1")


# ============================================================
# 系統設定區
# ============================================================
with st.expander("⚙️ 系統設定", expanded=False):
    # 模型選擇
    selected_model = st.selectbox(
        "選擇模型",
        options=["gemini-2.5-flash", "gemini-2.0-flash-exp"],
        index=0,
        help="選擇要使用的 Gemini 模型"
    )

    # 顯示 SDK 版本
    st.text(f"Google Gen AI SDK 版本: {genai.__version__}")


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
    st.image(uploaded_file, caption="已上傳的圖片", use_container_width=True)

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
                    contents.append("請描述這張圖片的內容。")

                # 呼叫 API
                response = client.models.generate_content(
                    model=selected_model,
                    contents=contents
                )

                # 顯示結果
                st.divider()
                st.subheader("🤖 AI 回應")
                st.markdown(response.text)

            except Exception as e:
                st.error(f"API 呼叫失敗: {str(e)}")

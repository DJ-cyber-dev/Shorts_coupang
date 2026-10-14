"""MVP-compatible optional Streamlit adapter for development."""
from pathlib import Path
import shutil
import tempfile
import streamlit as st
from shorts_studio.core import MediaError
from shorts_studio.pipeline import convert_source

st.set_page_config(page_title="Shorts Studio", page_icon="🎬")
st.title("Shorts Studio")
st.caption("9:16 MP4 · 전체 오디오 제거 · 개발용 UI")
input_type = st.radio("영상 가져오기", ["URL", "파일 업로드"], horizontal=True)
url, uploaded = "", None
if input_type == "URL":
    url = st.text_input("YouTube Shorts 또는 TikTok 영상 URL", placeholder="https://www.youtube.com/shorts/…")
else:
    uploaded = st.file_uploader("원본 영상 (최대 200 MB)", type=["mp4", "mov", "mkv", "webm"])
mode = st.selectbox("화면 처리", ["pad", "crop"], format_func=lambda x: "여백 추가" if x == "pad" else "중앙 Crop")
st.caption("문자 탐지와 제거를 전체 화면에 적용합니다. 완료 후 결과 미리보기를 확인하세요.")
if st.button("제작 시작", disabled=not url.strip() and uploaded is None):
    st.session_state.pop("result", None)
    st.session_state.pop("preview", None)
    try:
        with tempfile.TemporaryDirectory(prefix="shorts-upload-") as folder:
            target = Path(folder) / "shorts.mp4"
            if uploaded is not None:
                source = Path(folder) / ("input" + Path(uploaded.name).suffix.lower())
                uploaded.seek(0)
                with source.open("wb") as file:
                    shutil.copyfileobj(uploaded, file, length=1024 * 1024)
            else:
                source = url.strip()
            bar = st.progress(0.0)
            stage = st.empty()
            convert_source(source, target, is_url=input_type == "URL", mode=mode,
                           progress=bar.progress, status=stage.info)
            preview = target.with_suffix(".preview.jpg")
            if preview.exists():
                st.session_state["preview"] = preview.read_bytes()
            if target.stat().st_size > 200 * 1024 * 1024:
                st.error("결과가 200 MB를 넘습니다. Desktop UI를 사용하세요.")
            else:
                st.session_state["result"] = target.read_bytes()
    except (MediaError, OSError) as exc:
        st.error(str(exc))
if "result" in st.session_state:
    if "preview" in st.session_state:
        st.image(st.session_state["preview"], caption="첫 탐지 프레임: 원본 / 탐지 영역 / 제거 결과")
    st.video(st.session_state["result"])
    st.download_button("MP4 다운로드", st.session_state["result"], "shorts.mp4", "video/mp4")
    if st.button("결과 지우기"):
        del st.session_state["result"]
        st.session_state.pop("preview", None)
        st.rerun()

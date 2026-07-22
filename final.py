from __future__ import annotations

import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Iterable

import pyttsx3
import streamlit as st
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

APP_TITLE = "TJF Study Animator"
VIDEO_SIZE = (1280, 720)
FPS = 24

st.set_page_config(page_title=APP_TITLE, page_icon="🎓", layout="wide")


@st.cache_data(show_spinner=False)
def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, int]:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = Path(tmp.name)

    try:
        reader = PdfReader(str(pdf_path))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"Page {index}\n{text}")
        return "\n\n".join(pages), len(reader.pages)
    finally:
        pdf_path.unlink(missing_ok=True)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_into_scenes(text: str, max_chars: int = 420) -> list[str]:
    text = clean_text(text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    scenes: list[str] = []

    for paragraph in paragraphs:
        paragraph = re.sub(r"^Page\s+\d+\s*", "", paragraph, flags=re.IGNORECASE).strip()
        if not paragraph:
            continue

        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    scenes.append(current)
                if len(sentence) <= max_chars:
                    current = sentence
                else:
                    words = sentence.split()
                    chunk = ""
                    for word in words:
                        candidate_chunk = f"{chunk} {word}".strip()
                        if len(candidate_chunk) <= max_chars:
                            chunk = candidate_chunk
                        else:
                            if chunk:
                                scenes.append(chunk)
                            chunk = word
                    current = chunk
        if current:
            scenes.append(current)

    return scenes or ([text] if text else [])


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def create_slide(scene_text: str, scene_no: int, total: int, output_path: Path) -> None:
    image = Image.new("RGB", VIDEO_SIZE, (245, 247, 250))
    draw = ImageDraw.Draw(image)

    title_font = get_font(42, bold=True)
    body_font = get_font(34)
    small_font = get_font(22)

    draw.rounded_rectangle((55, 45, 1225, 675), radius=28, fill=(255, 255, 255), outline=(214, 220, 230), width=3)
    draw.text((95, 80), APP_TITLE, font=title_font, fill=(30, 45, 70))
    draw.text((1010, 92), f"Scene {scene_no}/{total}", font=small_font, fill=(90, 105, 125))
    draw.line((95, 145, 1185, 145), fill=(220, 225, 233), width=2)

    lines = wrap_lines(draw, scene_text, body_font, 1030)
    line_height = 50
    block_height = len(lines) * line_height
    y = max(190, 390 - block_height // 2)

    for line in lines:
        draw.text((125, y), line, font=body_font, fill=(35, 42, 55))
        y += line_height

    draw.text((95, 625), "Generated locally from your study material", font=small_font, fill=(115, 125, 140))
    image.save(output_path, quality=95)


def list_voices() -> list[tuple[str, str]]:
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    result = []
    for voice in voices:
        name = getattr(voice, "name", "System voice")
        result.append((name, voice.id))
    engine.stop()
    return result


def create_narration(text: str, output_path: Path, voice_id: str, rate: int) -> None:
    engine = pyttsx3.init()
    engine.setProperty("voice", voice_id)
    engine.setProperty("rate", rate)
    engine.save_to_file(text, str(output_path))
    engine.runAndWait()
    engine.stop()

    for _ in range(30):
        if output_path.exists() and output_path.stat().st_size > 0:
            return
        time.sleep(0.2)
    raise RuntimeError("Windows narration did not create an audio file.")


def render_video(scenes: Iterable[str], voice_id: str, rate: int, workdir: Path, progress) -> Path:
    scene_list = list(scenes)
    clips = []
    resources = []

    try:
        for index, scene in enumerate(scene_list, start=1):
            slide_path = workdir / f"slide_{index:03d}.png"
            audio_path = workdir / f"audio_{index:03d}.wav"

            create_slide(scene, index, len(scene_list), slide_path)
            create_narration(scene, audio_path, voice_id, rate)

            audio_clip = AudioFileClip(str(audio_path))
            resources.append(audio_clip)
            duration = max(audio_clip.duration + 0.35, 1.5)
            image_clip = ImageClip(str(slide_path)).set_duration(duration).set_audio(audio_clip)
            clips.append(image_clip)
            progress.progress(index / max(len(scene_list), 1), text=f"Rendering scene {index} of {len(scene_list)}")

        final = concatenate_videoclips(clips, method="compose")
        output_path = workdir / "tjf_study_video.mp4"
        final.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2,
            logger=None,
        )
        final.close()
        return output_path
    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
        for resource in resources:
            try:
                resource.close()
            except Exception:
                pass


st.markdown(
    """
    <style>
    .block-container {max-width: 1200px; padding-top: 2rem;}
    .hero {padding: 1.4rem 1.6rem; border-radius: 18px; background: #f4f7fb; border: 1px solid #dde4ef; margin-bottom: 1.5rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="hero">
      <h1 style="margin:0">🎓 {APP_TITLE}</h1>
      <p style="margin:.5rem 0 0 0">Convert a PDF or study text into a narrated MP4 video on your Windows computer. No API keys are required.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Video settings")
    max_chars = st.slider("Text per scene", 220, 650, 420, 20)
    speech_rate = st.slider("Narration speed", 120, 220, 170, 5)
    try:
        voices = list_voices()
        voice_names = [name for name, _ in voices]
        selected_voice_name = st.selectbox("Windows narrator", voice_names)
        selected_voice_id = dict(voices)[selected_voice_name]
    except Exception as exc:
        st.error(f"Could not load Windows voices: {exc}")
        selected_voice_id = ""

input_type = st.radio("Choose input", ["PDF document", "Direct text"], horizontal=True)
source_text = ""

if input_type == "PDF document":
    uploaded = st.file_uploader("Upload a text-based PDF", type=["pdf"])
    if uploaded:
        try:
            source_text, page_count = extract_pdf_text(uploaded.getvalue())
            st.success(f"Extracted text from {page_count} page(s).")
            if not source_text.strip():
                st.warning("No selectable text was found. Scanned PDFs will need OCR in a later version.")
        except Exception as exc:
            st.error(f"PDF extraction failed: {exc}")
else:
    source_text = st.text_area("Paste study content", height=240)

if source_text:
    default_scenes = split_into_scenes(source_text, max_chars=max_chars)
    default_script = "\n\n--- SCENE ---\n\n".join(default_scenes)
    edited_script = st.text_area(
        "Review and edit the study scenes",
        value=default_script,
        height=360,
        help="Each section separated by --- SCENE --- becomes one narrated slide.",
    )
    scenes = [clean_text(part) for part in edited_script.split("--- SCENE ---") if clean_text(part)]

    col1, col2, col3 = st.columns(3)
    col1.metric("Scenes", len(scenes))
    col2.metric("Words", len(" ".join(scenes).split()))
    col3.metric("Estimated duration", f"{max(1, round(len(' '.join(scenes).split()) / max(speech_rate, 1)))} min")

    if st.button("Generate narrated MP4", type="primary", use_container_width=True, disabled=not selected_voice_id):
        if not scenes:
            st.error("No scenes are available to render.")
        else:
            workdir = Path(tempfile.mkdtemp(prefix="tjf-study-animator-"))
            progress = st.progress(0, text="Preparing video")
            try:
                output_path = render_video(scenes, selected_voice_id, speech_rate, workdir, progress)
                progress.progress(1.0, text="Video complete")
                video_bytes = output_path.read_bytes()
                st.video(video_bytes)
                st.download_button(
                    "Download MP4",
                    data=video_bytes,
                    file_name="tjf_study_video.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                )
                st.success("The video was generated locally.")
            except Exception as exc:
                st.error(f"Video generation failed: {exc}")
                st.info("Keep this page open while Windows creates the narration and MoviePy renders the MP4.")
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
else:
    st.info("Upload a PDF or paste text to begin.")

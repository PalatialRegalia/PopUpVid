#!/usr/bin/env python3
"""
PopUp Video Overlay Generator - Production Ready
=================================================

AK-47 Framework: Ship at 70%, iterate from production.
- YouTube download (yt-dlp)
- Transcript extraction (youtube-transcript-api)
- Local LLM trivia (Ollama) with graceful fallback
- FFmpeg overlays with animated MTV-style bubbles
- Docker-ready, cross-platform, Windows 11 optimized

Bubble rendering notes (why this file looks the way it does):
- Every bubble is rendered by Pillow at the video's native resolution, sized
  to *exactly* fit its text, then overlaid by FFmpeg. No drawtext escaping, no
  fixed character counts -> text can never be clipped, garbled or oversized.
- Text colors are chosen from the bubble background luminance, so trivia stays
  readable on every palette (the old build painted white text on pale yellow /
  mint bubbles, which is why facts were hard to read).
- Fonts are bundled in ./fonts and resolved deterministically, so the exact
  same bubble renders on Windows, macOS and inside the Docker image.
- The overlay pass has a graceful fallback: if an exotic FFmpeg build rejects
  the animated (loop + fade) graph, we retry with a simpler static graph
  instead of failing the whole job.

Author: PopUp Video Generator Team
Date: October 2025
"""

import functools
import html
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime

import requests
import streamlit as st
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ─── Configuration ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PopUp Video Generator",
    page_icon="📺",
    layout="wide"
)

OUTPUT_DIR = "output"
TEMP_DIR = "temp"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# Ollama configuration — environment variables with sensible defaults
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")

# Palettes for MTV-style pop-up bubbles. Bright, saturated colors only: body
# text color is auto-picked from each swatch's luminance at render time.
STYLE_PALETTES = {
    "MTV Classic": ["#FF6B6B", "#4ECDC4", "#45B7D1", "#7FC8A9", "#FECA57", "#FF9FF3", "#F17E5A", "#8E7CFF"],
    "Neon Glow": ["#00FFFF", "#FF00FF", "#FFFF00", "#00FF88", "#FF66CC", "#7DF9FF"],
    "Retro Rainbow": ["#FF5964", "#FFB000", "#2EB872", "#35A7FF", "#9E00FF", "#FF6FD8"],
}

# Human-readable labels for the bubble header, per style
STYLE_TITLE = "POP-UP FACT"

# Trivia hygiene
TRIVIA_MAX_CHARS = 110      # hard cap per pop-up (fits 1-3 slides)
SLIDE_MAX_CHARS = 48        # characters per slide before rotating to the next bubble
MAX_TOTAL_SLIDES = 3        # never rotate one fact across more than 3 bubbles
MIN_SLIDE_SECONDS = 3.2     # minimum on-screen time per slide
OLLAMA_HEALTH_TTL = 30.0    # seconds to cache the "is Ollama up?" probe
OLLAMA_TIME_BUDGET = 90.0   # total seconds of LLM time before falling back to canned facts


# ─── Font Resolution ────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BUNDLED_FONT_DIR = os.path.join(PROJECT_ROOT, "fonts")


def _font_search_dirs():
    """Directories searched for fonts, in priority order."""
    dirs = [
        os.environ.get("POPUP_FONT_DIR", ""),   # explicit override
        BUNDLED_FONT_DIR,                        # shipped with the repo / image
        os.path.join(os.getcwd(), "fonts"),
        os.path.expanduser("~/.local/share/fonts"),
        os.path.expanduser("~/.fonts"),
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "/Library/Fonts",
        "/System/Library/Fonts",
    ]
    win_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    if os.path.isdir(win_fonts):
        dirs.append(win_fonts)
    return [d for d in dict.fromkeys(dirs) if d and os.path.isdir(d)]


# Preferred file-name prefixes: display/header font first, then body font.
HEADER_FONT_PREFIXES = ("archivoblack", "arialbd", "dejavusans-bold", "liberationsans-bold", "impact")
BODY_FONT_PREFIXES = ("dejavusans-bold", "dejavusans", "liberationsans-bold", "liberationsans", "arialbd", "arial")


def _find_font_file(prefixes):
    """Return the first font file whose basename starts with one of `prefixes`."""
    for root_dir in _font_search_dirs():
        for dirpath, _, files in os.walk(root_dir):
            for fname in sorted(files):
                low = fname.lower()
                if not low.endswith((".ttf", ".otf")):
                    continue
                if any(low.startswith(p) for p in prefixes):
                    return os.path.join(dirpath, fname)
    return None


@functools.lru_cache(maxsize=1)
def find_fonts():
    """
    Resolve the (header, body) TrueType fonts used for every bubble.

    Prefers the fonts bundled in ./fonts (deterministic on every platform),
    then falls back to whatever the host provides. Returns a tuple that may
    contain None values when nothing suitable exists on the system.
    """
    header = _find_font_file(HEADER_FONT_PREFIXES)
    body = _find_font_file(BODY_FONT_PREFIXES)
    return header, body


def find_font():
    """
    Return a single usable font path (body font preferred, else header), or
    None. Kept for backwards compatibility with the existing test suite.
    """
    header, body = find_fonts()
    return body or header


# ─── Text Hygiene ───────────────────────────────────────────────────────────

# Codepoint ranges that the bundled fonts actually cover. Anything outside
# these ranges (emoji, CJK, dingbats...) would render as tofu boxes in the
# bubble, so it is stripped instead of shown as garbage.
_SUPPORTED_RANGES = (
    (0x20, 0x7E),     # ASCII printable
    (0xA0, 0x17F),    # Latin-1 + Latin Extended-A
    (0x2010, 0x201F),  # dashes, quotes
    (0x2022, 0x2027),  # bullet, ellipsis
    (0x2039, 0x203A),  # single guillemets
    (0x20AC, 0x20AC),  # euro sign
    (0x2605, 0x2606),  # star glyphs used by the bubble badge
)

_GLYPH_FIXUPS = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2039": "'", "\u203a": "'",
    "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-",
    "\u2026": "...", "\u2022": "-", "\u00b7": "-",
    "\u00a0": " ", "\u2009": " ", "\u202f": " ", "\u200b": "",
}

_THINK_BLOCK_RE = re.compile(r"(?is)<(?:think|thinking|reasoning)>.*?</(?:think|thinking|reasoning)\s*>")
_THINK_TAIL_RE = re.compile(r"(?is)^.*?</(?:think|thinking|reasoning)\s*>")
_THINK_TAG_RE = re.compile(r"(?is)</?(?:think|thinking|reasoning)\s*>")
_PREFIX_RE = re.compile(
    r"^\s*(?:here'?s (?:a|another|one)? ?(?:fun |quick |little )?fact\s*[:\-\u2014]?\s*"
    r"|did you know\s*[:\-\u2014]?\s*|fun fact\s*[:\-\u2014]?\s*|pop-?up fact\s*[:\-\u2014]?\s*"
    r"|fact\s*[:\-\u2014]\s*|trivia\s*[:\-\u2014]\s*|answer\s*[:\-\u2014]\s*)",
    re.IGNORECASE,
)
_MARKDOWN_RE = re.compile(r"[*_`#>~]+")

def strip_think_blocks(text):
    """Remove qwen3-style `` reasoning from model output before display."""
    text = _THINK_BLOCK_RE.sub(" ", str(text))
    if re.search(r"(?is)</(?:think|thinking|reasoning)\s*>", text):
        # Truncated reasoning block without a matching opener.
        text = _THINK_TAIL_RE.sub(" ", text, count=1)
    return _THINK_TAG_RE.sub(" ", text)

def sanitize_trivia_text(text, max_len=TRIVIA_MAX_CHARS):
    """
    Normalize LLM trivia so it renders cleanly inside a bubble:

    * drops reasoning/think blocks and "Did you know:" style prefixes
    * strips markdown emphasis that would otherwise show as literal asterisks
    * normalizes smart quotes/dashes to glyphs every bundled font has
    * removes emoji / unsupported glyphs that would render as tofu boxes
    * collapses whitespace and trims to a word boundary (max_len)
    """
    if text is None:
        return ""
    text = strip_think_blocks(str(text))
    text = _MARKDOWN_RE.sub("", text)
    text = _PREFIX_RE.sub("", text)
    for bad, good in _GLYPH_FIXUPS.items():
        text = text.replace(bad, good)
    text = "".join(
        ch if any(lo <= ord(ch) <= hi for lo, hi in _SUPPORTED_RANGES) else " "
        for ch in text
    )
    text = " ".join(text.split())
    text = re.sub(r"\s*\((?:source|via)[^)]*\)\s*$", "", text, flags=re.IGNORECASE)
    text = text.strip(" \"'-")
    if len(text) > max_len:
        cut = text.rfind(" ", 0, max_len)
        if cut < int(max_len * 0.6):
            cut = max_len
        text = text[:cut].rstrip(" ,;:-")
        if not text.endswith((".", "!", "?", "\u2026")):
            text += "\u2026"
    return text.strip()


# ─── Color Utilities ────────────────────────────────────────────────────────

def _srgb_channel_to_linear(value):
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def relative_luminance(color):
    """WCAG relative luminance (0.0 dark - 1.0 light) of an RGB/RGBA color."""
    r, g, b = (list(color) + [0, 0, 0])[:3]
    return (
        0.2126 * _srgb_channel_to_linear(r)
        + 0.7152 * _srgb_channel_to_linear(g)
        + 0.0722 * _srgb_channel_to_linear(b)
    )

def pick_contrast_color(background, dark=(22, 22, 24, 255), light=(255, 255, 255, 255)):
    """
    Return whichever of `dark` / `light` text color contrasts better with
    `background`. Translucent backgrounds are composited over white first so
    the estimate matches what the viewer sees on a bright video frame.
    """
    channels = list(background) + [255]
    alpha = channels[3] / 255.0
    rgb = tuple(int(c * alpha + 255 * (1 - alpha)) for c in channels[:3])
    lum = relative_luminance(rgb)
    contrast_white = (1.0 + 0.05) / (lum + 0.05)
    contrast_dark = (lum + 0.05) / (relative_luminance(dark[:3]) + 0.05)
    return dark if contrast_dark >= contrast_white else light

def shade_color(color, factor=0.58, alpha=None):
    """Multiply an RGB(A) color by `factor` (darken when factor < 1)."""
    r, g, b, a = (list(color) + [255])[:4]
    return (
        max(0, min(255, int(round(r * factor)))),
        max(0, min(255, int(round(g * factor)))),
        max(0, min(255, int(round(b * factor)))),
        a if alpha is None else int(alpha),
    )


def escape_drawtext(text):
    """
    Escape text for safe single-quoted FFmpeg drawtext filter string.
    """
    text = str(text)
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("\n", "\\n")
    text = text.replace("\r", "")
    return text


# ─── YouTube Helpers ───────────────────────────────────────────────────────

# Accepts www./m./music. hosts, youtube.com/youtu.be, youtu.be shorts, and
# protocol-less URLs ("youtube.com/watch?v=..." pasted from address bars).
_YOUTUBE_HOST_RE = re.compile(
    r"^(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com|youtube-nocookie\.com|youtu\.be)/",
    re.IGNORECASE,
)

_VIDEO_ID_PATTERNS = (
    r"(?:youtube\.com|youtube-nocookie\.com)/watch\?(?:[^#\s]*&)?v=([A-Za-z0-9_-]{11})",
    r"(?:youtu\.be|youtube\.com|youtube-nocookie\.com)/(?:shorts|live|embed|v)/([A-Za-z0-9_-]{11})",
    r"[?&]v=([A-Za-z0-9_-]{11})",
)


def validate_youtube_url(url):
    """Return True when `url` looks like a YouTube video/playlist URL."""
    if not url or not isinstance(url, str):
        return False
    return bool(_YOUTUBE_HOST_RE.match(url.strip()))


def extract_video_id(url):
    """
    Extract an 11-character video id from any common YouTube URL shape:
    watch?v=, youtu.be/<id>, /shorts/<id>, /live/<id>, /embed/<id>, /v/<id>,
    including m. and music. hosts.
    """
    if not url or not isinstance(url, str):
        return None
    candidate = url.strip()
    for pattern in _VIDEO_ID_PATTERNS:
        match = re.search(pattern, candidate)
        if match:
            return match.group(1)
    # Bare 11-char id pasted directly
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        return candidate
    return None


def download_video(url, output_path, video_id=None):
    """Download a video with yt-dlp, raising friendlier errors on failure."""
    try:
        cmd = [
            "yt-dlp",
            "-f", "b[height<=720]/bv*[height<=720]+ba/b/bv*+ba",
            "-o", f"{output_path}/%(id)s.%(ext)s",
            "--no-playlist",
            "--no-warnings",
            "--merge-output-format", "mp4",
            "--retries", "2",
            "--socket-timeout", "30",
            url,
        ]

        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

        video_exts = ('.mp4', '.webm', '.mkv', '.mov')
        video_files = [f for f in os.listdir(output_path) if f.endswith(video_exts)]

        if video_files:
            if video_id:
                for f in video_files:
                    if f.startswith(video_id):
                        return os.path.join(output_path, f)
            video_files.sort(key=lambda f: os.path.getmtime(os.path.join(output_path, f)), reverse=True)
            return os.path.join(output_path, video_files[0])

        raise Exception("No video file found after download")
    except subprocess.TimeoutExpired:
        raise Exception("Download timeout - video too large or slow connection")
    except subprocess.CalledProcessError as e:
        error_msg = (e.stderr or str(e) or "").strip()
        low = error_msg.lower()
        if "private video" in low:
            raise Exception("Video is private - try a public video")
        if "not available" in low or "geo" in low:
            raise Exception("Video is not available in this region")
        if "sign in" in low or "age" in low:
            raise Exception("Video is age-restricted - try a different video")
        raise Exception(f"Download failed: {error_msg[:300] or 'unknown yt-dlp error'}")
    except FileNotFoundError:
        raise Exception("yt-dlp not found - ensure it is installed and in PATH")


def fetch_transcript(video_id, duration_hint=None):
    """
    Fetch transcript using youtube-transcript-api.

    Tries English first, then any available language (e.g. auto-generated).
    When no transcript exists at all, builds time-anchored placeholder
    segments spread across the *whole* video (using `duration_hint` from
    ffprobe), so caption-less videos still get pop-ups from start to finish
    instead of only in the first three minutes.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        def parse_fetched(fetched):
            segments = []
            for snippet in fetched:
                text = str(getattr(snippet, 'text', snippet) or "").strip()
                if not text:
                    continue
                segments.append({
                    'text': text,
                    'start': float(getattr(snippet, 'start', 0.0) or 0.0),
                    'duration': float(getattr(snippet, 'duration', 4.0) or 4.0),
                })
            return segments

        # Try v1.0+ instance API
        if hasattr(YouTubeTranscriptApi, 'fetch') or hasattr(YouTubeTranscriptApi, 'list'):
            api = YouTubeTranscriptApi()
            try:
                fetched = api.fetch(video_id, languages=["en"])
                segments = parse_fetched(fetched)
                if segments:
                    return segments
            except Exception:
                try:
                    # Try fetching any available transcript
                    transcript_list = api.list(video_id)
                    for transcript_item in transcript_list:
                        fetched = transcript_item.fetch()
                        segments = parse_fetched(fetched)
                        if segments:
                            return segments
                except Exception:
                    pass

        # Try legacy static API (< v1.0)
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            for kwargs in ({'languages': ['en']}, {}):
                try:
                    raw = YouTubeTranscriptApi.get_transcript(video_id, **kwargs)
                    segments = parse_fetched(raw)
                    if segments:
                        return segments
                except Exception:
                    continue

    except Exception:
        pass

    return build_fallback_transcript(duration_hint)


def build_fallback_transcript(duration_hint=None):
    """
    Time-anchored placeholder segments used when a video has no captions.
    Spread ~every 30s across the known duration (or the first 5 minutes when
    the duration is unknown) and vary the text so the LLM gets a bit of
    variety instead of the same string on every pop-up.
    """
    try:
        horizon = float(duration_hint or 0.0)
    except (TypeError, ValueError):
        horizon = 0.0
    if horizon < 20:
        horizon = 300.0

    anchors = [
        "instrumental introduction",
        "opening verse",
        "chorus hook",
        "second verse",
        "bridge section",
        "guitar solo",
        "final chorus",
        "outro",
    ]

    segments = []
    start = 12.0
    index = 0
    while start < horizon - 6 and len(segments) < 40:
        segments.append({
            'text': anchors[index % len(anchors)],
            'start': float(start),
            'duration': 5.0,
        })
        start += 30.0
        index += 1

    if not segments:
        segments.append({'text': anchors[0], 'start': 5.0, 'duration': 5.0})
    return segments


# ─── LLM / Fallback Trivia ──────────────────────────────────────────────────

# Cache the "is Ollama reachable?" probe so a missing/slow server costs one
# short timeout per run instead of one per pop-up (previously every segment
# re-probed the server, which made the app feel hung).
_OLLAMA_HEALTH = {"checked_at": 0.0, "ok": False}
_LLM_TIME_SPENT = 0.0


def reset_llm_budget():
    """Reset the per-run LLM time budget (called at the start of each job)."""
    global _LLM_TIME_SPENT
    _LLM_TIME_SPENT = 0.0


def ollama_available(force=False):
    """Return True when the Ollama /api/tags endpoint responds, cached briefly."""
    now = time.time()
    if not force and now - _OLLAMA_HEALTH["checked_at"] < OLLAMA_HEALTH_TTL:
        return _OLLAMA_HEALTH["ok"]
    ok = False
    try:
        base_url = OLLAMA_HOST.rstrip('/')
        response = requests.get(f"{base_url}/api/tags", timeout=3)
        ok = response.status_code == 200
    except Exception:
        ok = False
    _OLLAMA_HEALTH["checked_at"] = now
    _OLLAMA_HEALTH["ok"] = ok
    return ok


def generate_trivia_ollama(transcript_text, allow_llm=True):
    """
    Generate one punchy Pop-Up Video fact for a transcript snippet.

    Falls back to the curated fact pool whenever Ollama is unreachable, slow,
    returns unusable text, or the per-run time budget is exhausted. Always
    returns a short, bubble-ready string.
    """
    global _LLM_TIME_SPENT

    if not allow_llm or not ollama_available():
        return generate_fallback_trivia()
    if _LLM_TIME_SPENT >= OLLAMA_TIME_BUDGET:
        return generate_fallback_trivia()

    snippet = sanitize_trivia_text(transcript_text or "", max_len=120) or "this music video"
    prompt = (
        "You write trivia for a 1990s MTV Pop-Up Video broadcast. "
        f"Context from the video: \"{snippet}\".\n"
        "Write exactly ONE surprising, specific fact as a single plain sentence. "
        "Hard limit 90 characters. No preamble, no quotes, no emoji, "
        "no 'Did you know', no markdown. Just the fact:"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.8, "num_predict": 90, "top_p": 0.9},
    }

    started = time.time()
    try:
        base_url = OLLAMA_HOST.rstrip('/')
        res = requests.post(f"{base_url}/api/generate", json=payload, timeout=20)
        _LLM_TIME_SPENT += time.time() - started
        if res.status_code != 200:
            return generate_fallback_trivia()

        data = res.json()
        raw = data.get("response") or data.get("thinking") or ""
        # Keep the answer line, not any reasoning that came before it.
        candidate = strip_think_blocks(raw)
        lines = [ln.strip() for ln in candidate.splitlines() if ln.strip()]
        trivia = sanitize_trivia_text(lines[-1] if lines else "", max_len=TRIVIA_MAX_CHARS)

        if len(trivia) < 12 or trivia.lower().startswith(("i'm sorry", "i cannot", "as an ai")):
            return generate_fallback_trivia()
        return trivia
    except Exception:
        _LLM_TIME_SPENT += time.time() - started
        return generate_fallback_trivia()


def generate_fallback_trivia():
    """Curated, punchy facts used whenever live generation is unavailable."""
    facts = [
        "MTV launched Pop-Up Video in 1996!",
        "The average music video costs over $100K",
        "Pop-Up Video won an Emmy for Original Content in 1997",
        "First video on MTV: 'Video Killed the Radio Star'",
        "Pop-up bubbles boosted viewer retention by 47%",
        "Original episodes took 6 weeks of deep research",
        "Classic pop-ups were modeled on comic-strip balloons",
        "Director cameos appear in 30%+ of top 90s videos",
        "Pop-Up Video produced over 2,000 episodes",
        "Top videos needed 100+ hours of fact checking",
        "Each bubble popped on screen with a signature sound",
        "The show's writers fact-checked every single claim",
        "Pop-Up Video ran six seasons on VH1",
        "Rumor has it the first bubbles were drawn by hand",
    ]
    return random.choice(facts)

def probe_video(video_path):
    """
    Return ((width, height), duration_seconds) for a video file.

    Falls back to ((1280, 720), None) when ffprobe is missing or errors, so the
    pipeline still produces correctly proportioned bubbles on minimal systems.
    """
    dimensions, duration = (1280, 720), None
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "default=noprint_wrappers=1",
            video_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            values = {}
            for line in res.stdout.splitlines():
                if "=" in line:
                    key, _, value = line.partition("=")
                    values[key.strip()] = value.strip()
            try:
                width = int(float(values.get("width", 0)))
                height = int(float(values.get("height", 0)))
                if width > 0 and height > 0:
                    dimensions = (width, height)
            except (TypeError, ValueError):
                pass
            try:
                duration = float(values["duration"])
            except (KeyError, TypeError, ValueError):
                duration = None
    except Exception:
        pass
    return dimensions, duration


def get_video_dimensions(video_path):
    """Backwards-compatible dimensions helper (see probe_video)."""
    return probe_video(video_path)[0]


def hex_to_rgba(hex_str, alpha=235):
    """Convert a #RGB / #RRGGBB color code to an RGBA tuple."""
    value = str(hex_str).strip().lstrip('#')
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) == 6:
        try:
            return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), int(alpha))
        except ValueError:
            pass
    return (255, 107, 107, int(alpha))


def split_text_into_slides(text, max_chars_per_slide=SLIDE_MAX_CHARS, max_slides=MAX_TOTAL_SLIDES):
    """
    Split trivia into word-boundary slides of at most `max_chars_per_slide`
    characters, capped at `max_slides`. Overlong text is trimmed with an
    ellipsis rather than spawning an extra bubble.
    """
    text = " ".join(str(text or "").split())
    if not text:
        return [""]

    words = text.split()
    slides = []
    curr_words = []
    curr_len = 0

    for word in words:
        addition_len = len(word) + (1 if curr_words else 0)
        if curr_len + addition_len <= max_chars_per_slide or not curr_words:
            curr_words.append(word)
            curr_len += addition_len
        else:
            slides.append(' '.join(curr_words))
            curr_words = [word]
            curr_len = len(word)

    if curr_words:
        slides.append(' '.join(curr_words))

    # Rebalance so a trailing slide is never a lone word (e.g. "...signature"
    # + "sound"): shift words back until the last slide reads naturally.
    for i in range(len(slides) - 1, 0, -1):
        while len(slides[i]) < max_chars_per_slide * 0.4:
            prev_words = slides[i - 1].split()
            if len(prev_words) <= 1:
                break
            moved = prev_words[-1]
            if len(moved) + 1 + len(slides[i]) > max_chars_per_slide:
                break
            slides[i - 1] = ' '.join(prev_words[:-1])
            slides[i] = moved + ' ' + slides[i]

    if len(slides) > max_slides:
        slides = slides[:max_slides]
        if not slides[-1].endswith((".", "!", "?", "\u2026")):
            slides[-1] += "\u2026"

    return slides


# ─── Bubble Rendering ───────────────────────────────────────────────────────

def _load_font(font_path, size):
    """Load a TrueType font at `size`, degrading to Pillow's default font."""
    size = max(int(size), 8)
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_width(font, text):
    """Pixel width of `text` rendered in `font`."""
    try:
        return int(round(font.getlength(text)))
    except Exception:
        try:
            bbox = font.getbbox(text)
            return int(bbox[2] - bbox[0])
        except Exception:
            return int(round(len(text) * getattr(font, "size", 8) * 0.6))


def _wrap_text_px(text, font, max_px, max_lines=3):
    """
    Greedy word-wrap measured in pixels (not characters), so bubbles fit the
    video's real resolution instead of a hard-coded character count. Words
    wider than the line are hard-split; overflow past `max_lines` is trimmed
    with an ellipsis so a bubble can never grow past the video.
    """
    max_px = max(int(max_px), 40)
    words = [w for w in str(text).split() if w]
    if not words:
        return [""]

    def split_long(word):
        pieces, current = [], ""
        for ch in word:
            if _text_width(font, current + ch) <= max_px or not current:
                current += ch
            else:
                pieces.append(current)
                current = ch
        if current:
            pieces.append(current)
        return pieces

    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_width(font, candidate) <= max_px:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if _text_width(font, word) <= max_px:
            current = word
        else:
            pieces = split_long(word)
            lines.extend(pieces[:-1])
            current = pieces[-1]

    if current:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and _text_width(font, last + "\u2026") > max_px:
            last = last[:-1]
        lines[-1] = (last.rstrip() + "\u2026") if last else "\u2026"

    return lines or [""]


def _draw_text(draw, xy, text, font, fill, anchor=None):
    """
    draw.text with a graceful fallback: Pillow's built-in bitmap font does not
    support `anchor=`, and some exotic builds reject particular anchors.
    """
    try:
        if anchor:
            draw.text(xy, text, font=font, fill=fill, anchor=anchor)
        else:
            draw.text(xy, text, font=font, fill=fill)
        return
    except Exception:
        pass
    try:
        x, y = float(xy[0]), float(xy[1])
        if anchor and anchor[1] == "m":   # vertical centering fallback
            bbox = font.getbbox(text)
            y -= (bbox[3] - bbox[1]) / 2.0 + bbox[1]
        draw.text((x, y), text, font=font, fill=fill)
    except Exception:
        pass


def bubble_theme(style_name, color_hex, body_size):
    """
    Resolve every color/decoration choice for one bubble.

    Each style keeps its own identity, but body text color is always derived
    from the bubble fill's luminance so the trivia is readable no matter which
    palette swatch a pop-up happens to use.
    """
    accent = hex_to_rgba(color_hex, 255)

    if style_name == "Neon Glow":
        return {
            "fill": (9, 12, 26, 216),
            "border": accent,
            "border_w": max(2, int(round(body_size * 0.15))),
            "band": (4, 6, 16, 236),
            "title": accent,
            "text": (236, 243, 255, 255),
            "chip_fill": accent,
            "chip_text": (8, 10, 22, 255),
            "badge_fill": accent,
            "badge_star": (8, 10, 22, 255),
            "glow": True,
            "shadow": False,
            "gloss": False,
        }

    if style_name == "Retro Rainbow":
        band = accent
        return {
            "fill": (255, 249, 236, 246),
            "border": (24, 22, 20, 255),
            "border_w": max(3, int(round(body_size * 0.2))),
            "band": band,
            "title": pick_contrast_color(band),
            "text": (30, 27, 24, 255),
            "chip_fill": (24, 22, 20, 255),
            "chip_text": (255, 255, 255, 255),
            "badge_fill": pick_contrast_color(band),
            "badge_star": band,
            "glow": False,
            "shadow": True,
            "gloss": False,
        }

    # MTV Classic (default): bright swatch, chunky ink border, glassy highlight.
    fill = hex_to_rgba(color_hex, 242)
    band = shade_color(fill, 0.6, alpha=255)
    return {
        "fill": fill,
        "border": (16, 15, 15, 255),
        "border_w": max(2, int(round(body_size * 0.16))),
        "band": band,
        "title": pick_contrast_color(band),
        "text": pick_contrast_color(fill),
        "chip_fill": shade_color(band, 0.55, alpha=255),
        "chip_text": (255, 255, 255, 255),
        "badge_fill": (255, 255, 255, 242),
        "badge_star": band,
        "glow": False,
        "shadow": True,
        "gloss": True,
    }


def build_bubble_image(title, text, style_name, color_hex, v_width, v_height,
                       slide_idx=None, total_slides=None):
    """
    Render one speech bubble at the video's native resolution and return it as
    an RGBA PIL image.

    The bubble is sized to fit its exact text (measured in pixels), scaled to
    the video height, clamped to at most 86% of the video width, and colored
    for maximum legibility. This is the single source of truth for both the
    in-video overlays and the live sidebar preview.
    """
    v_width = max(int(v_width or 1280), 320)
    v_height = max(int(v_height or 720), 240)

    header_path, body_path = find_fonts()

    body_size = int(round(min(max(v_height * 0.030, 16), 40)))
    header_size = int(round(max(body_size * 0.70, 12)))
    chip_size = max(int(round(body_size * 0.56)), 11)

    body_font = _load_font(body_path, body_size)
    header_font = _load_font(header_path, header_size)
    chip_font = _load_font(body_path, chip_size)
    star_font = _load_font(body_path, max(int(body_size * 0.86), 11))

    heading = re.sub(r"[^A-Za-z0-9 \-]", "", str(title or STYLE_TITLE)).strip().upper() or STYLE_TITLE
    body = sanitize_trivia_text(text, max_len=TRIVIA_MAX_CHARS) or "Fun fact coming up"
    chip_text = f"{slide_idx}/{total_slides}" if (slide_idx and total_slides and total_slides > 1) else ""

    theme = bubble_theme(style_name, color_hex, body_size)

    pad_x = int(round(max(body_size * 1.0, v_width * 0.012, 14)))
    pad_y = int(round(max(body_size * 0.55, 10)))
    band_pad = int(round(max(header_size * 0.42, 6)))

    max_bubble_w = int(v_width * 0.86)
    max_text_w = max(max_bubble_w - pad_x * 2, int(body_size * 6))
    lines = _wrap_text_px(body, body_font, max_text_w, max_lines=3)

    ascent, descent = body_font.getmetrics()
    line_h = int(round((ascent + descent) * 1.16))
    h_ascent, h_descent = header_font.getmetrics()
    header_text_h = h_ascent + h_descent

    badge_r = int(round(max(header_text_h * 0.5, body_size * 0.42)))
    gap = int(round(body_size * 0.45))
    chip_h = int(round(chip_size * 1.7))
    chip_w = (_text_width(chip_font, chip_text) + int(chip_size * 1.1)) if chip_text else 0

    header_inner = badge_r * 2 + gap + _text_width(header_font, heading)
    if chip_w:
        header_inner += gap + chip_w
    band_h = max(int(round(header_text_h + band_pad * 2)), chip_h + band_pad, badge_r * 2 + band_pad)

    body_w = max((_text_width(body_font, line) for line in lines), default=0)
    b_width = max(header_inner, body_w) + pad_x * 2
    b_width = min(max(b_width, int(v_width * 0.26)), max_bubble_w)
    b_height = band_h + pad_y * 2 + line_h * len(lines)
    radius = int(min(max(b_height * 0.16, 12), 30, b_width / 2))
    band_h = max(band_h, radius + 2)

    tail_w = int(round(max(b_width * 0.13, body_size * 1.3)))
    tail_h = int(round(max(body_size * 0.85, 14)))

    margin = int(round(max(body_size * 1.1, 12)))   # room for shadow / glow
    canvas_w = b_width + margin * 2
    canvas_h = b_height + margin * 2 + tail_h
    ox, oy = margin, margin
    box = [ox, oy, ox + b_width, oy + b_height]

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # 1. Neon halo or soft drop shadow
    if theme["glow"]:
        halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(halo).rounded_rectangle(box, radius=radius, fill=theme["border"])
        halo = halo.filter(ImageFilter.GaussianBlur(max(theme["border_w"] * 2.4, 4)))
        halo.putalpha(halo.getchannel("A").point(lambda a: min(255, int(a * 0.6))))
        img.alpha_composite(halo)
    if theme["shadow"]:
        drop = max(3, int(round(body_size * 0.24)))
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            [box[0] + drop * 0.35, box[1] + drop, box[2] + drop * 0.35, box[3] + drop],
            radius=radius, fill=(0, 0, 0, 118),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(drop * 1.8))
        img.alpha_composite(shadow)

    draw = ImageDraw.Draw(img)

    # 2. Body fill, then a darker header band with matching top corners
    draw.rounded_rectangle(box, radius=radius, fill=theme["fill"])
    draw.rounded_rectangle(
        [box[0], box[1], box[2], box[1] + band_h + radius], radius=radius, fill=theme["band"]
    )
    draw.rectangle([box[0], box[1] + band_h, box[2], box[1] + band_h + radius], fill=theme["band"])

    # 3. Glassy highlight over the body (classic late-90s gel look)
    if theme["gloss"]:
        gloss_h = max(int((b_height - band_h) * 0.6), 8)
        gradient = Image.new("L", (1, gloss_h))
        gradient.putdata([int(round(52 * (1 - row / max(gloss_h - 1, 1)))) for row in range(gloss_h)])
        gradient = gradient.resize((b_width, gloss_h))
        sheen = Image.new("RGBA", (b_width, gloss_h), (255, 255, 255, 255))
        sheen.putalpha(gradient)
        gloss = Image.new("RGBA", img.size, (255, 255, 255, 0))
        gloss.paste(sheen, (ox, oy + band_h))
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
        gloss.putalpha(ImageChops.multiply(gloss.getchannel("A"), mask))
        img.alpha_composite(gloss)

    # 4. Outline
    if theme["border_w"] > 0:
        draw.rounded_rectangle(box, radius=radius, outline=theme["border"], width=theme["border_w"])

    # 5. Header row: star badge, title, optional slide chip
    band_mid = oy + band_h / 2
    badge_cx = ox + pad_x + badge_r
    draw.ellipse(
        [badge_cx - badge_r, band_mid - badge_r, badge_cx + badge_r, band_mid + badge_r],
        fill=theme["badge_fill"],
    )
    _draw_text(draw, (badge_cx, band_mid + 1), "\u2605", star_font, theme["badge_star"], anchor="mm")
    _draw_text(draw, (badge_cx + badge_r + gap, band_mid), heading, header_font,
               theme["title"], anchor="lm")

    if chip_w:
        chip_x2 = ox + b_width - pad_x
        chip_x1 = chip_x2 - chip_w
        draw.rounded_rectangle(
            [chip_x1, band_mid - chip_h / 2, chip_x2, band_mid + chip_h / 2],
            radius=chip_h / 2, fill=theme["chip_fill"],
        )
        _draw_text(draw, ((chip_x1 + chip_x2) / 2, band_mid), chip_text, chip_font,
                   theme["chip_text"], anchor="mm")

    # 6. Body copy
    text_y = oy + band_h + pad_y + int(line_h * 0.08)
    for line in lines:
        _draw_text(draw, (ox + pad_x, text_y), line, body_font, theme["text"], anchor="la")
        text_y += line_h

    # 7. Tail last, so it opens cleanly through the bubble border
    apex = ox + max(pad_x + tail_w, int(b_width * 0.18))
    y_base = oy + b_height - theme["border_w"] * 0.5
    left = (apex - tail_w * 0.6, y_base)
    right = (apex + tail_w * 0.4, y_base)
    tip = (apex - tail_w * 0.5, y_base + tail_h)
    draw.polygon([left, right, tip], fill=theme["fill"])
    draw.line([left, tip], fill=theme["border"], width=max(theme["border_w"], 2))
    draw.line([right, tip], fill=theme["border"], width=max(theme["border_w"], 2))

    return img


def generate_bubble_image(title, text, style_name, color_hex, v_width, v_height, output_path,
                          slide_idx=None, total_slides=None):
    """
    Render a bubble PNG to `output_path` and return its (width, height).
    Thin wrapper around build_bubble_image so the overlay pipeline and the
    sidebar preview always share exactly the same rendering path.
    """
    img = build_bubble_image(title, text, style_name, color_hex, v_width, v_height,
                             slide_idx=slide_idx, total_slides=total_slides)
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    img.save(output_path, "PNG")
    return img.size


def render_preview_image(style_name, text=None, v_width=1280, v_height=720):
    """Render the sidebar preview bubble (same code path as the overlays)."""
    palette = STYLE_PALETTES.get(style_name, STYLE_PALETTES["MTV Classic"])
    return build_bubble_image(
        STYLE_TITLE, text or PREVIEW_TEXT, style_name, palette[0], v_width, v_height,
        slide_idx=1, total_slides=2,
    )


# ─── Overlay Pipeline ───────────────────────────────────────────────────────

def select_segments(transcript, max_popups):
    """
    Pick up to `max_popups` transcript segments spread evenly across the video.
    (The previous build sliced with `transcript[::step]`, which could cluster
    pop-ups at the start of long videos.)
    """
    segments = [s for s in (transcript or []) if str(s.get('text', '')).strip()]
    if not segments or max_popups <= 0:
        return []
    if len(segments) <= max_popups:
        return segments

    step = (len(segments) - 1) / float(max(max_popups - 1, 1))
    picked, seen = [], set()
    for index in range(max_popups):
        position = int(round(index * step))
        if position not in seen:
            seen.add(position)
            picked.append(segments[position])
    return picked


def placement_for(index, video_w, video_h, bubble_w, bubble_h):
    """
    Cycle bubbles between bottom-center / bottom-left / bottom-right and
    alternate their height slightly, the way the original show scattered
    bubbles around the lower third of the frame.
    """
    margin = int(max(video_w * 0.05, 24))
    slot = index % 3
    if slot == 0:
        x = int(max((video_w - bubble_w) / 2, 0))
    elif slot == 1:
        x = margin
    else:
        x = int(max(video_w - bubble_w - margin, 0))
    lift = int(max(video_h * 0.10, 46)) + (index % 2) * int(max(video_h * 0.05, 18))
    y = int(max(video_h - bubble_h - lift, 8))
    return x, y


def build_overlay_graph(v_width, v_height, bubbles, animated=True):
    """
    Build the FFmpeg input flags + filter_complex graph for the bubble list.

    `bubbles` entries are dicts: png (path), w, h, start, end, x, y.
    `animated=True` loops each image and alpha-fades it in/out while it gently
    floats; `animated=False` uses static single-frame overlays (maximum
    compatibility fallback).
    """
    input_args = []
    graph = ["[0:v]setsar=1[base]"]
    last = "base"

    for index, bubble in enumerate(bubbles, start=1):
        start = float(bubble["start"])
        end = float(bubble["end"])
        label = f"b{index}"

        if animated:
            # NOTE: the image input is looped so the fade filters have frames to
            # work with, but an *unbounded* loop makes FFmpeg encode forever
            # (a looped input never EOFs). Bounding each input with -t keeps the
            # graph finite, so rendering finishes as soon as the video does.
            clip_end = end + 0.5
            input_args += [
                "-loop", "1", "-framerate", "25", "-t", f"{clip_end:.2f}", "-i", bubble["png"],
            ]
            fade = min(0.35, max((end - start) / 3.0, 0.08))
            fade_out = max(end - fade, start)
            graph.append(
                f"[{index}:v]format=rgba,setsar=1,"
                f"fade=t=in:st={start:.2f}:d={fade:.2f}:alpha=1,"
                f"fade=t=out:st={fade_out:.2f}:d={fade:.2f}:alpha=1[{label}]"
            )
            sway = 3
            x_expr = f"{bubble['x']}+sin((t-{start:.2f})*1.3)*{sway}"
            y_expr = f"{bubble['y']}+sin((t-{start:.2f})*1.8)*{sway}"
        else:
            input_args += ["-i", bubble["png"]]
            graph.append(f"[{index}:v]format=rgba,setsar=1[{label}]")
            x_expr = str(bubble["x"])
            y_expr = str(bubble["y"])

        out_label = f"v{index}"
        graph.append(
            f"[{last}][{label}]overlay=x='{x_expr}':y='{y_expr}'"
            f":enable='between(t,{start:.2f},{end:.2f})'[{out_label}]"
        )
        last = out_label

    # Force a broadly playable pixel format for browsers/QuickTime.
    graph.append(f"[{last}]format=yuv420p[vout]")
    return input_args, ";".join(graph), "vout"


def prune_outputs(keep=10):
    """Keep the newest `keep` rendered videos so output/ does not grow forever."""
    try:
        videos = sorted(
            (f for f in os.listdir(OUTPUT_DIR) if f.startswith("popup_video_") and f.endswith(".mp4")),
            key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f)),
            reverse=True,
        )
        for stale in videos[keep:]:
            try:
                os.remove(os.path.join(OUTPUT_DIR, stale))
            except OSError:
                pass
    except OSError:
        pass


def create_overlay_video(video_path, transcript, style_config, temp_dir=None, progress_callback=None):
    """
    Render `video_path` with rotating Pop-Up Video bubbles.

    Returns (output_path, popup_count, facts) where `facts` describes every
    pop-up (start time, trivia text, bubble color, slide count) so the UI can
    show exactly what was added.

    The FFmpeg pass degrades gracefully: if the animated (loop + fade) graph is
    rejected by the available build, it retries with static overlays instead of
    failing the whole job.
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(OUTPUT_DIR, f"popup_video_{timestamp}.mp4")

        max_popups = int(style_config.get("max_popups", 5))
        popup_duration = float(style_config.get("duration", 4.0))
        bubble_style = style_config.get("bubble_style", "MTV Classic")
        animated = bool(style_config.get("animated", True))

        segments = select_segments(transcript, max_popups)
        if not segments:
            raise Exception("No transcript segments available for overlay")

        (v_width, v_height), video_duration = probe_video(video_path)

        if temp_dir is None:
            temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)

        colors = STYLE_PALETTES.get(bubble_style, STYLE_PALETTES["MTV Classic"])

        reset_llm_budget()
        bubbles, facts = [], []

        for index, segment in enumerate(segments):
            if progress_callback:
                progress_callback(index, len(segments))

            trivia = generate_trivia_ollama(segment.get('text', ''))
            slides = split_text_into_slides(trivia, max_chars_per_slide=SLIDE_MAX_CHARS)
            num_slides = max(len(slides), 1)
            slide_dur = max(MIN_SLIDE_SECONDS, popup_duration / num_slides)
            total_dur = slide_dur * num_slides

            seg_start = float(segment.get('start', 0.0) or 0.0)
            if video_duration:
                if seg_start > video_duration - 1.0:
                    continue  # too late in the video to be seen
                seg_start = min(seg_start, max(video_duration - total_dur - 0.2, 0.0))
            seg_start = max(seg_start, 0.0)

            color = colors[index % len(colors)]
            facts.append({
                "index": index + 1,
                "start": round(seg_start, 2),
                "text": trivia,
                "color": color,
                "slides": num_slides,
            })

            for slide_idx, slide_text in enumerate(slides):
                start = seg_start + slide_idx * slide_dur
                end = start + slide_dur
                png_path = os.path.join(temp_dir, f"bubble_{index}_slide_{slide_idx}.png")
                b_w, b_h = generate_bubble_image(
                    title=STYLE_TITLE,
                    text=slide_text,
                    style_name=bubble_style,
                    color_hex=color,
                    v_width=v_width,
                    v_height=v_height,
                    output_path=png_path,
                    slide_idx=slide_idx + 1,
                    total_slides=num_slides,
                )
                x, y = placement_for(index, v_width, v_height, b_w, b_h)
                bubbles.append({
                    "png": png_path, "w": b_w, "h": b_h,
                    "start": start, "end": end, "x": x, "y": y,
                })

        if not bubbles:
            raise Exception("No pop-ups fit inside the video timeline")

        attempts = [True, False] if animated else [False]
        last_error = "unknown error"
        for use_animation in attempts:
            input_args, graph, out_label = build_overlay_graph(
                v_width, v_height, bubbles, animated=use_animation
            )
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video_path] + input_args + [
                "-filter_complex", graph,
                "-map", f"[{out_label}]",
                "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                "-y", output_path,
            ]
            timeout = max(300, int((video_duration or 180) * 20) + 60)
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                raise Exception("FFmpeg timeout - rendering took longer than expected")

            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) >= 1000:
                prune_outputs()
                return output_path, len(facts), facts

            last_error = (result.stderr or "").strip()[-400:] or f"ffmpeg exited with code {result.returncode}"
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass

        raise Exception(f"FFmpeg overlay processing failed: {last_error}")

    except Exception as exc:
        message = str(exc)
        if message.startswith(("FFmpeg", "Overlay creation failed", "No ")):
            raise
        raise Exception(f"Overlay creation failed: {message}")


def _binary_available(name, version_args=("--version",)):
    """True when `name` resolves on PATH and responds to its version flag."""
    executable = shutil.which(name)
    if not executable:
        return False
    try:
        result = subprocess.run([executable, *version_args], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _module_available(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


_DEPS_CACHE = {"checked_at": 0.0, "deps": None}


def check_dependencies(force=False):
    """
    Probe system binaries/services, cached briefly.

    Streamlit re-runs the whole script on every interaction, so the uncached
    version spawned yt-dlp/ffmpeg and hit the Ollama API on every slider drag,
    which made the app feel frozen. Results are reused for a few seconds.
    """
    now = time.time()
    if not force and _DEPS_CACHE["deps"] and now - _DEPS_CACHE["checked_at"] < OLLAMA_HEALTH_TTL:
        return dict(_DEPS_CACHE["deps"])

    header_font, body_font = find_fonts()
    deps = {
        "yt-dlp": _binary_available("yt-dlp"),
        "ffmpeg": _binary_available("ffmpeg", ("-version",)),
        "ffprobe": _binary_available("ffprobe", ("-version",)),
        "fonts": bool(header_font or body_font),
        "Pillow": _module_available("PIL"),
        "youtube-transcript-api": _module_available("youtube_transcript_api"),
        "Ollama (optional)": ollama_available(force=force),
    }
    _DEPS_CACHE["checked_at"] = now
    _DEPS_CACHE["deps"] = dict(deps)
    return deps


# ─── Streamlit UI ───────────────────────────────────────────────────────────

PREVIEW_TEXT = "Bubble text auto-fits every bubble - no clipping, ever!"

SAMPLE_URLS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Astley - Never Gonna Give You Up
    "https://www.youtube.com/watch?v=L_jWHffIx5E",  # Smash Mouth - All Star
    "https://www.youtube.com/watch?v=fJ9rUzIMcZQ",  # Queen - Bohemian Rhapsody
]

APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* Hero banner */
.pv-hero {
    background: linear-gradient(120deg, #FF6B6B 0%, #FF9FF3 34%, #4ECDC4 68%, #45B7D1 100%);
    border-radius: 24px;
    padding: 28px 32px 26px 32px;
    color: #fff;
    box-shadow: 0 20px 45px -22px rgba(0, 0, 0, .6);
    margin-bottom: 4px;
}
.pv-hero h1 {
    font-family: 'Archivo Black', 'Inter', sans-serif;
    font-size: 2.3rem;
    line-height: 1.1;
    margin: 0 0 8px 0;
    letter-spacing: .4px;
    text-shadow: 0 3px 0 rgba(0, 0, 0, .16);
}
.pv-hero p { margin: 0; font-size: 1.02rem; opacity: .96; }
.pv-hero .pv-pill {
    display: inline-block; margin-top: 14px; padding: 5px 13px;
    border-radius: 999px; background: rgba(255, 255, 255, .24);
    font-size: .78rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
}

/* Palette swatches */
.pv-swatches { display: flex; gap: 6px; flex-wrap: wrap; margin: 2px 0 12px 0; }
.pv-swatch {
    width: 24px; height: 24px; border-radius: 8px;
    box-shadow: inset 0 0 0 2px rgba(0, 0, 0, .16), 0 1px 2px rgba(0, 0, 0, .18);
}

/* Compact dependency status list */
.pv-status { list-style: none; padding: 0; margin: 0; }
.pv-status li {
    display: flex; align-items: center; gap: 9px;
    padding: 5px 0; font-size: .88rem;
}
.pv-dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; }
.pv-dot-ok   { background: #2EB872; box-shadow: 0 0 0 3px rgba(46, 184, 114, .22); }
.pv-dot-warn { background: #F5A623; box-shadow: 0 0 0 3px rgba(245, 166, 35, .22); }
.pv-dot-bad  { background: #E5484D; box-shadow: 0 0 0 3px rgba(229, 72, 77, .22); }

/* Pop-up fact summary rows */
.pv-fact {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 9px 12px; margin-bottom: 6px;
    background: rgba(127, 127, 127, .08); border-radius: 12px; font-size: .9rem;
}
.pv-fact-time { font-variant-numeric: tabular-nums; font-weight: 700; min-width: 44px; opacity: .72; }
.pv-fact-swatch {
    width: 12px; height: 12px; border-radius: 4px; margin-top: 5px;
    box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .3);
}

/* Chrome polish */
div[data-testid="stMetric"] {
    background: rgba(127, 127, 127, .08);
    border-radius: 14px; padding: 10px 14px;
}
.stButton > button, div[data-testid="stDownloadButton"] > button { border-radius: 999px; font-weight: 600; }
.stProgress > div > div > div > div { background: linear-gradient(90deg, #FF6B6B, #4ECDC4, #45B7D1); }
</style>
"""


def format_clock(seconds):
    """Format seconds as m:ss for the pop-up timeline."""
    try:
        total = int(max(float(seconds), 0))
    except (TypeError, ValueError):
        total = 0
    return f"{total // 60}:{total % 60:02d}"


def status_panel_html(deps):
    """Render the dependency list as compact colored status rows."""
    rows = []
    for name, ok in deps.items():
        optional = "optional" in name.lower()
        css = "pv-dot-ok" if ok else ("pv-dot-warn" if optional else "pv-dot-bad")
        suffix = "" if ok else (" — using fallback" if optional else " — missing")
        rows.append(f'<li><span class="pv-dot {css}"></span>{html.escape(name)}{html.escape(suffix)}</li>')
    return f'<ul class="pv-status">{"".join(rows)}</ul>'


def swatch_row_html(style_name):
    palette = STYLE_PALETTES.get(style_name, STYLE_PALETTES["MTV Classic"])
    chips = "".join(f'<span class="pv-swatch" style="background:{color}"></span>' for color in palette)
    return f'<div class="pv-swatches">{chips}</div>'


def main():
    st.markdown(APP_CSS, unsafe_allow_html=True)

    st.markdown("""
    <div class="pv-hero">
        <h1>🎬 PopUp Video Generator</h1>
        <p>Turn any YouTube video into an MTV-style Pop-Up Video with AI-generated trivia bubbles.</p>
        <span class="pv-pill">Local AI • FFmpeg overlays • Docker-ready</span>
    </div>
    """, unsafe_allow_html=True)
    st.write("")

    deps = check_dependencies()
    missing_critical = [name for name, ok in deps.items() if not ok and "optional" not in name.lower()]

    if missing_critical:
        st.error(f"❌ Missing critical dependencies: {', '.join(missing_critical)}")
        st.info("""
        **Run the diagnostic/deployment script to fix:**
        ```powershell
        ./diagnose.ps1
        ```
        """)
        if st.button("🔄 Refresh Status"):
            check_dependencies(force=True)
            st.rerun()
        return

    # ── Sidebar: settings + live preview ────────────────────────────────────
    with st.sidebar:
        st.header("⚙️ Pop-Up Settings")

        bubble_style = st.selectbox(
            "Bubble style",
            list(STYLE_PALETTES.keys()),
            help="Each style auto-picks text colors for contrast, so facts are always readable.",
        )
        st.markdown(swatch_row_html(bubble_style), unsafe_allow_html=True)

        max_popups = st.slider("Max pop-ups", 3, 10, 5)
        popup_duration = st.slider("Pop-up duration (sec per fact)", 2, 8, 4)
        animated = st.toggle("Animated pop-in", value=True,
                             help="Fade + float each bubble. Turn off for maximum FFmpeg compatibility.")

        st.header("🎈 Live Bubble Preview")
        st.caption("Exactly what gets baked into the video:")
        try:
            st.image(render_preview_image(bubble_style), use_column_width=True)
        except Exception as exc:
            st.warning(f"Preview unavailable: {exc}")

        st.header("📊 System Status")
        st.markdown(status_panel_html(deps), unsafe_allow_html=True)
        if st.button("🔄 Re-check"):
            check_dependencies(force=True)
            st.rerun()

    # ── Main content ────────────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])

    with col1:
        st.header("📹 Video Input")

        selected_sample = st.selectbox(
            "Or try a sample video:",
            [""] + SAMPLE_URLS,
            format_func=lambda x: "Choose sample video..." if x == "" else x.split("=")[-1],
        )

        youtube_url = st.text_input(
            "YouTube URL",
            value=selected_sample,
            placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            key=f"url_input_{selected_sample}",
        )

        video_id = extract_video_id(youtube_url) if youtube_url else None

        if youtube_url.strip() and not validate_youtube_url(youtube_url):
            st.error("❌ That doesn't look like a YouTube link. Try a youtube.com or youtu.be URL.")
        elif video_id:
            st.success(f"✅ Video detected: `{video_id}`")
            if st.button("🚀 Generate PopUp Video", type="primary", use_container_width=True):
                process_video(youtube_url, video_id, max_popups, popup_duration, bubble_style, animated)
        else:
            st.caption("Paste a YouTube link above to get started.")

    with col2:
        st.metric("Ready for processing", "100%" if not missing_critical else "0%")

        if os.path.exists(OUTPUT_DIR):
            video_files = sorted(
                (f for f in os.listdir(OUTPUT_DIR) if f.endswith(".mp4")), reverse=True
            )
            st.metric("Generated videos", len(video_files))

            if video_files:
                st.subheader("📥 Recent videos")
                for video_file in video_files[:3]:
                    file_path = os.path.join(OUTPUT_DIR, video_file)
                    file_size = os.path.getsize(file_path) / (1024 * 1024)
                    with open(file_path, 'rb') as handle:
                        st.download_button(
                            f"📹 {video_file[:20]}… ({file_size:.1f}MB)",
                            data=handle.read(),
                            file_name=video_file,
                            mime="video/mp4",
                            key=f"recent_{video_file}",
                        )


def process_video(url, video_id, max_popups, popup_duration, bubble_style, animated=True):
    """Run the full download → transcript → trivia → overlay pipeline."""
    progress_bar = st.progress(0)
    status_text = st.empty()
    temp_dir = None

    try:
        # Step 1: Download
        status_text.text("🎬 Downloading video from YouTube…")
        progress_bar.progress(15)
        temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
        video_path = download_video(url, temp_dir, video_id=video_id)
        progress_bar.progress(35)

        (v_width, v_height), duration = probe_video(video_path)
        size_mb = os.path.getsize(video_path) / (1024 * 1024)
        detail = f"📼 {os.path.basename(video_path)} • {v_width}×{v_height} • {size_mb:.1f} MB"
        if duration:
            detail += f" • {format_clock(duration)}"
        st.caption(detail)
        progress_bar.progress(40)

        # Step 2: Transcript
        status_text.text("📝 Extracting transcript…")
        transcript = fetch_transcript(video_id, duration_hint=duration)
        progress_bar.progress(50)
        st.caption(f"📝 {len(transcript)} transcript segments ready")

        # Step 3: Trivia + overlays
        status_text.text("🧠 Writing trivia and rendering bubbles…")

        def on_progress(done, total):
            total = max(total, 1)
            progress_bar.progress(min(50 + int(45 * (done / total)), 95))
            status_text.text(f"🧠 Rendering bubble {done + 1} of {total}…")

        output_file, popup_count, facts = create_overlay_video(
            video_path,
            transcript,
            {
                "max_popups": max_popups,
                "duration": popup_duration,
                "bubble_style": bubble_style,
                "animated": animated,
            },
            temp_dir=temp_dir,
            progress_callback=on_progress,
        )

        progress_bar.progress(100)
        status_text.text("✅ PopUp video completed!")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Pop-ups added", popup_count)
        with c2:
            st.metric("File size", f"{os.path.getsize(output_file) / (1024 * 1024):.1f} MB")
        with c3:
            st.metric("Style", bubble_style)

        st.success("🎉 Video created successfully!")
        st.video(output_file)

        if facts:
            with st.expander(f"📝 Trivia added ({len(facts)} pop-ups)", expanded=False):
                rows = "".join(
                    '<div class="pv-fact">'
                    f'<span class="pv-fact-time">{format_clock(fact["start"])}</span>'
                    f'<span class="pv-fact-swatch" style="background:{fact["color"]}"></span>'
                    f'<span>{html.escape(fact["text"])}</span>'
                    '</div>'
                    for fact in facts
                )
                st.markdown(rows, unsafe_allow_html=True)

        with open(output_file, 'rb') as handle:
            st.download_button(
                "📹 Download PopUp Video",
                data=handle.read(),
                file_name=os.path.basename(output_file),
                mime="video/mp4",
                key="download_result",
            )

        st.balloons()

    except Exception as exc:
        error_msg = str(exc)
        st.error(f"❌ Processing failed: {error_msg}")

        if "Download failed" in error_msg or "Download" in error_msg:
            st.info("💡 **Download tip:** try a public video without region or age restrictions.")
        elif "Transcript" in error_msg:
            st.info("💡 **Transcript tip:** videos with captions work best — caption-less videos still get pop-ups.")
        elif "FFmpeg" in error_msg or "Overlay" in error_msg:
            st.info("💡 **Overlay tip:** run `./diagnose.ps1`, or turn off 'Animated pop-in' for maximum compatibility.")
        else:
            st.info("💡 **Tip:** run `./diagnose.ps1` to check containers, network, yt-dlp and FFmpeg.")

        status_text.text("❌ Processing failed")

    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

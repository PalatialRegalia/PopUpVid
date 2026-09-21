import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add lightweight mock for streamlit if not installed
if 'streamlit' not in sys.modules:
    try:
        import streamlit
    except ImportError:
        mock_st = MagicMock()
        mock_st.set_page_config = MagicMock()
        sys.modules['streamlit'] = mock_st

# Add root folder to sys.path so app can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import (
    build_bubble_image,
    build_fallback_transcript,
    build_overlay_graph,
    escape_drawtext,
    extract_video_id,
    find_font,
    find_fonts,
    generate_bubble_image,
    generate_trivia_ollama,
    hex_to_rgba,
    pick_contrast_color,
    relative_luminance,
    sanitize_trivia_text,
    select_segments,
    shade_color,
    split_text_into_slides,
    strip_think_blocks,
    validate_youtube_url,
    _wrap_text_px,
)


class TestYouTubeUrlValidation(unittest.TestCase):
    """Test YouTube URL validation logic"""

    def test_valid_standard_url(self):
        self.assertTrue(validate_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_valid_short_url(self):
        self.assertTrue(validate_youtube_url("https://youtu.be/dQw4w9WgXcQ"))

    def test_valid_embed_url(self):
        self.assertTrue(validate_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ"))

    def test_valid_without_protocol(self):
        self.assertTrue(validate_youtube_url("www.youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_valid_mobile_and_music_hosts(self):
        self.assertTrue(validate_youtube_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(validate_youtube_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_valid_shorts_and_live(self):
        self.assertTrue(validate_youtube_url("https://www.youtube.com/shorts/dQw4w9WgXcQ"))
        self.assertTrue(validate_youtube_url("https://www.youtube.com/live/dQw4w9WgXcQ"))

    def test_invalid_urls(self):
        self.assertFalse(validate_youtube_url("https://vimeo.com/123456"))
        self.assertFalse(validate_youtube_url("https://google.com"))
        self.assertFalse(validate_youtube_url(""))
        self.assertFalse(validate_youtube_url(None))


class TestVideoIdExtraction(unittest.TestCase):
    """Test video ID extraction from various YouTube URL formats"""

    def test_standard_watch_url(self):
        self.assertEqual(extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_short_url(self):
        self.assertEqual(extract_video_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_embed_url(self):
        self.assertEqual(extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_url_with_extra_params(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=shared&t=10"),
            "dQw4w9WgXcQ",
        )

    def test_param_before_v(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?list=PL123&v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_shorts_live_mobile_and_music(self):
        self.assertEqual(extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(extract_video_id("https://m.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(extract_video_id("https://music.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_bare_video_id(self):
        self.assertEqual(extract_video_id("dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_invalid_or_empty(self):
        self.assertIsNone(extract_video_id("https://example.com"))
        self.assertIsNone(extract_video_id(""))
        self.assertIsNone(extract_video_id(None))
        self.assertIsNone(extract_video_id("https://www.youtube.com/watch?v=tooshort"))


class TestFFmpegEscaping(unittest.TestCase):
    """Test drawtext escaping helper (kept for backwards compatibility)"""

    def test_single_quotes(self):
        self.assertIn("\\'", escape_drawtext("It's a test"))

    def test_colons(self):
        self.assertIn("\\:", escape_drawtext("Fact: 100%"))

    def test_backslashes(self):
        self.assertIn("\\\\", escape_drawtext("path\\to\\file"))

    def test_newlines(self):
        self.assertIn("\\n", escape_drawtext("Line1\nLine2"))


class TestFontFinder(unittest.TestCase):
    """Test system/bundled font finder helpers"""

    def test_find_font_returns_string_or_none(self):
        font = find_font()
        self.assertTrue(font is None or (isinstance(font, str) and os.path.exists(font)))

    def test_bundled_fonts_are_used(self):
        """The repo ships fonts, so resolution must never fail in a checkout."""
        header, body = find_fonts()
        self.assertIsNotNone(body)
        self.assertTrue(os.path.exists(body))
        self.assertTrue(header is None or os.path.exists(header))


class TestTriviaSanitization(unittest.TestCase):
    """Trivia must come out bubble-ready: no reasoning, emoji, or markdown."""

    def test_strips_think_blocks(self):
        raw = " thinkingThe user wants a fact about 1996.</think>Pop-Up Video premiered in 1996."
        self.assertEqual(sanitize_trivia_text(raw), "Pop-Up Video premiered in 1996.")

    def test_strips_truncated_think_block(self):
        raw = "reasoning noise </think>The video was shot in one take."
        self.assertEqual(strip_think_blocks(raw).strip(), "The video was shot in one take.")

    def test_strips_prefixes_and_markdown(self):
        self.assertEqual(
            sanitize_trivia_text("Did you know: **MTV** launched in 1981!"),
            "MTV launched in 1981!",
        )
        self.assertEqual(sanitize_trivia_text("Fact: - the budget was huge"), "the budget was huge")

    def test_removes_unsupported_glyphs(self):
        cleaned = sanitize_trivia_text("Great song 🎵🎸 from Japan 東京 in 1985!")
        self.assertNotIn("🎵", cleaned)
        self.assertNotIn("東", cleaned)
        self.assertIn("1985", cleaned)

    def test_normalizes_smart_quotes_and_dashes(self):
        cleaned = sanitize_trivia_text("The \u201cvideo\u201d was shot in one take \u2013 no cuts")
        self.assertIn('"video"', cleaned)
        self.assertIn("-", cleaned)
        self.assertNotIn("\u201c", cleaned)

    def test_trims_at_word_boundary(self):
        long_text = "word " * 60
        cleaned = sanitize_trivia_text(long_text.strip(), max_len=40)
        self.assertLessEqual(len(cleaned), 41)  # 40 + ellipsis
        self.assertFalse(cleaned.rstrip("\u2026").endswith("wor"))

    def test_handles_none_and_empty(self):
        self.assertEqual(sanitize_trivia_text(None), "")
        self.assertEqual(sanitize_trivia_text("   "), "")


class TestColorContrast(unittest.TestCase):
    """Bubble text color must always contrast with the bubble fill."""

    def test_luminance_bounds(self):
        self.assertAlmostEqual(relative_luminance((0, 0, 0)), 0.0, places=5)
        self.assertAlmostEqual(relative_luminance((255, 255, 255)), 1.0, places=5)

    def test_dark_text_on_bright_fills(self):
        for hex_color in ("#FECA57", "#4ECDC4", "#FFFF00", "#96CEB4"):
            color = hex_to_rgba(hex_color, 242)
            chosen = pick_contrast_color(color)
            self.assertLessEqual(relative_luminance(chosen[:3]), 0.2, hex_color)

    def test_light_text_on_dark_fills(self):
        chosen = pick_contrast_color((9, 12, 26, 216))
        self.assertEqual(chosen, (255, 255, 255, 255))

    def test_shade_color_darkens(self):
        shaded = shade_color((200, 100, 50, 255), 0.5)
        self.assertEqual(shaded, (100, 50, 25, 255))

    def test_hex_to_rgba_variants(self):
        self.assertEqual(hex_to_rgba("#FF6B6B"), (255, 107, 107, 235))
        self.assertEqual(hex_to_rgba("#F00", 200), (255, 0, 0, 200))
        self.assertEqual(hex_to_rgba("nonsense", 10), (255, 107, 107, 10))


class TestSlideSplitting(unittest.TestCase):
    """Facts are split into readable, balanced slides."""

    def test_short_text_single_slide(self):
        self.assertEqual(split_text_into_slides("MTV launched in 1981!"), ["MTV launched in 1981!"])

    def test_respects_max_chars(self):
        slides = split_text_into_slides("one two three four five six seven eight nine ten", 12)
        for slide in slides:
            self.assertLessEqual(len(slide), 12, slide)

    def test_never_ends_on_lone_word(self):
        slides = split_text_into_slides("Each bubble popped on screen with a signature sound", 48)
        self.assertEqual(len(slides), 2)
        self.assertGreater(len(slides[-1].split()), 1)

    def test_caps_number_of_slides(self):
        long_text = " ".join(["factual"] * 40)
        slides = split_text_into_slides(long_text, 30, max_slides=3)
        self.assertEqual(len(slides), 3)

    def test_empty_text(self):
        self.assertEqual(split_text_into_slides(""), [""])



class TestBubbleRendering(unittest.TestCase):
    """The bubble renderer must fit text, stay inside the frame, and differ per style."""

    LONG_FACT = "Original episodes took 6 weeks of deep research and every claim was fact checked by hand"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _render(self, style, text, vw=1280, vh=720):
        path = os.path.join(self.tmp, f"{style.replace(' ', '_')}.png")
        size = generate_bubble_image("POP-UP FACT", text, style, "#FF6B6B", vw, vh, path,
                                     slide_idx=1, total_slides=2)
        return path, size

    def test_renders_every_style(self):
        for style in ("MTV Classic", "Neon Glow", "Retro Rainbow"):
            path, size = self._render(style, "MTV launched Pop-Up Video in 1996!")
            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 500)
            self.assertGreater(size[0], 100)
            self.assertGreater(size[1], 50)

    def test_bubble_never_exceeds_video_width(self):
        for vw, vh in ((854, 480), (1280, 720), (1920, 1080)):
            _, size = self._render("MTV Classic", self.LONG_FACT, vw, vh)
            self.assertLessEqual(size[0], vw * 0.92, f"{vw}x{vh}")

    def test_bubble_scales_with_resolution(self):
        _, small = self._render("MTV Classic", self.LONG_FACT, 854, 480)
        _, large = self._render("MTV Classic", self.LONG_FACT, 1920, 1080)
        self.assertGreater(large[0], small[0])
        self.assertGreater(large[1], small[1])

    def test_wrapping_never_exceeds_budget(self):
        font_path = find_fonts()[1]
        from app import _load_font, sanitize_trivia_text as clean
        font = _load_font(font_path, 22)
        for text in (self.LONG_FACT, "word " * 40, "Supercalifragilisticexpialidociousandthensomeextralongword"):
            for line in _wrap_text_px(clean(text), font, 500, max_lines=3):
                self.assertLessEqual(font.getlength(line), 500, line)

    def test_long_text_grows_height_not_width(self):
        _, short = self._render("MTV Classic", "Short fact")
        _, long = self._render("MTV Classic", self.LONG_FACT)
        self.assertGreater(long[1], short[1])

    def test_preview_matches_pipeline_renderer(self):
        from app import render_preview_image
        img = render_preview_image("Neon Glow")
        self.assertEqual(img.mode, "RGBA")
        self.assertGreater(img.size[0], 100)

    def test_rendered_bubble_has_visible_pixels(self):
        img = build_bubble_image("POP-UP FACT", "Readable trivia", "MTV Classic", "#FECA57", 1280, 720)
        alpha = img.getchannel("A")
        self.assertGreater(alpha.getextrema()[1], 200)



class TestFallbackTranscript(unittest.TestCase):
    """Caption-less videos still get pop-ups across their whole duration."""

    def test_spreads_across_duration(self):
        segments = build_fallback_transcript(600)
        self.assertGreater(len(segments), 10)
        self.assertLess(segments[-1]['start'], 600)
        self.assertGreater(segments[-1]['start'], 420)

    def test_default_horizon_is_bounded(self):
        segments = build_fallback_transcript(None)
        self.assertTrue(segments)
        self.assertLessEqual(len(segments), 40)

    def test_short_video_still_gets_a_segment(self):
        self.assertTrue(build_fallback_transcript(8))

    def test_texts_vary(self):
        texts = {s['text'] for s in build_fallback_transcript(600)}
        self.assertGreater(len(texts), 3)


class TestTranscriptSelection(unittest.TestCase):
    """Pop-ups are spread evenly instead of clustering at the start."""

    def _transcript(self, count):
        return [{'text': f'segment {i}', 'start': float(i * 5), 'duration': 4.0} for i in range(count)]

    def test_returns_all_when_fewer_than_requested(self):
        self.assertEqual(len(select_segments(self._transcript(3), 5)), 3)

    def test_spreads_evenly(self):
        picked = select_segments(self._transcript(100), 5)
        self.assertEqual(len(picked), 5)
        self.assertEqual(picked[0]['text'], 'segment 0')
        self.assertEqual(picked[-1]['text'], 'segment 99')

    def test_skips_blank_segments(self):
        transcript = [{'text': '', 'start': 0.0}, {'text': 'ok', 'start': 5.0}]
        picked = select_segments(transcript, 5)
        self.assertEqual(len(picked), 1)

    def test_empty_transcript(self):
        self.assertEqual(select_segments([], 5), [])


class TestOverlayGraph(unittest.TestCase):
    """The FFmpeg graph must be finite, chain overlays, and degrade gracefully."""

    def _bubbles(self, count=2):
        return [
            {'png': f'/tmp/b{i}.png', 'w': 600, 'h': 150,
             'start': float(i * 4 + 1), 'end': float(i * 4 + 4),
             'x': 100 + i * 20, 'y': 300}
            for i in range(count)
        ]

    def test_animated_graph_is_bounded_and_faded(self):
        inputs, graph, out_label = build_overlay_graph(1280, 720, self._bubbles(3), animated=True)
        # Unbounded loops made FFmpeg encode forever: every looped input is -t'd.
        self.assertEqual(inputs.count('-loop'), 3)
        self.assertEqual(inputs.count('-t'), 3)
        self.assertEqual(graph.count('fade=t=in'), 3)
        self.assertEqual(graph.count('fade=t=out'), 3)
        self.assertEqual(graph.count('overlay='), 3)
        self.assertIn('enable=\'between(t,', graph)
        self.assertIn('format=yuv420p[vout]', graph)
        self.assertEqual(out_label, 'vout')

    def test_static_graph_has_no_loops(self):
        inputs, graph, _ = build_overlay_graph(1280, 720, self._bubbles(2), animated=False)
        self.assertNotIn('-loop', inputs)
        self.assertNotIn('fade=', graph)
        self.assertEqual(graph.count('overlay='), 2)

    def test_labels_are_unique(self):
        _, graph, _ = build_overlay_graph(1280, 720, self._bubbles(4), animated=True)
        for label in ('b1', 'b2', 'b3', 'b4', 'v1', 'v2', 'v3', 'v4'):
            self.assertIn(f'[{label}]', graph)



class TestOllamaTrivia(unittest.TestCase):
    """Live LLM trivia is sanitized, and every failure path falls back safely."""

    def setUp(self):
        import app
        app._OLLAMA_HEALTH = {"checked_at": 0.0, "ok": False}
        app.reset_llm_budget()

    def test_uses_llm_answer_and_strips_reasoning(self):
        tags = MagicMock(status_code=200)
        generate = MagicMock(status_code=200)
        generate.json.return_value = {
            "response": " Thinking about it... \nThe video was shot in a single take."
        }
        with patch('app.requests.get', return_value=tags), \
             patch('app.requests.post', return_value=generate):
            fact = generate_trivia_ollama("some lyric")
        self.assertEqual(fact, "The video was shot in a single take.")

    def test_falls_back_when_ollama_unreachable(self):
        with patch('app.requests.get', side_effect=OSError("connection refused")):
            fact = generate_trivia_ollama("some lyric")
        self.assertIsInstance(fact, str)
        self.assertGreater(len(fact), 5)

    def test_falls_back_on_error_response(self):
        tags = MagicMock(status_code=200)
        bad = MagicMock(status_code=500)
        with patch('app.requests.get', return_value=tags), \
             patch('app.requests.post', return_value=bad):
            fact = generate_trivia_ollama("lyric")
        self.assertGreater(len(fact), 5)

    def test_ignores_refusals(self):
        tags = MagicMock(status_code=200)
        refusal = MagicMock(status_code=200)
        refusal.json.return_value = {"response": "I'm sorry, I cannot help with that."}
        with patch('app.requests.get', return_value=tags), \
             patch('app.requests.post', return_value=refusal):
            fact = generate_trivia_ollama("lyric")
        self.assertNotIn("sorry", fact.lower())


class TestEndToEndOverlay(unittest.TestCase):
    """Full FFmpeg render of a tiny synthetic video (skipped without FFmpeg)."""

    @classmethod
    def setUpClass(cls):
        if not (shutil.which('ffmpeg') and shutil.which('ffprobe')):
            raise unittest.SkipTest('ffmpeg/ffprobe not available')
        cls.tmp = tempfile.mkdtemp()
        cls.video = os.path.join(cls.tmp, 'source.mp4')
        result = subprocess.run(
            ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
             '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=6',
             '-f', 'lavfi', '-i', 'sine=duration=6',
             '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-shortest', cls.video],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0 or not os.path.exists(cls.video):
            raise unittest.SkipTest('could not synthesise a test video')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, 'tmp', ''), ignore_errors=True)

    def test_pipeline_produces_playable_video_with_bubbles(self):
        import app
        transcript = [
            {'text': 'intro', 'start': 1.0, 'duration': 4.0},
            {'text': 'chorus', 'start': 3.5, 'duration': 4.0},
        ]
        with patch('app.generate_trivia_ollama', return_value="MTV launched Pop-Up Video in 1996!"):
            output, count, facts = app.create_overlay_video(
                self.video,
                transcript,
                {'max_popups': 2, 'duration': 2.5, 'bubble_style': 'MTV Classic', 'animated': True},
                temp_dir=os.path.join(self.tmp, 'work'),
            )
        try:
            self.assertTrue(os.path.exists(output))
            self.assertGreater(os.path.getsize(output), 1000)
            self.assertEqual(count, len(facts))
            self.assertEqual(count, 2)

            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-show_entries', 'stream=codec_name,pix_fmt', '-of', 'default=noprint_wrappers=1', output],
                capture_output=True, text=True, timeout=30,
            )
            info = probe.stdout
            self.assertIn('yuv420p', info)
            self.assertIn('h264', info)
            self.assertIn('aac', info)
            # Rendering must be finite (bounded loops) and match the source length.
            self.assertAlmostEqual(float(info.split('duration=')[1].split()[0]), 6.0, delta=0.15)
        finally:
            if os.path.exists(output):
                os.remove(output)

    def test_static_fallback_also_renders(self):
        import app
        transcript = [{'text': 'intro', 'start': 1.0, 'duration': 4.0}]
        with patch('app.generate_trivia_ollama', return_value="Pop-Up Video premiered in 1996"):
            output, count, _ = app.create_overlay_video(
                self.video,
                transcript,
                {'max_popups': 1, 'duration': 2.5, 'bubble_style': 'Retro Rainbow', 'animated': False},
                temp_dir=os.path.join(self.tmp, 'work2'),
            )
        try:
            self.assertTrue(os.path.exists(output))
            self.assertGreater(os.path.getsize(output), 1000)
            self.assertEqual(count, 1)
        finally:
            if os.path.exists(output):
                os.remove(output)


class TestFallbackTrivia(unittest.TestCase):
    """Curated fallback facts stay short and varied."""

    def test_returns_non_empty_string(self):
        from app import generate_fallback_trivia
        fact = generate_fallback_trivia()
        self.assertIsInstance(fact, str)
        self.assertGreater(len(fact), 5)

    def test_variety(self):
        from app import generate_fallback_trivia
        facts = {generate_fallback_trivia() for _ in range(30)}
        self.assertGreater(len(facts), 1)

    def test_facts_fit_a_bubble(self):
        from app import generate_fallback_trivia
        for _ in range(30):
            self.assertLessEqual(len(sanitize_trivia_text(generate_fallback_trivia())), 110)


if __name__ == '__main__':
    unittest.main()


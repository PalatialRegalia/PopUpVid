import os
import sys
import unittest
from unittest.mock import MagicMock

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
    validate_youtube_url,
    extract_video_id,
    escape_drawtext,
    generate_fallback_trivia,
    find_font
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
        self.assertEqual(extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=shared&t=10"), "dQw4w9WgXcQ")

    def test_invalid_or_empty(self):
        self.assertIsNone(extract_video_id("https://example.com"))
        self.assertIsNone(extract_video_id(""))
        self.assertIsNone(extract_video_id(None))


class TestFFmpegEscaping(unittest.TestCase):
    """Test drawtext escaping helper"""

    def test_single_quotes(self):
        escaped = escape_drawtext("It's a test")
        self.assertIn("\\'", escaped)

    def test_colons(self):
        escaped = escape_drawtext("Fact: 100%")
        self.assertIn("\\:", escaped)

    def test_backslashes(self):
        escaped = escape_drawtext("path\\to\\file")
        self.assertIn("\\\\", escaped)

    def test_newlines(self):
        escaped = escape_drawtext("Line1\nLine2")
        self.assertIn("\\n", escaped)


class TestFallbackTrivia(unittest.TestCase):
    """Test fallback trivia generation"""

    def test_returns_non_empty_string(self):
        fact = generate_fallback_trivia()
        self.assertIsInstance(fact, str)
        self.assertGreater(len(fact), 5)

    def test_variety(self):
        facts = {generate_fallback_trivia() for _ in range(20)}
        self.assertGreater(len(facts), 1)


class TestFontFinder(unittest.TestCase):
    """Test system font finder helper"""

    def test_find_font_returns_string_or_none(self):
        font = find_font()
        self.assertTrue(font is None or (isinstance(font, str) and os.path.exists(font)))


if __name__ == '__main__':
    unittest.main()

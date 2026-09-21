#!/usr/bin/env python3
"""Discover and run the PopUp Video Generator test suite."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


def build_suite():
    loader = unittest.TestLoader()
    from test_app import (  # noqa: E402  (import after sys.path setup)
        TestBubbleRendering,
        TestColorContrast,
        TestEndToEndOverlay,
        TestFallbackTranscript,
        TestFallbackTrivia,
        TestFFmpegEscaping,
        TestFontFinder,
        TestOllamaTrivia,
        TestOverlayGraph,
        TestSlideSplitting,
        TestTranscriptSelection,
        TestTriviaSanitization,
        TestVideoIdExtraction,
        TestYouTubeUrlValidation,
    )

    suite = unittest.TestSuite()
    for case in (
        TestYouTubeUrlValidation,
        TestVideoIdExtraction,
        TestFFmpegEscaping,
        TestFontFinder,
        TestTriviaSanitization,
        TestColorContrast,
        TestSlideSplitting,
        TestBubbleRendering,
        TestFallbackTranscript,
        TestTranscriptSelection,
        TestOverlayGraph,
        TestOllamaTrivia,
        TestFallbackTrivia,
        TestEndToEndOverlay,
    ):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(build_suite())
    sys.exit(not result.wasSuccessful())

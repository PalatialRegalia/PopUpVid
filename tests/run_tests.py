#!/usr/bin/env python3
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from test_app import (
    TestYouTubeUrlValidation,
    TestVideoIdExtraction,
    TestFFmpegEscaping,
    TestFallbackTrivia,
    TestFontFinder
)

if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestYouTubeUrlValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestVideoIdExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestFFmpegEscaping))
    suite.addTests(loader.loadTestsFromTestCase(TestFallbackTrivia))
    suite.addTests(loader.loadTestsFromTestCase(TestFontFinder))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(not result.wasSuccessful())

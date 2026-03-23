#!/usr/bin/env python3
"""Add non-English blocking tests to test_intent_classification.py"""

from pathlib import Path

# Get the directory of this script and resolve the test file path
script_dir = Path(__file__).parent
test_file = script_dir / "test_intent_classification.py"
content = test_file.read_text()

# Add test for non-English blocking after the last test in TestDetectMessageIntent class
old_last_test = '''    def test_various_whitespace_returns_instruction(self):
        """Various whitespace should return instruction."""
        assert detect_message_intent("\\t") == "instruction"
        assert detect_message_intent("\\n") == "instruction"
        assert detect_message_intent("  \\t\\n  ") == "instruction"


class TestIntentPrefixes:'''

new_last_test = '''    def test_various_whitespace_returns_instruction(self):
        """Various whitespace should return instruction."""
        assert detect_message_intent("\\t") == "instruction"
        assert detect_message_intent("\\n") == "instruction"
        assert detect_message_intent("  \\t\\n  ") == "instruction"

    def test_non_english_blocked(self):
        """Non-English messages should be classified as unsupported_language.

        This prevents silent misclassification of non-English text as "instruction".
        The restore message will show [NON-ENGLISH MESSAGE BLOCKED] prefix.
        """
        # Cyrillic (Russian)
        assert detect_message_intent("Исправьте ошибку") == "unsupported_language"
        # Chinese
        assert detect_message_intent("修复这个bug") == "unsupported_language"
        # Japanese
        assert detect_message_intent("バグを修正") == "unsupported_language"
        # Arabic
        assert detect_message_intent("إصلاح الخطأ") == "unsupported_language"
        # Mixed ASCII with non-ASCII characters
        assert detect_message_intent("Fix the bug 🐛") == "unsupported_language"
        # English with emoji (emoji is non-ASCII)
        assert detect_message_intent("Is this working? 👍") == "unsupported_language"

    def test_english_messages_not_blocked(self):
        """English messages (even with special characters) should not be blocked.

        Only non-ASCII character sequences trigger unsupported_language.
        Regular ASCII punctuation should work fine.
        """
        # Standard ASCII punctuation
        assert detect_message_intent("Fix the bug!") == "instruction"
        assert detect_message_intent("Is this working?") == "question"
        # Quotes and special ASCII characters
        assert detect_message_intent('Fix the \\'bug\\' in "module"') == "instruction"
        # Numbers and symbols
        assert detect_message_intent("Test @#$%^&*()") == "instruction"


class TestIntentPrefixes:'''

content = content.replace(old_last_test, new_last_test)

test_file.write_text(content)
print("Added non-English blocking tests")

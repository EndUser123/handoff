#!/usr/bin/env python3
"""Test visual context extraction from transcript."""

import sys
import json
from pathlib import Path

# Add handoff package to path
HANDOFF_PACKAGE = Path(__file__).parent.parent / "core"
sys.path.insert(0, str(HANDOFF_PACKAGE))

from core.hooks.__lib.transcript import TranscriptParser


def test_extract_visual_context():
    """Test that visual context is extracted from synthetic transcript."""

    # Create a synthetic transcript with visual context
    synthetic_entries = [
        {"type": "user", "message": {"content": ["check this screenshot"]}},
        {
            "type": "tool_use",
            "name": "analyze_image",
            "input": {
                "image_source": "screenshot.png",
                "prompt": "What does this show?",
            },
            "result": {"analysis": "Shows a blue console flash"},
        },
        {"type": "user", "message": {"content": ["see, the flash is still happening"]}},
    ]

    # Write synthetic transcript to temp file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in synthetic_entries:
            f.write(json.dumps(entry) + "\n")
        temp_path = f.name

    try:
        parser = TranscriptParser(temp_path)
        visual_context = parser.extract_visual_context()

        print("Visual context extraction test:")
        print(f"  Result: {visual_context}")

        if visual_context:
            print("  ✓ PASS: Visual context extracted")
            print(f"    - Type: {visual_context.get('type')}")
            print(f"    - Description: {visual_context.get('description')[:80]}...")
            user_resp = visual_context.get("user_response")
            if user_resp:
                print(f"    - User response: {user_resp[:80]}...")
            return True
        else:
            print("  ✗ FAIL: No visual context extracted")
            return False
    finally:
        import os

        os.unlink(temp_path)


def test_extract_visual_context_from_screenshot_reference():
    """Test extraction of user's screenshot references."""

    synthetic_entries = [
        {
            "type": "user",
            "message": {
                "content": [
                    "as you can see from the screenshot, the bug is still there"
                ]
            },
        }
    ]

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for entry in synthetic_entries:
            f.write(json.dumps(entry) + "\n")
        temp_path = f.name

    try:
        parser = TranscriptParser(temp_path)
        visual_context = parser.extract_visual_context()

        print("\nScreenshot reference test:")
        print(f"  Result: {visual_context}")

        if visual_context:
            print("  ✓ PASS: Screenshot reference captured")
            print(f"    - Type: {visual_context.get('type')}")
            print(f"    - Description: {visual_context.get('description')[:80]}...")
            return True
        else:
            print("  ✗ FAIL: Screenshot reference not captured")
            return False
    finally:
        import os

        os.unlink(temp_path)


if __name__ == "__main__":
    results = [
        test_extract_visual_context(),
        test_extract_visual_context_from_screenshot_reference(),
    ]

    print(f"\n{'=' * 50}")
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    sys.exit(0 if all(results) else 1)

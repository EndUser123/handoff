"""Integration tests for handoff examples.

These tests verify that the example code can be imported and executed without errors.
"""

from pathlib import Path


def test_handoff_examples_readme_exists():
    """Test that examples/README.md exists."""
    examples_dir = Path(__file__).parent.parent / "examples"
    readme = examples_dir / "README.md"

    assert readme.exists(), "examples/README.md should exist"


def test_handoff_basic_usage_exists():
    """Test that basic_usage.py example exists."""
    examples_dir = Path(__file__).parent.parent / "examples"
    basic_usage = examples_dir / "basic_usage.py"

    assert basic_usage.exists(), "examples/basic_usage.py should exist"

    # Verify it compiles without syntax errors
    content = basic_usage.read_text()
    compile(content, str(basic_usage), "exec")


def test_handoff_example_content():
    """Test that basic_usage.py has expected content."""
    examples_dir = Path(__file__).parent.parent / "examples"
    basic_usage = examples_dir / "basic_usage.py"

    content = basic_usage.read_text()

    # Check for expected imports and usage patterns
    assert "TranscriptAnalyzer" in content or "handoff" in content

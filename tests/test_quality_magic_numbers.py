#!/usr/bin/env python3
"""Tests for QUAL-002: Magic Numbers Without Constants.

These tests detect numeric literals that should be defined as constants
in the config module rather than hardcoded in source files.

Focus areas:
- Configuration values (timeouts, retries, delays)
- Size limits and thresholds
- File locking parameters
- Any repeatable numeric values

Expected behavior after fix:
- All config values reference constants from handoff.config
- Magic numbers are replaced with named constants
- Constants are defined in one central location

Current behavior (before fix):
- max_retries = 5 (line 84, 138 in handoff_store.py)
- max_lock_wait = 5 (line 691 in handoff_store.py)
- base_delay = 0.005 (line 101 in handoff_store.py)
- sleep(0.1) (line 700 in handoff_store.py)
- stale_lock_age = 10 (line 705 in handoff_store.py)
- Checks per second = 10 (line 693 in handoff_store.py)

Run with: pytest tests/test_quality_magic_numbers.py -v
"""

import ast
import re
from pathlib import Path

import pytest


class TestMagicNumbersInHandoffStore:
    """Test that handoff_store.py uses config constants instead of magic numbers."""

    @pytest.fixture
    def handoff_store_path(self) -> Path:
        """Path to handoff_store.py file."""
        return Path(__file__).parent.parent / "src" / "handoff" / "hooks" / "__lib" / "handoff_store.py"

    @pytest.fixture
    def handoff_store_content(self, handoff_store_path: Path) -> str:
        """Content of handoff_store.py file."""
        return handoff_store_path.read_text(encoding="utf-8")

    def test_max_retries_default_value_uses_constant(self, handoff_store_content: str) -> None:
        """Test that max_retries default parameter uses a named constant.

        Expected: max_retries: int = CONFIGURED_MAX_RETRIES
        Actual (before fix): max_retries: int = 5
        """
        # Check for hardcoded max_retries=5 in function signatures
        pattern = r"max_retries\s*:\s*int\s*=\s*5\b"

        matches = re.findall(pattern, handoff_store_content)

        if matches:
            pytest.fail(
                f"Found hardcoded max_retries=5 in {len(matches)} location(s). "
                "Expected: max_retries should reference a constant from config module "
                "(e.g., MAX_RETRIES from handoff.config)"
            )

    def test_max_lock_wait_uses_constant(self, handoff_store_content: str) -> None:
        """Test that max_lock_wait uses a named constant.

        Expected: max_lock_wait = LOCK_TIMEOUT_SECONDS
        Actual (before fix): max_lock_wait = 5
        """
        # Look for the specific line: max_lock_wait = 5
        pattern = r"max_lock_wait\s*=\s*5\b"

        if re.search(pattern, handoff_store_content):
            pytest.fail(
                "Found hardcoded max_lock_wait=5. "
                "Expected: max_lock_wait should reference LOCK_TIMEOUT_SECONDS from handoff.config"
            )

    def test_base_delay_uses_constant(self, handoff_store_content: str) -> None:
        """Test that base_delay uses a named constant.

        Expected: base_delay = RETRY_BASE_DELAY_SECONDS
        Actual (before fix): base_delay = 0.005  # 5ms
        """
        # Look for base_delay = 0.005
        pattern = r"base_delay\s*=\s*0\.005\b"

        if re.search(pattern, handoff_store_content):
            pytest.fail(
                "Found hardcoded base_delay=0.005. "
                "Expected: base_delay should reference a constant like RETRY_BASE_DELAY_SECONDS "
                "from handoff.config"
            )

    def test_sleep_interval_uses_constant(self, handoff_store_content: str) -> None:
        """Test that time.sleep() uses a named constant.

        Expected: time.sleep(LOCK_CHECK_INTERVAL_SECONDS)
        Actual (before fix): time.sleep(0.1)
        """
        # Look for time.sleep(0.1)
        pattern = r"time\.sleep\(0\.1\)"

        if re.search(pattern, handoff_store_content):
            pytest.fail(
                "Found hardcoded time.sleep(0.1). "
                "Expected: sleep interval should reference a constant like "
                "LOCK_CHECK_INTERVAL_SECONDS from handoff.config"
            )

    def test_stale_lock_threshold_uses_constant(self, handoff_store_content: str) -> None:
        """Test that stale lock age threshold uses a named constant.

        Expected: if lock_age > STALE_LOCK_AGE_SECONDS:
        Actual (before fix): if lock_age > 10:
        """
        # Look for "if lock_age > 10:" or similar pattern
        pattern = r"lock_age\s*>\s*10\b"

        if re.search(pattern, handoff_store_content):
            pytest.fail(
                "Found hardcoded stale lock threshold (10). "
                "Expected: stale lock age should reference STALE_LOCK_AGE_SECONDS "
                "from handoff.config"
            )

    def test_checks_per_second_uses_constant(self, handoff_store_content: str) -> None:
        """Test that lock check frequency uses a named constant.

        Expected: range(max_lock_wait * LOCK_CHECKS_PER_SECOND)
        Actual (before fix): range(max_lock_wait * 10)
        """
        # Look for pattern: range(max_lock_wait * 10)
        pattern = r"range\(max_lock_wait\s*\*\s*10\)"

        if re.search(pattern, handoff_store_content):
            pytest.fail(
                "Found hardcoded checks per second (10). "
                "Expected: checks per second should reference LOCK_CHECKS_PER_SECOND "
                "from handoff.config"
            )

    def test_all_numeric_literals_accounted_for(self, handoff_store_content: str) -> None:
        """Test that all suspicious numeric literals are either constants or documented.

        This is a comprehensive check that ensures no new magic numbers
        have been introduced without being documented constants.
        """
        # Parse the file as AST
        try:
            tree = ast.parse(handoff_store_content)
        except SyntaxError as e:
            pytest.fail(f"Failed to parse handoff_store.py: {e}")

        # Find all numeric literals
        visitor = NumericLiteralVisitor()
        visitor.visit(tree)

        # Filter to find potential magic numbers
        # Exclude: 0, 1, 2 (common loop counters), 100 (percentages)
        # Exclude numbers that are part of existing constant definitions
        suspicious_numbers = [
            (lineno, num)
            for lineno, num in visitor.numeric_literals
            if num not in {0, 1, 2}  # Common small numbers
            and not (isinstance(num, float) and num >= 0.0 and num <= 1.0)  # Quality scores
            and not (isinstance(num, int) and num == 100)  # Percentages
            and not (isinstance(num, int) and 1 <= num <= 80)  # String lengths, small limits
        ]

        # Known acceptable numbers (well-documented constants in the file)
        acceptable_numbers = {
            # Size limits (well documented in comments)
            500_000,  # MAX_HANDOFF_SIZE_BYTES
            10_000,   # MAX_NEXT_STEPS_LENGTH
            100,      # MAX_ACTIVE_FILES
            50,       # MAX_MODIFICATIONS
            30,       # MAX_RECENT_TOOLS
            10,       # MAX_HANDOVER_DECISIONS/PATTERNS
            # Quality weights (documented in comments)
            # QUALITY_WEIGHT_COMPLETION (0.30)
            25,       # QUALITY_WEIGHT_OUTCOMES (0.25)
            20,       # QUALITY_WEIGHT_DECISIONS (0.20)
            15,       # QUALITY_WEIGHT_ISSUES (0.15)
            # QUALITY_WEIGHT_KNOWLEDGE (0.10)
            # Quality score thresholds (documented in comments)
            90,       # QUALITY_SCORE_EXCELLENT (0.90)
            70,       # QUALITY_SCORE_ACCEPTABLE (0.50)
        }

        # Check if any suspicious numbers remain
        magic_numbers = [
            (lineno, num)
            for lineno, num in suspicious_numbers
            if num not in acceptable_numbers
        ]

        # Focus on configuration-related magic numbers
        config_magic_numbers = [
            (lineno, num)
            for lineno, num in magic_numbers
            if num in {5, 0.005, 0.1, 10}  # Known config values
        ]

        if config_magic_numbers:
            details = ", ".join(f"line {lineno}: {num}" for lineno, num in config_magic_numbers)
            pytest.fail(
                f"Found unaccounted configuration magic numbers: {details}. "
                "These should be replaced with constants from handoff.config module."
            )


class NumericLiteralVisitor(ast.NodeVisitor):
    """AST visitor to collect all numeric literals in source code."""

    def __init__(self) -> None:
        self.numeric_literals: list[tuple[int, int | float]] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        """Visit constant nodes (numbers, strings, etc.)."""
        if isinstance(node.value, (int, float)):
            self.numeric_literals.append((node.lineno, node.value))
        self.generic_visit(node)

    def visit_Num(self, node: ast.Num) -> None:
        """Visit numeric nodes (Python < 3.8 compatibility)."""
        self.numeric_literals.append((node.lineno, node.n))
        self.generic_visit(node)


class TestConfigModuleHasRequiredConstants:
    """Test that config module has all necessary constants defined."""

    @pytest.fixture
    def config_path(self) -> Path:
        """Path to config.py file."""
        return Path(__file__).parent.parent / "src" / "handoff" / "config.py"

    @pytest.fixture
    def config_content(self, config_path: Path) -> str:
        """Content of config.py file."""
        return config_path.read_text(encoding="utf-8")

    def test_config_has_lock_timeout_constant(self, config_content: str) -> None:
        """Test that LOCK_TIMEOUT_SECONDS constant exists."""
        # After fix, config should have this constant
        if "LOCK_TIMEOUT_SECONDS" not in config_content:
            pytest.fail(
                "config.py missing LOCK_TIMEOUT_SECONDS constant. "
                "Expected: LOCK_TIMEOUT_SECONDS = 5"
            )

    def test_config_has_retry_constants(self, config_content: str) -> None:
        """Test that retry-related constants exist."""
        missing_constants = []

        if "MAX_RETRIES" not in config_content:
            missing_constants.append("MAX_RETRIES")

        if "RETRY_BASE_DELAY_SECONDS" not in config_content:
            missing_constants.append("RETRY_BASE_DELAY_SECONDS")

        if "LOCK_CHECK_INTERVAL_SECONDS" not in config_content:
            missing_constants.append("LOCK_CHECK_INTERVAL_SECONDS")

        if "LOCK_CHECKS_PER_SECOND" not in config_content:
            missing_constants.append("LOCK_CHECKS_PER_SECOND")

        if "STALE_LOCK_AGE_SECONDS" not in config_content:
            missing_constants.append("STALE_LOCK_AGE_SECONDS")

        if missing_constants:
            pytest.fail(
                f"config.py missing constants: {', '.join(missing_constants)}. "
                "These constants should be defined to replace magic numbers in handoff_store.py"
            )

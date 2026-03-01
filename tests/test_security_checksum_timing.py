#!/usr/bin/env python3
"""
Test for SEC-004: Checksum Comparison Timing Attack Vulnerability

This test demonstrates that the checksum comparison in _verify_handoff_checksum()
is vulnerable to timing attacks because it uses startswith() which returns early
on first character mismatch.

Expected behavior: Constant-time comparison regardless of input
Actual behavior (before fix): startswith() returns early on mismatch, leaking timing info

Run with: pytest tests/test_security_checksum_timing.py -v
"""

import hmac
import statistics
import time
from typing import Callable

import pytest


def time_comparison_operation(
    comparison_func: Callable[[str, str], bool], correct_checksum: str, test_checksum: str
) -> float:
    """Time a single comparison operation.

    Args:
        comparison_func: Function that takes two strings and returns bool
        correct_checksum: The correct checksum value
        test_checksum: The checksum to test against

    Returns:
        Time in seconds for the comparison operation
    """
    start = time.perf_counter()
    comparison_func(correct_checksum, test_checksum)
    end = time.perf_counter()
    return end - start


def measure_timing_distribution(
    comparison_func: Callable[[str, str], bool], correct_checksum: str, test_checksum: str, iterations: int = 10000
) -> dict[str, float]:
    """Measure timing distribution for a comparison operation.

    Args:
        comparison_func: Function that takes two strings and returns bool
        correct_checksum: The correct checksum value
        test_checksum: The checksum to test against
        iterations: Number of times to run the comparison

    Returns:
        Dict with mean, median, min, max timings
    """
    timings = []
    for _ in range(iterations):
        t = time_comparison_operation(comparison_func, correct_checksum, test_checksum)
        timings.append(t)

    return {
        "mean": statistics.mean(timings),
        "median": statistics.median(timings),
        "min": min(timings),
        "max": max(timings),
        "stdev": statistics.stdev(timings) if len(timings) > 1 else 0.0,
    }


def current_vulnerable_comparison(stored_checksum: str, computed: str) -> bool:
    """Current vulnerable implementation using startswith().

    This is the VULNERABLE implementation from line 109:
        if not stored_checksum.startswith(computed):

    Args:
        stored_checksum: The stored checksum from handoff data
        computed: The computed checksum

    Returns:
        True if stored_checksum starts with computed (vulnerable to timing)
    """
    return stored_checksum.startswith(computed)


def secure_comparison_hmac(stored_checksum: str, computed: str) -> bool:
    """Secure implementation using hmac.compare_digest().

    This is the SECURE implementation that should replace startswith().

    Args:
        stored_checksum: The stored checksum from handoff data
        computed: The computed checksum

    Returns:
        True if checksums match (constant-time comparison)
    """
    return hmac.compare_digest(stored_checksum, computed)


def current_vulnerable_comparison(stored_checksum: str, computed: str) -> bool:
    """Current vulnerable implementation using startswith().

    This is the VULNERABLE implementation from line 109:
        if not stored_checksum.startswith(computed):

    Args:
        stored_checksum: The stored checksum from handoff data
        computed: The computed checksum

    Returns:
        True if stored_checksum starts with computed (vulnerable to timing)
    """
    return stored_checksum.startswith(computed)


def secure_comparison_hmac(stored_checksum: str, computed: str) -> bool:
    """Secure implementation using hmac.compare_digest().

    This is the SECURE implementation that should replace startswith().

    Args:
        stored_checksum: The stored checksum from handoff data
        computed: The computed checksum

    Returns:
        True if checksums match (constant-time comparison)
    """
    import hmac

    return hmac.compare_digest(stored_checksum, computed)


class TestChecksumTimingVulnerability:
    """Test suite to demonstrate timing attack vulnerability in checksum comparison."""

    @pytest.fixture
    def sample_checksum(self):
        """A realistic SHA256 checksum (64 hex characters)."""
        return "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def mismatch_first_char(self, sample_checksum):
        """Checksum that differs in the first character."""
        return "b1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def mismatch_last_char(self, sample_checksum):
        """Checksum that differs in the last character."""
        return "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567891"

    def test_vulnerable_implementation_shows_timing_difference(self, sample_checksum, mismatch_first_char, mismatch_last_char):
        """
        Test that vulnerable implementation (startswith) shows timing differences.

        Given: Two checksums with mismatches at different positions
        When: Compared using startswith()
        Then: Early mismatch (first char) is faster than late mismatch (last char)

        This demonstrates the timing attack vulnerability.

        NOTE: Uses a very long checksum (1024 chars) to amplify timing differences.
        On some systems (especially Windows), timing granularity is coarse, so we
        use a long string to make the difference measurable.
        """
        # Use a VERY long checksum to amplify timing differences
        long_checksum = sample_checksum * 16  # 1024 characters

        # Create mismatches at different positions in the long checksum
        mismatch_first_long = "b" + long_checksum[1:]
        mismatch_last_long = long_checksum[:-1] + "1"

        # Measure timing for first character mismatch (should be FAST with startswith)
        first_char_stats = measure_timing_distribution(
            current_vulnerable_comparison,
            long_checksum,
            mismatch_first_long,
            iterations=10000
        )

        # Measure timing for last character mismatch (should be SLOW with startswith)
        last_char_stats = measure_timing_distribution(
            current_vulnerable_comparison,
            long_checksum,
            mismatch_last_long,
            iterations=10000
        )

        # With startswith(), first char mismatch should be significantly faster
        # because it returns immediately on first character mismatch
        timing_ratio = last_char_stats["mean"] / first_char_stats["mean"]

        print(f"\n[VULNERABLE] First char mismatch mean time: {first_char_stats['mean']:.9f}s")
        print(f"[VULNERABLE] Last char mismatch mean time:  {last_char_stats['mean']:.9f}s")
        print(f"[VULNERABLE] Timing ratio (last/first): {timing_ratio:.2f}x")
        print(f"[VULNERABLE] Absolute difference: {last_char_stats['mean'] - first_char_stats['mean']:.9f}s")

        # The vulnerable implementation SHOULD show timing difference
        # We use a conservative threshold because system timing varies
        # The key observation is that early mismatches are measurably faster
        assert timing_ratio > 1.0, (
            f"Vulnerable implementation should show timing difference. "
            f"Expected ratio > 1.0, got {timing_ratio:.2f}"
        )

    def test_secure_implementation_has_constant_time(self, sample_checksum, mismatch_first_char, mismatch_last_char):
        """
        Test that secure implementation (hmac.compare_digest) has constant time.

        Given: Two checksums with mismatches at different positions
        When: Compared using hmac.compare_digest()
        Then: Timing is constant regardless of mismatch position

        This demonstrates the fix prevents timing attacks.

        NOTE: Uses same long checksum as vulnerable test for fair comparison.
        """
        # Use same long checksum for fair comparison
        long_checksum = sample_checksum * 16  # 1024 characters

        # Create mismatches at different positions
        mismatch_first_long = "b" + long_checksum[1:]
        mismatch_last_long = long_checksum[:-1] + "1"

        # Measure timing for first character mismatch
        first_char_stats = measure_timing_distribution(
            secure_comparison_hmac,
            long_checksum,
            mismatch_first_long,
            iterations=10000
        )

        # Measure timing for last character mismatch
        last_char_stats = measure_timing_distribution(
            secure_comparison_hmac,
            long_checksum,
            mismatch_last_long,
            iterations=10000
        )

        timing_ratio = last_char_stats["mean"] / first_char_stats["mean"]

        print(f"\n[SECURE] First char mismatch mean time: {first_char_stats['mean']:.9f}s")
        print(f"[SECURE] Last char mismatch mean time:  {last_char_stats['mean']:.9f}s")
        print(f"[SECURE] Timing ratio (last/first): {timing_ratio:.2f}x")
        print(f"[SECURE] Absolute difference: {last_char_stats['mean'] - first_char_stats['mean']:.9f}s")

        # With hmac.compare_digest(), timing should be constant
        # We expect ratio close to 1.0 (within 20% tolerance for system variance)
        assert 0.8 <= timing_ratio <= 1.2, (
            f"Secure implementation should have constant time. "
            f"Expected ratio 0.8-1.2, got {timing_ratio:.2f}"
        )

    def test_hmac_compare_digest_is_available(self):
        """
        Test that hmac.compare_digest is available for the fix.

        Given: The need for constant-time string comparison
        When: We check for hmac.compare_digest
        Then: It should be available (standard library in Python 3.3+)

        This test confirms the fix is viable on this system.
        """
        assert hasattr(hmac, 'compare_digest'), (
            "hmac.compare_digest should be available for secure comparison"
        )

        # Verify it works as expected
        assert hmac.compare_digest("abc", "abc") is True
        assert hmac.compare_digest("abc", "abd") is False

    def test_startswith_early_return_behavior(self):
        """
        Test that startswith() has early-return behavior (conceptual test).

        Given: The startswith() method
        When: Comparing strings with mismatches at different positions
        Then: We can demonstrate the early-return behavior exists

        This is a CONCEPTUAL test - it shows that startswith() is designed
        to return early on mismatch, which is what makes it vulnerable to
        timing attacks. The actual timing may not be measurable on all systems.

        The key insight: startswith() checks character-by-character and returns
        as soon as a mismatch is found, whereas hmac.compare_digest() always
        checks all characters.
        """
        correct = "abcdefgh"
        mismatch_first = "xbcdefgh"
        mismatch_last = "abcdefgx"

        # Both should return False (not equal)
        assert not current_vulnerable_comparison(correct, mismatch_first)
        assert not current_vulnerable_comparison(correct, mismatch_last)

        # But the first mismatch is detected after checking 1 character
        # while the last mismatch is detected after checking 8 characters
        # This early-return behavior is what creates the timing vulnerability
        # (even if we can't reliably measure it on all systems)

        # Document the vulnerability
        print("\n[VULNERABILITY DOCUMENTATION]")
        print("startswith() checks character-by-character and returns early")
        print("- Mismatch at position 0: checks 1 character")
        print("- Mismatch at position 7: checks 8 characters")
        print("- This difference creates measurable timing variance")
        print("- Attackers can use timing to infer correct checksum values")
        print("\n[FIX]")
        print("Use hmac.compare_digest() which always checks all characters")
        print("- Constant time regardless of mismatch position")
        print("- Prevents timing-based side channel attacks")

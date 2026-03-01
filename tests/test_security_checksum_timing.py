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

import time
import statistics
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
    def mismatch_middle_char(self, sample_checksum):
        """Checksum that differs in the middle character."""
        return "a1b2c3d4e5f67890abcdee1234567890abcdef1234567890abcdef1234567890"

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
        """
        # Measure timing for first character mismatch (should be FAST with startswith)
        first_char_stats = measure_timing_distribution(
            current_vulnerable_comparison,
            sample_checksum,
            mismatch_first_char,
            iterations=50000
        )

        # Measure timing for last character mismatch (should be SLOW with startswith)
        last_char_stats = measure_timing_distribution(
            current_vulnerable_comparison,
            sample_checksum,
            mismatch_last_char,
            iterations=50000
        )

        # With startswith(), first char mismatch should be significantly faster
        # because it returns immediately on first character mismatch
        timing_ratio = last_char_stats["mean"] / first_char_stats["mean"]

        print(f"\n[VULNERABLE] First char mismatch mean time: {first_char_stats['mean']:.9f}s")
        print(f"[VULNERABLE] Last char mismatch mean time:  {last_char_stats['mean']:.9f}s")
        print(f"[VULNERABLE] Timing ratio (last/first): {timing_ratio:.2f}x")

        # The vulnerable implementation SHOULD show timing difference
        # We expect at least 1.2x ratio (conservative threshold)
        # In practice, it's often 2-3x or more
        assert timing_ratio > 1.2, (
            f"Vulnerable implementation should show timing difference. "
            f"Expected ratio > 1.2, got {timing_ratio:.2f}"
        )

    def test_secure_implementation_has_constant_time(self, sample_checksum, mismatch_first_char, mismatch_last_char):
        """
        Test that secure implementation (hmac.compare_digest) has constant time.

        Given: Two checksums with mismatches at different positions
        When: Compared using hmac.compare_digest()
        Then: Timing is constant regardless of mismatch position

        This demonstrates the fix prevents timing attacks.
        """
        # Measure timing for first character mismatch
        first_char_stats = measure_timing_distribution(
            secure_comparison_hmac,
            sample_checksum,
            mismatch_first_char,
            iterations=50000
        )

        # Measure timing for last character mismatch
        last_char_stats = measure_timing_distribution(
            secure_comparison_hmac,
            sample_checksum,
            mismatch_last_char,
            iterations=50000
        )

        timing_ratio = last_char_stats["mean"] / first_char_stats["mean"]

        print(f"\n[SECURE] First char mismatch mean time: {first_char_stats['mean']:.9f}s")
        print(f"[SECURE] Last char mismatch mean time:  {last_char_stats['mean']:.9f}s")
        print(f"[SECURE] Timing ratio (last/first): {timing_ratio:.2f}x")

        # With hmac.compare_digest(), timing should be constant
        # We expect ratio close to 1.0 (within 10% tolerance)
        assert 0.9 <= timing_ratio <= 1.1, (
            f"Secure implementation should have constant time. "
            f"Expected ratio 0.9-1.1, got {timing_ratio:.2f}"
        )

    def test_complete_match_vs_mismatch_timing(self, sample_checksum, mismatch_last_char):
        """
        Test timing difference between complete match vs mismatch.

        Given: Two checksums - one matching, one mismatching at last character
        When: Compared using vulnerable and secure implementations
        Then: Vulnerable shows timing difference, secure does not

        This is a practical attack scenario: attacker can distinguish
        between "correct checksum" and "close but wrong" by timing.
        """
        # Test vulnerable implementation
        match_stats_vulnerable = measure_timing_distribution(
            current_vulnerable_comparison,
            sample_checksum,
            sample_checksum,  # Complete match
            iterations=50000
        )

        mismatch_stats_vulnerable = measure_timing_distribution(
            current_vulnerable_comparison,
            sample_checksum,
            mismatch_last_char,  # Mismatch at last char
            iterations=50000
        )

        vulnerable_ratio = mismatch_stats_vulnerable["mean"] / match_stats_vulnerable["mean"]

        print(f"\n[VULNERABLE] Complete match mean time:     {match_stats_vulnerable['mean']:.9f}s")
        print(f"[VULNERABLE] Last-char mismatch mean time: {mismatch_stats_vulnerable['mean']:.9f}s")
        print(f"[VULNERABLE] Timing ratio (mismatch/match): {vulnerable_ratio:.2f}x")

        # Vulnerable implementation: complete match should be SLOWEST
        # (checks all characters), last-char mismatch should be slightly faster
        # The ratio may not be as dramatic as first-char vs last-char,
        # but there should still be a measurable difference
        assert vulnerable_ratio < 0.95 or vulnerable_ratio > 1.05, (
            f"Vulnerable implementation should show timing difference "
            f"between match and mismatch. Expected ratio outside [0.95, 1.05], "
            f"got {vulnerable_ratio:.2f}"
        )

        # Test secure implementation
        match_stats_secure = measure_timing_distribution(
            secure_comparison_hmac,
            sample_checksum,
            sample_checksum,
            iterations=50000
        )

        mismatch_stats_secure = measure_timing_distribution(
            secure_comparison_hmac,
            sample_checksum,
            mismatch_last_char,
            iterations=50000
        )

        secure_ratio = mismatch_stats_secure["mean"] / match_stats_secure["mean"]

        print(f"\n[SECURE] Complete match mean time:     {match_stats_secure['mean']:.9f}s")
        print(f"[SECURE] Last-char mismatch mean time: {mismatch_stats_secure['mean']:.9f}s")
        print(f"[SECURE] Timing ratio (mismatch/match): {secure_ratio:.2f}x")

        # Secure implementation: timing should be constant
        assert 0.9 <= secure_ratio <= 1.1, (
            f"Secure implementation should have constant time. "
            f"Expected ratio 0.9-1.1, got {secure_ratio:.2f}"
        )

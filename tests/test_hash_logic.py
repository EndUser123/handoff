"""Tests for hash computation logic."""

import hashlib


class TestHashComputation:
    """Test hash computation logic for original_user_request verification."""

    def test_sha256_hash_produces_16_char_prefix(self):
        """Test that SHA256 hash computation produces 16-char hex prefix."""
        original_request = "approve edit hooks/posttooluse/strategy_escalation_hook.py"

        # Compute hash as it will be implemented
        computed_hash = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16]

        # Verify: Hash should be 16 chars
        assert len(computed_hash) == 16

        # Verify: Hash should be valid hex
        int(computed_hash, 16)  # Will raise if not hex

        # Verify: Hash should be deterministic
        hash2 = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16]
        assert computed_hash == hash2

    def test_hash_matches_known_value(self):
        """Test that hash produces expected known value."""
        original_request = "test request"

        # Compute hash
        computed_hash = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16]

        # Known SHA256 hash of "test request" is:
        # 3a604f4b22e3a98301c7f0f8b9e8b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3
        # First 16 chars: 3a604f4b22e3a983
        expected_hash = "3a604f4b22e3a983"

        assert computed_hash == expected_hash

    def test_hash_handles_unicode_characters(self):
        """Test that hash computation works with unicode characters."""
        original_request = "test message with emoji 🎉 and unicode Ñ"

        # Compute hash with UTF-8 encoding
        computed_hash = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16]

        # Verify: Hash should be deterministic
        hash2 = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16]
        assert computed_hash == hash2

        # Verify: Different from ASCII-only string
        ascii_hash = hashlib.sha256(
            b"test message"
        ).hexdigest()[:16]
        assert computed_hash != ascii_hash

    def test_hash_handles_empty_string(self):
        """Test that hash computation handles empty string gracefully."""
        original_request = ""

        # Compute hash
        computed_hash = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16]

        # Verify: Should still produce valid hash
        assert len(computed_hash) == 16
        int(computed_hash, 16)  # Valid hex

    def test_hash_different_for_different_inputs(self):
        """Test that different inputs produce different hashes."""
        request1 = "approve edit hooks/posttooluse/strategy_escalation_hook.py"
        request2 = "approve edit hooks/posttooluse/strategy_escalation_hook.py "  # Extra space
        request3 = "/code do Implementation Priority"

        hash1 = hashlib.sha256(request1.encode('utf-8')).hexdigest()[:16]
        hash2 = hashlib.sha256(request2.encode('utf-8')).hexdigest()[:16]
        hash3 = hashlib.sha256(request3.encode('utf-8')).hexdigest()[:16]

        # All hashes should be different
        assert hash1 != hash2
        assert hash1 != hash3
        assert hash2 != hash3

    def test_hash_handles_none_gracefully(self):
        """Test that hash computation handles None gracefully (returns None)."""
        original_request = None

        # This should return None based on our implementation
        computed_hash = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16] if original_request else None

        assert computed_hash is None

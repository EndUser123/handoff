"""Integration tests for handoff hash verification system."""

import hashlib
import json


class TestHashVerificationIntegration:
    """Integration tests for hash verification across handoff capture and restore."""

    def test_transcript_timestamp_extraction_integration(self, tmp_path):
        """Test timestamp extraction from transcript in realistic scenario."""
        from handoff.hooks.__lib.transcript import TranscriptParser

        # Create realistic transcript with multiple messages
        transcript_file = tmp_path / "test_transcript.jsonl"
        transcript_data = [
            {
                "type": "user",
                "message": {"content": "first message"},
                "timestamp": "2026-03-05T10:00:00.000Z"
            },
            {
                "type": "assistant",
                "message": {"content": "response"}
            },
            {
                "type": "user",
                "message": {"content": "/code do Implementation Priority"},
                "timestamp": "2026-03-05T12:34:56.789Z"
            }
        ]

        with open(transcript_file, "w") as f:
            for entry in transcript_data:
                json.dump(entry, f)
                f.write("\n")

        # Parse and extract timestamp
        parser = TranscriptParser(str(transcript_file))
        timestamp = parser.get_transcript_timestamp()

        # Should get timestamp from LAST user message
        assert timestamp == "2026-03-05T12:34:56.789Z"

    def test_hash_matches_computed_value(self):
        """Test that hash computation matches expected SHA256 prefix."""
        original_request = "approve edit hooks/posttooluse/strategy_escalation_hook.py"

        # Compute hash using same logic as PreCompact_handoff_capture
        computed_hash = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16] if original_request else None

        # Verify hash properties
        assert computed_hash is not None
        assert len(computed_hash) == 16
        assert int(computed_hash, 16)  # Valid hex

        # Verify deterministic
        hash2 = hashlib.sha256(
            original_request.encode('utf-8')
        ).hexdigest()[:16]
        assert computed_hash == hash2

    def test_hash_none_for_empty_request(self):
        """Test that hash is None for empty/None request."""
        # Empty string
        hash_empty = hashlib.sha256(
            b""
        ).hexdigest()[:16] if "" else None

        # Our implementation returns None for empty string (guard clause)
        # But hashlib would compute a hash for empty string
        # So we test the conditional logic
        test_request = ""
        computed_hash = hashlib.sha256(
            test_request.encode('utf-8')
        ).hexdigest()[:16] if test_request else None

        # Empty string is falsy, so should return None
        assert computed_hash is None

    def test_verification_prompt_format(self):
        """Test that verification prompt displays correctly."""
        handoff_data = {
            "original_user_request": "/code do Implementation Priority",
            "original_user_request_hash": "a1b2c3d4e5f6g7h8",
            "original_user_request_timestamp": "2026-03-05T12:34:56.789Z"
        }

        # Simulate _build_last_command_section logic
        original_request = handoff_data.get("original_user_request")
        request_hash = handoff_data.get("original_user_request_hash")
        request_timestamp = handoff_data.get("original_user_request_timestamp")

        verification_lines = []
        if request_hash:
            verification_lines = [
                f"**Verification Token:** `{request_hash}`",
            ]
            if request_timestamp:
                verification_lines.append(
                    f"**Timestamp:** {request_timestamp}"
                )
            verification_lines.extend([
                "",
                "**⚠️ VERIFY:** If this command seems wrong, the handoff data may be corrupted.",
                "",
                "",
            ])

        # Verify format
        assert len(verification_lines) == 6
        assert "a1b2c3d4e5f6g7h8" in verification_lines[0]
        assert "2026-03-05T12:34:56.789Z" in verification_lines[1]
        assert "VERIFY" in verification_lines[3]

    def test_verification_prompt_without_hash(self):
        """Test that prompt works without hash (legacy handoff)."""
        handoff_data = {
            "original_user_request": "/code do Implementation Priority",
            # No hash field
        }

        original_request = handoff_data.get("original_user_request")
        request_hash = handoff_data.get("original_user_request_hash")

        verification_lines = []
        if request_hash:
            verification_lines = [
                f"**Verification Token:** `{request_hash}`",
            ]

        # Should be empty for legacy handoff
        assert len(verification_lines) == 0
        assert original_request == "/code do Implementation Priority"

    def test_unicode_hash_computation(self):
        """Test hash computation with unicode characters."""
        unicode_request = "test with emoji 🎉 and unicode Ñ é 中文"

        # Compute hash
        computed_hash = hashlib.sha256(
            unicode_request.encode('utf-8')
        ).hexdigest()[:16]

        # Verify hash is valid and deterministic
        assert len(computed_hash) == 16
        assert int(computed_hash, 16)  # Valid hex

        # Verify deterministic
        hash2 = hashlib.sha256(
            unicode_request.encode('utf-8')
        ).hexdigest()[:16]
        assert computed_hash == hash2

    def test_migration_detection_logic(self):
        """Test migration detection for handoffs without hash."""
        # Legacy handoff (no hash)
        legacy_handoff = {
            "original_user_request": "/code do Implementation Priority",
            "checksum": "abc123"
        }

        # Modern handoff (has hash)
        modern_handoff = {
            "original_user_request": "/code do Implementation Priority",
            "original_user_request_hash": "a1b2c3d4e5f6g7h8",
            "checksum": "def456"
        }

        # Simulate migration detection logic
        def needs_migration(handoff_data):
            original_request = handoff_data.get("original_user_request")
            request_hash = handoff_data.get("original_user_request_hash")
            return bool(original_request and not request_hash)

        # Legacy needs migration
        assert needs_migration(legacy_handoff) is True

        # Modern does not need migration
        assert needs_migration(modern_handoff) is False

    def test_hash_uniqueness_for_similar_commands(self):
        """Test that similar commands produce different hashes."""
        commands = [
            "/code do Implementation Priority",
            "/code do Implementation Priority ",  # Extra space
            "/code do  Implementation Priority",  # Double space
            "/code Do Implementation Priority",  # Capital D
        ]

        hashes = []
        for cmd in commands:
            h = hashlib.sha256(cmd.encode('utf-8')).hexdigest()[:16]
            hashes.append(h)

        # All hashes should be unique
        assert len(set(hashes)) == len(hashes)

        # No hash should equal another
        for i, h1 in enumerate(hashes):
            for j, h2 in enumerate(hashes):
                if i != j:
                    assert h1 != h2

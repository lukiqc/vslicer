"""Unit tests for export filters module.

Critical tests for the atempo chain algorithm with many edge cases.
"""

import pytest
from vslicer_core.export.filters import (
    build_atempo_chain,
    build_setpts_filter,
    build_video_filter,
    build_audio_filter,
)


class TestSetptsFilter:
    """Tests for setpts filter builder."""

    def test_basic_slowmo(self):
        assert build_setpts_filter(2.0) == "setpts=2.0*PTS"

    def test_extreme_slowmo(self):
        assert build_setpts_filter(10.0) == "setpts=10.0*PTS"

    def test_speedup(self):
        assert build_setpts_filter(0.5) == "setpts=0.5*PTS"


class TestAtempoChain:
    """Tests for atempo chain builder - CRITICAL component."""

    def test_identity_no_change(self):
        """Factor of 1.0 should return empty string (no filter needed)."""
        assert build_atempo_chain(1.0) == ""

    def test_simple_slowmo_within_limits(self):
        """Factor of 2.0 (2x slower) → tempo=0.5 → single atempo=0.5."""
        result = build_atempo_chain(2.0)
        assert result == "atempo=0.5"

    def test_simple_speedup_within_limits(self):
        """Factor of 0.5 (2x faster) → tempo=2.0 → single atempo=2.0."""
        result = build_atempo_chain(0.5)
        # Both "atempo=2.0" and "atempo=2" are valid
        assert result in ("atempo=2.0", "atempo=2")

    def test_slowmo_requiring_chain_factor_5(self):
        """Factor of 5.0 (5x slower) → tempo=0.2 → needs chaining.

        Algorithm:
        - tempo = 1/5.0 = 0.2
        - 0.2 < 0.5, apply atempo=0.5, tempo becomes 0.4
        - 0.4 < 0.5, apply atempo=0.5, tempo becomes 0.8
        - 0.8 in [0.5, 2.0], apply atempo=0.8
        Result: "atempo=0.5,atempo=0.5,atempo=0.8"
        """
        result = build_atempo_chain(5.0)
        # Parse the chain
        parts = result.split(",")
        assert len(parts) == 3
        assert parts[0] == "atempo=0.5"
        assert parts[1] == "atempo=0.5"
        # Third should be 0.8 (with possible floating point precision)
        third_val = float(parts[2].split("=")[1])
        assert abs(third_val - 0.8) < 1e-6

    def test_slowmo_factor_10(self):
        """Factor of 10.0 (10x slower) → tempo=0.1 → longer chain.

        Algorithm:
        - tempo = 1/10.0 = 0.1
        - 0.1 < 0.5, apply atempo=0.5, tempo becomes 0.2
        - 0.2 < 0.5, apply atempo=0.5, tempo becomes 0.4
        - 0.4 < 0.5, apply atempo=0.5, tempo becomes 0.8
        - 0.8 in [0.5, 2.0], apply atempo=0.8
        Result: "atempo=0.5,atempo=0.5,atempo=0.5,atempo=0.8"
        """
        result = build_atempo_chain(10.0)
        parts = result.split(",")
        assert len(parts) == 4
        assert parts[0] == "atempo=0.5"
        assert parts[1] == "atempo=0.5"
        assert parts[2] == "atempo=0.5"
        third_val = float(parts[3].split("=")[1])
        assert abs(third_val - 0.8) < 1e-6

    def test_slowmo_factor_20(self):
        """Factor of 20.0 (20x slower) → tempo=0.05 → even longer chain."""
        result = build_atempo_chain(20.0)
        parts = result.split(",")
        # tempo=0.05: 0.05→0.1→0.2→0.4→0.8, so 5 filters
        assert len(parts) == 5

    def test_speedup_factor_0_25(self):
        """Factor of 0.25 (4x faster) → tempo=4.0 → needs chaining.

        Algorithm:
        - tempo = 1/0.25 = 4.0
        - 4.0 > 2.0, apply atempo=2.0, tempo becomes 2.0
        - 2.0 in [0.5, 2.0], apply atempo=2.0
        Result: "atempo=2.0,atempo=2.0"
        """
        result = build_atempo_chain(0.25)
        parts = result.split(",")
        assert len(parts) == 2
        assert parts[0] in ("atempo=2.0", "atempo=2")
        assert parts[1] in ("atempo=2.0", "atempo=2")

    def test_speedup_factor_0_125(self):
        """Factor of 0.125 (8x faster) → tempo=8.0 → longer chain."""
        result = build_atempo_chain(0.125)
        parts = result.split(",")
        # tempo=8.0: 8.0→4.0→2.0, so 3 filters
        assert len(parts) == 3
        assert all("atempo=2.0" == p or "atempo=2" == p for p in parts)

    def test_edge_case_just_below_0_5(self):
        """Test edge case where tempo is just below 0.5."""
        # Factor slightly greater than 2.0
        result = build_atempo_chain(2.1)
        # tempo = 1/2.1 ≈ 0.476, needs one 0.5 then remainder
        parts = result.split(",")
        assert len(parts) == 2
        assert parts[0] == "atempo=0.5"

    def test_edge_case_just_above_2_0(self):
        """Test edge case where tempo is just above 2.0."""
        # Factor slightly less than 0.5
        result = build_atempo_chain(0.48)
        # tempo = 1/0.48 ≈ 2.083, needs one 2.0 then remainder
        parts = result.split(",")
        assert len(parts) == 2
        assert parts[0] == "atempo=2.0"

    def test_extreme_slowmo_factor_100(self):
        """Test extreme slow motion."""
        result = build_atempo_chain(100.0)
        # tempo = 0.01, very long chain
        parts = result.split(",")
        assert len(parts) > 5
        # All should start with "atempo="
        assert all(p.startswith("atempo=") for p in parts)

    def test_extreme_speedup_factor_0_01(self):
        """Test extreme speedup."""
        result = build_atempo_chain(0.01)
        # tempo = 100.0, very long chain
        parts = result.split(",")
        assert len(parts) > 5
        assert all(p.startswith("atempo=") for p in parts)


class TestVideoFilter:
    """Tests for complete video filter builder."""

    def test_no_slowmo(self):
        assert build_video_filter(None) == ""
        assert build_video_filter(1.0) == ""

    def test_with_slowmo(self):
        result = build_video_filter(5.0)
        assert result == "setpts=5.0*PTS"


class TestAudioFilter:
    """Tests for complete audio filter builder."""

    def test_no_slowmo(self):
        assert build_audio_filter(None) == ""
        assert build_audio_filter(1.0) == ""

    def test_with_slowmo(self):
        result = build_audio_filter(2.0)
        assert result == "atempo=0.5"

    def test_with_complex_slowmo(self):
        result = build_audio_filter(5.0)
        assert result.startswith("atempo=")
        assert "," in result  # Should be a chain

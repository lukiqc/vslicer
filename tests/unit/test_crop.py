"""Tests for crop filter functionality."""

import pytest

from vslicer_core.domain.models import CropOptions
from vslicer_core.export.filters import build_crop_filter


class TestBuildCropFilter:
    """Tests for build_crop_filter function."""

    def test_9_16_centered_1920x1080(self):
        """Test 9:16 crop centered on 1920x1080 source."""
        result = build_crop_filter("9:16", 0.5, 1920, 1080)
        # 9:16 ratio = 0.5625, crop_width = 1080 * 0.5625 = 607.5 -> 607
        # max_x = 1920 - 607 = 1313, x_offset = 1313 * 0.5 = 656
        assert result == "crop=607:1080:656:0"

    def test_9_16_left_edge_1920x1080(self):
        """Test 9:16 crop at left edge."""
        result = build_crop_filter("9:16", 0.0, 1920, 1080)
        assert result == "crop=607:1080:0:0"

    def test_9_16_right_edge_1920x1080(self):
        """Test 9:16 crop at right edge."""
        result = build_crop_filter("9:16", 1.0, 1920, 1080)
        # max_x = 1920 - 607 = 1313
        assert result == "crop=607:1080:1313:0"

    def test_4_5_centered_1920x1080(self):
        """Test 4:5 crop centered on 1920x1080 source."""
        result = build_crop_filter("4:5", 0.5, 1920, 1080)
        # 4:5 ratio = 0.8, crop_width = 1080 * 0.8 = 864
        # max_x = 1920 - 864 = 1056, x_offset = 1056 * 0.5 = 528
        assert result == "crop=864:1080:528:0"

    def test_1_1_centered_1920x1080(self):
        """Test 1:1 (square) crop centered on 1920x1080 source."""
        result = build_crop_filter("1:1", 0.5, 1920, 1080)
        # 1:1 ratio = 1.0, crop_width = 1080
        # max_x = 1920 - 1080 = 840, x_offset = 840 * 0.5 = 420
        assert result == "crop=1080:1080:420:0"

    def test_9_16_on_720p(self):
        """Test 9:16 crop on 1280x720 source."""
        result = build_crop_filter("9:16", 0.5, 1280, 720)
        # crop_width = 720 * 0.5625 = 405
        # max_x = 1280 - 405 = 875, x_offset = 875 * 0.5 = 437
        assert result == "crop=405:720:437:0"

    def test_unsupported_aspect_ratio(self):
        """Test that unsupported aspect ratios raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported aspect ratio"):
            build_crop_filter("16:9", 0.5, 1920, 1080)

    def test_position_at_quarter(self):
        """Test crop position at 25%."""
        result = build_crop_filter("9:16", 0.25, 1920, 1080)
        # max_x = 1313, x_offset = 1313 * 0.25 = 328
        assert result == "crop=607:1080:328:0"

    def test_custom_crop_centered(self):
        """Test custom crop with 50% width centered."""
        result = build_crop_filter("custom", 0.5, 1920, 1080, custom_width_ratio=0.5)
        # crop_width = 1920 * 0.5 = 960
        # max_x = 1920 - 960 = 960, x_offset = 960 * 0.5 = 480
        assert result == "crop=960:1080:480:0"

    def test_custom_crop_left_edge(self):
        """Test custom crop at left edge."""
        result = build_crop_filter("custom", 0.0, 1920, 1080, custom_width_ratio=0.3)
        # crop_width = 1920 * 0.3 = 576
        # x_offset = 0
        assert result == "crop=576:1080:0:0"

    def test_custom_crop_right_edge(self):
        """Test custom crop at right edge."""
        result = build_crop_filter("custom", 1.0, 1920, 1080, custom_width_ratio=0.4)
        # crop_width = 1920 * 0.4 = 768
        # max_x = 1920 - 768 = 1152
        assert result == "crop=768:1080:1152:0"

    def test_custom_crop_missing_ratio(self):
        """Test that custom mode requires custom_width_ratio."""
        with pytest.raises(ValueError, match="custom_width_ratio required"):
            build_crop_filter("custom", 0.5, 1920, 1080)


class TestCropOptions:
    """Tests for CropOptions model."""

    def test_valid_crop_options(self):
        """Test creating valid CropOptions."""
        opts = CropOptions(aspect_ratio="9:16", position=0.5)
        assert opts.aspect_ratio == "9:16"
        assert opts.position == 0.5

    def test_position_at_boundaries(self):
        """Test position at valid boundaries."""
        opts_left = CropOptions(aspect_ratio="9:16", position=0.0)
        assert opts_left.position == 0.0

        opts_right = CropOptions(aspect_ratio="9:16", position=1.0)
        assert opts_right.position == 1.0

    def test_invalid_position_negative(self):
        """Test that negative position raises ValueError."""
        with pytest.raises(ValueError, match="Position must be between"):
            CropOptions(aspect_ratio="9:16", position=-0.1)

    def test_invalid_position_over_one(self):
        """Test that position > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="Position must be between"):
            CropOptions(aspect_ratio="9:16", position=1.1)

    def test_custom_crop_options(self):
        """Test creating valid CropOptions with custom mode."""
        opts = CropOptions(aspect_ratio="custom", position=0.5, custom_width_ratio=0.6)
        assert opts.aspect_ratio == "custom"
        assert opts.position == 0.5
        assert opts.custom_width_ratio == 0.6

    def test_custom_missing_width_ratio(self):
        """Test that custom mode requires custom_width_ratio."""
        with pytest.raises(ValueError, match="custom_width_ratio required"):
            CropOptions(aspect_ratio="custom", position=0.5)

    def test_custom_width_ratio_too_low(self):
        """Test that custom_width_ratio <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="custom_width_ratio must be between"):
            CropOptions(aspect_ratio="custom", position=0.5, custom_width_ratio=0.0)

    def test_custom_width_ratio_too_high(self):
        """Test that custom_width_ratio > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="custom_width_ratio must be between"):
            CropOptions(aspect_ratio="custom", position=0.5, custom_width_ratio=1.5)

    def test_preset_ignores_custom_width_ratio(self):
        """Test that preset aspect ratios can have custom_width_ratio (ignored)."""
        opts = CropOptions(aspect_ratio="9:16", position=0.5, custom_width_ratio=0.5)
        assert opts.aspect_ratio == "9:16"
        assert opts.custom_width_ratio == 0.5  # Stored but not used

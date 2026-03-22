"""Unit tests for domain models."""

import pytest

from vslicer_core.domain.models import SlowMoOptions


def test_slowmo_options_factor_only():
    opts = SlowMoOptions(factor=2.0)
    assert opts.factor == 2.0


def test_slowmo_options_target_only():
    opts = SlowMoOptions(target_duration=4.0)
    assert opts.target_duration == 4.0


def test_slowmo_options_requires_one():
    with pytest.raises(ValueError):
        SlowMoOptions()


def test_slowmo_options_disallow_both():
    with pytest.raises(ValueError):
        SlowMoOptions(factor=2.0, target_duration=4.0)


def test_compute_factor_from_target():
    opts = SlowMoOptions(target_duration=10.0)
    assert opts.compute_factor(2.0) == pytest.approx(5.0)

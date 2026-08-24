"""Tests for the A2 eligibility rules."""

import pytest

from a2moto.eligibility import check_a2_eligibility


def test_ninja_400_passes_no_weight_floor() -> None:
    """168 kg at 33 kW is legal (0.196 kW/kg). No hardcoded minimum weight."""
    result = check_a2_eligibility(stock_kw=33.0, wet_weight_kg=168.0)
    assert result.eligible
    assert not result.failures
    assert result.restricted_kw == 33.0
    assert result.kw_per_kg == pytest.approx(33.0 / 168.0)


def test_exact_limit_ratio_passes() -> None:
    """33.4 kW / 167 kg == 0.2 exactly; floating point must not flip it to fail."""
    result = check_a2_eligibility(stock_kw=33.4, wet_weight_kg=167.0)
    assert result.eligible
    # exactly-at-limit is borderline, must warn
    assert result.warnings


def test_power_to_weight_over_limit_fails() -> None:
    """35 kW on a 170 kg bike is 0.206 kW/kg -> not A2 legal."""
    result = check_a2_eligibility(stock_kw=50.0, wet_weight_kg=170.0)
    assert not result.eligible
    assert any("power-to-weight" in f for f in result.failures)


def test_restricted_power_defaults_to_min_stock_35() -> None:
    result = check_a2_eligibility(stock_kw=54.9, wet_weight_kg=184.0)
    assert result.restricted_kw == 35.0
    assert result.eligible


def test_explicit_restricted_kw_below_35_is_used() -> None:
    """A bike advertised as restricted to 33 kW must be evaluated at 33 kW."""
    result = check_a2_eligibility(stock_kw=50.0, wet_weight_kg=170.0, restricted_kw=33.0)
    assert result.eligible  # 33/170 = 0.194 <= 0.2, would fail at 35 kW
    assert result.restricted_kw == 33.0


def test_stock_over_70kw_fails() -> None:
    """E.g. a full-power RS 660 at 73.5 kW may not derive an A2 restriction."""
    result = check_a2_eligibility(stock_kw=73.5, wet_weight_kg=183.0)
    assert not result.eligible
    assert any("70" in f for f in result.failures)


def test_stock_exactly_70kw_passes_with_warning() -> None:
    """CBR650R at 70 kW is at the cap: eligible but borderline."""
    result = check_a2_eligibility(stock_kw=70.0, wet_weight_kg=208.0)
    assert result.eligible
    assert any("borderline" in w for w in result.warnings)


def test_rs660_at_69kw_passes_with_borderline_warning() -> None:
    result = check_a2_eligibility(stock_kw=69.0, wet_weight_kg=183.0)
    assert result.eligible
    assert any("borderline" in w for w in result.warnings)


def test_restricted_over_35kw_fails() -> None:
    result = check_a2_eligibility(stock_kw=50.0, wet_weight_kg=200.0, restricted_kw=40.0)
    assert not result.eligible
    assert any("restricted power" in f for f in result.failures)


@pytest.mark.parametrize(
    ("stock_kw", "wet_weight_kg"),
    [(0, 180), (-5, 180), (35, 0), (35, -1)],
)
def test_invalid_inputs_raise(stock_kw: float, wet_weight_kg: float) -> None:
    with pytest.raises(ValueError):
        check_a2_eligibility(stock_kw=stock_kw, wet_weight_kg=wet_weight_kg)

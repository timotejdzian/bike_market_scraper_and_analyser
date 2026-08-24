"""A2 licence eligibility rules (EU directive 2006/126/EC, category A2).

Rules implemented -- as functions, not hardcoded flags:

1. Restricted power must not exceed 35 kW.
2. Power-to-weight at the bike's *actual* restricted power must not exceed
   0.2 kW/kg. No minimum-weight shortcut: a Ninja 400 at 33.4 kW / 168 kg
   (0.199 kW/kg) is legal and must pass.
3. Stock power must not exceed 70 kW: a restricted bike may not derive from
   a machine of more than double the restricted output.

Borderline cases produce warnings instead of being silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

A2_MAX_RESTRICTED_KW = 35.0
A2_MAX_KW_PER_KG = 0.2
A2_MAX_STOCK_KW = 70.0

# Tolerance for exact-limit floating point cases (e.g. 33.4 kW / 167 kg == 0.2).
_EPS = 1e-9

# Thresholds at which a passing bike is still flagged as borderline.
_BORDERLINE_STOCK_KW = 65.0
_BORDERLINE_KW_PER_KG = 0.195


@dataclass(frozen=True)
class EligibilityResult:
    """Outcome of an A2 eligibility check."""

    eligible: bool
    restricted_kw: float
    kw_per_kg: float
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_a2_eligibility(
    *,
    stock_kw: float,
    wet_weight_kg: float,
    restricted_kw: float | None = None,
) -> EligibilityResult:
    """Check whether a bike can be ridden legally on an A2 licence.

    Args:
        stock_kw: Unrestricted (homologated) power output.
        wet_weight_kg: Wet weight in kg.
        restricted_kw: Actual power in restricted form. Defaults to
            ``min(stock_kw, 35.0)``; pass the advertised figure when a
            listing states one, since it is often below 35 kW.
    """
    if stock_kw <= 0:
        raise ValueError(f"stock_kw must be positive, got {stock_kw}")
    if wet_weight_kg <= 0:
        raise ValueError(f"wet_weight_kg must be positive, got {wet_weight_kg}")
    if restricted_kw is None:
        restricted_kw = min(stock_kw, A2_MAX_RESTRICTED_KW)
    if restricted_kw <= 0:
        raise ValueError(f"restricted_kw must be positive, got {restricted_kw}")

    failures: list[str] = []
    warnings: list[str] = []

    if restricted_kw > A2_MAX_RESTRICTED_KW + _EPS:
        failures.append(
            f"restricted power {restricted_kw:g} kW exceeds the {A2_MAX_RESTRICTED_KW:g} kW cap"
        )

    if stock_kw > A2_MAX_STOCK_KW + _EPS:
        failures.append(
            f"stock power {stock_kw:g} kW exceeds {A2_MAX_STOCK_KW:g} kW: "
            "may not derive from a machine of more than double the restricted output"
        )
    elif stock_kw >= _BORDERLINE_STOCK_KW:
        warnings.append(
            f"borderline: stock power {stock_kw:g} kW is close to the "
            f"{A2_MAX_STOCK_KW:g} kW cap; verify the homologated figure"
        )

    kw_per_kg = restricted_kw / wet_weight_kg
    if kw_per_kg > A2_MAX_KW_PER_KG + _EPS:
        failures.append(
            f"power-to-weight {kw_per_kg:.4f} kW/kg at {restricted_kw:g} kW / "
            f"{wet_weight_kg:g} kg exceeds the {A2_MAX_KW_PER_KG:g} kW/kg cap"
        )
    elif kw_per_kg >= _BORDERLINE_KW_PER_KG:
        warnings.append(
            f"borderline: power-to-weight {kw_per_kg:.4f} kW/kg is close to the "
            f"{A2_MAX_KW_PER_KG:g} kW/kg cap; verify the wet weight figure"
        )

    return EligibilityResult(
        eligible=not failures,
        restricted_kw=restricted_kw,
        kw_per_kg=kw_per_kg,
        failures=failures,
        warnings=warnings,
    )

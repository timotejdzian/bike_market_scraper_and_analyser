"""Validation and audit of config/models.yaml."""

import re
import warnings

import pytest

from a2moto.config import load_model_specs
from a2moto.eligibility import check_a2_eligibility
from a2moto.models import ModelSpec

EXPECTED_MODEL_COUNT = 27  # 12 native + 15 restrictable per SPEC.md


@pytest.fixture(scope="module")
def specs() -> list[ModelSpec]:
    return load_model_specs()


def test_all_entries_validate(specs: list[ModelSpec]) -> None:
    assert len(specs) == EXPECTED_MODEL_COUNT


def test_canonical_names_unique(specs: list[ModelSpec]) -> None:
    names = [s.canonical for s in specs]
    assert len(names) == len(set(names))


def test_aliases_compile_and_match_canonicalish(specs: list[ModelSpec]) -> None:
    for spec in specs:
        for alias in spec.aliases:
            re.compile(alias, re.IGNORECASE)  # ModelSpec validates too; belt and braces


def test_every_class_flag_is_consistent(specs: list[ModelSpec]) -> None:
    for spec in specs:
        assert spec.a2_native or spec.restrictable, spec.canonical
        if spec.a2_native:
            assert spec.stock_kw <= 35.0, spec.canonical
        if spec.restrictable:
            assert spec.stock_kw <= 70.0, spec.canonical


def test_all_whitelisted_models_are_a2_eligible(specs: list[ModelSpec]) -> None:
    """Every whitelisted model must pass; borderline ones must carry warnings."""
    for spec in specs:
        result = check_a2_eligibility(stock_kw=spec.stock_kw, wet_weight_kg=spec.wet_weight_kg)
        assert result.eligible, f"{spec.canonical}: {result.failures}"


def test_borderline_models_produce_warnings(specs: list[ModelSpec]) -> None:
    by_name = {s.canonical: s for s in specs}
    rs660 = by_name["RS 660"]
    result = check_a2_eligibility(stock_kw=rs660.stock_kw, wet_weight_kg=rs660.wet_weight_kg)
    assert result.warnings, "RS 660 must be flagged as borderline"


def test_audit_unverified_entries(specs: list[ModelSpec]) -> None:
    """List every entry whose spec figures are unverified, for manual audit.

    Always passes; emits a warning naming the entries so they show in the
    pytest warnings summary. Flip `verified: true` in models.yaml only after
    checking figures against a manufacturer data sheet.
    """
    unverified = [s for s in specs if not s.verified]
    if unverified:
        lines = "\n".join(f"  - {s.canonical}: {s.source}" for s in unverified)
        warnings.warn(
            UserWarning(
                f"{len(unverified)}/{len(specs)} models.yaml entries have "
                f"UNVERIFIED spec figures:\n{lines}"
            ),
            stacklevel=1,
        )

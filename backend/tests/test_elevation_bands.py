"""Floor bands from the level markers of a section or elevation sheet (ADR-0013 Decision 1):
match by elevation, fallback by order, roof marker, median top, too few floors, noise ignored."""

from __future__ import annotations

from decimal import Decimal

from unitforma.documents.levels import Marker
from unitforma.publishing.elevation import FloorLine, bands, crop_of


def _m(text: str, y: float, x: float = 0.05) -> Marker:
    return Marker(text=text, value=float(text), x=x, y=y)


def _levels(*vals: tuple[int, float | None]) -> list[FloorLine]:
    return [FloorLine(level, Decimal(str(e)) if e is not None else None) for level, e in vals]


def test_bands_follow_floor_elevations_and_end_at_the_roof_marker():
    markers = [_m("+0.00", 0.80), _m("+3.20", 0.60), _m("+6.40", 0.40), _m("+9.60", 0.20)]
    out = bands(markers, _levels((0, 0.0), (1, 3.2), (2, 6.4)))
    assert [(b.level, b.y0, b.y1) for b in out] == [(0, 0.6, 0.8), (1, 0.4, 0.6), (2, 0.2, 0.4)]
    assert crop_of(out) == (0.0, 0.17, 1.0, 0.83)


def test_top_band_is_one_median_height_without_a_roof_marker():
    markers = [_m("+0.00", 0.80), _m("+3.00", 0.65), _m("+6.00", 0.50)]
    out = bands(markers, _levels((0, 0.0), (1, 3.0), (2, 6.0)))
    top = out[-1]
    assert top.level == 2 and top.y1 == 0.5 and abs(top.y0 - 0.35) < 1e-9


def test_repeated_marker_takes_the_median_and_noise_is_ignored():
    # the ground line printed on both sides, a dimension "+1.50" that is no floor
    markers = [
        _m("+0.00", 0.80, 0.05),
        _m("+0.00", 0.82, 0.95),
        _m("+1.50", 0.70),
        _m("+3.00", 0.60),
    ]
    out = bands(markers, _levels((0, 0.0), (1, 3.0)))
    assert [(b.level, b.y1) for b in out] == [(0, 0.81), (1, 0.6)]


def test_floors_without_elevations_match_by_order_when_counts_agree():
    markers = [_m("-3.00", 0.9), _m("+0.00", 0.7), _m("+3.00", 0.5)]
    out = bands(markers, _levels((-1, None), (0, None), (1, None)))
    assert [b.level for b in out] == [-1, 0, 1]
    assert bands(markers, _levels((0, None), (1, None))) is None  # three markers, two floors


def test_fewer_than_two_matched_floors_gives_nothing():
    assert bands([_m("+0.00", 0.8), _m("+3.00", 0.6)], _levels((0, 0.0), (1, 9.0))) is None
    assert bands([], _levels((0, 0.0), (1, 3.0))) is None

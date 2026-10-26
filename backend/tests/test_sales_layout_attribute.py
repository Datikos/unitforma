"""The unit layout code is a sales-editable unit field: the link is ``units.layout_id`` and the
code stays mirrored in ``units.attributes`` until ADR-0022 E1; a written code must exist in the
project's layout registry and is spelled as registered."""

from types import SimpleNamespace

from unitforma.sales import rules


def _unit(**attrs):
    return SimpleNamespace(
        rooms=None, bedrooms=None, bathrooms=None, orientation=None, entrance=None, attributes=attrs
    )


def test_layout_reads_from_attributes_and_diffs_like_a_column():
    project = SimpleNamespace(currency="EUR")
    cur = rules.current_values(project, _unit(layout="T2"), None)
    assert cur.values["layout"] == "T2"
    assert "layout" in rules.UNIT_FIELDS and "layout" in rules.ATTRIBUTE_FIELDS
    diffs = rules.diff(cur, {"layout": "T3"})
    assert [(d.field, d.old, d.new) for d in diffs] == [("layout", "T2", "T3")]
    assert rules.diff(cur, {"layout": "T2"}) == []


def test_layout_validation_rejects_blank_and_long_codes():
    project = SimpleNamespace(currency="EUR")
    cur = rules.current_values(project, _unit(), None)
    lookups = SimpleNamespace(
        plan_ids=set(),
        promotion_ids=set(),
        area_types={"net_internal"},
        layouts={"type a": (None, "Type A", None)},
    )
    assert cur.values["layout"] is None
    errors = rules.validate(
        rules.diff(cur, {"layout": "   "}), cur, lookups, allow_zero_price=False, reason=None
    )
    assert any("layout" in e for e in errors)
    errors = rules.validate(
        rules.diff(cur, {"layout": "x" * 41}), cur, lookups, allow_zero_price=False, reason=None
    )
    assert any("layout" in e for e in errors)
    assert (
        rules.validate(
            rules.diff(cur, {"layout": "Type A"}), cur, lookups, allow_zero_price=False, reason=None
        )
        == []
    )
    # an unregistered code is refused; a registered one is spelled as the registry has it
    errors = rules.validate(
        rules.diff(cur, {"layout": "Type B"}), cur, lookups, allow_zero_price=False, reason=None
    )
    assert any("registry" in e for e in errors)
    assert rules.normalise({"layout": " type a "}, lookups) == {"layout": "Type A"}
    assert rules.normalise({"layout": "Type B"}, lookups) == {"layout": "Type B"}


def test_wall_colour_is_an_attribute_field_with_the_same_rules():
    """ADR-0017 E5: the wall finish lives in ``units.attributes`` like the layout, diffs like a
    column, and refuses blanks and codes over 40 characters."""
    project = SimpleNamespace(currency="EUR")
    cur = rules.current_values(project, _unit(wall_colour="RAL 9010"), None)
    assert cur.values["wall_colour"] == "RAL 9010"
    assert "wall_colour" in rules.UNIT_FIELDS and "wall_colour" in rules.ATTRIBUTE_FIELDS
    diffs = rules.diff(cur, {"wall_colour": "#f1ece1"})
    assert [(d.field, d.old, d.new) for d in diffs] == [("wall_colour", "RAL 9010", "#f1ece1")]
    lookups = SimpleNamespace(plan_ids=set(), promotion_ids=set(), area_types={"net_internal"})
    errors = rules.validate(
        rules.diff(cur, {"wall_colour": "x" * 41}),
        cur,
        lookups,
        allow_zero_price=False,
        reason=None,
    )
    assert any("wall_colour" in e for e in errors)

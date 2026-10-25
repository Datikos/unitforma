"""The unit layout code (ADR-0016 Decision 4) is a sales-editable unit field kept in
``units.attributes``; no column, no migration."""

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
    lookups = SimpleNamespace(plan_ids=set(), promotion_ids=set(), area_types={"net_internal"})
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

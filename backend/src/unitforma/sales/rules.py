"""Field catalogue, value parsing and business rules for sales data (plan §6.2–§6.6).

One rule set serves inline edit, bulk edit and spreadsheet import, so a value accepted by
one path is accepted by all of them and an import dry run predicts exactly what apply does.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

AVAILABILITY = ("available", "reserved", "sold", "withdrawn")
UNIT_FIELDS = ("rooms", "bedrooms", "bathrooms", "orientation", "entrance", "layout")
# unit fields that live in ``units.attributes`` (JSONB) rather than in a column
ATTRIBUTE_FIELDS = ("layout",)
SALES_FIELDS = (
    "availability",
    "availability_reason",
    "list_price",
    "currency",
    "price_on_request",
    "price_area_type",
    "payment_plan_id",
    "promotion_ids",
    "public_description",
    "internal_notes",
    "public_fields",
)
EDITABLE = SALES_FIELDS + UNIT_FIELDS

# what may enter the publication snapshot; internal_notes, availability_reason and history
# are internal by construction and have no switch at all (plan §6.6)
PUBLIC_FIELD_KEYS = (
    "list_price",
    "payment_plan",
    "promotions",
    "description",
    "areas",
    "rooms",
    "media",
)
PUBLIC_FIELD_DEFAULTS = {k: True for k in PUBLIC_FIELD_KEYS}
INTERNAL_ONLY = ("internal_notes", "availability_reason", "price_history", "import_batches")

CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
MAX_PRICE = Decimal("999999999999.99")
SOURCE_RANK = {"manual": 0, "ifc": 1, "drawing_schedule": 2, "drawing_measured": 3}
TRUE_WORDS = {"true", "yes", "y", "1", "x", "да", "კი", "on"}
FALSE_WORDS = {"false", "no", "n", "0", "нет", "არა", "off"}


class CellError(ValueError):
    pass


@dataclass
class Lookups:
    """Project-scoped reference data, loaded once per request or import."""

    area_keys: set[str]
    plan_ids: set[uuid.UUID]
    plan_by_name: dict[str, uuid.UUID]
    plan_names: dict[uuid.UUID, str]
    promotion_ids: set[uuid.UUID]
    promotion_by_name: dict[str, uuid.UUID]
    promotion_names: dict[uuid.UUID, str]


@dataclass
class NumberFormat:
    decimal_separator: str = "."
    thousands_separator: str = ""

    def __post_init__(self) -> None:
        if self.decimal_separator not in (".", ","):
            raise ValueError("decimal separator must be '.' or ','")
        if self.thousands_separator not in ("", ",", ".", " ", "'"):
            raise ValueError("thousands separator must be empty, ',', '.', ' ' or \"'\"")
        if self.decimal_separator == self.thousands_separator:
            raise ValueError("decimal and thousands separators must differ")


@dataclass
class FieldDiff:
    field: str
    old: Any
    new: Any

    def as_json(self) -> dict[str, Any]:
        return {"field": self.field, "old": to_json(self.old), "new": to_json(self.new)}


@dataclass
class Current:
    """Current values of every editable field (defaults when no sales row exists yet)."""

    values: dict[str, Any] = field(default_factory=dict)
    version: int = 0


def to_json(v: Any) -> Any:
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [to_json(x) for x in v]
    if isinstance(v, dict):
        return {k: to_json(x) for k, x in v.items()}
    return v


def is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


# --- cell parsing (import) -------------------------------------------------------------------
def parse_decimal(v: Any, fmt: NumberFormat) -> Decimal | None:
    if is_blank(v):
        return None
    if isinstance(v, bool):
        raise CellError("expected a number, got a boolean")
    if isinstance(v, (int, Decimal)):
        d = Decimal(v)
    elif isinstance(v, float):
        d = Decimal(repr(v))
    else:
        s = str(v).strip().replace(" ", " ").replace(" ", " ")
        if fmt.thousands_separator:
            s = s.replace(fmt.thousands_separator, "")
            if fmt.thousands_separator == " ":
                s = s.replace(" ", "")
        if fmt.decimal_separator == ",":
            s = s.replace(",", ".")
        if not re.fullmatch(r"-?\d+(\.\d+)?", s):
            raise CellError(f"'{v}' is not a number with the configured separators")
        d = Decimal(s)
    return d


def parse_price(v: Any, fmt: NumberFormat) -> Decimal | None:
    try:
        d = parse_decimal(v, fmt)
    except InvalidOperation as e:
        raise CellError(f"'{v}' is not a number") from e
    if d is None:
        return None
    if d < 0:
        raise CellError("price cannot be negative")
    if d > MAX_PRICE:
        raise CellError("price is too large")
    if d != d.quantize(Decimal("0.01")):
        raise CellError("price has more than two decimals")
    return d.quantize(Decimal("0.01"))


def parse_int(v: Any, fmt: NumberFormat, lo: int = 0, hi: int = 100) -> int | None:
    d = parse_decimal(v, fmt)
    if d is None:
        return None
    if d != d.to_integral_value():
        raise CellError(f"'{v}' is not a whole number")
    i = int(d)
    if not lo <= i <= hi:
        raise CellError(f"{i} is outside {lo}..{hi}")
    return i


def parse_bool(v: Any) -> bool | None:
    if is_blank(v):
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    s = str(v).strip().lower()
    if s in TRUE_WORDS:
        return True
    if s in FALSE_WORDS:
        return False
    raise CellError(f"'{v}' is not true/false")


def parse_currency(v: Any) -> str | None:
    if is_blank(v):
        return None
    s = str(v).strip().upper()
    if not CURRENCY_RE.match(s):
        raise CellError(f"'{v}' is not an ISO 4217 currency code")
    return s


def parse_availability(v: Any) -> str | None:
    if is_blank(v):
        return None
    s = str(v).strip().lower()
    if s not in AVAILABILITY:
        raise CellError(f"'{v}' is not one of {', '.join(AVAILABILITY)}")
    return s


def parse_text(v: Any, max_len: int) -> str | None:
    if is_blank(v):
        return None
    s = str(v).strip()
    if len(s) > max_len:
        raise CellError(f"text longer than {max_len} characters")
    return s


# --- current values & validation --------------------------------------------------------------
def current_values(project, unit, sales) -> Current:
    if sales is None:
        values = {
            "availability": "available",
            "availability_reason": None,
            "list_price": None,
            "currency": project.currency,
            "price_on_request": False,
            "price_area_type": None,
            "payment_plan_id": None,
            "promotion_ids": [],
            "public_description": None,
            "internal_notes": None,
            "public_fields": {},
        }
        version = 0
    else:
        values = {f: getattr(sales, f) for f in SALES_FIELDS}
        values["promotion_ids"] = list(values["promotion_ids"] or [])
        values["public_fields"] = dict(values["public_fields"] or {})
        if values["list_price"] is not None:
            values["list_price"] = Decimal(values["list_price"]).quantize(Decimal("0.01"))
        version = sales.version
    for f in UNIT_FIELDS:
        values[f] = (unit.attributes or {}).get(f) if f in ATTRIBUTE_FIELDS else getattr(unit, f)
    return Current(values=values, version=version)


def _same(field_name: str, a: Any, b: Any) -> bool:
    if field_name == "promotion_ids":
        return sorted(map(str, a or [])) == sorted(map(str, b or []))
    if field_name == "list_price":
        if a is None or b is None:
            return a is b
        return Decimal(a) == Decimal(b)
    return a == b


def diff(current: Current, changes: dict[str, Any]) -> list[FieldDiff]:
    out = []
    for k, v in changes.items():
        if k not in EDITABLE:
            continue
        if not _same(k, current.values.get(k), v):
            out.append(FieldDiff(k, current.values.get(k), v))
    return out


def validate(
    diffs: list[FieldDiff],
    current: Current,
    lookups: Lookups,
    *,
    allow_zero_price: bool,
    reason: str | None,
) -> list[str]:
    """Business rules on a set of changes; returns human-readable errors (empty = valid)."""
    errors: list[str] = []
    new = {d.field: d.new for d in diffs}
    for d in diffs:
        f, v = d.field, d.new
        if f == "availability":
            if v not in AVAILABILITY:
                errors.append(f"availability must be one of {', '.join(AVAILABILITY)}")
            elif current.values["availability"] == "sold" and not (
                reason or new.get("availability_reason")
            ):
                errors.append("changing the availability of a sold unit requires a reason")
        elif f == "list_price":
            if v is not None:
                if v < 0:
                    errors.append("price cannot be negative")
                elif v == 0 and not allow_zero_price:
                    errors.append(
                        "price 0 is not accepted: leave the price empty for 'price on request', "
                        "or confirm zero prices explicitly"
                    )
                elif v > MAX_PRICE:
                    errors.append("price is too large")
        elif f == "currency":
            if not isinstance(v, str) or not CURRENCY_RE.match(v):
                errors.append("currency must be an ISO 4217 code such as EUR, USD or GEL")
        elif f == "price_area_type":
            if v is not None and v not in lookups.area_keys:
                errors.append(f"price area type '{v}' is not defined for this project")
        elif f == "payment_plan_id":
            if v is not None and v not in lookups.plan_ids:
                errors.append("payment plan does not belong to this project")
        elif f == "promotion_ids":
            unknown = [p for p in v or [] if p not in lookups.promotion_ids]
            if unknown:
                errors.append("promotion does not belong to this project")
        elif f == "public_fields":
            bad = [k for k in (v or {}) if k not in PUBLIC_FIELD_KEYS]
            if bad or not all(isinstance(x, bool) for x in (v or {}).values()):
                errors.append(f"public_fields accepts only {', '.join(PUBLIC_FIELD_KEYS)} = bool")
        elif f in ("rooms", "bedrooms", "bathrooms"):
            if v is not None and not (isinstance(v, int) and 0 <= v <= 100):
                errors.append(f"{f} must be a whole number between 0 and 100")
        elif f in ("orientation", "entrance"):
            if v is not None and len(v) > 20:
                errors.append(f"{f} is limited to 20 characters")
        elif f == "layout":
            if v is not None and (not isinstance(v, str) or not v.strip() or len(v) > 40):
                errors.append("layout is a code of 1 to 40 characters")
    return errors


def effective_public_fields(project, sales) -> dict[str, bool]:
    out = dict(PUBLIC_FIELD_DEFAULTS)
    out.update(
        {
            k: bool(v)
            for k, v in ((project.sales_settings or {}).get("public_fields") or {}).items()
            if k in PUBLIC_FIELD_KEYS
        }
    )
    if sales is not None:
        out.update({k: bool(v) for k, v in (sales.public_fields or {}).items() if k in out})
    return out


def resolve_price_area_type(project, sales) -> str:
    keys = [a.get("key") for a in (project.area_definitions or []) if isinstance(a, dict)]
    if sales is not None and sales.price_area_type:
        return sales.price_area_type
    configured = (project.sales_settings or {}).get("price_area_type")
    if configured:
        return configured
    for k in ("total_sellable", "net_internal"):
        if k in keys:
            return k
    return keys[0] if keys else "net_internal"


def best_area(areas: list, area_type: str):
    """The area value a price per m² is based on: verified first, then by source."""
    cands = [a for a in areas if a.area_type == area_type and a.is_current]
    if not cands:
        return None
    cands.sort(key=lambda a: (a.verification_status != "verified", SOURCE_RANK.get(a.source, 9)))
    return cands[0]


def price_per_area(list_price: Decimal | None, area) -> Decimal | None:
    if list_price is None or area is None or not area.value_m2:
        return None
    return (Decimal(list_price) / Decimal(area.value_m2)).quantize(Decimal("0.01"))

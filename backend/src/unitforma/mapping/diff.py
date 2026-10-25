"""Revision diff classification (plan §5.5 rule 1, §13.2 "Revision diff", §13.3).

Given the current boundaries on an old sheet and candidate polygons on the new revision of
the same page, build the overlap matrix and group the bipartite graph of significant overlaps
into proposal items:

* ``matched``    one old ↔ one new, same (or unknown) label
* ``relabelled`` one old ↔ one new, different label
* ``split``      one old ↔ several new
* ``merged``     several old ↔ one new
* ``new``        a candidate without an old counterpart
* ``missing``    an old boundary without a counterpart
* ``complex``    several old ↔ several new (reviewer resolves manually)

Overlap is intersection / min(area) so that a slightly redrawn wall still counts as the same
unit; the threshold (0.7) comes from the plan and is tunable per call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import Polygon

from unitforma.mapping.suggest import normalise_label

Ring = list[list[float]]


@dataclass
class OldBoundary:
    boundary_id: str
    unit_id: str
    ring: Ring
    label: str | None
    code: str
    status: str


@dataclass
class NewCandidate:
    index: int
    ring: Ring
    label: str | None


@dataclass
class DiffItem:
    kind: str
    old_unit_ids: list[str]
    old_boundary_ids: list[str]
    new_indexes: list[int]
    overlaps: list[list[Any]]  # [old_unit_id, new_index, ratio]
    confidence: float
    labels: list[str | None] = field(default_factory=list)


def _poly(ring: Ring) -> Polygon | None:
    try:
        p = Polygon(ring)
    except (ValueError, TypeError):
        return None
    if not p.is_valid:
        p = p.buffer(0)
    return p if (not p.is_empty and p.area > 0) else None


def overlap_matrix(
    olds: list[OldBoundary], news: list[NewCandidate]
) -> dict[tuple[int, int], float]:
    po = [_poly(o.ring) for o in olds]
    pn = [_poly(n.ring) for n in news]
    out: dict[tuple[int, int], float] = {}
    for i, a in enumerate(po):
        if a is None:
            continue
        for j, b in enumerate(pn):
            if b is None or not a.intersects(b):
                continue
            inter = a.intersection(b).area
            denom = min(a.area, b.area)
            if denom > 0 and inter > 0:
                out[(i, j)] = round(inter / denom, 4)
    return out


def classify(
    olds: list[OldBoundary], news: list[NewCandidate], threshold: float = 0.7
) -> list[DiffItem]:
    matrix = overlap_matrix(olds, news)
    sig = {k: v for k, v in matrix.items() if v >= threshold}
    # connected components over the bipartite graph of significant overlaps
    parent: dict[tuple[str, int], tuple[str, int]] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(olds)):
        find(("o", i))
    for j in range(len(news)):
        find(("n", j))
    for (i, j), _ in sig.items():
        union(("o", i), ("n", j))
    groups: dict[tuple[str, int], tuple[list[int], list[int]]] = {}
    for key in list(parent):
        root = find(key)
        g = groups.setdefault(root, ([], []))
        (g[0] if key[0] == "o" else g[1]).append(key[1])

    items: list[DiffItem] = []
    for o_idx, n_idx in groups.values():
        o_idx.sort()
        n_idx.sort()
        pairs = [[olds[i].unit_id, j, sig[(i, j)]] for i in o_idx for j in n_idx if (i, j) in sig]
        conf = round(sum(p[2] for p in pairs) / len(pairs), 3) if pairs else 1.0
        labels = [news[j].label for j in n_idx]
        base = dict(
            old_unit_ids=[olds[i].unit_id for i in o_idx],
            old_boundary_ids=[olds[i].boundary_id for i in o_idx],
            new_indexes=n_idx,
            overlaps=pairs,
            labels=labels,
        )
        if len(o_idx) == 1 and len(n_idx) == 1:
            ol, nl = normalise_label(olds[o_idx[0]].label), normalise_label(news[n_idx[0]].label)
            kind = "relabelled" if ol and nl and ol != nl else "matched"
            if kind == "matched" and (ol is None or nl is None):
                conf = round(conf * 0.9, 3)
            items.append(DiffItem(kind=kind, confidence=conf, **base))
        elif len(o_idx) == 1 and len(n_idx) > 1:
            items.append(DiffItem(kind="split", confidence=conf, **base))
        elif len(o_idx) > 1 and len(n_idx) == 1:
            items.append(DiffItem(kind="merged", confidence=conf, **base))
        elif len(o_idx) == 0 and len(n_idx) == 1:
            items.append(DiffItem(kind="new", confidence=0.5, **base))
        elif len(o_idx) == 1 and len(n_idx) == 0:
            items.append(DiffItem(kind="missing", confidence=0.6, **base))
        else:
            items.append(DiffItem(kind="complex", confidence=round(conf * 0.5, 3), **base))
    order = {
        "missing": 0,
        "merged": 1,
        "split": 2,
        "relabelled": 3,
        "complex": 4,
        "new": 5,
        "matched": 6,
    }
    items.sort(key=lambda it: (order[it.kind], -it.confidence))
    return items


def summarise(items: list[DiffItem]) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        out[it.kind] = out.get(it.kind, 0) + 1
    out["total"] = len(items)
    return out

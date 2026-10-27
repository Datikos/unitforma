"""Tbilisi Architecture Service permits (tas.ge / docs.tbilisi.gov.ge) — ADR-0007.

The public page ``https://tas.ge/?p=publicpage&documentId=<id>`` is a shell; the record comes from
one DWR remote call on ``docs.tbilisi.gov.ge`` and attachments from its download servlet, both
without a session (research note ``docs/research/regulatory-permit-data.md``).

Rules toward the source (Decision 10): one record per user action, no enumeration of ids, no
polling, a User-Agent that names Unitforma. Rules toward the data (Decisions 2 and 3): only the
document id is taken from what the user pastes, every request goes to the constant hosts below,
and personal data (names, personal numbers, phones, emails of applicants, architects, experts and
officials) is dropped while normalising; the raw payload is never stored.
"""

from __future__ import annotations

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from unitforma import __version__
from unitforma.core.errors import ProblemError

SYSTEM = "tasge"
PUBLIC_HOSTS = frozenset({"tas.ge", "www.tas.ge", "docs.tbilisi.gov.ge"})
DWR_URL = (
    "https://docs.tbilisi.gov.ge/architect/dwr/call/plaincall/"
    "UserMethods.getUserDocumentLastMotion.dwr"
)
PUBLIC_PAGE = "https://tas.ge/?p=publicpage&documentId={doc_id}"
ATTACHMENT_URL = "https://docs.tbilisi.gov.ge/DownloadServlet?downloadCase=2&attachedFileId={id}"
RESPONSE_URL = (
    "https://docs.tbilisi.gov.ge/NewArchitectureResponse?documentId={doc_id}&motionId={motion_id}"
)
MESSAGE_URL = "https://docs.tbilisi.gov.ge/ArchitectureViewMessage?messageId={id}"
SIGNED_URL = "https://esign.tbilisi.gov.ge/api/signature/download/file?fileId={id}"
DOWNLOAD_HOSTS = frozenset({"docs.tbilisi.gov.ge", "esign.tbilisi.gov.ge"})
USER_AGENT = f"unitforma/{__version__} (+https://unitforma.com)"

RECORD_TIMEOUT_S = 20.0
RECORD_MAX_BYTES = 5 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 300.0  # per read: a stalled connection
# the whole file: on 2026-10-27 one attachment trickled for about 80 min inside the per-read timeout
# and held the import worker (ADR-0025 D5); 50 MB in 15 min is 0.5 Mbit/s
DOWNLOAD_TOTAL_TIMEOUT_S = 900.0
DOWNLOAD_MAX_BYTES = 50 * 1024 * 1024

# Observed on the public page: documentStatusId 3 renders as "თანხმობა" (consent / approved).
STATUS_LABELS = {3: "approved"}

# Field or fieldset labels that carry personal data; such values are never kept (Decision 3).
PII_LABEL_MARKERS = (
    "პირადი ნომერი",  # personal number
    "ტელეფონის ნომერი",  # phone number
    "ელექტრონული ფოსტა",  # email
    "სახელი და გვარი",  # first and last name
    "მინდობილობა",  # power of attorney
)

# Attachment fieldset title → document kind (Decision 6); first match wins.
KIND_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("site_plan", ("გენერალური გეგმა", "გენგეგმა")),
    ("floor_plan", ("სართულ",)),
    ("section", ("ჭრილ",)),
    ("elevation", ("ფასად",)),
    ("render", ("ფოტომონტაჟ", "აქსონომეტრ", "სავიზიტო")),
)
IMPORTABLE_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
SKIP_REASONS = {".pla": "ArchiCAD project file: no open parser", ".rar": "archive"}

FUNCTIONAL_PURPOSE_LABEL = "ფუნქციური დანიშნულების სახეობა"
HEIGHT_ABOVE_LABEL = "შენობის სიმაღლე (მ)"
HEIGHT_BELOW_LABEL = "ჩაღრმავება"
BUILDING_CODE_RE = re.compile(r"\b([A-Z]{1,3})\s?-?\s?(\d{1,3})(?:\s?/\s?(\d{1,3}))?\b")


# --------------------------------------------------------------------------- reference → id
def extract_document_id(reference: str) -> int:
    """The permit id from a bare number or a tas.ge / docs.tbilisi.gov.ge URL (Decision 2)."""
    ref = (reference or "").strip()
    if re.fullmatch(r"\d{1,12}", ref):
        return int(ref)
    parts = urlsplit(ref if "://" in ref else f"https://{ref}")
    host = (parts.hostname or "").lower()
    if host not in PUBLIC_HOSTS:
        raise ProblemError(
            422,
            "Unsupported permit reference",
            "Paste the tas.ge public page address or the document id",
        )
    q = parse_qs(parts.query)
    for key in ("documentId", "docId"):
        for v in q.get(key, []):
            if re.fullmatch(r"\d{1,12}", v):
                return int(v)
    raise ProblemError(422, "Unsupported permit reference", "The address has no documentId")


# --------------------------------------------------------------------------- DWR parsing
class _JSLiteral:
    """Parser for DWR's data-only JavaScript: objects, arrays, strings, numbers, null, booleans,
    ``new Date(n)`` and references to previously declared ``sN`` variables."""

    def __init__(self, text: str, env: dict[str, Any]):
        self.t, self.i, self.env = text, 0, env

    def ws(self) -> None:
        while self.i < len(self.t) and self.t[self.i] in " \t\r\n":
            self.i += 1

    def value(self) -> Any:
        self.ws()
        c = self.t[self.i]
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        if c in "\"'":
            return self.string()
        if self.t.startswith("new Date(", self.i):
            j = self.t.index(")", self.i)
            n = int(self.t[self.i + 9 : j])
            self.i = j + 1
            return {"$date_ms": n}
        m = re.match(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", self.t[self.i :])
        if m:
            self.i += m.end()
            s = m.group(0)
            return float(s) if any(ch in s for ch in ".eE") else int(s)
        m = re.match(r"[A-Za-z_$][\w$]*", self.t[self.i :])
        if not m:
            raise ValueError(f"unexpected character {c!r} at {self.i}")
        self.i += m.end()
        word = m.group(0)
        if word in ("null", "undefined"):
            return None
        if word == "true":
            return True
        if word == "false":
            return False
        if word in self.env:
            return self.env[word]
        raise ValueError(f"unknown identifier {word}")

    def string(self) -> str:
        q = self.t[self.i]
        j = self.i + 1
        out: list[str] = []
        while True:
            ch = self.t[j]
            if ch == "\\":
                out.append(self.t[j : j + 2])
                j += 2
                continue
            if ch == q:
                break
            out.append(ch)
            j += 1
        self.i = j + 1
        raw = "".join(out).replace('\\"', '"').replace("\\'", "'")
        return json.loads('"' + raw.replace('"', '\\"') + '"')

    def obj(self) -> dict[str, Any]:
        self.i += 1
        res: dict[str, Any] = {}
        while True:
            self.ws()
            if self.t[self.i] == "}":
                self.i += 1
                return res
            m = re.match(r"[\w$]+|\"[^\"]*\"", self.t[self.i :])
            if not m:
                raise ValueError(f"bad object key at {self.i}")
            key = m.group(0).strip('"')
            self.i += m.end()
            self.ws()
            if self.t[self.i] != ":":
                raise ValueError(f"expected ':' at {self.i}")
            self.i += 1
            res[key] = self.value()
            self.ws()
            if self.t[self.i] == ",":
                self.i += 1

    def arr(self) -> list[Any]:
        self.i += 1
        res: list[Any] = []
        while True:
            self.ws()
            if self.t[self.i] == "]":
                self.i += 1
                return res
            res.append(self.value())
            self.ws()
            if self.t[self.i] == ",":
                self.i += 1


def parse_dwr(body: str) -> Any:
    """The object passed to ``dwr.engine.remote.handleCallback`` in a DWR reply."""
    env: dict[str, Any] = {}
    for m in re.finditer(r"var (s\d+)=\{\};", body):
        env[m.group(1)] = {}
    pos = 0
    for m in re.finditer(r"(s\d+)\.([\w$]+)=", body):
        if m.start() < pos or m.group(1) not in env:
            continue
        p = _JSLiteral(body, env)
        p.i = m.end()
        env[m.group(1)][m.group(2)] = p.value()
        pos = p.i
    k = body.index("handleCallback(")
    p = _JSLiteral(body, env)
    p.i = body.index(",", body.index(",", k) + 1) + 1
    return p.value()


def record_from_dwr(body: str) -> dict[str, Any]:
    """Raw record ``{last_motion, wrapper}`` from a DWR reply; raises on a failed remote call."""
    data = parse_dwr(body)
    if not isinstance(data, dict) or not data.get("isSuccess"):
        msg = data.get("errorMessage") if isinstance(data, dict) else None
        raise ProblemError(502, "Permit registry refused the request", msg or None)
    wrapper = next((s for s in data.get("sources") or [] if isinstance(s, dict)), None)
    if wrapper is None or "document" not in wrapper:
        raise ProblemError(404, "Permit not found", "The registry returned no document")
    return {"last_motion": data.get("source") or {}, "wrapper": wrapper}


# --------------------------------------------------------------------------- fetching
class TasgeClient:
    """HTTP access to the registry: fixed hosts, timeouts, size caps, identifying User-Agent."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT}, follow_redirects=False
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_record(self, doc_id: int) -> dict[str, Any]:
        page = quote(f"/architect/public.html?docId={doc_id}", safe="")
        body = (
            "callCount=1\nwindowName=\nc0-scriptName=UserMethods\n"
            "c0-methodName=getUserDocumentLastMotion\nc0-id=0\n"
            f"c0-param0=string:{doc_id}\nbatchId=1\npage={page}\nhttpSessionId=\n"
            "scriptSessionId=\n"
        )
        try:
            text = (
                await self._capped(
                    "POST",
                    DWR_URL,
                    RECORD_TIMEOUT_S,
                    RECORD_MAX_BYTES,
                    content=body.encode(),
                    headers={"Content-Type": "text/plain"},
                )
            ).decode("utf-8", errors="replace")
        except httpx.HTTPError as e:
            raise ProblemError(502, "Permit registry unreachable", str(e)[:200]) from e
        return record_from_dwr(text)

    async def download(self, url: str) -> bytes:
        host = (urlsplit(url).hostname or "").lower()
        if host not in DOWNLOAD_HOSTS or not url.startswith("https://"):
            raise ProblemError(422, "Refusing to download from an unknown host", host)
        return await self._capped(
            "GET", url, DOWNLOAD_TIMEOUT_S, DOWNLOAD_MAX_BYTES, total_s=DOWNLOAD_TOTAL_TIMEOUT_S
        )

    async def _capped(
        self,
        method: str,
        url: str,
        timeout_s: float,
        max_bytes: int,
        *,
        total_s: float | None = None,
        **kw: Any,
    ) -> bytes:
        """The response body, or a problem: 413 past ``max_bytes``, 504 past ``total_s`` for the
        whole transfer (``timeout_s`` bounds one read, not the file)."""
        try:
            async with asyncio.timeout(total_s):
                async with self._http().stream(method, url, timeout=timeout_s, **kw) as r:
                    r.raise_for_status()
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in r.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise ProblemError(
                                413,
                                "Response too large",
                                f"more than {max_bytes // (1024 * 1024)} MB",
                            )
                        chunks.append(chunk)
        except TimeoutError as e:
            raise ProblemError(
                504, "Download took too long", f"more than {total_s:.0f} s for the whole file"
            ) from e
        return b"".join(chunks)


# --------------------------------------------------------------------------- normalisation
def _iso(v: Any) -> Any:
    if isinstance(v, dict) and "$date_ms" in v:
        return datetime.fromtimestamp(v["$date_ms"] / 1000, UTC).isoformat()
    return v


def _is_pii_label(label: str) -> bool:
    return any(m in label for m in PII_LABEL_MARKERS)


def _looks_like_company(owner: str | None) -> bool:
    return bool(owner) and bool(
        re.search(r"\b(შპს|სს|ააიპ|სსიპ|კოოპერატივი)\b|\(\d{9}\)", owner or "")
    )


def normalise(rec: dict[str, Any]) -> dict[str, Any]:
    """The stored shape of a permit: identity, nomenclature, parameters, parcels, indicators,
    fields and attachments — with every personal-data field removed (Decision 3)."""
    w = rec["wrapper"]
    doc = w["document"]
    doc_id = int(doc["documentId"])
    nomen: dict[str, Any] = {}
    if doc.get("cachedInfo"):
        try:
            root = ET.fromstring(doc["cachedInfo"])  # noqa: S314 - small XML from a fixed source
        except ET.ParseError:
            root = None
        n = root.find("nomenklature") if root is not None else None
        if n is not None:
            nomen = {
                "category": n.findtext("categoryName"),
                "category_id": n.findtext("categoryId"),
                "class": n.findtext("className"),
                "class_id": n.findtext("classId"),
                "action": n.findtext("actionName"),
                "stages": [s.text for s in n.findall("stadiums")],
            }
    fields: dict[int, dict[str, Any]] = {}
    fieldsets: dict[int, str] = {}
    # fieldsets that collect personal data (by title or by any of their fields): their files
    # (identity scans, powers of attorney) are never imported
    pii_fieldsets: set[int] = set()
    for fs in w.get("fieldsetPojos") or []:
        title = (fs.get("fieldsetTitle") or "").strip(". ")
        fieldsets[fs["fieldsetId"]] = title
        if _is_pii_label(title):
            pii_fieldsets.add(fs["fieldsetId"])
        for f in fs.get("fields") or []:
            label = (f.get("fieldLabel") or "").strip(". ")
            fields[f["documentFieldId"]] = {"label": label, "fieldset": title}
            if _is_pii_label(label):
                pii_fieldsets.add(fs["fieldsetId"])
    latest: dict[int, dict[str, Any]] = {}
    for v in w.get("docValues") or []:
        if v.get("isActive") != 1:
            continue
        cur = latest.get(v["documentFieldId"])
        if cur is None or (v.get("documentValueId") or 0) > (cur.get("documentValueId") or 0):
            latest[v["documentFieldId"]] = v
    values: list[dict[str, Any]] = []
    for v in sorted(latest.values(), key=lambda x: x.get("documentValueId") or 0):
        meta = fields.get(
            v["documentFieldId"], {"label": f"field#{v['documentFieldId']}", "fieldset": ""}
        )
        if _is_pii_label(meta["label"]) or _is_pii_label(meta["fieldset"]):
            continue
        val = v.get("numberValue")
        if val is None:
            val = v.get("stringValue") or v.get("clobValue") or (v.get("dateValueStr") or None)
        if val in (None, ""):
            continue
        values.append(
            {
                "fieldset": meta["fieldset"],
                "label": meta["label"],
                "value": val,
                "field_id": v["documentFieldId"],
            }
        )
    tech = [
        x for x in values if "ტექნიკურ" in x["fieldset"] and isinstance(x["value"], (int, float))
    ]
    parcels = []
    for mi in w.get("mapInfos") or []:
        owner = mi.get("naprOwner")
        parcels.append(
            {
                "cadastral_code": mi.get("naprCadCode"),
                "address": mi.get("naprAddress") or mi.get("address"),
                "area_m2": mi.get("naprArea"),
                "purpose": mi.get("naprPurpose"),
                "owner": owner
                if _looks_like_company(owner)
                else ("<redacted person>" if owner else None),
            }
        )
    attachments: list[dict[str, Any]] = []
    for a in w.get("attachedFiles") or []:
        if a.get("isActive") != 1:
            continue
        fs_title = fieldsets.get(a.get("fieldsetId"), "")
        if a.get("fieldsetId") in pii_fieldsets:
            continue
        name = a.get("fileName") or ""
        attachments.append(
            {
                "attached_file_id": int(a["attachedFileId"]),
                "fieldset_id": a.get("fieldsetId"),
                "fieldset": fs_title,
                "file_name": name,
                "extension": PurePosixPath(name).suffix.lower(),
                "uploaded_at": _iso(a.get("insertDate")),
                "download_url": ATTACHMENT_URL.format(id=int(a["attachedFileId"])),
                "latest_in_fieldset": False,
            }
        )
    newest: dict[Any, dict[str, Any]] = {}
    for a in attachments:
        fid = a["fieldset_id"]
        if fid not in newest or a["attached_file_id"] > newest[fid]["attached_file_id"]:
            newest[fid] = a
    for a in newest.values():
        a["latest_in_fieldset"] = True
    responses = [
        {
            "motion_id": m["motionId"],
            "date": _iso(m.get("motionDate")),
            "status_id": m.get("documentStatusId"),
            "url": RESPONSE_URL.format(doc_id=doc_id, motion_id=m["motionId"]),
        }
        for m in w.get("oldResponseMotions") or []
    ]
    status_id = (rec.get("last_motion") or {}).get("documentStatusId")
    return {
        "source": {
            "system": SYSTEM,
            "document_id": doc_id,
            "public_page": PUBLIC_PAGE.format(doc_id=doc_id),
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
        "permit": {
            "application_no": doc.get("documentNo"),
            "application_date": doc.get("createDateStr"),
            "registered_at": _iso(doc.get("registrationDate")),
            "deadline": _iso(doc.get("deadLineDate")),
            "decided_at": _iso((w.get("archDocMeta") or {}).get("responseDate")),
            "status_id": status_id,
            "status": STATUS_LABELS.get(status_id, f"status#{status_id}"),
            "address": doc.get("address"),
        },
        "nomenclature": nomen,
        "class_calculator": [
            {
                "label": c.get("fieldName"),
                "value": c.get("numberValue")
                if c.get("numberValue") is not None
                else c.get("comboValue"),
            }
            for c in w.get("docClassCalculatorValues") or []
        ],
        "parcels": parcels,
        "technical_indicators": tech,
        "fields": values,
        "attachments": attachments,
        "responses": responses,
    }


# --------------------------------------------------------------------------- derived values
def kind_for_fieldset(title: str) -> str:
    for kind, words in KIND_KEYWORDS:
        if any(w in title for w in words):
            return kind
    return "permit"


def classify_attachments(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Every current attachment with the document kind it becomes, or why it is skipped."""
    out = []
    for a in record.get("attachments") or []:
        if not a.get("latest_in_fieldset"):
            continue
        ext = a.get("extension") or ""
        row = {**a, "kind": kind_for_fieldset(a.get("fieldset") or ""), "skip_reason": None}
        if ext not in IMPORTABLE_EXTENSIONS:
            row["skip_reason"] = SKIP_REASONS.get(ext, f"unsupported file type {ext or '(none)'}")
        out.append(row)
    return out


def field_value(record: dict[str, Any], label: str) -> Any:
    for f in record.get("fields") or []:
        if f.get("label") == label:
            return f.get("value")
    return None


def heights(record: dict[str, Any]) -> dict[str, float | None]:
    above = below = None
    for c in record.get("class_calculator") or []:
        label, value = c.get("label") or "", c.get("value")
        if not isinstance(value, (int, float)):
            continue
        if label.strip() == HEIGHT_ABOVE_LABEL:
            above = float(value)
        elif HEIGHT_BELOW_LABEL in label:
            below = float(value)
    return {"above_zero_m": above, "below_zero_m": below}


def suggest_name(record: dict[str, Any]) -> str:
    purpose = field_value(record, FUNCTIONAL_PURPOSE_LABEL)
    if isinstance(purpose, str) and purpose.strip():
        return purpose.strip()[:200]
    cat = (record.get("nomenclature") or {}).get("category")
    addr = (record.get("permit") or {}).get("address")
    return (" — ".join(x for x in (cat, addr) if x) or f"Permit {record['source']['document_id']}")[
        :200
    ]


def suggest_building_code(record: dict[str, Any]) -> str:
    purpose = field_value(record, FUNCTIONAL_PURPOSE_LABEL)
    m = BUILDING_CODE_RE.search(purpose) if isinstance(purpose, str) else None
    if not m:
        return "A"
    code = f"{m.group(1)}-{m.group(2)}" + (f"-{m.group(3)}" if m.group(3) else "")
    return code[:20]


def suggest_slug(record: dict[str, Any]) -> str:
    return f"permit-{record['source']['document_id']}"


def summary(record: dict[str, Any], import_id: Any) -> dict[str, Any]:
    """What ``projects.regulatory`` keeps (Decision 4)."""
    p = record.get("permit") or {}
    return {
        "source": SYSTEM,
        "external_id": str(record["source"]["document_id"]),
        "public_page": record["source"]["public_page"],
        "application_no": p.get("application_no"),
        "status": p.get("status"),
        "decided_at": p.get("decided_at"),
        "address": p.get("address"),
        "cadastral_codes": [
            x["cadastral_code"] for x in record.get("parcels") or [] if x.get("cadastral_code")
        ],
        "import_id": str(import_id),
        "fetched_at": record["source"].get("fetched_at"),
    }

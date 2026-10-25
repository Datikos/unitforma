#!/usr/bin/env python3
"""Extract a Tbilisi Architecture Service building-permit record (tas.ge / docs.tbilisi.gov.ge).

Research prototype (plan: docs/research/regulatory-permit-data.md). Standard library only.

    python3 extract_permit.py 1127975 --out permit.json [--download-dir ./files] [--include-pii]

What it does
1. POSTs the DWR remote call ``UserMethods.getUserDocumentLastMotion(docId)`` that the public page
   itself makes, and parses the DWR JavaScript reply into JSON (no browser needed).
2. Builds a normalised, PII-filtered record: permit identity and dates, status, nomenclature
   (category, class, action, stages), class-calculator values, parcel(s) from the national
   registry (cadastral code, address, area, purpose), technical-economic indicators and other
   business fields with their Georgian labels, attachments grouped by fieldset with download
   URLs, decision documents and signed files.
3. Optionally downloads the attachments (PDF/images/CAD) into a directory.

Personal data (names, personal numbers, phones, emails of applicants, architects, officials) is
dropped unless ``--include-pii`` is given. Be polite: one record per call, no crawling.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "https://docs.tbilisi.gov.ge/architect/"
DWR_URL = BASE + "dwr/call/plaincall/UserMethods.getUserDocumentLastMotion.dwr"
PUBLIC_PAGE = "https://tas.ge/?p=publicpage&documentId={doc_id}"
ATTACHMENT_URL = "https://docs.tbilisi.gov.ge/DownloadServlet?downloadCase=2&attachedFileId={id}"
RESPONSE_URL = (
    "https://docs.tbilisi.gov.ge/NewArchitectureResponse?documentId={doc_id}&motionId={motion_id}"
)
MESSAGE_URL = "https://docs.tbilisi.gov.ge/ArchitectureViewMessage?messageId={id}"
SIGNED_URL = "https://esign.tbilisi.gov.ge/api/signature/download/file?fileId={id}"
USER_AGENT = "unitforma-research/0.1 (+https://unitforma.com)"

# Observed on the public page: documentStatusId 3 renders as "თანხმობა" (consent/approved).
STATUS_LABELS = {3: "approved (თანხმობა)"}

PII_LABEL_MARKERS = (
    "პირადი ნომერი",  # personal number
    "ტელეფონის ნომერი",  # phone number
    "ელექტრონული ფოსტა",  # email
    "სახელი და გვარი",  # first and last name
    "მინდობილობა",  # power of attorney
)


# --------------------------------------------------------------------------- DWR parsing
class _JSLiteral:
    """Minimal parser for DWR's data-only JavaScript: objects, arrays, strings, numbers,
    null/true/false, ``new Date(n)`` and references to previously declared ``sN`` variables."""

    def __init__(self, text: str, env: dict):
        self.t, self.i, self.env = text, 0, env

    def ws(self):
        while self.i < len(self.t) and self.t[self.i] in " \t\r\n":
            self.i += 1

    def value(self):
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
            raise ValueError(f"unexpected char {c!r} at {self.i}")
        self.i += m.end()
        word = m.group(0)
        if word == "null" or word == "undefined":
            return None
        if word == "true":
            return True
        if word == "false":
            return False
        if word in self.env:
            return self.env[word]
        raise ValueError(f"unknown identifier {word}")

    def string(self):
        q = self.t[self.i]
        j = self.i + 1
        out = []
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
        # JSON string decoding handles \uXXXX, \n, \\ etc.
        return json.loads('"' + raw.replace('"', '\\"') + '"')

    def obj(self):
        self.i += 1
        res = {}
        while True:
            self.ws()
            if self.t[self.i] == "}":
                self.i += 1
                return res
            m = re.match(r"[\w$]+|\"[^\"]*\"", self.t[self.i :])
            key = m.group(0).strip('"')
            self.i += m.end()
            self.ws()
            assert self.t[self.i] == ":"
            self.i += 1
            res[key] = self.value()
            self.ws()
            if self.t[self.i] == ",":
                self.i += 1

    def arr(self):
        self.i += 1
        res = []
        while True:
            self.ws()
            if self.t[self.i] == "]":
                self.i += 1
                return res
            res.append(self.value())
            self.ws()
            if self.t[self.i] == ",":
                self.i += 1


def parse_dwr(body: str):
    """Return the object passed to ``dwr.engine.remote.handleCallback``."""
    env: dict = {}
    # 1. declarations and incremental assignments: var sN={}; sN.key=value;
    for m in re.finditer(r"var (s\d+)=\{\};", body):
        env[m.group(1)] = {}
    pos = 0
    for m in re.finditer(r"(s\d+)\.([\w$]+)=", body):
        if m.start() < pos:
            continue
        p = _JSLiteral(body, env)
        p.i = m.end()
        env[m.group(1)][m.group(2)] = p.value()
        pos = p.i
    # 2. the callback payload
    k = body.index("handleCallback(")
    p = _JSLiteral(body, env)
    p.i = body.index(",", body.index(",", k) + 1) + 1
    return p.value()


# --------------------------------------------------------------------------- fetching
def fetch_record(doc_id: str, timeout: int = 60) -> dict:
    page = urllib.parse.quote(f"/architect/public.html?docId={doc_id}", safe="")
    body = (
        "callCount=1\nwindowName=\nc0-scriptName=UserMethods\n"
        "c0-methodName=getUserDocumentLastMotion\nc0-id=0\n"
        f"c0-param0=string:{doc_id}\nbatchId=1\npage={page}\nhttpSessionId=\nscriptSessionId=\n"
    )
    req = urllib.request.Request(  # noqa: S310 - fixed https URL
        DWR_URL,
        data=body.encode(),
        headers={"Content-Type": "text/plain", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https URL
        text = r.read().decode("utf-8")
    data = parse_dwr(text)
    if not data or not data.get("isSuccess"):
        raise RuntimeError(f"remote call failed: {data and data.get('errorMessage')}")
    wrapper = next(s for s in data["sources"] if isinstance(s, dict))
    return {"last_motion": data["source"], "wrapper": wrapper}


# --------------------------------------------------------------------------- normalisation
def _iso(v):
    if isinstance(v, dict) and "$date_ms" in v:
        import datetime as dt

        return dt.datetime.fromtimestamp(v["$date_ms"] / 1000, dt.UTC).isoformat()
    return v


def _is_pii_label(label: str) -> bool:
    return any(m in label for m in PII_LABEL_MARKERS)


def _looks_like_company(owner: str | None) -> bool:
    return bool(owner) and bool(re.search(r"\b(შპს|სს|ააიპ|სსიპ|კოოპერატივი)\b|\(\d{9}\)", owner))


def normalise(rec: dict, include_pii: bool = False) -> dict:
    w = rec["wrapper"]
    doc = w["document"]
    # nomenclature from the cached XML
    nomen = {}
    if doc.get("cachedInfo"):
        root = ET.fromstring(doc["cachedInfo"])  # noqa: S314 - small XML from a known source
        n = root.find("nomenklature")
        if n is not None:
            nomen = {
                "category": n.findtext("categoryName"),
                "category_id": n.findtext("categoryId"),
                "class": n.findtext("className"),
                "class_id": n.findtext("classId"),
                "action": n.findtext("actionName"),
                "stages": [s.text for s in n.findall("stadiums")],
            }
    # field labels
    fields: dict[int, dict] = {}
    fieldsets: dict[int, str] = {}
    for fs in w.get("fieldsetPojos") or []:
        fieldsets[fs["fieldsetId"]] = (fs.get("fieldsetTitle") or "").strip(". ")
        for f in fs.get("fields") or []:
            fields[f["documentFieldId"]] = {
                "label": (f.get("fieldLabel") or "").strip(". "),
                "fieldset": fieldsets[fs["fieldsetId"]],
                "input_type": f.get("inputType"),
            }
    # docValues keep every revision of a field; the public page shows the latest per field.
    latest: dict[int, dict] = {}
    for v in w.get("docValues") or []:
        if v.get("isActive") != 1:
            continue
        cur = latest.get(v["documentFieldId"])
        if cur is None or (v.get("documentValueId") or 0) > (cur.get("documentValueId") or 0):
            latest[v["documentFieldId"]] = v
    values = []
    for v in sorted(latest.values(), key=lambda x: x.get("documentValueId") or 0):
        meta = fields.get(
            v["documentFieldId"], {"label": f"field#{v['documentFieldId']}", "fieldset": ""}
        )
        label = meta["label"]
        if not include_pii and (_is_pii_label(label) or _is_pii_label(meta["fieldset"])):
            continue
        val = v.get("numberValue")
        if val is None:
            val = v.get("stringValue") or v.get("clobValue") or (v.get("dateValueStr") or None)
        if val in (None, ""):
            continue
        values.append(
            {
                "fieldset": meta["fieldset"],
                "label": label,
                "value": val,
                "field_id": v["documentFieldId"],
            }
        )
    # technical-economic indicators are the numeric values of that fieldset
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
                if (include_pii or _looks_like_company(owner))
                else ("<redacted person>" if owner else None),
                "flags": {
                    k: mi.get(k) for k in ("laisOnTbilisi", "laisOnOldTbilisi", "isCultureMonument")
                },
            }
        )
    attachments = []
    for a in w.get("attachedFiles") or []:
        if a.get("isActive") != 1:
            continue
        fs_title = fieldsets.get(a.get("fieldsetId"), "")
        if not include_pii and _is_pii_label(fs_title):
            continue
        attachments.append(
            {
                "attached_file_id": a["attachedFileId"],
                "fieldset_id": a.get("fieldsetId"),
                "fieldset": fs_title,
                "file_name": a.get("fileName"),
                "extension": Path(a.get("fileName") or "").suffix.lower(),
                "uploaded_at": _iso(a.get("insertDate")),
                "storage_id": a.get("msdaFileIdOnStorage"),
                "download_url": ATTACHMENT_URL.format(id=a["attachedFileId"]),
                "latest_in_fieldset": False,
            }
        )
    # every upload revision is kept; flag the most recent file per fieldset (what the page shows)
    newest: dict[int, dict] = {}
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
            "url": RESPONSE_URL.format(doc_id=doc["documentId"], motion_id=m["motionId"]),
        }
        for m in w.get("oldResponseMotions") or []
    ]
    signed = [
        {
            "signed_file_id": s.get("msdaSignedFileId"),
            "signed_at": _iso(s.get("signatureDate")),
            "url": SIGNED_URL.format(id=s.get("msdaSignedFileId")),
        }
        for s in w.get("userSignatures") or []
    ]
    messages = [
        {
            "message_id": m["messageId"],
            "date": _iso(m.get("messageDate")),
            "subject": m.get("subject"),
            "url": MESSAGE_URL.format(id=m["messageId"]),
        }
        for m in w.get("messages") or []
    ]
    status_id = rec["last_motion"].get("documentStatusId")
    return {
        "source": {
            "system": "tas.ge / docs.tbilisi.gov.ge",
            "document_id": doc["documentId"],
            "public_page": PUBLIC_PAGE.format(doc_id=doc["documentId"]),
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
            "decision_text_html": doc.get("responseText")
            if include_pii
            else None,  # names appear in the text
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
        "signed_files": signed,
        "messages": messages,
    }


def download(attachments: list[dict], out_dir: Path, max_mb: int = 50) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for a in attachments:
        target = out_dir / f"{a['attached_file_id']}_{a['file_name']}"
        if target.exists():
            continue
        req = urllib.request.Request(  # noqa: S310 - https URL built from a fixed template
            a["download_url"], headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310
            data = r.read(max_mb * 1024 * 1024 + 1)
        if len(data) > max_mb * 1024 * 1024:
            print(f"skip {a['file_name']}: larger than {max_mb} MB", file=sys.stderr)
            continue
        target.write_bytes(data)
        print(f"downloaded {target.name} ({len(data) // 1024} KB)", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("doc_id")
    ap.add_argument("--out", type=Path)
    ap.add_argument(
        "--raw", type=Path, help="also save the raw parsed payload (contains personal data)"
    )
    ap.add_argument("--download-dir", type=Path, help="download active attachments here")
    ap.add_argument("--include-pii", action="store_true")
    args = ap.parse_args(argv)
    rec = fetch_record(args.doc_id)
    if args.raw:
        args.raw.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    out = normalise(rec, include_pii=args.include_pii)
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        args.out.write_text(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    if args.download_dir:
        download(out["attachments"], args.download_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

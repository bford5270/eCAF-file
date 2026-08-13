#!/usr/bin/env python3
"""Ingest completed peer review forms into e-CAF import CSVs.

  python3 tools/parse_review_forms.py --inspect  forms/            # dry run, read this first
  python3 tools/parse_review_forms.py --parse    forms/ --out dist/ingest

Reviewers will not all work inside the app. Some will be handed a Word form,
some a printed sheet that gets scanned, some a spreadsheet the department
already uses. This turns those into `eCAF_ReviewResponses` /
`eCAF_ReviewSummaries` import CSVs so the MSP is not retyping them.

WHAT IT WILL NOT DO — these are CLAUDE.md hard rules, not settings:

  * It never invents a result. An unrecognised value is reported and the field
    is left blank; the run exits non-zero. A wrongly canonicalised MET is
    invisible and permanent, a refusal is loud and fixable.
  * It never reads a DHA 455 item 12 rating. If a form carries a
    Poor/Fair/Good/Superior mark, the file is REJECTED outright rather than
    parsed-minus-that-field, because a form bearing that rating means the local
    process is rating item 12 and that needs a human, not a parser.
  * It never ingests a patient identifier. A form containing an SSN, MRN, DOB or
    patient-name field is REJECTED whole. FIN is the only encounter identifier.
  * It never writes to SharePoint. Output is CSV for human review, same as every
    other artifact in this repo.

CONFIDENCE. Two extraction paths, and the parser always tells you which it used:

  high    the form is one of `dist/templates/*.docx` filled in — values are read
          from named content controls, so the field identity is exact.
  low     any other layout — values are scraped from label/value tables and
          `Standard-ID: result` lines. Positional guessing, and it says so.

Low-confidence rows are written to a SEPARATE file that is not import-ready and
requires line-by-line confirmation. Do not merge them without reading them.
"""

import argparse
import collections
import csv
import json
import os
import re
import sys
import zipfile

from ecaf_normalize import (
    canonical_construct,
    canonical_determination,
    canonical_result,
    csv_safe,
    fin_looks_valid,
    is_item12_value,
    scan_pii,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Standard IDs look like DOC-001, PC-GMO-003, 455-I11:medication.
STANDARD_ID_RE = re.compile(r"\b([A-Z]{2,6}(?:-[A-Z]{2,5})?-\d{3})\b")
# "DOC-001: <value>" on one line. Deliberately captures ANY word-ish value
# rather than a list of known results: if the pattern only matched values we
# already understand, an unrecognised one would produce no match and be dropped
# in silence — which is the exact failure this tool exists to prevent. Match the
# shape, then let canonical_result decide and report what it cannot place.
INLINE_RESULT_RE = re.compile(
    r"\b([A-Z]{2,6}(?:-[A-Z]{2,5})?-\d{3})\b\s*[:\-–|\t]\s*([A-Za-z/ ]{1,24}?)\s*$",
    re.I | re.M,
)

TEXT_EXT = (".txt", ".md", ".csv")
DOCX_EXT = (".docx",)
PDF_EXT = (".pdf",)
XLSX_EXT = (".xlsx", ".xlsm")


# ---------------------------------------------------------------------------
# Extraction — each returns (full_text, controls, tables)
#   controls: {control_name: value}  — only .docx content controls, high trust
#   tables:   [[row_cells, ...], ...]
# ---------------------------------------------------------------------------
def read_docx(path):
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8", "replace")

    # Content controls: <w:tag w:val="NAME"/> ... <w:sdtContent>...text...</w:sdtContent>
    controls = {}
    for m in re.finditer(
        r'<w:tag w:val="([^"]+)"/>.*?<w:sdtContent>(.*?)</w:sdtContent>', xml, re.S
    ):
        name, content = m.group(1), m.group(2)
        text = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", content, re.S))
        controls[name] = _unescape(text).strip()

    from docx import Document  # local import: only needed for this path

    doc = Document(path)
    paras = [p.text for p in doc.paragraphs]
    tables = []
    for t in doc.tables:
        rows = [[c.text.strip() for c in row.cells] for row in t.rows]
        tables.append(rows)
        for row in rows:
            paras.extend(row)
    return "\n".join(paras), controls, tables


def read_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError(
            "pypdf is not installed — run `pip install pypdf`, or convert the PDF "
            "to .docx first. A scanned PDF with no text layer needs OCR before "
            "this tool can read it at all; there is no silent fallback."
        )
    reader = PdfReader(path)
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        raise RuntimeError(
            "No extractable text — this is almost certainly a scan with no text "
            "layer. OCR it first. Parsing it as empty would silently produce a "
            "form with no findings, which is worse than failing."
        )
    return text, {}, []


def read_xlsx(path):
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    rows, lines = [], []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c).strip() for c in row]
            if any(cells):
                rows.append(cells)
                lines.append("\t".join(cells))
    return "\n".join(lines), {}, [rows]


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    rows = [re.split(r"\t|\s{2,}|,", ln) for ln in text.splitlines() if ln.strip()]
    return text, {}, [rows]


def _unescape(s):
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#39;", "'"))


def read_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in DOCX_EXT:
        return read_docx(path)
    if ext in PDF_EXT:
        return read_pdf(path)
    if ext in XLSX_EXT:
        return read_xlsx(path)
    if ext in TEXT_EXT:
        return read_text(path)
    raise RuntimeError(f"unsupported file type {ext}")


# ---------------------------------------------------------------------------
# Control-name mapping — inverse of tools/build_templates.py control_name()
# ---------------------------------------------------------------------------
def load_element_keys():
    p = os.path.join(ROOT, "dist", "app", "src", "fixed-instrument.json")
    with open(p, encoding="utf-8") as fh:
        fi = json.load(fh)
    return (
        [e["key"] for e in fi["item11Elements"]],
        [c["key"] for c in fi["competencyConstructs"]],
    )


def control_to_element(name, element_keys):
    """C455_I11_medication -> medication. Returns None if not an item 11 control."""
    if not name.startswith("C455_I11_"):
        return None
    key = name[len("C455_I11_"):]
    return key if key in element_keys else None


# ---------------------------------------------------------------------------
# Gates — a failure here rejects the whole file
# ---------------------------------------------------------------------------
def gate_file(path, text, controls, tables):
    """[] if the file may be parsed, else a list of blocking reasons."""
    blocks = []

    pii = scan_pii(text)
    if pii:
        seen = collections.Counter(label for label, _ in pii)
        for label, n in seen.items():
            blocks.append(
                f"contains a {label} ({n}×). FIN is the only encounter identifier "
                f"e-CAF may hold. Redact the form and re-run — see the redact-pii "
                f"skill, or strike it by hand."
            )

    # Item 12: a MARKED Poor/Fair/Good/Superior scale.
    # Checked per TABLE, not per row: on the real form the four ratings are a
    # header row and the mark sits in the row beneath, so a row-local check sees
    # the labels and the tick in separate rows and passes both. An unmarked
    # scale is the blank item 12 box our own template ships, and is fine.
    for table in tables:
        labels = {c.strip().lower() for row in table for c in row if is_item12_value(c)}
        if len(labels) < 2:
            continue
        if any(c.strip() in ("X", "x", "✓", "√", "✔")
               for row in table for c in row):
            blocks.append(
                "carries a marked DHA 455 item 12 rating (Poor/Fair/Good/Superior). "
                "e-CAF does not store item 12 — no crosswalk exists from the "
                "Satisfactory/Unsatisfactory review scale. Route this to the "
                "clinical supervisor rather than ingesting it."
            )
            break
    for name, val in controls.items():
        if is_item12_value(val):
            blocks.append(
                f"content control {name!r} holds an item 12 rating ({val!r}). "
                "e-CAF does not store item 12."
            )

    return blocks


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_file(path, element_keys, construct_keys):
    text, controls, tables = read_any(path)
    out = {
        "file": os.path.basename(path),
        "blocked": gate_file(path, text, controls, tables),
        "confidence": "high" if controls else "low",
        "case_id": None,
        "fin": None,
        "determination": None,
        "responses": [],     # (standard_id, result, source)
        "elements": [],      # (element_key, result, source)
        "constructs": [],    # (construct_key, result, source)
        "unmapped": [],      # (field, raw_value)
        "notes": [],
    }
    if out["blocked"]:
        return out

    # --- case identity
    m = re.search(r"\bRC-\d{4}-\d{4}\b", text)
    if m:
        out["case_id"] = m.group(0)
    else:
        out["notes"].append("no CaseID (RC-YYYY-NNNN) found — must be supplied by hand")

    m = re.search(r"\bFIN\b[\s:#]*([A-Za-z0-9]{1,12})\b", text, re.I)
    if m:
        fin = m.group(1)
        if fin_looks_valid(fin):
            out["fin"] = fin
        else:
            out["notes"].append(f"value beside FIN ({fin!r}) does not look like a FIN")

    # --- high-confidence path: named content controls
    for name, val in controls.items():
        if not val or val.startswith("[VERIFY]"):
            continue
        key = control_to_element(name, element_keys)
        if key:
            canon, ok = canonical_result(val)
            if ok:
                out["elements"].append((key, canon, f"control:{name}"))
            else:
                out["unmapped"].append((f"control:{name}", val))

    # --- standards results, both paths
    for m in INLINE_RESULT_RE.finditer(text):
        sid, raw = m.group(1), m.group(2).strip()
        if not raw:
            continue
        canon, ok = canonical_result(raw)
        if ok:
            out["responses"].append((sid, canon, "inline"))
        else:
            out["unmapped"].append((sid, raw))

    # --- table rows: [.., StandardID, .., result, ..]
    for row in [r for table in tables for r in table]:
        joined = " ".join(row)
        sid_m = STANDARD_ID_RE.search(joined)
        if not sid_m:
            continue
        sid = sid_m.group(1)
        if any(sid == r[0] for r in out["responses"]):
            continue                      # already captured inline
        for cell in row:
            if not cell or STANDARD_ID_RE.fullmatch(cell.strip()):
                continue
            canon, ok = canonical_result(cell)
            if ok and cell.strip():
                out["responses"].append((sid, canon, "table"))
                break
        else:
            marked = [c for c in row if c.strip()]
            if len(marked) > 1:
                out["unmapped"].append((sid, " | ".join(marked)[:80]))

    # --- overall determination
    m = re.search(r"overall[^\n:]*[:\s]+\s*(\w+)", text, re.I)
    if m:
        canon, ok = canonical_determination(m.group(1))
        if ok:
            out["determination"] = canon
        else:
            out["unmapped"].append(("OverallDetermination", m.group(1)))

    # --- competency constructs, e.g. "PC-A  Satisfactory"
    for key in construct_keys:
        m = re.search(rf"\b{re.escape(key)}\b\s*[:\-|\t ]+\s*([A-Za-z/ ]{{1,15}})", text)
        if m:
            canon, ok = canonical_construct(m.group(1))
            if ok:
                out["constructs"].append((key, canon, "text"))
            else:
                out["unmapped"].append((key, m.group(1).strip()))

    if not (out["responses"] or out["elements"] or out["constructs"]):
        out["notes"].append("nothing extracted — check the layout, do not assume empty")

    return out


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def gather(target):
    if os.path.isfile(target):
        return [target]
    files = []
    for dirpath, _, names in os.walk(target):
        for n in sorted(names):
            if os.path.splitext(n)[1].lower() in DOCX_EXT + PDF_EXT + XLSX_EXT + TEXT_EXT:
                files.append(os.path.join(dirpath, n))
    return files


def cmd_inspect(target):
    files = gather(target)
    if not files:
        print(f"No parsable files under {target}")
        return 1
    element_keys, construct_keys = load_element_keys()
    blocked = unmapped = 0

    for path in files:
        try:
            r = parse_file(path, element_keys, construct_keys)
        except RuntimeError as e:
            print(f"\n{os.path.basename(path)}\n  ! cannot read: {e}")
            blocked += 1
            continue

        print(f"\n{r['file']}   [{r['confidence']} confidence]")
        if r["blocked"]:
            blocked += 1
            for b in r["blocked"]:
                print(f"  REJECTED: {b}")
            continue

        print(f"  case {r['case_id'] or '—'}   FIN {r['fin'] or '—'}"
              f"   determination {r['determination'] or '—'}")
        print(f"  {len(r['responses'])} standard results, {len(r['elements'])} item 11 "
              f"elements, {len(r['constructs'])} constructs")
        for sid, res, src in r["responses"][:6]:
            print(f"    {sid:<14} {res:<8} ({src})")
        if len(r["responses"]) > 6:
            print(f"    … {len(r['responses']) - 6} more")
        for field, raw in r["unmapped"]:
            unmapped += 1
            print(f"    ? {field}: {raw!r} — unrecognised, add to "
                  f"ecaf_normalize.RESULT_CANON or fix the form")
        for n in r["notes"]:
            print(f"    note: {n}")

    print(f"\n{len(files)} file(s): {blocked} rejected, {unmapped} unrecognised value(s)")
    if blocked or unmapped:
        print("Resolve these before --parse. Nothing is safe to import yet.")
        return 1
    return 0


def cmd_parse(target, outdir):
    files = gather(target)
    element_keys, construct_keys = load_element_keys()
    os.makedirs(outdir, exist_ok=True)

    high, low, rejected, unmapped = [], [], [], []

    for path in files:
        try:
            r = parse_file(path, element_keys, construct_keys)
        except RuntimeError as e:
            rejected.append((os.path.basename(path), str(e)))
            continue
        if r["blocked"]:
            rejected.extend((r["file"], b) for b in r["blocked"])
            continue
        unmapped.extend((r["file"], f, v) for f, v in r["unmapped"])
        (high if r["confidence"] == "high" else low).append(r)

    def write_responses(rows, name):
        p = os.path.join(outdir, name)
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["Title", "ReviewCase", "Standard", "Result", "Comment",
                        "_SourceFile", "_Extraction"])
            n = 0
            for r in rows:
                for sid, res, src in r["responses"]:
                    case = r["case_id"] or ""
                    w.writerow([csv_safe(f"{case}-{sid}" if case else sid),
                                csv_safe(case), csv_safe(sid), res, "",
                                csv_safe(r["file"]), src])
                    n += 1
        return p, n

    hp, hn = write_responses(high, "ingested_responses.csv")
    lp, ln = write_responses(low, "NEEDS-REVIEW_responses.csv")

    # Summaries only from the high-confidence path — a determination scraped
    # positionally is not something to write into a credentialing record.
    sp = os.path.join(outdir, "ingested_summaries.csv")
    with open(sp, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Title", "ReviewCase", "OverallDetermination", "Item11Elements",
                    "CompetencyDomains", "Narrative", "CompletedDate", "_SourceFile"])
        sn = 0
        for r in high:
            if not r["determination"]:
                continue
            w.writerow([
                csv_safe(f"SUM-{r['case_id']}" if r["case_id"] else ""),
                csv_safe(r["case_id"] or ""),
                r["determination"],
                json.dumps([{"key": k, "result": v} for k, v, _ in r["elements"]],
                           separators=(",", ":")),
                json.dumps([{"key": k, "result": v} for k, v, _ in r["constructs"]],
                           separators=(",", ":")),
                "", "", csv_safe(r["file"]),
            ])
            sn += 1

    rp = os.path.join(outdir, "ingest-report.md")
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write("# Form ingest report\n\n")
        fh.write(f"- {len(high)} file(s) parsed at **high** confidence "
                 f"(named content controls) -> `ingested_responses.csv` ({hn} rows)\n")
        fh.write(f"- {len(low)} file(s) parsed at **low** confidence "
                 f"(positional scraping) -> `NEEDS-REVIEW_responses.csv` ({ln} rows)\n")
        fh.write(f"- {sn} summary row(s) -> `ingested_summaries.csv`\n")
        fh.write(f"- {len(rejected)} file(s) rejected\n\n")

        if rejected:
            fh.write("## Rejected — not parsed at all\n\n")
            for f, why in rejected:
                fh.write(f"- **{f}** — {why}\n")
            fh.write("\n")

        if unmapped:
            fh.write("## Unrecognised values — BLOCKING\n\n")
            fh.write("Left blank rather than guessed. Add the spelling to "
                     "`tools/ecaf_normalize.py` `RESULT_CANON` if it is a genuine "
                     "synonym, or fix the form. **Do not import until this is "
                     "empty** — a blank result drops the case out of every "
                     "denominator that counts it.\n\n")
            for f, field, val in unmapped:
                fh.write(f"- `{f}` · {field}: `{val}`\n")
            fh.write("\n")

        if low:
            fh.write("## Low-confidence rows need line-by-line confirmation\n\n")
            fh.write("`NEEDS-REVIEW_responses.csv` was scraped positionally from "
                     "forms that are not one of `dist/templates/*.docx`. The "
                     "standard IDs and results were matched by pattern, not by "
                     "field identity. Read every row against the source form "
                     "before merging it into `ingested_responses.csv`.\n\n")
            for r in low:
                fh.write(f"- `{r['file']}` — {len(r['responses'])} row(s)\n")
            fh.write("\n")

        fh.write("## Before importing\n\n")
        fh.write("- [ ] Unrecognised values section is empty\n")
        fh.write("- [ ] Every rejected file has been dealt with (redacted, "
                "OCR'd, or routed to a human)\n")
        fh.write("- [ ] Low-confidence rows confirmed against their source forms\n")
        fh.write("- [ ] `ReviewCase` and `Standard` resolve to real list items — "
                "these are lookup columns and a CSV carries only the display "
                "value\n")
        fh.write("- [ ] Source forms are handled as CUI and not left in this repo\n")

    for p, n in ((hp, hn), (lp, ln), (sp, sn)):
        print(f"  {os.path.basename(p):<32} {n:>4} rows")
    print(f"  {os.path.basename(rp):<32} report")
    if rejected or unmapped:
        print(f"\n! {len(rejected)} rejected, {len(unmapped)} unrecognised — "
              f"see ingest-report.md. Not safe to import.")
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--inspect", metavar="PATH")
    ap.add_argument("--parse", metavar="PATH")
    ap.add_argument("--out", default="dist/ingest")
    args = ap.parse_args()

    if args.inspect:
        return cmd_inspect(args.inspect)
    if args.parse:
        return cmd_parse(args.parse, args.out)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Tests for the form parser's refusal behaviour.

  python3 tools/test_parse_review_forms.py

Builds fixtures in a temp dir and asserts what the parser must refuse. Every
case here is a real bug that was present in the first version:

  * the item 12 gate checked one table row at a time, so a form with the
    ratings in a header row and the tick in the row beneath sailed through;
  * the inline pattern only matched result words it already knew, so an
    unrecognised value produced no match at all and was dropped in silence —
    the exact failure the tool exists to prevent.

Both were found by running the parser against a form that should have been
refused and watching it not be. Keep these tests.
"""

import os
import shutil
import sys
import tempfile
import zipfile
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx import Document  # noqa: E402

import parse_review_forms as P  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def filled_template(out):
    """A DHA455 staging template with its content controls filled in."""
    src = os.path.join(ROOT, "dist", "templates", "DHA455_PAR_Template.docx")
    dst = os.path.join(out, "completed_455.docx")
    shutil.copy(src, dst)
    vals = {
        "C455_I11_standardofcare": "MET",
        "C455_I11_medication": "Not Met",     # variant spelling, must canonicalise
        "C455_I11_blood": "N/A",
        "C455_I11_consults": "MET",
    }
    z = zipfile.ZipFile(dst)
    items = {n: z.read(n) for n in z.namelist()}
    z.close()
    xml = items["word/document.xml"].decode()
    for tag, v in vals.items():
        xml = re.sub(
            r'(<w:tag w:val="%s"/>.*?<w:sdtContent>.*?<w:t[^>]*>)(.*?)(</w:t>)' % tag,
            lambda m: m.group(1) + v + m.group(3), xml, flags=re.S,
        )
    xml = xml.replace("Item 12 — Overall rating",
                      "Case RC-2026-0001 Overall: Satisfactory Item 12 — Overall rating", 1)
    items["word/document.xml"] = xml.encode()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zo:
        for n, b in items.items():
            zo.writestr(n, b)
    return dst


def item12_marked(out):
    """Ratings in a header row, the mark in the row beneath — the layout that
    defeated the original row-local gate."""
    d = Document()
    d.add_paragraph("Case RC-2026-0009")
    t = d.add_table(rows=2, cols=4)
    for i, h in enumerate(["Poor", "Fair", "Good", "Superior"]):
        t.rows[0].cells[i].text = h
    t.rows[1].cells[2].text = "X"
    d.add_paragraph("DOC-001: MET")
    p = os.path.join(out, "item12_marked.docx")
    d.save(p)
    return p


def item12_blank(out):
    """The same scale with nothing marked — this is our own template's empty
    item 12 box and must NOT be refused."""
    d = Document()
    d.add_paragraph("Case RC-2026-0011")
    t = d.add_table(rows=2, cols=4)
    for i, h in enumerate(["Poor", "Fair", "Good", "Superior"]):
        t.rows[0].cells[i].text = h
    d.add_paragraph("DOC-001: MET")
    p = os.path.join(out, "item12_blank.docx")
    d.save(p)
    return p


def with_pii(out):
    d = Document()
    d.add_paragraph("Case RC-2026-0008")
    d.add_paragraph("Patient Name: DOE, JOHN   DOB: 01/02/1990   MRN: 5544332")
    d.add_paragraph("DOC-001: MET")
    p = os.path.join(out, "with_pii.docx")
    d.save(p)
    return p


def odd_value(out):
    p = os.path.join(out, "odd_value.txt")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("Case RC-2026-0010\nDOC-001: Partially Met\nMED-001: MET\n")
    return p


def main():
    out = tempfile.mkdtemp(prefix="ecaf-forms-")
    try:
        elements, constructs = P.load_element_keys()
        parse = lambda p: P.parse_file(p, elements, constructs)

        print("Form parser refusal behaviour\n")

        r = parse(filled_template(out))
        check("filled template parses at high confidence", r["confidence"] == "high")
        check("no blocking reason on a clean template", not r["blocked"], r["blocked"])
        got = {k: v for k, v, _ in r["elements"]}
        check("'Not Met' canonicalises to NOT_MET", got.get("medication") == "NOT_MET", got)
        check("'N/A' canonicalises to NA", got.get("blood") == "NA", got)
        check("all four item 11 elements read", len(r["elements"]) == 4, got)

        r = parse(item12_marked(out))
        check("marked item 12 rating rejects the file",
              any("item 12" in b for b in r["blocked"]), r["blocked"])

        r = parse(item12_blank(out))
        check("unmarked item 12 scale does NOT reject", not r["blocked"], r["blocked"])

        r = parse(with_pii(out))
        labels = " ".join(r["blocked"])
        check("patient identifiers reject the file", bool(r["blocked"]))
        check("MRN detected", "MRN" in labels, labels)
        check("date of birth detected", "date-of-birth" in labels, labels)
        check("patient name detected", "patient name" in labels, labels)
        check("nothing extracted from a rejected file", not r["responses"])

        r = parse(odd_value(out))
        check("unrecognised value is reported, not dropped",
              any(f == "DOC-001" for f, _ in r["unmapped"]), r["unmapped"])
        check("unrecognised value is NOT stored as a result",
              all(sid != "DOC-001" for sid, _, _ in r["responses"]), r["responses"])
        check("the recognisable value beside it still parses",
              any(sid == "MED-001" for sid, _, _ in r["responses"]), r["responses"])
    finally:
        shutil.rmtree(out, ignore_errors=True)

    print()
    if failures:
        print(f"FAILED — {len(failures)}:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("PASS — all refusal behaviour holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

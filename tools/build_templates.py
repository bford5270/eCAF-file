#!/usr/bin/env python3
"""Build order step 6 — emit dist/templates/*.docx staging templates.

Each template carries real Word plain-text content controls whose tag/alias match
the MapsTo token vocabulary in standards/standards-schema.json, which is what the
Word Online (Business) "Populate a Word template" action (flow F6) binds to.

Tokens are sanitised for the control name: ':' and '-' become '_', because the
Word connector exposes control names as flow parameter names and rejects the
punctuation. The mapping is mechanical and reversible — see control_name().

CUI marking goes in the page header AND footer of every template, so it survives
printing, page extraction, and copy-paste of a single page.

DHA 455 item 12 is rendered as an empty bordered table with NO content control.
There is deliberately nothing for a flow to bind to.

Usage: python3 tools/build_templates.py
"""

import os

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist", "templates")

CUI = ("CUI // Medical Quality Assurance Program document protected "
       "pursuant to 10 U.S.C. § 1102")

_cc_id = [1000]


def control_name(token: str) -> str:
    """MapsTo token -> Word content control name.

    455-I11:medication -> C455_I11_medication
    FPPE-3I            -> FPPE_3I
    Leading digits are prefixed with 'C' because a flow parameter name cannot
    start with a digit.
    """
    n = token.replace(":", "_").replace("-", "_").replace(".", "_")
    return ("C" + n) if n[0].isdigit() else n


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def add_content_control(paragraph, token, placeholder="[VERIFY]"):
    """Append a plain-text content control to `paragraph`.

    python-docx has no API for structured document tags, so the sdt element is
    built directly. Every control gets a unique w:id; duplicate ids make Word
    repair the file on open.
    """
    _cc_id[0] += 1
    name = control_name(token)
    sdt = parse_xml(
        f'<w:sdt {nsdecls("w")}>'
        f'  <w:sdtPr>'
        f'    <w:rPr><w:color w:val="A80000"/></w:rPr>'
        f'    <w:alias w:val="{_xml_escape(name)}"/>'
        f'    <w:tag w:val="{_xml_escape(name)}"/>'
        f'    <w:id w:val="{_cc_id[0]}"/>'
        f'    <w:text/>'
        f'  </w:sdtPr>'
        f'  <w:sdtContent>'
        f'    <w:r><w:rPr><w:color w:val="A80000"/></w:rPr>'
        f'    <w:t xml:space="preserve">{_xml_escape(placeholder)}</w:t></w:r>'
        f'  </w:sdtContent>'
        f'</w:sdt>'
    )
    paragraph._p.append(sdt)
    return name


def shade(cell, hex_fill):
    cell._tc.get_or_add_tcPr().append(
        parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_fill}"/>')
    )


def marked_document():
    """A Document with the CUI marking in both header and footer."""
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)

    section = doc.sections[0]
    for part in (section.header, section.footer):
        p = part.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(CUI)
        run.bold = True
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0x7A, 0x0F, 0x0F)
    return doc


def heading(doc, text, size=14):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(size)
    return p


def field_row(table, label, token, placeholder="[VERIFY]"):
    """One label/value row where the value is a bound content control."""
    row = table.add_row()
    row.cells[0].text = label
    add_content_control(row.cells[1].paragraphs[0], token, placeholder)
    return row


def provider_block(doc):
    """Identity block. Provider identity only — no patient identifiers appear on
    any staged document. FIN lives on the review case, never on a rolled-up
    product, because a product aggregates many encounters."""
    heading(doc, "Provider")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    for label, token in [
        ("Name", "PROVIDER_NAME"),
        ("Rank / Grade", "PROVIDER_RANK"),
        ("Specialty", "PROVIDER_SPECIALTY"),
        ("Department", "PROVIDER_DEPARTMENT"),
        ("Privileging status", "PROVIDER_PRIVSTATUS"),
        ("Review period", "PERIOD_RANGE"),
    ]:
        field_row(t, label, token)
    doc.add_paragraph()


def signature_block(doc, stages):
    heading(doc, "Endorsements")
    t = doc.add_table(rows=1, cols=4)
    t.style = "Table Grid"
    for i, h in enumerate(["Stage", "Name", "Signature", "Date"]):
        t.rows[0].cells[i].text = h
        shade(t.rows[0].cells[i], "D9D9D9")
    for stage in stages:
        row = t.add_row()
        row.cells[0].text = stage
    doc.add_paragraph()


def draft_exclusion_note(doc):
    p = doc.add_paragraph()
    r = p.add_run(
        "Standards in DRAFT-VALIDATE status are excluded from this document. "
        "They are answered during review and shown on the dashboard, but do not "
        "appear here until a Clinical Leader has validated them."
    )
    r.font.size = Pt(8)
    r.italic = True


# ---------------------------------------------------------------------------
# FPPE
# ---------------------------------------------------------------------------
def build_fppe():
    doc = marked_document()
    heading(doc, "Focused Professional Practice Evaluation (FPPE)", 16)
    provider_block(doc)

    heading(doc, "Section 3 — Practice data")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    field_row(t, "3.E  Appropriate medication use (Y/N/NA)", "FPPE-3E")
    field_row(t, "3.F  Broad scope of treatments reviewed", "FPPE-3F")
    field_row(t, "3.I  % incomplete notes > 3 business days", "FPPE-3I")
    field_row(t, "3.J  Appropriate blood / blood component use", "FPPE-3J")
    field_row(t, "3.L  # record reviews NOT within standard of care", "FPPE-3L")
    doc.add_paragraph()

    heading(doc, "Section 4 — Competency domains")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    field_row(t, "Patient Care", "FPPE-4-PC")
    field_row(t, "Professional Knowledge", "FPPE-4-PK")
    field_row(t, "Practice Based Learning & Improvement", "FPPE-4-PBLI")
    field_row(t, "Interpersonal & Communication Skills", "FPPE-4-ICS")
    doc.add_paragraph()

    heading(doc, "Standards assessed")
    p = doc.add_paragraph()
    add_content_control(p, "STANDARDS_TABLE_FPPE", "[VERIFY] standards table")
    draft_exclusion_note(doc)

    heading(doc, "Clinical Leader assessment")
    p = doc.add_paragraph()
    add_content_control(p, "FPPE_CL_ASSESSMENT", "[VERIFY] narrative")

    signature_block(doc, ["Preceptor", "Clinical Leader"])
    return doc, "FPPE_Template.docx"


# ---------------------------------------------------------------------------
# OPPE
# ---------------------------------------------------------------------------
def build_oppe():
    doc = marked_document()
    heading(doc, "Ongoing Professional Practice Evaluation (OPPE)", 16)
    provider_block(doc)

    heading(doc, "Section III — Documentation")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    field_row(t, "III.F  % incomplete notes > 3 business days", "OPPE-IIIF")
    doc.add_paragraph()

    heading(doc, "Section IV — Clinical practice")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    field_row(t, "IV.D  Appropriate blood / blood component use", "OPPE-IVD")
    field_row(t, "IV.E  Appropriate medication use", "OPPE-IVE")
    field_row(t, "IV.F  Medical record pertinence review", "OPPE-IVF")
    field_row(t, "IV.G  Medical record OPPE review (# reviewed)", "OPPE-IVG")
    field_row(t, "IV.H  Medical record OPPE review (# deficient)", "OPPE-IVH")
    doc.add_paragraph()

    heading(doc, "Section V — Specialty specific quality indicators")
    p = doc.add_paragraph()
    r = p.add_run("Minimum two per OPPE period.")
    r.font.size = Pt(8)
    r.italic = True
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    field_row(t, "Indicator 1", "OPPE-V")
    field_row(t, "Indicator 2", "OPPE-V-2")
    doc.add_paragraph()

    heading(doc, "Review basis")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    # Stated on the face of the document. A reader must be able to see the
    # denominator without going back to the app.
    field_row(t, "Qualifying peer reviews completed in period", "REVIEW_COUNT")
    field_row(t, "Review floor", "REVIEW_FLOOR")
    field_row(t, "Cross-specialty reviews (not counted toward floor)", "XSPEC_COUNT")
    doc.add_paragraph()

    heading(doc, "Standards assessed")
    p = doc.add_paragraph()
    add_content_control(p, "STANDARDS_TABLE_OPPE", "[VERIFY] standards table")
    draft_exclusion_note(doc)

    signature_block(doc, ["Provider", "Peer / Proctor", "CRC Chair", "Department Head"])
    return doc, "OPPE_Template.docx"


# ---------------------------------------------------------------------------
# DHA 455 — Provider Adverse-action / Performance Assessment Report
# ---------------------------------------------------------------------------
def build_dha455():
    doc = marked_document()
    heading(doc, "DHA Form 455 — Performance Assessment Report (staging copy)", 16)

    p = doc.add_paragraph()
    r = p.add_run(
        "Staging copy. Transcribe onto the current official DHA Form 455 before "
        "signature — this is not a substitute for the form."
    )
    r.font.size = Pt(8)
    r.italic = True
    r.font.color.rgb = RGBColor(0xA8, 0x00, 0x00)

    provider_block(doc)

    heading(doc, "Item 11 — Element results")
    t = doc.add_table(rows=1, cols=2)
    t.style = "Table Grid"
    t.rows[0].cells[0].text = "Element"
    t.rows[0].cells[1].text = "Met / Denominator"
    for c in t.rows[0].cells:
        shade(c, "D9D9D9")
    # Element list mirrors dist/app/src/fixed-instrument.json. If that file is
    # reconciled against the real form, re-run this script.
    for label, key in [
        ("Care within the applicable standard of care", "455-I11:standardofcare"),
        ("Medication use appropriate", "455-I11:medication"),
        ("Blood / blood component use appropriate", "455-I11:blood"),
        ("Consults and referrals appropriate and timely", "455-I11:consults"),
    ]:
        field_row(t, label, key)
    doc.add_paragraph()

    # ----- Item 12: blank, always. No content control. -----------------
    heading(doc, "Item 12 — Overall rating")
    t = doc.add_table(rows=2, cols=4)
    t.style = "Table Grid"
    for i, h in enumerate(["Poor", "Fair", "Good", "Superior"]):
        t.rows[0].cells[i].text = h
        shade(t.rows[0].cells[i], "D9D9D9")
    for c in t.rows[1].cells:
        c.text = ""
        c.paragraphs[0].add_run("\n")      # give the row printable height

    p = doc.add_paragraph()
    r = p.add_run(
        "Clinical supervisor determination required. This system displays "
        "aggregate evidence and does not rate item 12 — no source document "
        "crosswalks the Satisfactory/Unsatisfactory review scale to the "
        "Poor/Fair/Good/Superior scale. There is no content control in the row "
        "above and no automated path that can populate it."
    )
    r.font.size = Pt(8)
    r.bold = True
    r.font.color.rgb = RGBColor(0xA8, 0x00, 0x00)
    doc.add_paragraph()

    heading(doc, "Item 13 — Narrative")
    p = doc.add_paragraph()
    add_content_control(p, "455-I13", "[VERIFY] narrative")

    signature_block(doc, ["Clinical Supervisor"])
    return doc, "DHA455_PAR_Template.docx"


# ---------------------------------------------------------------------------
# Unified data sheet — every mapped field on one page, for reconciliation
# ---------------------------------------------------------------------------
def build_unified():
    doc = marked_document()
    heading(doc, "e-CAF Unified Data Sheet", 16)
    p = doc.add_paragraph()
    r = p.add_run(
        "Every mapped field in one place. Used to reconcile a provider's data "
        "before generating the individual products, and as the reconciliation "
        "target for the migration in docs/dry-run.md."
    )
    r.font.size = Pt(8)
    r.italic = True

    provider_block(doc)

    heading(doc, "All mapped tokens")
    t = doc.add_table(rows=1, cols=3)
    t.style = "Table Grid"
    for i, h in enumerate(["Token", "Feeds", "Value"]):
        t.rows[0].cells[i].text = h
        shade(t.rows[0].cells[i], "D9D9D9")

    tokens = [
        ("FPPE-3E", "FPPE 3.E medication use"),
        ("FPPE-3F", "FPPE 3.F scope of treatments"),
        ("FPPE-3I", "FPPE 3.I incomplete notes"),
        ("FPPE-3J", "FPPE 3.J blood use"),
        ("FPPE-3L", "FPPE 3.L reviews outside standard of care"),
        ("FPPE-4-PC", "FPPE 4 Patient Care"),
        ("FPPE-4-PK", "FPPE 4 Professional Knowledge"),
        ("FPPE-4-PBLI", "FPPE 4 Practice Based Learning"),
        ("FPPE-4-ICS", "FPPE 4 Interpersonal & Communication"),
        ("OPPE-IIIF", "OPPE III.F incomplete notes"),
        ("OPPE-IVD", "OPPE IV.D blood use"),
        ("OPPE-IVE", "OPPE IV.E medication use"),
        ("OPPE-IVF", "OPPE IV.F record pertinence"),
        ("OPPE-IVG", "OPPE IV.G records reviewed"),
        ("OPPE-IVH", "OPPE IV.H records deficient"),
        ("OPPE-V", "OPPE V specialty indicator"),
        ("455-I11:standardofcare", "455 item 11 standard of care"),
        ("455-I11:medication", "455 item 11 medication"),
        ("455-I11:blood", "455 item 11 blood"),
        ("455-I11:consults", "455 item 11 consults"),
        ("455-I13", "455 item 13 narrative"),
    ]
    for token, feeds in tokens:
        row = t.add_row()
        row.cells[0].text = token
        row.cells[1].text = feeds
        add_content_control(row.cells[2].paragraphs[0], token + "_U")

    doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run(
        "DASH-ONLY standards appear on the cross-specialty dashboard and "
        "deliberately have no field here — they map to no form."
    )
    r.font.size = Pt(8)
    r.italic = True

    return doc, "Unified_DataSheet.docx"


def main():
    os.makedirs(OUT, exist_ok=True)
    for builder in (build_fppe, build_oppe, build_dha455, build_unified):
        doc, name = builder()
        path = os.path.join(OUT, name)
        doc.save(path)
        print(f"  {name:<30} {os.path.getsize(path):>7,} bytes")
    print(f"\n4 templates written to dist/templates/")


if __name__ == "__main__":
    main()

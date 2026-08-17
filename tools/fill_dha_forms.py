#!/usr/bin/env python3
"""Fill the real DHA FPPE and OPPE PDFs from structured input.

  # 1. get a spreadsheet to fill in
  python3 tools/fill_dha_forms.py --blank-inputs my-oppe.csv --form OPPE
  # 2. fill my-oppe.csv in Excel, one row per provider, then:
  python3 tools/fill_dha_forms.py --fill my-oppe.csv --form OPPE \
        --template DHA_OPPE_Template.pdf --out filled/

  python3 tools/fill_dha_forms.py --list-fields DHA_OPPE_Template.pdf

This is the "put in inputs, get my form back" path. It writes into the ACTUAL
DHA PDF — the same file the MSP office already uses — not a lookalike. No
SharePoint, no Power Apps, no premium connector, no tenant approval. It runs on
a laptop.

THE LINE THIS TOOL DOES NOT CROSS
---------------------------------
It fills what is COUNTED. It never fills what is JUDGED.

  filled    Administrative identity, and the practice-volume data:
            FPPE Section 3 (A-L), OPPE Sections III and IV. These are counts and
            percentages the MSP already holds; typing them again by hand is
            transcription, and transcription is where errors enter.

  NEVER     FPPE Section 4 / OPPE Section VII — the 16 competency constructs.
            OPPE Section VI facility-wide monitors. Every signature block.
            DHA 455 item 12.

            These are a preceptor's, clinical leader's or supervisor's
            professional judgement about a named provider. A system that
            pre-checks them is not saving typing, it is manufacturing an
            assessment — and it would be indistinguishable on the signed page
            from one a human actually made. This is the same rule that keeps
            e-CAF out of DHA 455 item 12, applied consistently.

            `--fill` refuses input that tries to set one of these fields.

The DHA 455 is NOT supported. It is an XFA/LiveCycle form, which cannot be
reliably filled outside Adobe, and the copy supplied to this build is watermarked
DRAFT ("DHA FORM 455 (TEST), OCT 2025"). See docs/form-reconciliation.md.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from ecaf_normalize import scan_pii  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reader(path):
    from pypdf import PdfReader
    return PdfReader(path)


# --- Field maps: our input key -> the PDF's actual field name.
# Names are taken verbatim from the AcroForm; DHA's own naming has doubled
# spaces and dropped punctuation ("Total  of Encounters"), so these are ugly on
# purpose. Do not tidy them — they must match the PDF byte for byte.
FPPE_MAP = {
    "Medical Facility":            "Medical Facility",
    "Department/Clinic":           "DepartmentClinic",
    "Provider's Name":             "Providers Name",
    "Direct observation (exact number)": "Direct observation Exact number",
    "Record review (exact number)":      "Record review Exact number",
    # Section 3 — Practice Volume Data and Quality Measures (A-L), worded as
    # the form words them so the spreadsheet reads like the page in front of you.
    "3.A Total # of Encounters":                  "Total  of Encounters",
    "3.B Total # of Outpatient Encounters":       "Total  of Outpatient Encounters",
    "3.C Total # of Inpatient Encounters":        "Total  of Inpatient Encounters if applicable",
    "3.D Total # of surgical procedures":         "Total  of surgical procedures if applicable",
    "3.E Appropriate medication use (Y/N/NA)":    "Appropriate medication use Y N or NA",
    "3.F Broad scope of treatments reviewed (Y/N/NA)": "Broad scope of treatments reviewed Y N or NA",
    "3.G Total % of time in direct patient care": "Total  of time in direct patient care",
    "3.H Total # of patient safety events":       "Total  of adverse events",
    "3.I Total % of incomplete notes >3 business days": "Total  of incomplete notes 3 business days",
    "3.J Appropriate blood/blood components use (Y/N/NA)": "Appropriate blood useblood components use Y N or NA",
    "3.K Total # of completed record reviews":    "Total  of completed record reviews",
    "3.L Total # of record reviews NOT within standard of care": "Total  of record reviews NOT within standard of care",
    "Additional Comments":                        "Additional Comments",
}

OPPE_MAP = {
    "Reporting Activity":  "Reporting Activity",
    "Provider Rank/Name":  "Provider RankName",
    "Period From":         "From",
    "Period To":           "To",
    "Department":          "Department",
    "Position":            "Position",
    "Department Specific Life Support/Trainings and expiration":
                           "Department Specific Life SupportTrainings and expiration",
    # Section III — Practice Volume Data (A-F)
    "III.A Number of Admissions":                    "Number of Admissions",
    "III.B Number of outpatient encounters":         "Number of outpatient encounters",
    "III.C Days unavailable due to TAD/deployment":  "Days unavailable due to TADdeployment etc",
    "III.D Number of adverse events":                "Number of adverse events",
    "III.E Percent of time in direct patient care":  "Percent of time in direct patient care",
    "III.F % incomplete notes > 3 business days":    " incomplete notes  3 business days",
    # Section IV.G/H. The PDF names these fields "FPPE review" — a typo in DHA's
    # own form; on the page they sit under Section IV "Medical record OPPE
    # review". Column reads as the page does, value goes where the PDF wants it.
    "IV.G Medical record OPPE review (# reviewed)":  "Medical record FPPE review  reviewed",
    "IV.H Medical record OPPE review (# deficient)": "Medical record FPPE review  deficient",
    # Section V — specialty specific quality indicators (minimum of 2)
    "V.A Metric": "Metric",
    "V.B Metric": "Metric_2",
    "VIII Clinical competency narrative":
        "SECTION VIII CLINICAL COMPETENCY OF CORE AND NON CORE PRIVILEGES"
        "Address overall clinical competency of this provider attach "
        "additional sheets as neededRow1",
    # NOT MAPPED ON PURPOSE: OPPE Section IV A-F (surgical / invasive /
    # noninvasive procedures, blood use, medication use, record pertinence).
    # This PDF gives them no named fields — they are generic "Text195"-style
    # boxes and unlabelled dropdowns. Guessing which anonymous box is "blood
    # use" would put a number on a credentialing document based on a hunch.
    # Run --list-fields, identify them by opening the PDF, and add them here.
}

# Old code-style column names still work, so a spreadsheet made before the
# rename does not silently drop every value. Values are LISTS because the same
# old key means different fields on the two forms — "provider_name" is
# "Provider's Name" on the FPPE and "Provider Rank/Name" on the OPPE — so
# resolution tries each candidate against the map for the form being filled.
ALIASES = {
    "facility": ["Medical Facility"],
    "department": ["Department", "Department/Clinic"],
    "provider_name": ["Provider Rank/Name", "Provider's Name"],
    "position": ["Position"],
    "reporting_activity": ["Reporting Activity"],
    "period_from": ["Period From"], "period_to": ["Period To"],
    "s3a_total_encounters": ["3.A Total # of Encounters"],
    "s3b_outpatient_encounters": ["III.B Number of outpatient encounters",
                                  "3.B Total # of Outpatient Encounters"],
    "s3c_inpatient_encounters": ["3.C Total # of Inpatient Encounters"],
    "s3d_surgical_procedures": ["3.D Total # of surgical procedures"],
    "s3e_appropriate_med_use": ["3.E Appropriate medication use (Y/N/NA)"],
    "s3f_broad_scope_treatments": ["3.F Broad scope of treatments reviewed (Y/N/NA)"],
    "s3g_pct_direct_patient_care": ["3.G Total % of time in direct patient care"],
    "s3h_patient_safety_events": ["3.H Total # of patient safety events"],
    "s3i_pct_incomplete_notes": ["3.I Total % of incomplete notes >3 business days"],
    "s3j_appropriate_blood_use": ["3.J Appropriate blood/blood components use (Y/N/NA)"],
    "s3k_record_reviews_completed": ["3.K Total # of completed record reviews"],
    "s3l_reviews_not_within_soc": ["3.L Total # of record reviews NOT within standard of care"],
    "s3a_admissions": ["III.A Number of Admissions"],
    "s3c_days_unavailable": ["III.C Days unavailable due to TAD/deployment"],
    "s3d_adverse_events": ["III.D Number of adverse events"],
    "s3e_pct_direct_patient_care": ["III.E Percent of time in direct patient care"],
    "s3f_pct_incomplete_notes": ["III.F % incomplete notes > 3 business days"],
    "s4g_records_reviewed": ["IV.G Medical record OPPE review (# reviewed)"],
    "s4h_records_deficient": ["IV.H Medical record OPPE review (# deficient)"],
    "s5a_metric": ["V.A Metric"], "s5b_metric": ["V.B Metric"],
    "additional_comments": ["Additional Comments"],
}


def resolve_key(k, fmap):
    """Column name -> PDF field name. Tries the friendly name, then any old
    alias that exists in this form's map. Returns None if unknown."""
    if k in fmap:
        return fmap[k]
    for cand in ALIASES.get(k, []):
        if cand in fmap:
            return fmap[cand]
    return None

# Never fillable, whatever the input says. Matched case-insensitively as a
# substring of the PDF field name.
JUDGEMENT_FIELDS = [
    "satisfactory", "unsatisfactory", "not observed", "notobserved",
    "signature", "sign", "recommendation", "approval",
    "poor", "fair", "good", "superior",
    "check box",          # every /Btn on these forms is a judgement or a reason code
]


def is_judgement_field(name):
    n = name.lower()
    return any(t in n for t in JUDGEMENT_FIELDS)


def cmd_list_fields(path):
    r = _reader(path)
    fields = r.get_fields() or {}
    print(f"{len(fields)} fields in {os.path.basename(path)}\n")
    for k, v in fields.items():
        kind = str(v.get("/FT", "?"))
        flag = "  [JUDGEMENT — never filled]" if is_judgement_field(k) else ""
        print(f"  {kind:<6} {k}{flag}")
    return 0


def load_records(path):
    """Accept .csv or .json. CSV is the normal case — one row per provider,
    openable in Excel, which is where this data already lives. Blank cells are
    dropped rather than written as empty strings, so a half-filled row fills the
    fields it has and leaves the rest alone."""
    if path.lower().endswith(".csv"):
        import csv as _csv
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return [{k: v for k, v in row.items() if k and str(v).strip()}
                    for row in _csv.DictReader(fh)]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else [data]


def cmd_blank_inputs(form, out):
    """Write a starter CSV: header = every key this tool accepts, plus one
    example row. Fill it in Excel, delete the example row, run --fill."""
    import csv as _csv
    fmap = resolve_map(form)
    keys = list(fmap)
    example = {
        "provider_name": "PROVIDER, SAMPLE A.",
        "department": "SAMPLE Medical Battalion",
    }
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = _csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerow({k: example.get(k, "") for k in keys})
    print(f"Wrote {out} — {len(keys)} columns, one example row.\n")
    print("Next:")
    print("  1. Open it in Excel. One row per provider.")
    print("  2. Replace the example row with real values. Leave blanks blank.")
    print(f"  3. python3 tools/fill_dha_forms.py --fill {out} --form {form.upper()} \\")
    print("         --template <the DHA PDF> --out filled/")
    print("\nColumns map to the form as follows:")
    for k, v in fmap.items():
        print(f"  {k:<30} -> {v[:64]}")
    return 0


def resolve_map(form):
    return {"FPPE": FPPE_MAP, "OPPE": OPPE_MAP}[form.upper()]


def write_xfdf(values, template_name, out_path):
    """Write an Acrobat XFDF — the field values, not the document.

    Why this exists: the person filling forms is not the person who can install
    Python. An XFDF is opened by double-clicking it; Acrobat finds the PDF named
    in <f href> and populates it. Nothing installs on the recipient's machine,
    and a credentialing office already lives in Acrobat.

    The PDF must sit next to the XFDF (or at the href path) — Acrobat resolves
    href relative to the XFDF's own location.
    """
    import xml.sax.saxutils as sax
    fields = "".join(
        f"<field name={sax.quoteattr(name)}><value>{sax.escape(str(val))}</value></field>"
        for name, val in values.items()
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xfdf xmlns="http://ns.adobe.com/xfdf/" xml:space="preserve">'
        f"<f href={sax.quoteattr(template_name)}/>"
        f"<fields>{fields}</fields></xfdf>"
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(xml)


def cmd_fill(inputs_path, form, template, outdir, fmt="both"):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject

    records = load_records(inputs_path)

    fmap = resolve_map(form)
    reader = PdfReader(template)
    pdf_fields = set((reader.get_fields() or {}).keys())
    os.makedirs(outdir, exist_ok=True)

    problems, written = [], []

    for rec in records:
        who = (rec.get("Provider Rank/Name") or rec.get("Provider's Name")
               or rec.get("provider_name") or rec.get("_id") or "unnamed")

        # --- Refuse judgement fields, whatever they are called.
        for k in rec:
            if k.startswith("_"):
                continue
            target = resolve_key(k, fmap) or k
            looks_like_rating = str(rec.get(k, "")).strip().lower() in (
                "satisfactory", "unsatisfactory", "not observed", "notobserved",
                "poor", "fair", "good", "superior",
            )
            if is_judgement_field(target) or is_judgement_field(k) or looks_like_rating:
                problems.append(
                    f"{who}: refused '{k}'. Competency ratings, facility-wide "
                    f"monitors and signatures are a human's judgement about a named "
                    f"provider; this tool fills counts, not assessments."
                )

        # --- Refuse patient identifiers.
        blob = " ".join(f"{k} {v}" for k, v in rec.items())
        for label, hit in scan_pii(blob):
            problems.append(f"{who}: refused input containing a {label} ({hit!r}).")

        refused = {k for k in rec if not k.startswith('_') and (
            is_judgement_field(fmap.get(k, k)) or is_judgement_field(k)
            or str(rec[k]).strip().lower() in (
                'satisfactory','unsatisfactory','not observed','notobserved',
                'poor','fair','good','superior'))}
        values, unknown = {}, []
        for k, v in rec.items():
            if k.startswith("_") or v in (None, ""):
                continue
            if k in refused:
                continue                      # already reported above
            target = resolve_key(k, fmap)
            if target is None:
                unknown.append(k)
                continue
            if target not in pdf_fields:
                problems.append(
                    f"{who}: field map says '{k}' -> '{target}', which is not in "
                    f"this PDF. The template version may differ from the one this "
                    f"map was built against — run --list-fields and fix the map."
                )
                continue
            if is_judgement_field(target):
                continue
            values[target] = str(v)

        if unknown:
            problems.append(f"{who}: no mapping for {unknown} — dropped, not guessed.")

        writer = PdfWriter(clone_from=template)
        # NeedAppearances makes viewers render values we set without us having to
        # generate appearance streams per field.
        writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)
        for page in writer.pages:
            writer.update_page_form_field_values(page, values, auto_regenerate=False)

        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(who)).strip("-") or "form"
        stem = os.path.join(outdir, f"{form.upper()}_{safe}")

        if fmt in ("pdf", "both"):
            with open(stem + ".pdf", "wb") as fh:
                writer.write(fh)
            written.append((stem + ".pdf", len(values)))

        if fmt in ("xfdf", "both"):
            write_xfdf(values, os.path.basename(template), stem + ".xfdf")
            written.append((stem + ".xfdf", len(values)))

    for out, n in written:
        print(f"  {os.path.basename(out):<44} {n:>3} fields filled")

    if problems:
        print(f"\n! {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")

    n_pdf = sum(1 for f, _ in written if f.endswith(".pdf"))
    n_xfdf = sum(1 for f, _ in written if f.endswith(".xfdf"))
    print(f"\n{n_pdf} PDF(s), {n_xfdf} XFDF(s) into {outdir}/")
    if n_xfdf:
        print(f"Put {os.path.basename(template)} in that folder alongside the "
              f".xfdf files, then send both. The recipient double-clicks the "
              f".xfdf and Acrobat opens the form populated — nothing to install.")
    print("Sections left deliberately blank for a human: "
          + ("FPPE Section 4 (16 competency constructs) and all signatures."
             if form.upper() == "FPPE" else
             "OPPE Section VI monitors, Section VII (16 competency constructs), "
             "and Section X endorsements."))
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blank-inputs", metavar="OUT_CSV",
                    help="write a starter CSV you fill in Excel (needs --form)")
    ap.add_argument("--list-fields", metavar="PDF")
    ap.add_argument("--fill", metavar="INPUTS_JSON")
    ap.add_argument("--form", choices=["FPPE", "OPPE", "fppe", "oppe"])
    ap.add_argument("--template", metavar="PDF")
    ap.add_argument("--out", default="dist/filled")
    ap.add_argument("--format", choices=["pdf", "xfdf", "both"], default="both",
                    help="pdf = a filled PDF you can check; xfdf = a file the "
                         "recipient double-clicks to open the real DHA form "
                         "populated, with nothing to install; both (default)")
    a = ap.parse_args()

    if a.blank_inputs:
        if not a.form:
            ap.error("--blank-inputs needs --form FPPE or --form OPPE")
        return cmd_blank_inputs(a.form, a.blank_inputs)
    if a.list_fields:
        return cmd_list_fields(a.list_fields)
    if a.fill:
        if not (a.form and a.template):
            ap.error("--fill needs --form and --template")
        return cmd_fill(a.fill, a.form, a.template, a.out, a.format)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

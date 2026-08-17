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
    "facility":            "Medical Facility",
    "department":          "DepartmentClinic",
    "provider_name":       "Providers Name",
    "direct_obs_count":    "Direct observation Exact number",
    "record_review_count": "Record review Exact number",
    # Section 3 — Practice Volume Data and Quality Measures (A-L)
    "s3a_total_encounters":        "Total  of Encounters",
    "s3b_outpatient_encounters":   "Total  of Outpatient Encounters",
    "s3c_inpatient_encounters":    "Total  of Inpatient Encounters if applicable",
    "s3d_surgical_procedures":     "Total  of surgical procedures if applicable",
    "s3e_appropriate_med_use":     "Appropriate medication use Y N or NA",
    "s3f_broad_scope_treatments":  "Broad scope of treatments reviewed Y N or NA",
    "s3g_pct_direct_patient_care": "Total  of time in direct patient care",
    "s3h_patient_safety_events":   "Total  of adverse events",
    "s3i_pct_incomplete_notes":    "Total  of incomplete notes 3 business days",
    "s3j_appropriate_blood_use":   "Appropriate blood useblood components use Y N or NA",
    "s3k_record_reviews_completed":"Total  of completed record reviews",
    "s3l_reviews_not_within_soc":  "Total  of record reviews NOT within standard of care",
    "additional_comments":         "Additional Comments",
}

OPPE_MAP = {
    "reporting_activity": "Reporting Activity",
    "provider_name": "Provider RankName",
    "period_from": "From",
    "period_to":   "To",
    "department":  "Department",
    "position":    "Position",
    "life_support_trainings": "Department Specific Life SupportTrainings and expiration",
    # Section III — Practice Volume Data (A-F)
    "s3a_admissions":              "Number of Admissions",
    "s3b_outpatient_encounters":   "Number of outpatient encounters",
    "s3c_days_unavailable":        "Days unavailable due to TADdeployment etc",
    "s3d_adverse_events":          "Number of adverse events",
    "s3e_pct_direct_patient_care": "Percent of time in direct patient care",
    "s3f_pct_incomplete_notes":    " incomplete notes  3 business days",
    # Section IV.G/H. The PDF names these "FPPE review" — a typo in DHA's own
    # form; on the page they sit under Section IV "Medical record OPPE review".
    # Mapped to what the page says, keyed to what the PDF actually calls them.
    "s4g_records_reviewed":  "Medical record FPPE review  reviewed",
    "s4h_records_deficient": "Medical record FPPE review  deficient",
    # Section V — specialty specific quality indicators (minimum of 2)
    "s5a_metric": "Metric",
    "s5b_metric": "Metric_2",
    # Section VIII / IX narrative
    "s8_clinical_competency": "SECTION VIII CLINICAL COMPETENCY OF CORE AND NON CORE PRIVILEGES"
                              "Address overall clinical competency of this provider attach "
                              "additional sheets as neededRow1",
    # NOT MAPPED ON PURPOSE: OPPE Section IV A-F (surgical / invasive /
    # noninvasive procedures, blood use, medication use, record pertinence).
    # This PDF gives them no named fields — they are generic "Text195"-style
    # boxes and unlabelled dropdowns. Guessing which anonymous box is "blood
    # use" would put a number on a credentialing document based on a hunch.
    # Run --list-fields, identify them by opening the PDF, and add them here.
}

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


def cmd_fill(inputs_path, form, template, outdir):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject

    records = load_records(inputs_path)

    fmap = resolve_map(form)
    reader = PdfReader(template)
    pdf_fields = set((reader.get_fields() or {}).keys())
    os.makedirs(outdir, exist_ok=True)

    problems, written = [], []

    for rec in records:
        who = rec.get("provider_name") or rec.get("_id") or "unnamed"

        # --- Refuse judgement fields, whatever they are called.
        for k in rec:
            if k.startswith("_"):
                continue
            target = fmap.get(k, k)
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
            target = fmap.get(k)
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
        out = os.path.join(outdir, f"{form.upper()}_{safe}.pdf")
        with open(out, "wb") as fh:
            writer.write(fh)
        written.append((out, len(values)))

    for out, n in written:
        print(f"  {os.path.basename(out):<44} {n:>3} fields filled")

    if problems:
        print(f"\n! {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")

    print(f"\nFilled {len(written)} form(s) into {outdir}/")
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
        return cmd_fill(a.fill, a.form, a.template, a.out)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

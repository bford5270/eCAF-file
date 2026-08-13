#!/usr/bin/env python3
"""The single canonical vocabulary. Import it; never re-declare it.

CLAUDE.md hard rule: element results are stored as exactly MET | NOT_MET | NA,
and a second representation must never be introduced. That rule is about stored
data, but it applies just as much to the code that produces it — two ingestion
tools with two private copies of the variant table is precisely how the
predecessor ended up writing "Not Met" down one path and "NOT_MET" down another.

So `migrate_ewp.py` and `parse_review_forms.py` both import from here, and
`tools/lint_hard_rules.py` fails the build if either declares its own copy.

Nothing in this module guesses. Every canonicaliser returns (value, ok) and
reports ok=False rather than picking a plausible answer, because a wrongly
canonicalised MET is invisible and permanent, while a refusal is loud and
fixable.
"""

import re

# --- element / standard results -------------------------------------------
RESULT_CANON = {
    "met": "MET",
    "yes": "MET",
    "y": "MET",
    "pass": "MET",
    "passed": "MET",
    "compliant": "MET",
    "satisfactory": "MET",
    "notmet": "NOT_MET",
    "not met": "NOT_MET",
    "not_met": "NOT_MET",
    "not-met": "NOT_MET",
    "no": "NOT_MET",
    "n": "NOT_MET",
    "fail": "NOT_MET",
    "failed": "NOT_MET",
    "noncompliant": "NOT_MET",
    "non-compliant": "NOT_MET",
    "unsatisfactory": "NOT_MET",
    "deficient": "NOT_MET",
    "na": "NA",
    "n/a": "NA",
    "n\\a": "NA",
    "notapplicable": "NA",
    "not applicable": "NA",
    "not observed": "NA",
    "notobserved": "NA",
    "": "NA",
}

# --- overall determination (eCAF_ReviewSummaries.OverallDetermination) ------
DETERMINATION_CANON = {
    "satisfactory": "Satisfactory",
    "sat": "Satisfactory",
    "s": "Satisfactory",
    "acceptable": "Satisfactory",
    "unsatisfactory": "Unsatisfactory",
    "unsat": "Unsatisfactory",
    "u": "Unsatisfactory",
    "unacceptable": "Unsatisfactory",
}

# --- competency constructs -------------------------------------------------
CONSTRUCT_CANON = {
    "satisfactory": "Satisfactory",
    "sat": "Satisfactory",
    "s": "Satisfactory",
    "unsatisfactory": "Unsatisfactory",
    "unsat": "Unsatisfactory",
    "u": "Unsatisfactory",
    "notobserved": "NotObserved",
    "not observed": "NotObserved",
    "not-observed": "NotObserved",
    "no": "NotObserved",
    "n/o": "NotObserved",
    "na": "NotObserved",
    "n/a": "NotObserved",
}

# --- the scale that must never be ingested ---------------------------------
# DHA 455 item 12. CLAUDE.md: no source document crosswalks the
# Satisfactory/Unsatisfactory review scale to Poor/Fair/Good/Superior, so the
# system displays aggregate evidence and leaves item 12 to the clinical
# supervisor. A parser that reads a rating off a form and stores it would be
# doing exactly the auto-rating the rule prohibits — worse than computing it,
# because it would look like provenance.
ITEM12_SCALE = {"poor", "fair", "good", "superior"}

# --- patient identifiers that must never enter the system ------------------
# FIN is the sole encounter identifier. These are a tripwire, not a guarantee:
# they catch labelled fields and formatted identifiers, which is what a real
# peer review form has. They cannot recognise a bare patient name, so the
# operator review step in the parser is not optional.
PII_PATTERNS = [
    (re.compile(r"\bSSN\b|\bsocial\s+security\b", re.I), "SSN label"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "SSN-formatted number"),
    (re.compile(r"\bMRN\b|\bmedical\s+record\s+(number|no|#)", re.I), "MRN label"),
    (re.compile(r"\bDOB\b|\bdate\s+of\s+birth\b", re.I), "date-of-birth label"),
    (re.compile(r"\bpatient\s+(name|first|last)\b", re.I), "patient name label"),
    (re.compile(r"\bpt\.?\s+name\b", re.I), "patient name label"),
    (re.compile(r"\bbeneficiary\s+name\b", re.I), "patient name label"),
    (re.compile(r"\bEDIPI\b|\bDoD\s*ID\b", re.I), "DoD ID label"),
    (re.compile(r"\bsponsor\s+ssn\b", re.I), "sponsor SSN label"),
]

# A FIN is alphanumeric, <= 12 chars. Nine straight digits reads as an SSN far
# more often than a FIN. Mirrors the FINLooksValid UDF in App.fx.yaml.
FIN_RE = re.compile(r"^[A-Za-z0-9]{1,12}$")


def canonical_result(raw):
    """(canonical, ok). ok=False means unrecognised — report, never guess."""
    key = ("" if raw is None else str(raw)).strip().lower()
    if key in RESULT_CANON:
        return RESULT_CANON[key], True
    return None, False


def canonical_determination(raw):
    key = ("" if raw is None else str(raw)).strip().lower()
    if key in DETERMINATION_CANON:
        return DETERMINATION_CANON[key], True
    return None, False


def canonical_construct(raw):
    key = ("" if raw is None else str(raw)).strip().lower()
    if key in CONSTRUCT_CANON:
        return CONSTRUCT_CANON[key], True
    return None, False


def is_item12_value(raw):
    """True if the value is a DHA 455 item 12 rating. Callers must refuse it."""
    return ("" if raw is None else str(raw)).strip().lower() in ITEM12_SCALE


def fin_looks_valid(raw):
    t = ("" if raw is None else str(raw)).strip()
    return bool(FIN_RE.match(t)) and not re.match(r"^\d{9}$", t)


def scan_pii(text):
    """[(label, matched_text)] for every patient identifier found."""
    hits = []
    for pattern, label in PII_PATTERNS:
        for m in pattern.finditer(text or ""):
            hits.append((label, m.group(0)))
    return hits


def csv_safe(value):
    """Neutralise spreadsheet formula injection.

    Ingested and migrated values land in CSVs the operator is instructed to open
    and reconcile, which in practice means Excel. A cell beginning =, +, -, @,
    tab or CR is a formula or DDE payload waiting for that double-click.
    Prefixing a single quote makes Excel treat it as text; SharePoint import
    does not evaluate formulas, so the imported value is unchanged.
    """
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s

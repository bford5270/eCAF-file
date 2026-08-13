#!/usr/bin/env python3
"""Enforce the CLAUDE.md hard rules against the build artifacts.

CLAUDE.md ends every build phase with "a self-review against the Hard rules".
This is that review, automated, so it runs on every change rather than whenever
someone remembers. Exit code 1 on any violation.

What it cannot check is stated at the end of the run — the rules that only hold
if the operator does something in the browser. Those are in
docs/hard-rule-review.md and dist/lists/provisioning-runbook.md.

Usage: python3 tools/lint_hard_rules.py
"""

import csv
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

failures = []
checks_run = 0


def fail(rule, detail):
    failures.append((rule, detail))


def check(rule):
    global checks_run
    checks_run += 1
    print(f"  {rule}")


def walk(exts, *subdirs):
    for sub in subdirs:
        base = os.path.join(ROOT, sub)
        for dirpath, _, files in os.walk(base):
            if ".git" in dirpath:
                continue
            for f in files:
                if f.endswith(exts):
                    yield os.path.join(dirpath, f)


# ---------------------------------------------------------------------------
# Rule: FIN is the only encounter identifier. No MRN/SSN/DOB/patient name.
# ---------------------------------------------------------------------------
def rule_no_patient_identifiers():
    check("FIN is the sole encounter identifier — no MRN/SSN/DOB/patient name")
    # Word-boundary patterns. 'DOB' must not match 'DOB' inside a longer word,
    # and 'name' alone is far too broad — provider names are legitimate.
    banned = [
        (r"\bMRN\b", "MRN"),
        (r"\bSSN\b", "SSN"),
        (r"\bDOB\b", "DOB"),
        (r"\bDateOfBirth\b", "DateOfBirth"),
        (r"\bPatientName\b", "PatientName"),
        (r"\bPatientDOB\b", "PatientDOB"),
        (r"\bPatientID\b", "PatientID"),
        (r"\bMedicalRecordNumber\b", "MedicalRecordNumber"),
    ]

    # Schema column names are the real test — prose that says "do not enter an
    # SSN" is a good thing, not a violation. So check structure, not prose.
    with open(os.path.join(ROOT, "schemas", "lists.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    for lst in schema["lists"]:
        for col in lst["columns"]:
            for pat, label in banned:
                if re.search(pat, col["name"], re.I):
                    fail("FIN-only", f"{lst['internalName']}.{col['name']} looks like {label}")

    # CSV headers.
    for path in walk((".csv",), "dist/lists"):
        with open(path, newline="", encoding="utf-8-sig") as fh:
            header = next(csv.reader(fh), [])
        for h in header:
            for pat, label in banned:
                if re.search(pat, h, re.I):
                    fail("FIN-only", f"{os.path.basename(path)} column {h} looks like {label}")

    # Content control names in the templates.
    for path in walk((".docx",), "dist/templates"):
        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        for tag in re.findall(r'<w:tag w:val="([^"]+)"/>', xml):
            for pat, label in banned:
                if re.search(pat, tag, re.I):
                    fail("FIN-only", f"{os.path.basename(path)} control {tag} looks like {label}")


# ---------------------------------------------------------------------------
# Rule: normalize "not met" at write time — MET | NOT_MET | NA only.
# ---------------------------------------------------------------------------
def rule_canonical_results():
    check("Element results are exactly MET | NOT_MET | NA")
    variants = [
        r'"Not Met"', r'"not met"', r'"NotMet"', r'"not_met"',
        r'"N/A"', r'"n/a"', r'"Met"', r'"NA "',
    ]
    for path in walk((".fx.yaml", ".csv", ".json"), "dist"):
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                # Comments naming a bad variant are the point — they explain why
                # it must not exist. Only executable lines are violations.
                if line.lstrip().startswith(("#", "//", '"_')):
                    continue
                for v in variants:
                    m = re.search(v, line)
                    if m:
                        fail(
                            "canonical-results",
                            f"{os.path.relpath(path, ROOT)}:{i} non-canonical result value {m.group(0)}",
                        )

    # And the stored sample data really is canonical.
    p = os.path.join(ROOT, "dist", "lists", "eCAF_ReviewResponses.csv")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if row["Result"] not in ("MET", "NOT_MET", "NA"):
                fail("canonical-results", f"eCAF_ReviewResponses Result={row['Result']!r}")


# ---------------------------------------------------------------------------
# Rule: CUI + 1102 marking on every screen and every template.
# ---------------------------------------------------------------------------
def rule_cui_marking():
    check("CUI / 10 U.S.C. 1102 marking on every screen and template")
    for path in walk((".fx.yaml",), "dist/app/src/Screens"):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if "cmpCUIFooter" not in text:
            fail("cui-marking", f"{os.path.basename(path)} has no cmpCUIFooter instance")

    for path in walk((".docx",), "dist/templates"):
        z = zipfile.ZipFile(path)
        names = [n for n in z.namelist() if re.match(r"word/(header|footer)\d*\.xml", n)]
        marked = [
            n for n in names
            if "1102" in z.read(n).decode("utf-8") and "CUI" in z.read(n).decode("utf-8")
        ]
        if not marked:
            fail("cui-marking", f"{os.path.basename(path)} has no CUI/1102 header or footer")


# ---------------------------------------------------------------------------
# Rule: no auto-rating of DHA 455 item 12.
# ---------------------------------------------------------------------------
def rule_no_item12_rating():
    check("DHA 455 item 12 is never computed or bound")
    scale = re.compile(r"\b(Poor|Fair|Good|Superior)\b")

    # The 455 template must have no content control anywhere near item 12.
    p = os.path.join(ROOT, "dist", "templates", "DHA455_PAR_Template.docx")
    xml = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8")
    start = xml.find("Item 12")
    end = xml.find("Clinical supervisor determination")
    if start == -1 or end == -1:
        fail("item-12", "DHA455 template: item 12 block or its note is missing")
    elif xml.count("<w:sdt>", start, end) > 0:
        fail("item-12", "DHA455 template: item 12 region contains a content control")

    # No app formula may assign the Poor/Fair/Good/Superior scale.
    for path in walk((".fx.yaml",), "dist/app/src"):
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                # Comments and the on-screen "we do not do this" note are fine.
                stripped = line.strip()
                if stripped.startswith(("//", "#")):
                    continue
                if scale.search(line) and re.search(r"\b(Patch|Set|Update)\s*\(", line):
                    fail(
                        "item-12",
                        f"{os.path.relpath(path, ROOT)}:{i} writes an item 12 scale value",
                    )


# ---------------------------------------------------------------------------
# Rule: denominator integrity — the rule is data, not a hard-code.
# ---------------------------------------------------------------------------
def rule_denominator_is_data():
    check("Denominator rule is data (eCAF_Config), not a hard-coded 'Peer'")
    # A filter comparing ReviewType to the literal "Peer" defeats the config.
    bad = re.compile(r'ReviewType[^\n]{0,40}=\s*"Peer"')
    for path in walk((".fx.yaml",), "dist/app/src"):
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if line.strip().startswith("//"):
                    continue
                if bad.search(line):
                    fail(
                        "denominator",
                        f"{os.path.relpath(path, ROOT)}:{i} hard-codes ReviewType = \"Peer\"",
                    )

    # And the config key must actually exist with the documented default.
    p = os.path.join(ROOT, "dist", "lists", "eCAF_Config.csv")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        cfg = {r["Title"]: r["ConfigValue"] for r in csv.DictReader(fh)}
    if cfg.get("DenominatorReviewTypes") != "Peer":
        fail("denominator", f"eCAF_Config DenominatorReviewTypes = {cfg.get('DenominatorReviewTypes')!r}, expected 'Peer'")


# ---------------------------------------------------------------------------
# Rule: MapsTo tokens come from the closed vocabulary.
# ---------------------------------------------------------------------------
def rule_mapsto_vocabulary():
    check("Every MapsTo token is in the standards-schema vocabulary")
    with open(os.path.join(ROOT, "standards", "standards-schema.json"), encoding="utf-8") as fh:
        vocab = set(json.load(fh)["mapsToTokens"])
    with open(os.path.join(ROOT, "dist", "app", "src", "fixed-instrument.json"), encoding="utf-8") as fh:
        elements = {e["key"] for e in json.load(fh)["item11Elements"]}

    p = os.path.join(ROOT, "dist", "lists", "eCAF_Standards.csv")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            for token in filter(None, (t.strip() for t in row["MapsTo"].split(";"))):
                if token.startswith("455-I11:"):
                    key = token.split(":", 1)[1]
                    if key not in elements:
                        fail(
                            "mapsto",
                            f"{row['Title']}: 455-I11:{key} — no such element in fixed-instrument.json",
                        )
                elif token not in vocab:
                    fail("mapsto", f"{row['Title']}: unknown token {token!r}")


# ---------------------------------------------------------------------------
# Rule: specialty clinical standards ship as DRAFT-VALIDATE.
# ---------------------------------------------------------------------------
def rule_specialty_standards_are_draft():
    check("Seeded specialty standards are DRAFT-VALIDATE; DHA-sourced cite verbatim")
    p = os.path.join(ROOT, "dist", "lists", "eCAF_Standards.csv")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if row["Specialty"] != "Universal" and row["Status"] != "DRAFT-VALIDATE":
                fail(
                    "draft-standards",
                    f"{row['Title']} is specialty '{row['Specialty']}' but Status={row['Status']}",
                )
            if not row["SourceCitation"].strip():
                fail("draft-standards", f"{row['Title']} has an empty SourceCitation")


# ---------------------------------------------------------------------------
# Rule: no CUI/PHI in build artifacts — sample data is obviously fake.
# ---------------------------------------------------------------------------
def rule_sample_data_is_fake():
    check("Sample data is unmistakably fake")
    p = os.path.join(ROOT, "dist", "lists", "eCAF_ReviewCases.csv")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if not row["FIN"].startswith("TEST"):
                fail("fake-data", f"{row['Title']} FIN={row['FIN']!r} does not start with TEST")

    p = os.path.join(ROOT, "dist", "lists", "eCAF_Providers.csv")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if not row["Title"].startswith("PROVIDER, SAMPLE"):
                fail("fake-data", f"provider {row['Title']!r} is not an obvious sample name")

    # Person columns must be unroutable.
    for path in walk((".csv",), "dist/lists"):
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
        for addr in re.findall(r"[\w.+-]+@[\w.-]+", text):
            if not addr.endswith("@test.invalid"):
                fail("fake-data", f"{os.path.basename(path)} has non-test address {addr}")


# ---------------------------------------------------------------------------
# Rule: CSVs match the schema.
# ---------------------------------------------------------------------------
def rule_csv_matches_schema():
    check("Every list CSV header matches schemas/lists.json")
    with open(os.path.join(ROOT, "schemas", "lists.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    for lst in schema["lists"]:
        p = os.path.join(ROOT, "dist", "lists", lst["internalName"] + ".csv")
        if not os.path.exists(p):
            fail("csv-schema", f"missing {lst['internalName']}.csv — run tools/build_lists.py")
            continue
        with open(p, newline="", encoding="utf-8-sig") as fh:
            header = next(csv.reader(fh), [])
        expected = [c["name"] for c in lst["columns"]]
        if header != expected:
            fail("csv-schema", f"{lst['internalName']}.csv header {header} != schema {expected}")


# ---------------------------------------------------------------------------
# Rule: indexed columns are declared for every delegable filter target.
# ---------------------------------------------------------------------------
def rule_indexes_declared():
    check("Columns used in gallery filters are indexed in the schema")
    with open(os.path.join(ROOT, "schemas", "lists.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    indexed = {
        (l["internalName"], c["name"])
        for l in schema["lists"]
        for c in l["columns"]
        if c.get("indexed")
    }
    # The filters the app actually depends on being delegable.
    required = [
        ("eCAF_ReviewCases", "CaseStatus"),
        ("eCAF_ReviewCases", "AssignedReviewer"),
        ("eCAF_ReviewCases", "Suspense"),
        ("eCAF_ReviewCases", "Provider"),
        ("eCAF_Standards", "Status"),
        ("eCAF_Standards", "Specialty"),
        ("eCAF_Providers", "PrivilegeExpiration"),
        ("eCAF_Providers", "Department"),
    ]
    for lst, col in required:
        if (lst, col) not in indexed:
            fail("indexes", f"{lst}.{col} is filtered on but not marked indexed")


def rule_html_generation_is_encoded():
    check("Free text interpolated into generated HTML is HTML-encoded")
    p = os.path.join(ROOT, "dist", "app", "src", "App.fx.yaml")
    with open(p, encoding="utf-8") as fh:
        lines = fh.readlines()

    if not any("EncodeHtml(s: Text)" in l for l in lines):
        fail("html-encoding", "App.fx.yaml defines no EncodeHtml UDF")
        return

    # Free-text values that reach the generated .doc and the S6 HtmlViewer.
    # Provider names (S3) and standard text (S8) are typed by users, and the
    # output is a document that goes into a credentialing file.
    free_text = ["StandardText", "prov.Title", "ElementLabel", "docTitle"]
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith(("//", "#")):
            continue
        # Only lines that are actually building HTML.
        if '"<' not in line:
            continue
        for field in free_text:
            if re.search(rf"&\s*{re.escape(field)}\s*&", line) and "EncodeHtml" not in line:
                fail(
                    "html-encoding",
                    f"App.fx.yaml:{i} interpolates {field} into HTML unencoded",
                )


def rule_migration_csv_is_neutralised():
    check("Migration output neutralises spreadsheet formula injection")
    p = os.path.join(ROOT, "tools", "migrate_ewp.py")
    with open(p, encoding="utf-8") as fh:
        src = fh.read()
    if "def csv_safe(" not in src:
        fail("csv-injection", "migrate_ewp.py has no csv_safe neutraliser")
    elif "row[col] = csv_safe(" not in src:
        fail("csv-injection", "migrate_ewp.py writes rows without passing through csv_safe")


def main():
    print("Hard-rule review (CLAUDE.md)\n")
    for fn in (
        rule_no_patient_identifiers,
        rule_canonical_results,
        rule_cui_marking,
        rule_no_item12_rating,
        rule_denominator_is_data,
        rule_mapsto_vocabulary,
        rule_specialty_standards_are_draft,
        rule_sample_data_is_fake,
        rule_csv_matches_schema,
        rule_indexes_declared,
        rule_html_generation_is_encoded,
        rule_migration_csv_is_neutralised,
    ):
        fn()

    print()
    if failures:
        print(f"FAILED — {len(failures)} violation(s):\n")
        for rule, detail in failures:
            print(f"  [{rule}] {detail}")
        print()
        return 1

    print(f"PASS — {checks_run} hard-rule checks, no violations.\n")
    print("Not checkable here — the operator must verify in the browser:")
    print("  · Broken inheritance and the five permission groups (the actual")
    print("    § 1102 boundary; app-side filtering is UX only)")
    print("  · F1 item-level permission stamping, tested with two accounts")
    print("  · Business-day math against the tenant's observed holiday calendar")
    print("  · fixed-instrument.json reconciled against the real DHA 455 and")
    print("    FPPE Template — the element and construct sets were derived, not")
    print("    transcribed from the forms")
    return 0


if __name__ == "__main__":
    sys.exit(main())

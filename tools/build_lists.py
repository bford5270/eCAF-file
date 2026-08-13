#!/usr/bin/env python3
"""Build order step 1 — emit dist/lists/*.csv and dist/lists/provisioning-runbook.md.

Both outputs are generated from schemas/lists.json so they cannot drift from the
schema. Re-run after any lists.json edit.

Sample rows are deliberately, unmistakably fake (CLAUDE.md hard rule: no CUI/PHI in
build artifacts). Person columns use @test.invalid, which RFC 2606 reserves and
which cannot resolve in the tenant, so an accidental import fails loudly rather
than silently mailing a real person.

Usage: python3 tools/build_lists.py
"""

import csv
import json
import os
from datetime import date, timedelta

import build_holidays

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist", "lists")

# --- business-day math, mirrored from the app's BusinessDaysBetween named formula.
# Kept here so sample suspense dates in the CSVs are the same dates the app would
# compute, which makes the step-8 dry run a real comparison rather than a tautology.
HOLIDAYS = {
    date.fromisoformat(r["HolidayDate"]) for r in build_holidays.build(2025, 2030)
}


def add_business_days(start: date, n: int) -> date:
    d, added = start, 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in HOLIDAYS:
            added += 1
    return d


# --- sample data -------------------------------------------------------------
# Three rows per list, cross-consistent: the same three providers and three cases
# thread through every list so the dry run can follow one case end to end.

P_A, P_B, P_C = "PROVIDER, SAMPLE A.", "PROVIDER, SAMPLE B.", "PROVIDER, SAMPLE C."
SUP = "sample.supervisor@test.invalid"
PRE1, PRE2 = "sample.preceptor1@test.invalid", "sample.preceptor2@test.invalid"
REV1, REV2, REV3 = (
    "sample.reviewer1@test.invalid",
    "sample.reviewer2@test.invalid",
    "sample.reviewer3@test.invalid",
)
MSP = "sample.msp@test.invalid"

ASSIGNED_1 = date(2026, 7, 8)
ASSIGNED_3 = date(2026, 7, 1)

def _fixed_instrument():
    with open(os.path.join(ROOT, "dist", "app", "src", "fixed-instrument.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _blobs(item11_overrides=None, construct_default="Satisfactory"):
    """Build the two JSON blobs eCAF_ReviewSummaries stores, from the fixed
    instrument definition — so sample data and the app read the same element keys."""
    fi = _fixed_instrument()
    item11 = {e["key"]: "MET" for e in fi["item11Elements"]}
    item11.update(item11_overrides or {})
    domains = {c["key"]: construct_default for c in fi["competencyConstructs"]}
    return (json.dumps(item11, separators=(",", ":")),
            json.dumps(domains, separators=(",", ":")))


SUM1_I11, SUM1_CD = _blobs({"medication": "NOT_MET", "blood": "NA"})
SUM2_I11, SUM2_CD = _blobs({"standardofcare": "NOT_MET", "blood": "NA"}, "Unsatisfactory")
SUM3_I11, SUM3_CD = _blobs({"blood": "NA", "consults": "NA"})

SAMPLES = {
    "eCAF_Providers": [
        {
            "Title": P_A, "RankGrade": "O-3", "Service": "Navy",
            "Specialty": "PrimaryCare-GMO", "Department": "SAMPLE Medical Battalion",
            "UnitUIC": "TEST00", "ProviderCategory": "ActiveDuty",
            "PrivilegingStatus": "FPPE-Initial", "PrivilegeExpiration": "2027-06-30",
            "OPPEPeriodStart": "2026-01-01", "OPPEPeriodEnd": "2026-12-31",
            "FPPEWindowEnd": "2026-09-30", "ClinicalSupervisor": SUP,
            "PrimaryPreceptor": PRE1, "AlternatePreceptor": PRE2,
            "CQEnrolled": "Yes", "OperationalPlatform": "No",
            "CCQASLocation": "TEST-MTF-01",
        },
        {
            # Supervised + OperationalPlatform=Yes: exercises F4 stop-and-resolve.
            "Title": P_B, "RankGrade": "O-4", "Service": "Navy",
            "Specialty": "EmergencyMedicine", "Department": "SAMPLE Medical Battalion",
            "UnitUIC": "TEST00", "ProviderCategory": "ActiveDuty",
            "PrivilegingStatus": "Supervised", "PrivilegeExpiration": "2027-03-31",
            "OPPEPeriodStart": "2026-01-01", "OPPEPeriodEnd": "2026-12-31",
            "FPPEWindowEnd": "", "ClinicalSupervisor": SUP,
            "PrimaryPreceptor": PRE1, "AlternatePreceptor": "",
            "CQEnrolled": "Yes", "OperationalPlatform": "Yes",
            "CCQASLocation": "TEST-MTF-01",
        },
        {
            # Expiration inside 90 days of the sample "today": exercises F3 STOP-EWP.
            "Title": P_C, "RankGrade": "GS-12", "Service": "Civilian",
            "Specialty": "PhysicalTherapy", "Department": "SAMPLE Regiment Aid Station",
            "UnitUIC": "TEST01", "ProviderCategory": "Civilian",
            "PrivilegingStatus": "Full", "PrivilegeExpiration": "2026-09-15",
            "OPPEPeriodStart": "2026-01-01", "OPPEPeriodEnd": "2026-12-31",
            "FPPEWindowEnd": "", "ClinicalSupervisor": SUP,
            "PrimaryPreceptor": "", "AlternatePreceptor": "",
            "CQEnrolled": "No", "OperationalPlatform": "No",
            "CCQASLocation": "TEST-MTF-02",
        },
    ],
    "eCAF_ReviewCases": [
        {
            "Title": "RC-2026-0001", "Provider": P_A, "FIN": "TEST0000001",
            "EncounterDate": "2026-07-06", "EncounterType": "Outpatient",
            "ReviewPurpose": "OPPE", "ReviewType": "Peer",
            "RequiredReviewerSpecialty": "PrimaryCare-GMO", "AssignedReviewer": REV1,
            "AssignedDate": ASSIGNED_1.isoformat(),
            "Suspense": add_business_days(ASSIGNED_1, 10).isoformat(),
            "CaseStatus": "Complete", "PairedCase": "RC-2026-0002",
        },
        {
            # The CrossSpecialty twin of 0001. Feeds competency aggregates and
            # narrative only — never the OPPE floor or 455 item 11 denominators.
            "Title": "RC-2026-0002", "Provider": P_A, "FIN": "TEST0000001",
            "EncounterDate": "2026-07-06", "EncounterType": "Outpatient",
            "ReviewPurpose": "OPPE", "ReviewType": "CrossSpecialty",
            "RequiredReviewerSpecialty": "EmergencyMedicine", "AssignedReviewer": REV2,
            "AssignedDate": ASSIGNED_1.isoformat(),
            "Suspense": add_business_days(ASSIGNED_1, 10).isoformat(),
            "CaseStatus": "InProgress", "PairedCase": "RC-2026-0001",
        },
        {
            "Title": "RC-2026-0003", "Provider": P_B, "FIN": "TEST0000002",
            "EncounterDate": "2026-06-29", "EncounterType": "Telemedicine",
            "ReviewPurpose": "FPPE", "ReviewType": "Peer",
            "RequiredReviewerSpecialty": "EmergencyMedicine", "AssignedReviewer": REV3,
            "AssignedDate": ASSIGNED_3.isoformat(),
            "Suspense": add_business_days(ASSIGNED_3, 10).isoformat(),
            "CaseStatus": "Overdue", "PairedCase": "",
        },
    ],
    "eCAF_ReviewResponses": [
        {"Title": "RESP-0001", "ReviewCase": "RC-2026-0001", "Standard": "DOC-001",
         "Result": "MET", "Comment": "Sample response. No PHI in this field."},
        {"Title": "RESP-0002", "ReviewCase": "RC-2026-0001", "Standard": "MED-001",
         "Result": "NOT_MET", "Comment": "Sample response. No PHI in this field."},
        {"Title": "RESP-0003", "ReviewCase": "RC-2026-0001", "Standard": "BLD-001",
         "Result": "NA", "Comment": "Not applicable to this encounter type."},
    ],
    "eCAF_ReviewSummaries": [
        {"Title": "SUM-0001", "ReviewCase": "RC-2026-0001",
         "OverallDetermination": "Satisfactory",
         "Item11Elements": SUM1_I11, "CompetencyDomains": SUM1_CD,
         "Narrative": "Sample narrative. No PHI, no FIN, no clinical detail.",
         "CompletedDate": "2026-07-20"},
        {"Title": "SUM-0002", "ReviewCase": "RC-2026-0003",
         "OverallDetermination": "Unsatisfactory",
         "Item11Elements": SUM2_I11, "CompetencyDomains": SUM2_CD,
         "Narrative": "Sample narrative. No PHI, no FIN, no clinical detail.",
         "CompletedDate": "2026-07-17"},
        {"Title": "SUM-0003", "ReviewCase": "RC-2026-0002",
         "OverallDetermination": "Satisfactory",
         "Item11Elements": SUM3_I11, "CompetencyDomains": SUM3_CD,
         "Narrative": "Sample cross-specialty narrative. Aggregates only.",
         "CompletedDate": "2026-07-21"},
    ],
    "eCAF_ActivityData": [
        {"Title": "ACT-0001", "Provider": P_A, "PeriodStart": "2026-01-01",
         "PeriodEnd": "2026-06-30", "Admissions": 0, "OutpatientEncounters": 412,
         "SurgicalProcedures": 0, "InvasiveProcedures": 3, "NoninvasiveProcedures": 47,
         "AdverseEvents": 0, "PctDirectPatientCare": 80,
         "PctIncompleteNotesOver3BD": 2, "DaysUnavailable": 14,
         "AppropriateMedUse": "Y", "AppropriateBloodUse": "NA",
         "RecordReviewsCompleted": 12, "RecordReviewsDeficient": 1},
        {"Title": "ACT-0002", "Provider": P_B, "PeriodStart": "2026-01-01",
         "PeriodEnd": "2026-06-30", "Admissions": 22, "OutpatientEncounters": 690,
         "SurgicalProcedures": 0, "InvasiveProcedures": 31, "NoninvasiveProcedures": 88,
         "AdverseEvents": 1, "PctDirectPatientCare": 90,
         "PctIncompleteNotesOver3BD": 6, "DaysUnavailable": 5,
         "AppropriateMedUse": "Y", "AppropriateBloodUse": "Y",
         "RecordReviewsCompleted": 10, "RecordReviewsDeficient": 2},
        {"Title": "ACT-0003", "Provider": P_C, "PeriodStart": "2026-01-01",
         "PeriodEnd": "2026-06-30", "Admissions": 0, "OutpatientEncounters": 305,
         "SurgicalProcedures": 0, "InvasiveProcedures": 0, "NoninvasiveProcedures": 0,
         "AdverseEvents": 0, "PctDirectPatientCare": 95,
         "PctIncompleteNotesOver3BD": 0, "DaysUnavailable": 0,
         "AppropriateMedUse": "NA", "AppropriateBloodUse": "NA",
         "RecordReviewsCompleted": 8, "RecordReviewsDeficient": 0},
    ],
    "eCAF_Routing": [
        {"Title": "RT-0001", "Document": "OPPE_SAMPLE-A_2026H1.docx", "Stage": "Provider",
         "CurrentHolder": SUP, "Action": "Recommend", "ActionDate": "2026-07-24",
         "Comments": "Sample endorsement comment."},
        {"Title": "RT-0002", "Document": "OPPE_SAMPLE-A_2026H1.docx", "Stage": "PeerProctor",
         "CurrentHolder": REV1, "Action": "Pending", "ActionDate": "",
         "Comments": ""},
        {"Title": "RT-0003", "Document": "FPPE_SAMPLE-B_2026H1.docx", "Stage": "ClinicalLeader",
         "CurrentHolder": SUP, "Action": "Pending", "ActionDate": "",
         "Comments": ""},
    ],
    "eCAF_ReviewerPool": [
        {"Title": "POOL-0001", "Reviewer": REV1,
         "QualifiedSpecialties": "Universal;PrimaryCare-GMO", "Department": "SAMPLE Medical Battalion",
         "Available": "Yes", "OpenAssignments": 1},
        {"Title": "POOL-0002", "Reviewer": REV2,
         "QualifiedSpecialties": "Universal;EmergencyMedicine", "Department": "SAMPLE Medical Battalion",
         "Available": "Yes", "OpenAssignments": 1},
        {"Title": "POOL-0003", "Reviewer": REV3,
         "QualifiedSpecialties": "Universal;EmergencyMedicine;PhysicalTherapy",
         "Department": "SAMPLE Regiment Aid Station", "Available": "No", "OpenAssignments": 1},
    ],
    "eCAF_Config": [
        {"Title": "DenominatorReviewTypes", "ConfigValue": "Peer",
         "Description": "Semicolon list of ReviewType values that count toward the OPPE "
                        "review floor and DHA 455 item 11 denominators. Credentials-committee "
                        "reversible: add CrossSpecialty here to include cross-specialty reviews. "
                        "No app change required.",
         "LastChangedBy": MSP, "AuthorityRef": "SAMPLE - replace with committee minute reference"},
        {"Title": "OPPEReviewFloor", "ConfigValue": "10",
         "Description": "Minimum completed qualifying reviews per OPPE period.",
         "LastChangedBy": MSP, "AuthorityRef": "SAMPLE - replace with committee minute reference"},
        {"Title": "DefaultSuspenseBusinessDays", "ConfigValue": "10",
         "Description": "Business days from AssignedDate to Suspense at intake.",
         "LastChangedBy": MSP, "AuthorityRef": "SAMPLE - replace with committee minute reference"},
        {"Title": "OverdueGraceBusinessDays", "ConfigValue": "2",
         "Description": "Business days past Suspense before F2 sets CaseStatus=Overdue.",
         "LastChangedBy": MSP, "AuthorityRef": "SAMPLE - replace with committee minute reference"},
        {"Title": "PrivilegeExpiryWarningDays", "ConfigValue": "90",
         "Description": "Calendar days ahead of PrivilegeExpiration that F3 raises the "
                        "STOP-EWP / legacy process determination alert (DHA-PM 6025.13 Vol 8).",
         "LastChangedBy": MSP, "AuthorityRef": "SAMPLE - replace with committee minute reference"},
        {"Title": "DraftStandardsInDocuments", "ConfigValue": "No",
         "Description": "DRAFT-VALIDATE standards are excluded from generated documents. "
                        "Changing this to Yes contradicts a CLAUDE.md hard rule and the app "
                        "ignores it; the key exists so the intent is auditable, not settable.",
         "LastChangedBy": MSP, "AuthorityRef": "CLAUDE.md hard rule - not operator-settable"},
        {"Title": "CUIBanner",
         "ConfigValue": "CUI // Medical Quality Assurance Program document protected "
                        "pursuant to 10 U.S.C. § 1102",
         "Description": "Rendered in the footer of every screen and every generated document. "
                        "Do not shorten.",
         "LastChangedBy": MSP, "AuthorityRef": "CLAUDE.md hard rule"},
    ],
}


def load_schema():
    with open(os.path.join(ROOT, "schemas", "lists.json"), encoding="utf-8") as fh:
        return json.load(fh)


def write_csv(name, columns, rows):
    path = os.path.join(OUT, f"{name}.csv")
    fields = [c["name"] for c in columns]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({f: r.get(f, "") for f in fields})
    return path, len(rows)


SP_TYPE = {
    "text": "Single line of text",
    "note": "Multiple lines of text (plain text, appending OFF)",
    "date": "Date and time (Date Only format)",
    "number": "Number (0 decimals)",
    "yesno": "Yes/No",
    "choice": "Choice (drop-down)",
    "choiceMulti": "Choice (checkboxes, multiple selections allowed)",
    "lookup": "Lookup",
    "person": "Person or Group (people only)",
}

RUNBOOK_HEAD = """# Provisioning Runbook — eCAF SharePoint Lists

Generated by `tools/build_lists.py` from `schemas/lists.json`. Do not hand-edit —
edit the schema and re-run, or your changes are lost on the next build.

**Read this first.** "Create list from CSV" gets you the list and roughly-typed
columns in one action. It cannot set choice values, lookups, person columns,
indexes, required flags, or max length. Every one of those is a manual step below,
and several of them *cannot be applied by changing the imported column* — the
column has to be deleted and recreated. The per-list tables say which.

## What CSV import gets wrong, every time

| Schema type | What import creates | Fix |
|---|---|---|
| `choice` | Single line of text | Change type to Choice, then paste the choice values. Converting text->choice is supported and keeps data. |
| `choiceMulti` | Single line of text | Change to Choice, tick "allow multiple selections". Sample rows use `;` separators — re-enter the 3 sample rows by hand afterwards. |
| `lookup` | Single line of text | **Cannot convert.** Delete the imported column, add a real Lookup column of the same name, re-key the 3 sample rows. Provision parent lists first (order below). |
| `person` | Single line of text | **Cannot convert.** Delete, add Person or Group. Sample values are `@test.invalid` and will not resolve — that is intentional; clear them or replace with test accounts. |
| `date` | Date and time (with time) | Change format to Date Only. |
| `number` | Number, sometimes with decimals | Set 0 decimals. |
| `yesno` | Single line of text ("Yes"/"No") | Change type to Yes/No. |
| `note` | Single line of text (truncates at 255!) | **Change before entering real data.** Multiple lines of text, plain text, appending OFF (appending breaks Patch). |

## Provisioning order (parents before children — lookups depend on it)

1. `eCAF_Holidays`, `eCAF_Config` — no dependencies, and the app will not start without them.
2. `eCAF_Providers`
3. `eCAF_Standards`
4. `eCAF_ReviewerPool`
5. `eCAF_ReviewCases` — looks up Providers, and **self-references** for `PairedCase`.
   Create the list first, then add the `PairedCase` lookup pointing at itself.
6. `eCAF_ReviewResponses`, `eCAF_ReviewSummaries`, `eCAF_ActivityData`
7. `eCAF_Documents` (document library — see the content-type section)
8. `eCAF_Routing` — looks up the document library, so it goes last.

## Per-list steps
"""

RUNBOOK_TAIL = """
## Document library — eCAF_Documents

1. Create a document library named `eCAF_Documents`, display name **CAF Documents**.
2. Site settings -> Site content types -> create each content type below, deriving
   from **Document**. Add the listed site columns, then add the content type to the
   library and enable "Allow management of content types" in library settings.
3. Structure is folder-per-provider. Create folders as providers are onboarded; the
   app's document staging screen writes into the folder matching the provider name.

| Content type | Columns |
|---|---|
{CONTENT_TYPES}

`Adverse-ForCause` is **restricted to eCAF-MSP + PA only**. Break inheritance on
that content type's folder, or hold those documents in a separate library with its
own permissions. Library-level content-type permissions do not exist in SharePoint —
the boundary has to be a folder or a library, so decide which and record it.

## Permission groups

Create these five SharePoint groups before provisioning any list:

{GROUPS}

Baseline assignment (tighten per tenant SOP; this is the least-privilege starting
point, not a finished authorization):

| Group | Site | Providers | ReviewCases | Responses/Summaries | Standards | Config | Documents |
|---|---|---|---|---|---|---|---|
| eCAF-MSP | Read | Contribute | Contribute | Contribute | Contribute | Contribute | Contribute |
| eCAF-ClinicalLeaders | Read | Read | Contribute | Read | Contribute | Read | Contribute |
| eCAF-Reviewers | Read | Read | *item-level only* | Contribute | Read | Read | None |
| eCAF-Preceptors | Read | Read | *item-level only* | Read | Read | Read | Contribute |
| eCAF-Providers | Read | None | None | None | Read | Read | *own folder only* |

## Broken inheritance

Break inheritance on these lists **before importing any data**, so no item is ever
briefly visible site-wide:

{BROKEN}

On `eCAF_ReviewCases`, `eCAF_ReviewResponses`, `eCAF_ReviewSummaries` and
`eCAF_Routing`: remove all groups except **eCAF-MSP** at the list level. Reviewer
access is granted per item by flow F1 ("Stop sharing an item or file" then "Grant
access to an item or file"). A reviewer must not be able to enumerate cases that
are not theirs — that is the § 1102 boundary, and the app's own filtering is UX
only, not a control.

**Test this with two accounts before any real data is entered.** Sign in as test
reviewer A and confirm you cannot see test reviewer B's case, by direct item URL,
not just in the app.

## Indexes

Create these before the lists exceed 5,000 items — after the threshold, index
creation itself can fail and the fix gets ugly.

{INDEXES}

## Versioning

Enable versioning on every list (major versions, keep 50). CLAUDE.md relies on
SharePoint item versioning for concurrency — there is no custom merge logic, so
version history is the only record of a lost update.

## Verification before you load real data

- [ ] `eCAF_Config` has all 7 keys and `DenominatorReviewTypes` = `Peer`.
- [ ] `eCAF_Holidays` has 66 rows and `HolidayDate` is Date Only.
- [ ] Every `note` column is Multiple lines of text with appending OFF.
- [ ] Every lookup resolves (open a `eCAF_ReviewResponses` item, confirm the
      Standard picker lists 26 standards).
- [ ] Two-account item-level permission test passed on `eCAF_ReviewCases`.
- [ ] No column named MRN, SSN, DOB, PatientName, or DateOfBirth exists on any
      list. `FIN` is the only encounter identifier. Run
      `python3 tools/lint_hard_rules.py` to check the artifacts; check the live
      site by eye.
- [ ] Sample rows deleted before go-live (they are fake, but they are also noise).
"""


def _list_table(lst):
    rows = []
    for c in lst["columns"]:
        t = SP_TYPE.get(c["type"], c["type"])
        flags = []
        if c.get("required"):
            flags.append("**required**")
        if c.get("indexed"):
            flags.append("**indexed**")
        if c.get("maxLength"):
            flags.append(f"max {c['maxLength']} chars")
        if c["type"] == "lookup":
            flags.append(f"-> `{c['target']}` (Title)")
        if c["type"] in ("choice", "choiceMulti") and c.get("choices"):
            flags.append("values: " + ", ".join(f"`{v}`" for v in c["choices"]))
        if c.get("choicesFrom"):
            flags.append(f"values mirror `{c['choicesFrom']}`")
        if c["type"] in ("lookup", "person"):
            flags.append("_delete imported column and recreate_")
        note = c.get("note", "")
        rows.append(f"| `{c['name']}` | {t} | {' · '.join(flags)} | {note} |")
    return "\n".join(rows)


def write_runbook(schema):
    parts = [RUNBOOK_HEAD]
    for lst in schema["lists"]:
        name = lst["internalName"]
        parts.append(f"\n### {name} — {lst['displayName']}\n")
        if lst.get("addedByBuild"):
            parts.append(f"> Added by this build: {lst['addedByBuild']}\n")
        if lst.get("note"):
            parts.append(f"> {lst['note']}\n")
        if lst.get("brokenInheritance"):
            parts.append("> **Break inheritance on this list before importing.**\n")
        parts.append(f"Import `{name}.csv`, then:\n")
        parts.append("| Column | SharePoint type | Settings | Why |")
        parts.append("|---|---|---|---|")
        parts.append(_list_table(lst))

    dl = schema["documentLibrary"]
    ct = "\n".join(
        f"| {c['name']} | {', '.join(c['metadata'])}"
        + (f" — **restricted: {c['restricted']}**" if c.get("restricted") else "")
        + " |"
        for c in dl["contentTypes"]
    )
    groups = "\n".join(f"- `{g}`" for g in schema["permissionGroups"])
    broken = "\n".join(
        f"- `{l['internalName']}`" for l in schema["lists"] if l.get("brokenInheritance")
    ) or "- (none)"
    indexes = "\n".join(
        f"- `{l['internalName']}`: " + ", ".join(f"`{c['name']}`" for c in l["columns"] if c.get("indexed"))
        for l in schema["lists"]
        if any(c.get("indexed") for c in l["columns"])
    )
    parts.append(
        RUNBOOK_TAIL.replace("{CONTENT_TYPES}", ct)
        .replace("{GROUPS}", groups)
        .replace("{BROKEN}", broken)
        .replace("{INDEXES}", indexes)
    )

    path = os.path.join(OUT, "provisioning-runbook.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    schema = load_schema()
    written = []

    for lst in schema["lists"]:
        name = lst["internalName"]
        if name == "eCAF_Holidays":
            rows = build_holidays.build(2025, 2030)          # reference data, not samples
        elif name == "eCAF_Standards":
            rows = load_standards_seed()                      # the real seed library
        else:
            rows = SAMPLES.get(name, [])
        path, n = write_csv(name, lst["columns"], rows)
        written.append((name, n, os.path.basename(path)))

    for name, n, fn in written:
        print(f"  {fn:<32} {n:>3} rows")
    rb = write_runbook(schema)
    print(f"\n{len(written)} CSVs + {os.path.basename(rb)} written to dist/lists/")


def load_standards_seed():
    """The standards seed is real content, not sample data — pass it through,
    adding the two columns lists.json defines but the seed file omits."""
    src = os.path.join(ROOT, "standards", "standards-seed.csv")
    with open(src, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["Title"] = r.pop("StandardID")
        r.setdefault("ValidatedBy", "")
        r.setdefault("ValidatedDate", "")
    return rows


if __name__ == "__main__":
    main()

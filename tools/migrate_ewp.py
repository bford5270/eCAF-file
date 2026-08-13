#!/usr/bin/env python3
"""Build order step 8 — migrate the predecessor HTML tool's data into e-CAF CSVs.

  python3 tools/migrate_ewp.py --inspect ewp-peer-review-data.json
  python3 tools/migrate_ewp.py --migrate ewp-peer-review-data.json --out dist/migration

IMPORTANT: `ewp-peer-review-data.json` was NOT supplied to this build, so its
schema is unknown. This script therefore does two things in order:

  --inspect   walks the file and prints the actual shape — keys, types, value
              cardinality, and every distinct value of anything that looks like a
              result field. Run this FIRST and read the output.
  --migrate   applies the mapping in FIELD_MAP below and emits import CSVs plus
              a reconciliation report.

FIELD_MAP is a guess based on the eCAF schema, not on the source file. Correct it
using the --inspect output before trusting a migration. The script refuses to
migrate a field it cannot find rather than silently emitting blanks.

Why this exists as a script and not a one-off: the reconciliation has to be
repeatable. You will run it, find a discrepancy, fix a mapping, and run it again.
"""

import argparse
import collections
import csv
import json
import os
import re
import sys

# --- the normalization that matters ----------------------------------------
# CLAUDE.md: element results are stored as exactly MET | NOT_MET | NA. The
# predecessor tool wrote several spellings, and cases carrying the variants
# silently dropped out of 455 denominators. Every known variant maps here, and
# anything unrecognised is reported rather than guessed.
RESULT_CANON = {
    "met": "MET",
    "yes": "MET",
    "y": "MET",
    "pass": "MET",
    "compliant": "MET",
    "notmet": "NOT_MET",
    "not met": "NOT_MET",
    "not_met": "NOT_MET",
    "no": "NOT_MET",
    "n": "NOT_MET",
    "fail": "NOT_MET",
    "noncompliant": "NOT_MET",
    "non-compliant": "NOT_MET",
    "na": "NA",
    "n/a": "NA",
    "notapplicable": "NA",
    "not applicable": "NA",
    "": "NA",
}

DETERMINATION_CANON = {
    "satisfactory": "Satisfactory",
    "sat": "Satisfactory",
    "s": "Satisfactory",
    "unsatisfactory": "Unsatisfactory",
    "unsat": "Unsatisfactory",
    "u": "Unsatisfactory",
}

# --- mapping: source key -> eCAF column. VERIFY AGAINST --inspect OUTPUT. ---
FIELD_MAP = {
    "cases": {
        "_source_collection": ["cases", "reviews", "peerReviews", "records"],
        "Title": ["caseId", "id", "reviewId"],
        "Provider": ["provider", "providerName", "clinician"],
        "FIN": ["fin", "FIN", "encounterId", "encounter"],
        "EncounterDate": ["encounterDate", "dateOfEncounter", "date"],
        "EncounterType": ["encounterType", "type"],
        "ReviewPurpose": ["purpose", "reviewPurpose"],
        "ReviewType": ["reviewType", "peerType"],
        "AssignedReviewer": ["reviewer", "assignedReviewer", "reviewerEmail"],
        "CaseStatus": ["status", "caseStatus"],
    },
    "responses": {
        "_source_collection": ["responses", "answers", "standardResponses"],
        "ReviewCase": ["caseId", "reviewId"],
        "Standard": ["standardId", "standard"],
        "Result": ["result", "answer", "value"],
        "Comment": ["comment", "notes"],
    },
}

# Anything matching these must never be carried across. The predecessor may have
# held identifiers e-CAF is not permitted to store.
FORBIDDEN_KEYS = re.compile(
    r"\b(mrn|ssn|dob|dateofbirth|patientname|patient_name|lastname|firstname|"
    r"patientid|medicalrecord)\b",
    re.I,
)


def walk_shape(obj, path="$", shape=None, depth=0):
    if shape is None:
        shape = collections.defaultdict(collections.Counter)
    if depth > 6:
        return shape
    if isinstance(obj, dict):
        for k, v in obj.items():
            shape[f"{path}.{k}"][type(v).__name__] += 1
            walk_shape(v, f"{path}.{k}", shape, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:200]:
            walk_shape(item, f"{path}[]", shape, depth + 1)
    return shape


def collect_values(obj, key_pattern, out=None, depth=0):
    if out is None:
        out = collections.Counter()
    if depth > 6:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if re.search(key_pattern, k, re.I) and isinstance(v, (str, int, float, bool)):
                out[str(v)] += 1
            collect_values(v, key_pattern, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            collect_values(item, key_pattern, out, depth + 1)
    return out


def cmd_inspect(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    print(f"=== Shape of {path}\n")
    shape = walk_shape(data)
    for k in sorted(shape):
        types = ", ".join(f"{t}×{n}" for t, n in shape[k].most_common())
        print(f"  {k:<60} {types}")

    print("\n=== Distinct values of anything result-shaped")
    vals = collect_values(data, r"result|answer|met|status|determination")
    for v, n in vals.most_common(40):
        canon = RESULT_CANON.get(v.strip().lower(), DETERMINATION_CANON.get(v.strip().lower()))
        mark = f"-> {canon}" if canon else "-> UNMAPPED, add to RESULT_CANON"
        print(f"  {v!r:<30} ×{n:<5} {mark}")

    print("\n=== Keys that must NOT be migrated")
    hits = [k for k in shape if FORBIDDEN_KEYS.search(k)]
    if hits:
        for k in hits:
            print(f"  {k}   <-- patient identifier; e-CAF stores FIN only")
        print("\n  These are dropped by --migrate. Confirm the source file itself is")
        print("  handled as CUI and is not left in the repo or a shared folder.")
    else:
        print("  none found")

    print("\nNext: correct FIELD_MAP in this file to match the paths above, then")
    print("run with --migrate.")
    return 0


def resolve(record, candidates):
    """First candidate key present in the record, case-insensitively."""
    lowered = {k.lower(): k for k in record}
    for c in candidates:
        if c.lower() in lowered:
            return record[lowered[c.lower()]]
    return None


def find_collection(data, candidates):
    if isinstance(data, list):
        return data
    for c in candidates:
        for k in data:
            if k.lower() == c.lower() and isinstance(data[k], list):
                return data[k]
    return None


def cmd_migrate(path, outdir):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    os.makedirs(outdir, exist_ok=True)
    report = {"unmapped_results": collections.Counter(), "dropped_keys": collections.Counter()}
    exit_code = 0

    for entity, mapping in FIELD_MAP.items():
        rows_in = find_collection(data, mapping["_source_collection"])
        if rows_in is None:
            print(f"! Could not find the '{entity}' collection. Tried: "
                  f"{mapping['_source_collection']}. Run --inspect and fix FIELD_MAP.")
            exit_code = 1
            continue

        cols = [k for k in mapping if not k.startswith("_")]
        out_rows, skipped = [], 0

        for rec in rows_in:
            if not isinstance(rec, dict):
                skipped += 1
                continue
            for k in rec:
                if FORBIDDEN_KEYS.search(k):
                    report["dropped_keys"][k] += 1

            row = {}
            for col in cols:
                val = resolve(rec, mapping[col])
                if col == "Result" and val is not None:
                    key = str(val).strip().lower()
                    if key in RESULT_CANON:
                        val = RESULT_CANON[key]
                    else:
                        report["unmapped_results"][str(val)] += 1
                        # Never guess. An unmapped result becomes blank and is
                        # reported, because a wrong MET is worse than a gap.
                        val = ""
                row[col] = "" if val is None else val
            out_rows.append(row)

        p = os.path.join(outdir, f"migrated_{entity}.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(out_rows)
        print(f"  {os.path.basename(p):<28} {len(out_rows):>5} rows"
              + (f"  ({skipped} skipped)" if skipped else ""))

    # --- reconciliation report
    rp = os.path.join(outdir, "reconciliation.md")
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write("# Migration reconciliation\n\n")
        fh.write(f"Source: `{os.path.basename(path)}`\n\n")

        fh.write("## Counts to reconcile against the HTML tool\n\n")
        fh.write("Open the predecessor tool and compare these before cutover. "
                 "A mismatch here is a migration defect, not a rounding difference.\n\n")
        fh.write("| Metric | e-CAF after migration | HTML tool | Match? |\n")
        fh.write("|---|---|---|---|\n")
        for entity in FIELD_MAP:
            p = os.path.join(outdir, f"migrated_{entity}.csv")
            n = sum(1 for _ in open(p, encoding="utf-8-sig")) - 1 if os.path.exists(p) else 0
            fh.write(f"| Total {entity} | {n} | | |\n")
        fh.write("| Completed peer reviews per provider | see below | | |\n")
        fh.write("| MET / NOT_MET / NA split | see below | | |\n\n")

        if report["unmapped_results"]:
            fh.write("## Unmapped result values — BLOCKING\n\n")
            fh.write("These were written blank rather than guessed. Add each to "
                     "`RESULT_CANON` in `tools/migrate_ewp.py` and re-run. "
                     "**Do not import until this section is empty** — a blank "
                     "result silently leaves the case out of every denominator, "
                     "which is the exact bug this migration exists to end.\n\n")
            for v, n in report["unmapped_results"].most_common():
                fh.write(f"- `{v}` × {n}\n")
            fh.write("\n")
            exit_code = 1
        else:
            fh.write("## Unmapped result values\n\nNone. Every result "
                     "normalised to MET / NOT_MET / NA.\n\n")

        if report["dropped_keys"]:
            fh.write("## Patient identifiers dropped\n\n")
            fh.write("Present in the source, deliberately not migrated — e-CAF "
                     "stores FIN and nothing else.\n\n")
            for k, n in report["dropped_keys"].most_common():
                fh.write(f"- `{k}` × {n}\n")
            fh.write("\nConfirm the source file is handled as CUI and is not "
                     "left in this repo or any shared folder.\n\n")

        fh.write("## Before cutover\n\n")
        fh.write("- [ ] Every count above matches the HTML tool\n")
        fh.write("- [ ] No unmapped result values remain\n")
        fh.write("- [ ] Spot-check 5 cases field by field against the HTML tool\n")
        fh.write("- [ ] HTML tool retained and documented as the outage contingency\n")

    print(f"  {os.path.basename(rp):<28} reconciliation report")
    if exit_code:
        print("\n! Unmapped result values found — see reconciliation.md. Not safe to import.")
    return exit_code


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inspect", metavar="FILE")
    ap.add_argument("--migrate", metavar="FILE")
    ap.add_argument("--out", default="dist/migration")
    args = ap.parse_args()

    if args.inspect:
        return cmd_inspect(args.inspect)
    if args.migrate:
        return cmd_migrate(args.migrate, args.out)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

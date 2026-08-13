# Ingesting completed peer review forms

`tools/parse_review_forms.py` turns completed forms into `eCAF_ReviewResponses`
and `eCAF_ReviewSummaries` import CSVs, so the MSP is not retyping a reviewer's
worksheet into the app.

```
python3 tools/parse_review_forms.py --inspect forms/                 # always first
python3 tools/parse_review_forms.py --parse   forms/ --out dist/ingest
```

`dist/ingest/` is gitignored. Once you run this against real forms its contents
are CUI; treat the output the way you treat the source forms.

## Formats

| Input | Read via | Confidence |
|---|---|---|
| `dist/templates/*.docx` filled in | named content controls | **high** |
| Any other .docx | label/value tables, `ID: result` lines | low |
| .xlsx / .xlsm | cell grid | low |
| .txt / .md / .csv | line patterns | low |
| .pdf with a text layer | pypdf text extraction | low |
| .pdf that is a scan | **fails loudly** — OCR it first | — |

A scanned PDF with no text layer is refused rather than read as empty. An empty
parse of a completed form looks exactly like a review with no findings, and that
is the kind of wrong that gets signed.

## The two confidence paths

**High** means the form is one of our own templates filled in. Values come from
content controls whose names the build generated, so field identity is exact:
`C455_I11_medication` is the medication element, not something that happened to
sit next to the word "medication". These rows go to `ingested_responses.csv` and
`ingested_summaries.csv`.

**Low** means everything else. Standard IDs and results were matched by pattern —
positional guessing dressed up as parsing. These rows go to
`NEEDS-REVIEW_responses.csv`, which is deliberately not named like something you
would import, and every row carries `_SourceFile` and `_Extraction` columns so
you can check it against the paper.

Summaries are written **only** from the high-confidence path. An overall
determination scraped positionally is not something to write into a credentialing
record.

**The easiest way to get high-confidence ingest is to hand reviewers the
generated templates.** That is the round trip the templates were built for.

## What it refuses, and why refusal is the right answer

Three gates reject a file whole rather than parsing it minus the offending part.

**Patient identifiers.** A form carrying an SSN, MRN, DOB or patient-name field
is rejected entirely. FIN is the only encounter identifier e-CAF may hold. The
fix is to redact the form and re-run — the `redact-pii` skill does true
redaction, or strike it by hand.

The detector is label-based plus SSN formatting. **It cannot recognise a bare
patient name written into a comment box.** It is a tripwire, not a guarantee, and
it does not replace reading what you are ingesting.

**A marked DHA 455 item 12 rating.** If a form has Poor/Fair/Good/Superior with a
mark against one, the file is rejected. Not "parsed without item 12" — rejected.
A form bearing that rating means the local process is rating item 12, and no
source document crosswalks the Satisfactory/Unsatisfactory review scale to it.
That needs a human, and quietly ingesting the rest would hide the fact that it
happened. An *unmarked* scale is the blank box our own template ships and passes
fine.

**An unrecognised result value.** `Partially Met` is not `MET` and is not
`NOT_MET`. The field is left blank, the value is reported, and the run exits
non-zero. Add the spelling to `RESULT_CANON` in `tools/ecaf_normalize.py` if it
is a genuine synonym, or fix the form.

Never "just import it anyway" past that last one. A blank result drops the case
out of every denominator that counts it — silently, permanently, and in the
direction that makes a provider look better reviewed than they were. That is the
predecessor bug this whole system was built to end.

## One vocabulary, not two

`RESULT_CANON` lives in `tools/ecaf_normalize.py` and nowhere else. Both the
parser and `migrate_ewp.py` import it, and `tools/lint_hard_rules.py` fails the
build if either declares its own copy.

The hard rule is about stored data, but it bites in code the same way: two
ingestion tools with two private variant tables is precisely how the predecessor
came to write `Not Met` down one path and `NOT_MET` down another.

## Before importing anything

The generated `ingest-report.md` carries this checklist:

- [ ] Unrecognised-values section is empty
- [ ] Every rejected file dealt with — redacted, OCR'd, or routed to a human
- [ ] Low-confidence rows confirmed line by line against their source forms
- [ ] `ReviewCase` and `Standard` resolve to real list items. **These are lookup
      columns and a CSV carries only the display value** — an ID that does not
      match an existing item imports as a broken lookup, and a response attached
      to no standard counts toward nothing.
- [ ] Source forms handled as CUI, not left in this repo

## Known limits

- Comments are not extracted. Free text is where a stray patient name is most
  likely to be, and the value of automating it does not justify carrying that
  risk — type them across deliberately.
- Constructs are matched by key (`PC-A: Satisfactory`). A form using prose labels
  instead of keys will not match, and will say so rather than guess.
- `CaseID` must appear as `RC-YYYY-NNNN`. If the form does not carry one, the
  rows come out with a blank `ReviewCase` and the report says so; fill it in
  before import.

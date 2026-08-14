# Form reconciliation — 14 Aug 2026

The three DHA forms were supplied and decoded. This closes most of the open item
in `docs/hard-rule-review.md` and opens one new question.

Sources:

| Form | Version as printed on the form | Machine-readable? |
|---|---|---|
| DHA FPPE Template | **Effective OCTOBER 2025** | AcroForm, 102 fields |
| DHA OPPE Template | DHA-PM 6025.13, **revised 02/16/2021** | AcroForm, 126 fields |
| DHA Form 455 PAR | **"DHA FORM 455 (TEST), OCT 2025"**, DRAFT watermark | XFA/LiveCycle, 200 fields |

---

## RESOLVED — the 16 competency constructs

The build package mandated "16 competency constructs across the six domains
(Sat/Unsat/NotObserved)" without enumerating them. Both forms carry them, and
**they agree**: FPPE Section 4 "Facility Wide Assessment" and OPPE Section VII
"Professional Evaluation Elements" are the same 16 constructs, the same six
domains, the same three-value scale. Two independent forms agreeing is why this
is now high confidence rather than a derivation.

| Domain | Count |
|---|---|
| Patient Care | 3 |
| Professional Knowledge | 3 |
| Practice Based Learning & Improvement | 3 |
| Interpersonal & Communication Skills | 2 |
| Professionalism | 3 |
| Systems Based Practice | 2 |
| **Total** | **16** |

Transcribed verbatim into `dist/app/src/fixed-instrument.json`.

**What the derivation got wrong.** The count and the six domains were right. The
*distribution* was wrong — ICS had 3 and Professionalism 2; the real forms are
ICS 2 and Professionalism 3. Every construct label was approximated rather than
correct. Anyone who had entered reviews against the derived set would have been
answering questions that are not on the form.

Two smaller corrections:

- The domain the schema called `MedicalClinicalKnowledge` is **Professional
  Knowledge** on both forms.
- FPPE and OPPE **order ICS A and B oppositely**. Keys follow FPPE (the newer
  form); the OPPE wording is recorded per construct in `oppeVariant`.

## RESOLVED — FPPE Section 3 and OPPE Sections III–V

Every `MapsTo` token in `standards-seed.csv` checks out against the real forms:

- FPPE Section 3 runs A–L. `3.E` medication use (Y/N/NA), `3.F` broad scope of
  treatments, `3.I` % incomplete notes > 3 business days, `3.J` blood use,
  `3.L` # record reviews NOT within standard of care — all confirmed.
- OPPE Section III A–F and Section IV A–H — all confirmed, including `III.F`
  % incomplete notes and `IV.D`–`IV.H`.
- OPPE Section V is "Specialty Specific Quality Indicators (**minimum of 2**)",
  each a Metric with Met Yes/No — confirmed, including the minimum of two.

**The OPPE form states the review floor in its own words**, at the foot of the
last page:

> *This form should be accompanied by a minimum of 10 peer reviews.*

The `eCAF_Config!OPPEReviewFloor = 10` default is on the face of the form.

The OPPE endorsement chain in Section X is Provider → Peer/Proctor → Credentials
Review Committee Chair → Department Head, exactly as `flows-spec.md` had it.

## NEW — OPPE Section VI is not modelled

Section VI "Facility Wide Monitors" is five items on the Sat/Unsat/Not Observed
scale — Utilization Review, Infection Control, Incident Reports/management
variance reports, Patient Contact/satisfaction program, Risk management
activities. Nothing in the build captures these. They are period-level monitors
rather than per-encounter findings, so they most likely belong on
`eCAF_ActivityData`, not on the review instrument. Not yet built.

---

## OPEN — the DHA 455, and why it was not rebuilt

**The 455 supplied is not a released form.** Its form-number block reads
`DHA FORM 455 (TEST), OCT 2025`, it carries a DRAFT watermark image, and the
XFA template's own base path is `...\STADEN - DRAFT Forms\DHA Form 455 -
Performance Assessment Report - in progress\`. The supplied filename says
FEB 2026. Item 11 and item 12 have therefore **not** been rebuilt around it.

That matters, because the real 455 is structurally different from what the build
package described — in a way that changes the schema, not just some labels.

### Item 11 is not a four-element ratio block

It is **"11. ASSESSMENT OF PRIVILEGES"**, sub-items a through n, and most
sub-items are numerator / denominator pairs with an auto-calculated percentage:

| | Sub-item | Shape |
|---|---|---|
| a | Medication usage review | 2 ratio pairs (prescribed appropriately; reconciliation documented) |
| b | Treatment/follow-up plan review | 3 ratio pairs (documentation; pain plan; elevated BP) |
| c | Procedure review | 1 ratio pair (time-out, site marking, consent) |
| d | Records review / peer review | count + count-with-discrepancy, plus timeliness Y/N |
| e | Pharmacy and therapeutics | 2 Y/N + narrative |
| f | Morbidity/mortality review | count |
| g | Infection control | Y/N + narrative |
| h | Utilization review | 3 Y/N + narrative |
| i | Ancillary review | Y/N |
| j | Occurrence screening | Y/N + narrative |
| k | Risk management | PCE count, SOC review count + SOC met, claims count + SOC met |
| l | Focused professional practice | Y/N — for-cause FPPE this period |
| m | Clinical adverse actions | count + per-CAA outcome (Reinstatement / Reinstatement with M&E / Restriction / Reduction / Revocation / Denial) + date |
| n | Department/service specific reviews | — |

The four elements currently in `fixed-instrument.json`
(`standardofcare`, `medication`, `blood`, `consults`) do **not** match this.
`medication` corresponds roughly to 11.a; `blood` is not a 455 item 11 element at
all (it is FPPE 3.J / OPPE IV.D); `standardofcare` and `consults` have no
counterpart.

### Item 12 is eleven ratings, not one

**"12. PERFORMANCE (Check appropriate block for each item listed)"** is a grid of
**11 rows** (a–k) grouped under four headings — Medical Knowledge (a–e),
Professionalism (f–h), Practice-Based Learning & Improvement (i), Systems-Based
Practice (j–k) — each rated **POOR / FAIR / GOOD / SUPERIOR / NOT OBSERVED**.
Five columns, not four.

This makes the no-auto-rating hard rule **larger, not smaller**: there are eleven
supervisor judgements the system must not make, not one. The current
`DHA455_PAR_Template.docx` renders item 12 as a single four-cell row, which is
the wrong shape — it is still safely unbindable, but it does not match the form.

### What needs deciding

Rebuilding item 11 and item 12 around a form marked TEST/DRAFT risks baking a
draft into the schema and the templates. The current placeholder is wrong but
loudly flagged; a confident-looking implementation of a draft form is worse.
**Confirm whether this is the released 455 before item 11/12 is rebuilt.**

Nothing else is blocked by this. The competency constructs, FPPE Section 3, and
OPPE Sections III–V are all now correct and in the artifacts.

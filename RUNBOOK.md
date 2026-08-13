# RUNBOOK — Building and deploying the e-CAF

## Build status: all 8 build-order steps are complete

The artifacts in `dist/` are generated and hard-rule-checked. Nothing below
requires another Claude Code session unless you are changing the design.

```
python3 tools/build_holidays.py     # schemas/holidays.csv from 5 USC 6103
python3 tools/build_lists.py        # dist/lists/ CSVs + provisioning runbook
python3 tools/build_templates.py    # dist/templates/ .docx staging templates
python3 tools/lint_hard_rules.py    # the CLAUDE.md hard-rule review — must pass
python3 tools/test_parse_review_forms.py   # form-parser refusal behaviour

# Ingest (not part of the build; run against real forms as they arrive)
python3 tools/parse_review_forms.py --inspect forms/
python3 tools/migrate_ewp.py       --inspect ewp-peer-review-data.json
```

Everything in `dist/` is generated. **Edit the source and re-run; do not
hand-edit `dist/`** — the next build overwrites it.

Read in this order before touching the tenant:
1. `PLAN.md` — what was built and the decisions taken where the spec was silent
2. `docs/hard-rule-review.md` — how each hard rule is satisfied, and the one
   open item that must be closed before real data
3. `dist/lists/provisioning-runbook.md` — the per-list provisioning steps
4. `docs/dry-run.md` — the acceptance test

## One-time setup (any machine — artifacts contain no CUI)
1. Python 3.9+ and `pip install python-docx` (only needed to regenerate).
2. Install Power Platform CLI (`pac`) if permitted. It was **not** available on
   the build machine, so the canvas app is YAML source — see
   `dist/app/README.md` for the packing procedure, which needs one
   `pac canvas unpack` of a blank app in your own environment first.
3. If you are changing the design rather than deploying it, open a terminal here
   and run `claude`, then: "Read CLAUDE.md and PLAN.md in full, then <change>.
   Re-run tools/lint_hard_rules.py and report any hard rule you could not
   satisfy before finishing."

## What you do in the browser (Claude Code cannot)
1. **Phase 0 first — approval.** Confirm with the tenant/RMF POC what a
   citizen-developed Power App holding § 1102/CUI content requires. Long pole.
2. **Reconcile `dist/app/src/fixed-instrument.json` against the real DHA Form 455
   and DHA FPPE Template.** The item 11 element set and the 16 competency
   constructs were *derived* from the standards seed's MapsTo tokens — neither
   form was supplied to this build. Re-run `build_lists.py` and
   `build_templates.py` after editing. See `docs/hard-rule-review.md`
   "Open item". Do this before any real review is entered.
3. Create the site (Team site, no M365 group, or per tenant SOP). Name:
   *I MEF e-CAF (MQA Protected)*. Add CUI banner to home page.
4. Create the five permission groups; break inheritance per lists.json.
5. Provision the **eleven** lists per `dist/lists/provisioning-runbook.md`, in
   the order given there — parents before children, and `eCAF_Holidays` +
   `eCAF_Config` first, because the app will not start without them.
   (Two lists beyond the original schema: see `PLAN.md` "Decisions taken".)
6. Import `dist/lists/eCAF_Standards.csv` into eCAF_Standards. Route
   DRAFT-VALIDATE items to Clinical Leaders via S8 once the app is live.
7. Import the app per `dist/app/README.md`. Fix connection references. **Record
   here which role-resolution path is live — Office 365 Groups or the
   `eCAF_RoleMap` list.** An access complaint later is unanswerable without it:

   > Role resolution in production: ____________________  (date: __________)

8. Recreate flows per `dist/flows/README.md` — F1 first and alone. Test F1's
   permission stamping with two test accounts, **by direct item URL**, before any
   real data.
9. Run `docs/dry-run.md` end to end with the fake sample data: intake → assign →
   review → aggregate → stage document → route → "CCQAS uploaded" flag. It
   includes the denominator-reversal test, which is the check that the
   credentials committee's default is really data and not a hard-code.
10. Migrate `ewp-peer-review-data.json` with `tools/migrate_ewp.py` — `--inspect`
    first, then `--migrate`. **A non-zero exit means unmapped result values;
    importing then recreates the exact denominator bug this system exists to
    end.** Reconcile counts against the HTML tool before cutover. Keep the HTML
    tool as the documented outage contingency.
11. **Ongoing — ingesting completed paper/Word forms.** Reviewers who work
    outside the app hand in forms; `tools/parse_review_forms.py` turns those into
    import CSVs. `--inspect` first, always. It rejects any form carrying patient
    identifiers or a marked DHA 455 item 12 rating, and refuses to guess an
    unrecognised result. Hand reviewers the generated `dist/templates/*.docx` —
    a filled-in template parses at high confidence from its content controls;
    anything else is positional scraping and lands in a NEEDS-REVIEW file.
    See `docs/form-ingest.md`.
12. Delete every sample row (`PROVIDER, SAMPLE *`, FIN `TEST*`,
    `*@test.invalid`) before go-live.
13. Document adoption + the ReviewType denominator default in credentials
    committee minutes, and put the minute reference into
    `eCAF_Config!DenominatorReviewTypes.AuthorityRef`; calendar the quarterly
    access review (F8).

## Standing decisions already made (don't relitigate in-session)
- FIN is the sole encounter identifier.
- Peer-type reviews only in OPPE floor / 455 denominators (committee-reversible).
- No auto-rating of 455 item 12.
- DRAFT-VALIDATE standards render badged, excluded from generated documents.
- CCQAS remains system of record for OPPE.

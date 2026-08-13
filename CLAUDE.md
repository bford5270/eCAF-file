# CLAUDE.md — I MEF e-CAF Build Instructions

You are building the I MEF electronic Clinical Activity File (e-CAF): a SharePoint +
Power Apps canvas app for medical peer review and privileging documentation, supporting
30–75 users (MSP office, Clinical Leaders, peer reviewers, preceptors, providers).

## What you produce

You generate **importable artifacts only**. You cannot and must not attempt to
authenticate to or automate the tenant. The human operator imports everything through
the browser or the Power Platform CLI (`pac`). Outputs:

1. `dist/lists/` — one CSV per SharePoint list for browser-based "Create list from
   Excel/CSV" provisioning, plus `provisioning-runbook.md` with exact column type
   settings (CSV import cannot set lookups, choices, or indexes — the runbook covers
   the manual finishing steps per list).
2. `dist/app/` — canvas app as Power Apps YAML source under `src/`, packed with
   `pac canvas pack --sources src --msapp eCAF.msapp`. Target format: Power Apps
   source-code (YAML) schema. If `pac` is unavailable on the build machine, still
   emit the YAML source and note the pack command.
3. `dist/flows/` — Power Automate flow definitions as importable solution zip where
   feasible; otherwise per-flow build instructions with exact trigger/action/expression
   text the operator recreates in the browser designer.
4. `dist/templates/` — .docx staging templates (FPPE, OPPE, DHA 455, unified data
   sheet) with content controls named to match the mapping in
   `standards/standards-schema.json`.

## Hard rules — never violate

- **No CUI/PHI in build artifacts.** No real provider names, no real FINs, no clinical
  narratives. Sample data uses obviously fake values (`PROVIDER, SAMPLE A.`,
  FIN `TEST0000001`).
- **FIN is the only encounter identifier.** No MRN, no SSN, no DOB, no patient name
  fields anywhere in any schema, screen, or template. The review-case form has exactly
  one encounter-identity field: FIN (text, 12 chars max).
- **CUI + § 1102 marking on every screen and template.** Footer on every app screen:
  `CUI // Medical Quality Assurance Program document protected pursuant to
  10 U.S.C. § 1102`. Header/footer on every generated document.
- **No auto-rating of DHA 455 item 12** (Poor/Fair/Good/Superior). No source document
  provides a crosswalk from the Satisfactory/Unsatisfactory scale. The app displays
  aggregate evidence; item 12 stays blank for the clinical supervisor.
- **Denominator integrity.** Only reviews with `ReviewType = Peer` count toward the
  OPPE 10-review minimum and DHA 455 item 11 denominators. `ReviewType =
  CrossSpecialty` reviews feed competency-domain aggregates and narrative only.
  This is a credentials-committee-reversible default — implement as data, not
  hard-code.
- **Normalize "not met" at write time.** Element results are stored as exactly one of
  `MET | NOT_MET | NA`. Never introduce a second representation (this bug silently
  dropped cases from 455 denominators in the predecessor tool).
- **Standards drive the instrument.** The review form renders from the Standards list
  (filtered to the case's specialty + universal standards), not from hard-coded
  questions. Adding a standard must require zero app changes.
- **Specialty clinical standards ship as drafts.** Every seeded clinical standard for
  a specialty carries `Status = DRAFT-VALIDATE` until a Clinical Leader signs it off.
  DHA-sourced standards carry their citation verbatim.
- Business-day math excludes weekends and the federal holiday list in
  `schemas/holidays.csv`.

## Source of truth

- `schemas/lists.json` — all list definitions. Column names there are canonical;
  screens and flows reference them exactly.
- `standards/standards-schema.json` — the standard record shape and the
  standard-to-form-field mapping vocabulary.
- `standards/standards-seed.csv` — initial standards library.
- `app/app-spec.md` — screens, navigation, role gating, formula-level guidance.
- `flows/flows-spec.md` — F1–F8 automation inventory.
- `RUNBOOK.md` — the human operator's end-to-end sequence. Keep it current: every
  time you change an artifact, update the corresponding runbook step.

## Conventions

- List internal names: `eCAF_` prefix, PascalCase (`eCAF_Providers`).
- Delegation: all gallery filters must be delegable to SharePoint (avoid `Search()`
  on non-indexed columns; index the columns named in `lists.json` `"indexed": true`).
- Concurrency: rely on SharePoint item versioning; no custom merge logic.
- Roles resolve from SharePoint group membership checked at app start
  (`User().Email` against the five `eCAF-*` groups); cache in a global variable.
  App-side filtering is UX only — the runbook's permission steps are the boundary.
- Comments in YAML/formulas explain *why* for anything non-obvious (especially
  denominator filters and business-day calcs).

## Environment notes for the operator (surface these, don't act on them)

- DoD cloud: `pac auth create --cloud UsDod` (or `UsGovHigh` — operator verifies
  which enclave). Copilot features in the tenant may be absent or lagged; irrelevant
  to this build path.
- Premium connectors may be unlicensed. Flows must degrade: any flow using a premium
  connector needs a documented standard-connector or manual fallback in
  `flows/flows-spec.md`.
- Document generation fallback: if Word Online (Business) connector is unavailable,
  the app itself generates HTML-based `.doc` output (port the predecessor tool's
  generation logic — proven, license-free).

## Build order

Work in this order unless instructed otherwise; each phase ends with an updated
RUNBOOK and a self-review against the Hard rules above.

1. Validate/emit list CSVs + provisioning runbook from `schemas/lists.json`.
2. Standards library seed + the standards-to-form mapping engine spec.
3. Canvas app YAML: shell, role gating, dashboard, provider record.
4. Review instrument screen (standards-driven rendering) + case intake.
5. Aggregation logic (455 item 11 ratios, OPPE floor tracking, FPPE/OPPE rollups).
6. Document staging templates + generation.
7. Flows F1–F8.
8. End-to-end dry-run script with sample (fake) data + reconciliation checklist.

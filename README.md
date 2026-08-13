# I MEF e-CAF

Build repository for the I MEF electronic Clinical Activity File — a SharePoint
Online + Power Apps canvas app for medical peer review and privileging
documentation, for 30–75 users across the MSP office, Clinical Leaders, peer
reviewers, preceptors and providers.

**This repo produces importable artifacts, not a running application.** The
target is a DoD tenant that the build process cannot and must not authenticate
to. A human operator imports everything through the browser or `pac`.

## Start here

| If you want to… | Read |
|---|---|
| Deploy it | `RUNBOOK.md` |
| Understand what was built and why | `PLAN.md` |
| Provision the SharePoint lists | `dist/lists/provisioning-runbook.md` |
| Import the app | `dist/app/README.md` |
| Build the flows | `dist/flows/README.md` |
| Accept the build | `docs/dry-run.md` |
| Check the compliance posture | `docs/hard-rule-review.md` |

## Layout

```
CLAUDE.md                  build rules — the hard rules are non-negotiable
schemas/lists.json         source of truth for all 11 lists + the doc library
schemas/holidays.csv       generated: federal holidays, for business-day math
standards/                 standards schema + the 26-row seed library
app/ flows/                the original screen and flow specifications

dist/lists/                11 import CSVs + provisioning runbook
dist/app/src/              canvas app Power Fx YAML (9 screens + component)
dist/flows/                F1–F8 recreate-in-the-designer instructions
dist/templates/            4 .docx staging templates with content controls

tools/                     generators, the hard-rule linter, the migration script
docs/                      mapping engine, dry run, hard-rule review
```

## Regenerating

Everything under `dist/` and `schemas/holidays.csv` is generated. Edit the
source and re-run — do not hand-edit `dist/`.

```
pip install python-docx
python3 tools/build_holidays.py
python3 tools/build_lists.py
python3 tools/build_templates.py
python3 tools/lint_hard_rules.py     # must pass before anything ships
```

## The rules that shape every design decision here

From `CLAUDE.md`, and worth knowing before reading any of the code:

- **FIN is the only encounter identifier.** No MRN, SSN, DOB or patient name
  exists in any schema, screen or template.
- **CUI // 10 U.S.C. § 1102** marking on every screen and every generated
  document.
- **DHA 455 item 12 is never rated by the system.** No crosswalk exists between
  the review scale and the item 12 scale. The template has no content control
  there, so there is nothing to bind.
- **Only `Peer` reviews count toward the OPPE floor and 455 item 11
  denominators** — implemented as data in `eCAF_Config`, so the credentials
  committee can reverse it without an app change.
- **Element results are exactly `MET | NOT_MET | NA`.** The radio controls'
  items *are* the stored strings, so no mapping step exists that could produce a
  variant. A second spelling silently dropped cases from denominators in the
  predecessor tool.
- **Standards drive the instrument.** Adding a standard requires zero app
  changes.

`tools/lint_hard_rules.py` checks ten of these automatically. Three more can only
be verified in the tenant, and are gated in `docs/dry-run.md`.

## Known open item

`dist/app/src/fixed-instrument.json` — the DHA 455 item 11 element set and the 16
competency constructs — was **derived from the standards seed's MapsTo tokens,
not transcribed from the forms**, because neither DHA Form 455 nor the DHA FPPE
Template was supplied to this build. It must be reconciled by someone holding the
actual forms before real reviews are entered. Nothing downstream is hard-coded to
it: correct that one file, re-run the generators, and the correction propagates.
See `docs/hard-rule-review.md`.

# e-CAF Build Plan

Derived from `CLAUDE.md` build order. This file records what gets built, in what
order, and the decisions taken where the source package was silent or ambiguous.

## What this repo is

A **build repository**, not a running application. The target platform is
SharePoint Online + Power Apps canvas in a DoD tenant that Claude Code cannot and
must not authenticate to. Everything under `dist/` is an artifact a human operator
imports through the browser or `pac`.

```
schemas/  standards/  app/  flows/     <- source of truth (from the build package)
dist/lists/       <- CSVs + provisioning runbook  (Build order 1)
dist/app/src/     <- canvas app Power Fx YAML      (Build order 3-6)
dist/flows/       <- F1-F8 build instructions      (Build order 7)
dist/templates/   <- .docx staging templates       (Build order 6)
tools/            <- generators, linters, migration (Build order 8)
docs/             <- dry-run + reconciliation       (Build order 8)
```

## Build order status

| # | Phase | Output | Status |
|---|-------|--------|--------|
| 1 | List CSVs + provisioning runbook | `dist/lists/` | done |
| 2 | Standards seed + mapping engine | `dist/lists/eCAF_Standards.csv`, `docs/standards-mapping-engine.md` | done |
| 3 | App shell, role gating, dashboard, provider record | `dist/app/src/` | done |
| 4 | Review instrument + case intake | `dist/app/src/` | done |
| 5 | Aggregation logic | `dist/app/src/App.fx.yaml` named formulas | done |
| 6 | Document templates + generation | `dist/templates/`, `dist/app/src/Screens/S6_*` | done |
| 7 | Flows F1-F8 | `dist/flows/` | done |
| 8 | Dry run + migration | `docs/dry-run.md`, `tools/` | done |

## Decisions taken (gaps in the source package)

1. **`schemas/holidays.csv` was referenced by `CLAUDE.md` but not shipped.** Built
   it from the 5 U.S.C. § 6103 rules (11 federal holidays, Sat->Fri / Sun->Mon
   observance) via `tools/build_holidays.py`, 2025-2030. Added a matching
   `eCAF_Holidays` list to `schemas/lists.json` because `app-spec.md` loads
   `colHolidays` from a list, and `lists.json` had no list to load it from.
2. **`pac` is not installed on this build machine.** Per `CLAUDE.md` §2 the YAML
   source is emitted anyway and the pack command documented. `dist/app/README.md`
   carries the exact round-trip procedure and the caveat that a hand-authored
   source tree needs one `pac canvas unpack` of a blank app to supply the
   non-authored scaffold before it will pack.
3. **`ReviewType` denominator rule is implemented as data, not a hard-code.** A
   `eCAF_Config` list holds `DenominatorReviewTypes = Peer`. The credentials
   committee reverses the default by editing one list item; no app change.
4. **Item 12 of the DHA 455 is a literal blank in the template**, wrapped in a
   content control the generator never binds, with the note text beside it. There
   is no code path that can write to it.
5. **Cross-specialty pairing** (`PairedCase`) is written after both items exist —
   SharePoint cannot self-reference a lookup on create — so intake patches the
   twin, then back-patches the original.

## Hard-rule self-review

See `docs/hard-rule-review.md`. Every rule in `CLAUDE.md` "Hard rules" is listed
with the artifact and line that satisfies it, plus the two rules that can only be
satisfied by the operator in the browser.

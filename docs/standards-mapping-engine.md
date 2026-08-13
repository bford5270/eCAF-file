# Standards Mapping Engine

How a row in `eCAF_Standards` becomes a question on the review screen, a response
in `eCAF_ReviewResponses`, and a number on a generated document — with **zero app
changes** when a standard is added. That last property is a CLAUDE.md hard rule, so
this document is also the test for whether the implementation still satisfies it.

## The three-stage path

```
eCAF_Standards row          the review screen           the generated document
------------------          -----------------          ----------------------
Title       PC-GMO-001      one gallery item           MapsTo tokens select which
StandardText "Red-flag..."  MET / NOT_MET / NA         form fields the aggregate
Specialty   PrimaryCare-GMO + comment box              lands in
Status      DRAFT-VALIDATE  amber DRAFT badge          -> excluded when DRAFT
MapsTo      OPPE-V;DASH-ONLY                           -> OPPE Template Sec V
```

### Stage 1 — selection

The review screen's standards gallery is filtered, server-side, to:

```
Status <> "RETIRED"  AND  Specialty in { "Universal", case.RequiredReviewerSpecialty }
```

Both `Status` and `Specialty` are indexed (see `lists.json`), so this is delegable.
Note the filter is on **`RequiredReviewerSpecialty` of the case**, not the
provider's specialty — on a CrossSpecialty case those differ, and the reviewer must
be asked the standards for the specialty they were selected to represent.

`RETIRED` standards are excluded from new reviews but never deleted, so historical
`eCAF_ReviewResponses` rows keep a resolvable lookup.

### Stage 2 — capture

One `eCAF_ReviewResponses` item per standard per case. Long format, not a wide
column-per-standard table, which is what makes "add a standard, change no app"
possible and what makes per-standard cross-specialty analytics a group-by instead
of a schema migration.

`Result` is written as exactly `MET`, `NOT_MET`, or `NA`. The canonical value is
written by the control itself — the radio group's items *are* the canonical strings,
so there is no mapping step at which a variant could be introduced. This is the
normalization hard rule; the predecessor tool wrote "Not Met" in one path and
"NOT_MET" in another, and cases silently vanished from 455 denominators.

`tools/lint_hard_rules.py` fails the build if any artifact contains a
non-canonical variant (`Not Met`, `not_met`, `NotMet`, `N/A`, `n/a`).

### Stage 3 — aggregation and mapping

Per standard, over the qualifying case set:

```
rate = MET / (MET + NOT_MET)          NA excluded from BOTH numerator and denominator
```

"Qualifying" means `CaseStatus = Complete` and `ReviewType` in the set named by
`eCAF_Config!DenominatorReviewTypes` (default `Peer`). Cross-specialty responses
still exist and still show on the cross-specialty dashboard panel — they are
excluded from *form* denominators only.

The `MapsTo` column then routes that rate to form fields. It is a semicolon list of
tokens from the vocabulary in `standards/standards-schema.json`:

| Token family | Lands on |
|---|---|
| `FPPE-3x`, `FPPE-4-xxx` | FPPE Template sections 3.E/3.F/3.I/3.J/3.L and the Section 4 domains |
| `OPPE-IIIF`, `OPPE-IVx`, `OPPE-V` | OPPE Template sections III.F, IV.D–IV.H, V |
| `455-I11:<element>` | The named DHA 455 item 11 element ratio |
| `455-I13` | DHA 455 narrative support (listed, not computed) |
| `DASH-ONLY` | Cross-specialty dashboard only — no form field |

A standard may carry several tokens; `DOC-001` feeds both `FPPE-3I` and
`OPPE-IIIF`. A standard with only `DASH-ONLY` never reaches a document.

## Adding a standard — the zero-app-change test

1. Add a row to `eCAF_Standards` via screen S8 (or import a CSV row).
2. Set `Status = DRAFT-VALIDATE`, `SourceCitation`, and `MapsTo`.
3. It appears immediately on the next review of a matching specialty, badged DRAFT.
4. It is excluded from generated documents until a Clinical Leader validates it.
5. **No app edit, no republish, no schema change.**

If a change ever requires editing the canvas app to add a standard, the engine has
been broken. The specific things that would break it, and must not be done:

- hard-coding a standard's ID in a formula
- a column-per-standard table
- a `Switch()` over `MapsTo` token values in app code rather than data
- filtering the gallery client-side on a non-indexed column (works at 26 standards,
  silently truncates at 2,000)

## Where the `MapsTo` vocabulary is enforced

`standards-schema.json` `mapsToTokens` is the closed vocabulary.
`tools/lint_hard_rules.py` checks every `MapsTo` value in the standards CSV against
it and fails on an unknown token, so a typo (`OPPE-IVX`) is caught at build time
rather than silently dropping a standard out of a document.

`455-I11:<element>` is validated further: the element key after the colon must
exist in `dist/app/src/fixed-instrument.json`. This is what ties the standards
library to the fixed instrument — if someone reconciles the item 11 element set
against the real DHA 455 and renames an element, the lint fails until the standards
that reference it are updated too.

## What the engine deliberately does not do

- **It does not rate DHA 455 item 12.** No source document crosswalks
  Satisfactory/Unsatisfactory to Poor/Fair/Good/Superior. The aggregates are
  displayed; item 12 stays blank for the clinical supervisor. There is no code path
  that writes it.
- **It does not infer a standard's specialty from the provider.** Only
  `case.RequiredReviewerSpecialty` selects, so a cross-specialty reviewer is never
  shown standards for a specialty they were not asked to assess.
- **It does not compute a rate from fewer than the configured floor of reviews**
  without saying so. Below `eCAF_Config!OPPEReviewFloor` completed qualifying
  reviews, the OPPE tracker shows `n of 10` in red and document staging marks the
  affected fields `[VERIFY]` rather than printing a ratio that looks authoritative.

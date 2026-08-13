# Dry run — the acceptance test

Build order step 8. Run this end to end with the fake sample data **before any
real provider or encounter exists in the site.** If a step fails, fix it before
loading real data; several of these failures are unrecoverable once real CUI is
in the lists.

Everything here uses the sample rows from `dist/lists/` — `PROVIDER, SAMPLE A.`,
FIN `TEST0000001`. Nothing in this run touches a real record.

You need three test accounts:

| Account | In group | Plays |
|---|---|---|
| TEST-MSP | eCAF-MSP | MSP office |
| TEST-REV-A | eCAF-Reviewers | primary care reviewer |
| TEST-REV-B | eCAF-Reviewers | emergency medicine reviewer |

---

## Gate 0 — before you start

These block everything downstream.

- [ ] **Phase 0 approval is done.** Tenant/RMF POC has confirmed what a
      citizen-developed Power App holding § 1102 / CUI content requires. This is
      the long pole; do not build a user base ahead of it.
- [ ] `python3 tools/lint_hard_rules.py` passes.
- [ ] **`dist/app/src/fixed-instrument.json` has been reconciled against the real
      DHA Form 455 and the DHA FPPE Template.** The four item 11 elements and the
      16 competency constructs in that file were derived from the MapsTo tokens
      in the standards seed, because neither form was supplied to this build.
      Until a human has opened both forms and corrected that file, every 455
      element ratio the app produces is against an unverified element set.
      Re-run `tools/build_lists.py` and `tools/build_templates.py` after editing.

---

## 1 — Permissions, before anything else

The § 1102 boundary is SharePoint permissions. App-side filtering is UX. Prove
the boundary first, because everything after it assumes it holds.

- [ ] Sign in as **TEST-REV-A**. Open `eCAF_ReviewCases` **by direct list URL**,
      not through the app.
- [ ] Confirm you see only items shared with you — not the whole list.
- [ ] Take the item ID of a case assigned to TEST-REV-B and open it by direct
      item URL. **You must get access denied.**
- [ ] Repeat as TEST-REV-B in the other direction.

> If a reviewer can enumerate another reviewer's cases, stop. Nothing else in
> this run matters until that is fixed.

---

## 2 — Intake

As **TEST-MSP**, on S3:

- [ ] Create a case: `PROVIDER, SAMPLE A.`, FIN `TEST0000001`, encounter type
      Outpatient, purpose OPPE, type Peer, specialty PrimaryCare-GMO.
- [ ] Suspense defaults to **10 business days out, skipping weekends and federal
      holidays**. Check it against `schemas/holidays.csv` by hand once. Pick a
      date near a holiday deliberately — 1 Jul 2026 should give 16 Jul 2026,
      skipping the observed Independence Day on Friday 3 Jul.
- [ ] Type `123456789` into FIN. The SSN warning appears and Create is disabled.
- [ ] Type `TEST0000001`. Warning clears.
- [ ] Confirm there is **no** field on this form for name, MRN, SSN, or DOB.
- [ ] Switch ReviewType to CrossSpecialty. The note changes to say it does not
      count toward the floor.
- [ ] Turn on "create pair", pick EmergencyMedicine, create. **Two** cases exist
      and each one's `PairedCase` points at the other.

---

## 3 — Assignment and item permissions (F1)

- [ ] The new case gets an AssignedReviewer within a minute or two.
- [ ] Open the case's *Manage Access* in SharePoint: the reviewer, eCAF-MSP and
      the cognizant Clinical Leader are listed, and **nobody else**.
- [ ] The reviewer's `OpenAssignments` in `eCAF_ReviewerPool` incremented.
- [ ] The reviewer received a mail containing **a link and nothing else** — no
      FIN, no provider name, no determination, in body or subject.
- [ ] Set every pool member to `Available = No` and create another case. It must
      notify the MSP that no reviewer is available and **not** assign anyone.

---

## 4 — The review instrument

As **TEST-REV-A**, open the assigned case from the dashboard queue:

- [ ] Case status flips to InProgress on open.
- [ ] Section 1 shows the item 11 elements and all 16 competency constructs
      grouped under the six domains.
- [ ] Section 2 shows Universal standards **plus** PrimaryCare-GMO standards, and
      no standards from other specialties.
- [ ] The three PC-GMO standards carry an amber **DRAFT** badge.
- [ ] Answer one standard, then **close the browser without submitting**. Reopen.
      The answer is still there. (This is the autosave; if it fails, reviewers
      will lose work and stop using the tool.)
- [ ] Open `eCAF_ReviewResponses` and confirm the stored `Result` is literally
      `MET`, `NOT_MET`, or `NA` — not `Met`, not `Not Met`.
- [ ] The Submit button stays disabled until every element, every construct and
      every standard is answered.
- [ ] Submit. Case status becomes Complete and a `eCAF_ReviewSummaries` row
      exists with both JSON blobs populated.

**Now the standards engine test — the zero-app-change rule:**

- [ ] As TEST-MSP on S8, add a new standard: specialty PrimaryCare-GMO, MapsTo
      `OPPE-V;DASH-ONLY`. Save.
- [ ] Type a deliberate typo, `OPPE-IVX`, into MapsTo. It is rejected as an
      unknown token.
- [ ] Open a **new** PrimaryCare-GMO case as a reviewer. The new standard is
      there, badged DRAFT. **No app edit, no republish.**

---

## 5 — Aggregation and the denominator rule

This is the part that was wrong in the predecessor tool. Test it deliberately.

Set up: for `PROVIDER, SAMPLE A.`, create and complete **10 Peer OPPE cases** and
**3 CrossSpecialty cases** in the same period.

- [ ] Dashboard OPPE floor tracker reads **10 of 10** and is green.
- [ ] It reads 10, **not 13**. The cross-specialty note reads
      "+ 3 cross-specialty (not counted toward the floor)".
- [ ] F5 fired once on the tenth case, not three times.
- [ ] On S6, "qualifying of completed" reads **10 of 13**.
- [ ] An item 11 element answered MET on 7, NOT_MET on 2 and NA on 1 displays
      **"7 of 9 (78%)"** — NA excluded from both sides, not "7 of 10".
- [ ] An element with no data displays **"no data"**, never "0%".

**Now reverse the rule as the credentials committee would:**

- [ ] Edit `eCAF_Config` → `DenominatorReviewTypes` to `Peer;CrossSpecialty`.
- [ ] Reopen the app. The tracker now reads **13**. **No app change was made.**
- [ ] Set it back to `Peer`. It reads 10 again.

> If reversing the rule required editing a formula or a flow, the hard rule is
> not satisfied — find the hard-code and route it through `CountsInDenominator`
> and `eCAF_Config`.

---

## 6 — Documents

On S6, provider `PROVIDER, SAMPLE A.`, the OPPE period, doc type OPPE Product:

- [ ] Generate with the **.doc (no license)** button. It always works.
- [ ] Open the file in Word. CUI / § 1102 marking is in the header **and** the
      footer.
- [ ] The DRAFT-VALIDATE standards you answered during review are **absent** from
      the document, and the count of excluded drafts is stated on screen.
- [ ] Switch doc type to DHA455 PAR and generate. **Item 12 is an empty four-cell
      box** with the clinical-supervisor note beneath it. There is no control to
      type into and nothing pre-filled.
- [ ] Delete cases until the provider is below the floor, regenerate: every ratio
      is prefixed **[VERIFY]** and the below-floor warning is on the document.
- [ ] The file landed in the provider's folder in `eCAF_Documents` and an
      `eCAF_Routing` stage 1 item was created.

---

## 7 — Routing

- [ ] As the stage-1 holder, S7 shows the item and the chain map.
- [ ] Not-recommend and return-without-action are disabled until a comment is
      entered.
- [ ] Recommend. F7 creates the next stage and notifies the next holder — link
      only.
- [ ] Return without action on a later stage. It goes back to MSP, not onward.
- [ ] Complete the chain. The CCQAS upload prompt appears and the flag is
      settable.
- [ ] **F7 did not re-trigger itself.** Check its run history for a loop.

---

## 8 — The nightly and scheduled flows

- [ ] Set a case's Suspense to 3 business days out. F2 sends a T-3 reminder.
- [ ] Set one to 3 business days past. F2 sets status Overdue and mails the
      Clinical Leader. The dashboard card and the mail agree on which cases are
      late.
- [ ] `PROVIDER, SAMPLE C.` (expiry 15 Sep 2026) appears in the F3 STOP-EWP alert
      and on the watchlist card.
- [ ] `PROVIDER, SAMPLE B.` (Supervised + operational) triggers the F4
      stop-and-resolve alert.
- [ ] F8 produces an access report listing all five groups and their members.

---

## 9 — Migration and cutover

- [ ] `python3 tools/migrate_ewp.py --inspect ewp-peer-review-data.json` — read
      the output before mapping anything.
- [ ] Correct `FIELD_MAP` in that script to match the real shape.
- [ ] `--migrate` exits **0**. A non-zero exit means unmapped result values, and
      importing then would recreate the exact denominator bug this system exists
      to end.
- [ ] Every count in `dist/migration/reconciliation.md` matches the HTML tool.
- [ ] Spot-check 5 migrated cases field by field.
- [ ] The HTML tool is retained and documented as the outage contingency.

---

## 10 — Before you switch it on

- [ ] Delete every sample row (`PROVIDER, SAMPLE *`, FIN `TEST*`,
      `*@test.invalid`) from all lists.
- [ ] Record in credentials committee minutes: adoption, and the `ReviewType`
      denominator default with the authority reference in `eCAF_Config`.
- [ ] Calendar the quarterly access review (F8).
- [ ] Record in `RUNBOOK.md` which role-resolution path is live — Office 365
      Groups or `eCAF_RoleMap`. An access complaint later is unanswerable
      without it.
- [ ] Route the DRAFT-VALIDATE standards to Clinical Leaders for validation.
      Until they are validated they appear in reviews but in no document.

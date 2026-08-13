# Power Automate Flows F1–F8 — build instructions

No solution zip is emitted. A solution zip carries environment-specific
connection references and an environment GUID; importing one built off-tenant
into a DoD enclave fails on connection resolution and leaves half-created flows
behind. These are exact recreate-in-the-designer instructions instead — trigger,
each action, and the literal expression text to paste.

**Every flow here uses standard connectors only, except F6, which is explicitly
optional.** Each flow's fallback is stated; the app works with zero flows enabled,
degraded but correct.

Common settings for all flows:
- Run-only permissions: eCAF-MSP.
- **Notifications contain a link only.** Never put review content, FIN, provider
  name, or determination in an email body — § 1102 channel discipline. The
  content stays inside the permissioned site. Every mail action below is written
  to satisfy this; do not "helpfully" add detail to a subject line.
- Set each flow's failure notification to the MSP shared mailbox, not to the
  flow owner's personal mailbox — the owner will change.

---

## F1 — Assign reviewer and stamp item permissions

**The most important flow in the set.** It is the thing that makes item-level
confidentiality real. Test it with two accounts before any real data.

**Trigger:** SharePoint — *When an item is created* → `eCAF_ReviewCases`

| # | Action | Configuration |
|---|---|---|
| 1 | Get items | `eCAF_ReviewerPool`, Filter Query: `Available eq 1` |
| 2 | Filter array | From: step 1 value. Condition: `QualifiedSpecialties` contains `RequiredReviewerSpecialty` |
| 3 | Compose — sort | see expression below |
| 4 | Condition | length of step 2 output `is equal to` 0 → **yes branch: notify MSP "no qualified reviewer available", terminate as Succeeded.** Do not assign a random reviewer. |
| 5 | Update item | `eCAF_ReviewCases`: AssignedReviewer = chosen reviewer, AssignedDate = `utcNow()`, Suspense = business-day calc below, CaseStatus = `Assigned` |
| 6 | **Stop sharing an item or file** | `eCAF_ReviewCases`, Id = trigger Id. This removes inherited access. |
| 7 | Grant access to an item or file | Recipients: chosen reviewer; Roles: `Can edit`; **Notify: No** |
| 8 | Grant access to an item or file | Recipients: `eCAF-MSP`; Roles: `Can edit`; Notify: No |
| 9 | Grant access to an item or file | Recipients: cognizant Clinical Leader; Roles: `Can view`; Notify: No |
| 10 | Update item | `eCAF_ReviewerPool`: OpenAssignments = current + 1 |
| 11 | Send an email (V2) | To: reviewer. Subject: `e-CAF review assigned — <CaseID>`. Body: link only. |

**Load-balanced pick (step 3):**
```
first(sort(body('Filter_array'), 'OpenAssignments'))
```

**Suspense — 10 business days, weekends and federal holidays excluded.**
Power Automate has no business-day function. Get the holiday list first, then
loop. Add before step 5:

- Get items → `eCAF_Holidays`, Filter Query:
  `HolidayDate ge '@{utcNow()}'`
- Initialize variable `varDate` (String) = `@{utcNow()}`
- Initialize variable `varAdded` (Integer) = `0`
- Do until `varAdded` is greater or equal to `10`:
  - Set `varDate` = `addDays(variables('varDate'), 1)`
  - Condition:
    `and(less(dayOfWeek(variables('varDate')), 6), greater(dayOfWeek(variables('varDate')), 0), not(contains(body('Get_holidays')?['value'], formatDateTime(variables('varDate'),'yyyy-MM-dd'))))`
    → yes: increment `varAdded` by 1

`dayOfWeek()` returns 0=Sunday…6=Saturday, so `>0 and <6` is Mon–Fri.

> **Ordering matters.** Steps 6–9 must complete before step 11 sends the mail. If
> the reviewer clicks the link before the grant lands, they get access denied and
> raise a ticket. Keep them sequential — do not parallelise the branch.

> **Throttling.** "Stop sharing"/"Grant access" are expensive. At 30–75 users and
> a few hundred cases a year this is fine. If throttling appears at volume, the
> documented fallback is per-department folders with library-level permissions
> plus app-side filtering — a **weaker boundary** requiring formal risk
> acceptance, per flows-spec.md. Do not adopt it silently.

**Fallback if flows are unavailable:** MSP assigns in the app and shares the item
manually. The provisioning runbook's permission steps cover the manual share.

---

## F2 — Suspense reminders and overdue escalation

**Trigger:** Recurrence — daily 0600 local

| # | Action | Configuration |
|---|---|---|
| 1 | Get items | `eCAF_ReviewCases`, Filter Query: `CaseStatus ne 'Complete'` |
| 2 | Get items | `eCAF_Holidays` |
| 3 | Apply to each | over step 1 |
| 3a | Condition — T-3 | business days between today and Suspense `equals` 3 → remind reviewer (link only) |
| 3b | Condition — T-0 | Suspense `equals` today → remind reviewer (link only) |
| 3c | Condition — overdue | business days past Suspense `greater than` 2 → Update item CaseStatus = `Overdue`; email cognizant Clinical Leader (link only) |

The grace period is 2 business days and must match
`eCAF_Config!OverdueGraceBusinessDays` and the app's `IsOverdue` UDF. If you
change one, change all three, or the MSP's dashboard and the escalation mail will
disagree about which cases are late.

**Fallback:** the dashboard overdue card, which uses the same rule.

---

## F3 — 90-day privilege expiration watch (STOP-EWP)

**Trigger:** Recurrence — daily

| # | Action | Configuration |
|---|---|---|
| 1 | Get items | `eCAF_Providers`, Filter Query: `PrivilegeExpiration le '@{addDays(utcNow(),90)}'` |
| 2 | Apply to each → Send an email (V2) | To: MSP. Subject: `STOP-EWP determination due — <provider>`. Body: link + the determination owed (STOP-EWP vs legacy process, DHA-PM 6025.13 Vol 8). |

Filter server-side on `PrivilegeExpiration` — it is indexed. Do not pull all
providers and filter in the loop.

**Fallback:** dashboard watchlist card.

---

## F4 — Supervised + operational stop-and-resolve

**Trigger:** SharePoint — *When an item is created or modified* → `eCAF_Providers`

| # | Action | Configuration |
|---|---|---|
| 1 | Condition | `PrivilegingStatus` equals `Supervised` **AND** `OperationalPlatform` equals `true` |
| 2 | Yes → Send an email (V2) | To: MSP + cognizant Clinical Leader. Subject: `STOP AND RESOLVE — supervised privileges on operational platform`. Body: link + BUMEDNOTE 6000 reference. |

Add a trigger condition so the flow does not fire on every unrelated edit:
```
@or(not(equals(triggerOutputs()?['body/PrivilegingStatus/Value'], 'Supervised')), equals(triggerOutputs()?['body/OperationalPlatform'], true))
```

**Fallback:** dashboard stop-and-resolve card.

---

## F5 — Review floor reached

**Trigger:** SharePoint — *When an item is created or modified* → `eCAF_ReviewCases`

| # | Action | Configuration |
|---|---|---|
| 1 | Condition | `CaseStatus` equals `Complete` |
| 2 | Get items | `eCAF_Config`, Filter Query: `Title eq 'DenominatorReviewTypes'` |
| 3 | Get items | `eCAF_ReviewCases`, Filter Query: `Provider eq <id> and ReviewPurpose eq 'OPPE' and CaseStatus eq 'Complete'` |
| 4 | Filter array | keep items whose `ReviewType` is in the step-2 value, split on `;` |
| 5 | Condition | `length(body('Filter_array'))` equals the configured floor → notify MSP + CL: floor met, staging available |

**Read the denominator rule from `eCAF_Config` (step 2). Do not hard-code
`ReviewType eq 'Peer'` in the step-3 filter query.** The rule is
credentials-committee-reversible; a hard-coded flow is the thing that makes the
reversal a code change instead of a data change, which is exactly what the
CLAUDE.md rule prohibits.

Use `equals` the floor, not `greater or equal` — otherwise it fires on every
completion after the tenth.

**Fallback:** dashboard floor tracker.

---

## F6 — Generate document from Word template  ⚠ PREMIUM

**This flow is optional and must never become a dependency.** It uses **Word
Online (Business)** — a premium connector that may be unlicensed in the enclave.
The in-app HTML→.doc generator on S6 produces the same content with no license
and is built regardless (CLAUDE.md). F6 is the upgrade.

**Trigger:** Power Apps (V2) — parameters: `ProviderId` (number),
`PeriodStart` (text), `PeriodEnd` (text), `DocType` (text)

| # | Action | Configuration |
|---|---|---|
| 1 | Get item | `eCAF_Providers`, Id = ProviderId |
| 2 | Get items | `eCAF_ReviewCases` for provider + period, CaseStatus `Complete` |
| 3 | Get items | `eCAF_Config` → denominator types |
| 4 | Filter array | qualifying cases only |
| 5 | Get items | `eCAF_ReviewSummaries` for those cases; parse `Item11Elements` JSON |
| 6 | Get items | `eCAF_Standards`, Filter Query: `Status eq 'ACTIVE'` — **ACTIVE only; DRAFT-VALIDATE never reaches a document** |
| 7 | **Populate a Word template** | Template: the matching file from `dist/templates/`. Map each content control by name — see the name mapping below. |
| 8 | Create file | `eCAF_Documents`, folder = provider folder |
| 9 | Create item | `eCAF_Routing` stage 1 |

**Content control names.** `tools/build_templates.py` sanitises MapsTo tokens for
Word: `:` `-` `.` become `_`, and a leading digit is prefixed with `C`.
So `455-I11:medication` → `C455_I11_medication`, `FPPE-3I` → `FPPE_3I`.

**Item 12 has no content control and no mapping.** There is nothing in the
template to bind to. Do not add one.

Every unpopulated field must be written as `[VERIFY]`, not left blank — a blank
cell on a signed document reads as "assessed and found nothing", which is not
what an absent measurement means.

**Fallback:** S6's HTML generator. Same content, same exclusions, no license.

---

## F7 — Advance the endorsement chain

**Trigger:** SharePoint — *When an item is modified* → `eCAF_Routing`

| # | Action | Configuration |
|---|---|---|
| 1 | Condition | `Action` not equal `Pending` |
| 2 | Switch on `Action` | |
| 2a | `Recommend` | create next `eCAF_Routing` item per chain map; set CurrentHolder; notify (link only) |
| 2b | `NotRecommend` | record; notify MSP; **do not advance** |
| 2c | `ReturnWithoutAction` | create a new stage item held by MSP; notify MSP |
| 3 | Condition — final stage | if the completed stage is the last in the chain → set `UploadedToCCQAS` prompt on the document, notify MSP to upload |

**Chain maps** (from flows-spec.md):
- **OPPE:** Provider → Peer/Proctor → CRC Chair → Department Head
- **FPPE:** Preceptor → Clinical Leader
- **455:** Clinical Supervisor → (per form signature blocks; MSP verifies before PA)

Add a trigger condition so the flow does not re-fire on its own writes:
```
@not(equals(triggerOutputs()?['body/Action/Value'], 'Pending'))
```
Without it, F7 updating a routing item re-triggers F7. That loop is the single
most common way a Power Automate flow gets an environment throttled.

CCQAS remains the system of record for OPPE. The flag records that the upload
happened; it does not replace it.

**Fallback:** manual routing from S7, which shows the chain map on screen.

---

## F8 — Quarterly access report

**Trigger:** Recurrence — quarterly

| # | Action | Configuration |
|---|---|---|
| 1 | Send an HTTP request to SharePoint | `GET _api/web/sitegroups?$expand=Users` |
| 2 | Create CSV table | group name, member, email |
| 3 | Create file | `eCAF_Documents/_access-reviews/` |
| 4 | Send an email (V2) | To: MSP — link only, for credentials committee minutes |

Step 1 uses the SharePoint connector's own HTTP action — standard connector, not
the premium HTTP connector.

**Fallback:** manual site permissions review; checklist in the provisioning
runbook.

---

## Build order for the operator

F1 first and alone — test with two accounts, confirm reviewer A cannot open
reviewer B's case **by direct item URL**, not just in the app. Then F2–F5, then
F7, then F8. F6 last, and only if Word Online (Business) turns out to be
licensed.

# Canvas App Specification — eCAF

Format: Power Apps YAML source under `src/`, packed via
`pac canvas pack --sources src --msapp dist/app/eCAF.msapp`.
Tablet layout. Every screen footer: the CUI/§ 1102 banner (see CLAUDE.md).

## App start (App.OnStart)
1. Resolve role: check `User().Email` membership in the five `eCAF-*` groups
   (Office 365 Groups connector or a maintained `eCAF_RoleMap` fallback list if
   the connector is blocked — document which in RUNBOOK).
2. Set `gblRole`, `gblMe`, `gblToday`.
3. Load `colHolidays` from holidays CSV list; define `BusinessDaysBetween()` as a
   named formula excluding weekends + colHolidays.

## Screens

### S1 Dashboard (role-aware)
- **MSP:** cards — open cases by status; overdue (Suspense < Today && Status <> Complete);
  OPPE floor tracker per provider in an active OPPE window: `CountRows(Peer-type
  Complete cases in period)` vs 10, color-coded; 90-day privilege-expiration
  watchlist (STOP-EWP banner per Vol 8); supervised+operational stop-and-resolve
  alerts; DRAFT-VALIDATE standards awaiting Clinical Leader sign-off.
- **Clinical Leader:** same cards filtered to Department; plus standards-validation
  queue for their specialty.
- **Reviewer:** my queue (AssignedReviewer = me, Status <> Complete), sorted by Suspense.
- **Cross-specialty compliance panel (MSP/CL):** per-standard MET rate by specialty —
  grouped by Standard, computed as MET/(MET+NOT_MET), NA excluded. This is the
  "best standards across specialties" view.

### S2 Provider Record (MSP/CL)
Roster detail; CAF document index (eCAF_Documents filtered to provider); review
history; cycle timeline (FPPE window, OPPE period, privilege expiration).

### S3 Case Intake (MSP/CL)
Provider, FIN (**only** encounter identity field; input mask 12 chars), encounter
date/type, purpose, ReviewType, required reviewer specialty, suspense
(default: AssignedDate + 10 business days). "Create pair" toggle spawns the
CrossSpecialty twin with PairedCase back-link. Bulk mode: N cases for an OPPE cycle.

### S4 Review Instrument (Reviewer)
Two sections, in order:
1. **Fixed instrument** — DHA 455 item 11 element block (each MET/NOT_MET/NA),
   16 competency constructs across the six domains (Sat/Unsat/NotObserved),
   overall determination. Writes to eCAF_ReviewSummaries (JSON blobs per
   standards-schema.json).
2. **Standards checklist** — gallery over eCAF_Standards where
   `Status <> RETIRED && Specialty in ["Universal", caseSpecialty]`;
   DRAFT-VALIDATE items show an amber DRAFT badge. Each renders
   MET/NOT_MET/NA + comment → one eCAF_ReviewResponses item per standard.
   Patch results with canonical values only.
Submit: validate all required answered → Status = Complete → CompletedDate.
Autosave on every toggle (Patch per item — no bulk save to lose).

### S5 Activity Data Entry (MSP)
Per provider/period grid for eCAF_ActivityData.

### S6 Document Staging (MSP/CL)
Provider + period + doc type → shows populated-vs-[VERIFY] preview →
generate (flow F6 or in-app HTML fallback). **Item 12 of the 455 renders
blank with the note "Clinical supervisor determination required" — never computed.**
DRAFT-VALIDATE standards are excluded from generated documents.

### S7 Endorsement Queue
eCAF_Routing filtered to CurrentHolder = me; actions Recommend / NotRecommend /
ReturnWithoutAction; comments; advance handled by F7.

### S8 Standards Admin (MSP/CL)
CRUD over eCAF_Standards. Clinical Leader "Validate" button: sets ACTIVE,
stamps ValidatedBy/Date. Retire, never delete (RETIRED keeps history joins intact).

## Aggregation formulas (the ones to get right)
- 455 item 11 ratios: per element, over **Peer-type Complete** cases in the period:
  `met = CountRows(Result=MET)`, `denom = met + CountRows(Result=NOT_MET)`,
  render "met of denom = %". NA excluded. CrossSpecialty cases excluded.
- OPPE floor: `CountRows(ReviewCases: Provider, Purpose=OPPE, Type=Peer,
  Status=Complete, EncounterDate within period) >= 10`.
- Delegation: all filters on indexed columns per lists.json; pre-filter server-side
  before any in-memory grouping.

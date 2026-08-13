# RUNBOOK — Building the e-CAF with Claude Code

## One-time setup (any machine — artifacts contain no CUI)
1. Install Claude Code: `npm install -g @anthropic-ai/claude-code` (Node 18+).
2. Install Power Platform CLI (`pac`) if permitted; if not, Claude Code still
   emits YAML source + you pack later or import lists/flows manually.
3. Put this folder in a git repo. Open a terminal in it and run `claude`.

## The master prompt (paste into Claude Code, first session)

> Read CLAUDE.md, schemas/lists.json, standards/standards-schema.json,
> standards/standards-seed.csv, app/app-spec.md, and flows/flows-spec.md in full
> before writing anything. Then execute Build order step 1 from CLAUDE.md:
> generate dist/lists/ (one import CSV per list with 3 rows of obviously-fake
> sample data each) and dist/lists/provisioning-runbook.md covering every manual
> finishing step CSV import cannot do (column types, choices, lookups, indexes,
> broken inheritance, the five permission groups, content types on the document
> library). Self-review against the Hard rules in CLAUDE.md and report any rule
> you could not satisfy before finishing.

Then per session: "Execute Build order step N" — one step per session, review the
diff before moving on. Step 8's dry-run script is your acceptance test.

## What you do in the browser (Claude Code cannot)
1. **Phase 0 first — approval.** Confirm with the tenant/RMF POC what a
   citizen-developed Power App holding § 1102/CUI content requires. Long pole.
2. Create the site (Team site, no M365 group, or per tenant SOP). Name:
   *I MEF e-CAF (MQA Protected)*. Add CUI banner to home page.
3. Create the five permission groups; break inheritance per lists.json.
4. Provision lists per `dist/lists/provisioning-runbook.md`.
5. Import standards-seed.csv into eCAF_Standards. Route DRAFT-VALIDATE items to
   Clinical Leaders via S8 once the app is live.
6. Import the app: maker portal → Apps → Import canvas app → eCAF.msapp
   (or open YAML source via `pac canvas` round-trip). Fix connection references.
7. Recreate/import flows per flows-spec.md. Test F1's permission stamping with
   two test accounts before any real data.
8. Run the step-8 dry-run with fake data end-to-end: intake → assign → review →
   aggregate → stage document → route → "CCQAS uploaded" flag.
9. Migrate `ewp-peer-review-data.json` (Build order step 8 emits the mapping
   script); reconcile counts against the HTML tool before cutover. Keep the HTML
   tool as the documented outage contingency.
10. Document adoption + the ReviewType denominator default in credentials
    committee minutes; calendar the quarterly access review (F8).

## Standing decisions already made (don't relitigate in-session)
- FIN is the sole encounter identifier.
- Peer-type reviews only in OPPE floor / 455 denominators (committee-reversible).
- No auto-rating of 455 item 12.
- DRAFT-VALIDATE standards render badged, excluded from generated documents.
- CCQAS remains system of record for OPPE.

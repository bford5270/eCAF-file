# Power Automate Flow Inventory — eCAF

All flows use standard connectors (SharePoint, Office 365 Outlook) unless noted.
Every notification contains a **link only** — never review content in email bodies
(content stays inside the permissioned site; § 1102 channel discipline).

| # | Trigger | Logic | Fallback if flows are unavailable |
|---|---------|-------|-----------------------------------|
| F1 | eCAF_ReviewCases item created | Pick reviewer from eCAF_ReviewerPool (QualifiedSpecialties contains RequiredReviewerSpecialty, Available, lowest OpenAssignments); set AssignedReviewer/Date; **Grant access to item** (SharePoint "Stop sharing" then grant: reviewer + eCAF-MSP + cognizant CL); increment OpenAssignments; notify with suspense | MSP assigns manually in app; app "Share" instruction in runbook |
| F2 | Recurrence daily 0600 | For open cases: T-3/T-0 reminders; T+2 business days overdue → Status=Overdue + CL escalation. Business days via holidays list | Dashboard overdue card (already role-visible) |
| F3 | Recurrence daily | eCAF_Providers where PrivilegeExpiration <= Today+90 → MSP alert: STOP-EWP / legacy process determination (Vol 8) | Dashboard watchlist card |
| F4 | Provider item modified | If PrivilegingStatus=Supervised AND OperationalPlatform=Yes → stop-and-resolve alert MSP + CL (BUMEDNOTE 6000) | Dashboard alert card |
| F5 | ReviewCases item modified | On 10th Peer/Complete case in an OPPE period → notify MSP/CL: floor met, staging available | Dashboard floor tracker |
| F6 | App button (Document staging) | Populate Word template (**premium — Word Online Business**) from aggregates; file to eCAF_Documents; create eCAF_Routing stage 1 | **In-app HTML→.doc generation (predecessor tool logic) — build this regardless; F6 is the upgrade, not the dependency** |
| F7 | eCAF_Routing item modified | On action: advance to next stage per chain map + notify; ReturnWithoutAction → back to MSP; final stage → prompt CCQAS upload, set UploadedToCCQAS flag | Manual routing via S7 queue + email |
| F8 | Recurrence quarterly | Export access/permission report → MSP for credentials committee minutes | Manual site permissions review, checklist in runbook |

## Item-level permission pattern (F1)
SharePoint "Stop sharing an item or file" + "Grant access to an item or file"
actions. Test at expected volume; if throttling appears, fall back to
per-department folders with library-level permissions and app-side filtering,
documented as a formal risk acceptance (weaker boundary).

## Chain maps (F7)
- OPPE: Provider → Peer/Proctor → CRC Chair → Department Head (OPPE Template Sec X)
- FPPE: Preceptor → Clinical Leader (FPPE Template CL Assessment block)
- 455: Clinical Supervisor → (per form signature blocks; MSP verifies before PA)

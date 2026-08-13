# Canvas app — source, packing, and what still needs a human

## What is here

```
src/App.fx.yaml                 App object: OnStart, named formulas, UDFs
src/fixed-instrument.json       455 item 11 elements + 16 competency constructs
src/Components/cmpCUIFooter…    the mandatory CUI / § 1102 marking
src/Screens/S0…S8               nine screens
```

## Read this before you try to pack

`pac` was **not available on the build machine**, so this source has not been
round-tripped. CLAUDE.md anticipates that and asks for the YAML source plus the
pack command anyway. Be aware of what that means in practice:

`pac canvas pack` does not build an .msapp from screen YAML alone. A canvas app
package also contains `Entropy/`, `Connections/`, `DataSources/`, `pkgs/`, and
`Header.json` — machine-generated files carrying connection references, data
source metadata and internal GUIDs, none of which can be authored correctly
off-tenant.

**The working procedure:**

1. In the target environment, create a blank tablet canvas app. Add the eleven
   SharePoint list connections and the `eCAF_Documents` library as data sources.
   Save and publish it once.
2. Export it and unpack it:
   ```
   pac canvas unpack --msapp blank.msapp --sources ./scaffold
   ```
3. Copy the files from `src/` over `./scaffold/Src/`, keeping the scaffold's
   generated folders untouched.
4. Repack and import:
   ```
   pac canvas pack --sources ./scaffold --msapp eCAF.msapp
   ```
5. Open in the maker portal, fix any connection reference it flags, publish.

If `pac` is not permitted on the operator's machine at all, the fallback is to
build the screens in the maker portal and paste each formula from these files.
Slow, but every formula is here and commented, and the aggregation and
business-day logic — the parts that are actually hard to get right — transfer
verbatim.

**Schema version.** The Power Apps YAML schema has changed across `pac` releases.
Confirm the shape against a `pac canvas unpack` of a blank app in your own
environment before assuming these files parse as-is; the property names and
formula text are the durable part, the surrounding structure is not.

## Data sources to add

Eleven SharePoint lists plus one library:

`eCAF_Providers`, `eCAF_ReviewCases`, `eCAF_ReviewResponses`,
`eCAF_ReviewSummaries`, `eCAF_Standards`, `eCAF_ActivityData`, `eCAF_Routing`,
`eCAF_ReviewerPool`, `eCAF_Holidays`, `eCAF_Config`, `eCAF_RoleMap`, and the
`eCAF_Documents` library.

## Embedding fixed-instrument.json

`src/fixed-instrument.json` is read at startup as `varFixedInstrumentJson`. Two
ways to supply it:

- **Preferred:** add it as an app *media/resource* file and set
  `Set(varFixedInstrumentJson, YourResourceName)` as the first line of OnStart.
- **If resources are awkward:** paste the JSON as a literal string into that
  `Set()`. Uglier, works identically, and keeps it out of a list where anyone
  with list edit rights could change the instrument.

It is deliberately *not* a SharePoint list. It is form structure, not
operational data, and the people who maintain lists are not the people who
should be able to change which elements a 455 has.

## Two things to set at import

**`varWordConnectorAvailable`** — S6 shows the Word-template button only when
this is true. Set it in OnStart after probing the connector, or simply hard-set
it once you know whether Word Online (Business) is licensed in the enclave:

```
Set(varWordConnectorAvailable, false)   // no premium connectors
```

The HTML→.doc generator next to it always works, so `false` is a safe default
and the app is fully functional with it.

**Role resolution** — `UserInGroup()` in OnStart is a placeholder for whichever
mechanism the tenant permits. If the Office 365 Groups connector is available,
replace it with `Office365Groups.ListGroupMembers()`. If not, delete the probe
and let it fall through to the `eCAF_RoleMap` list, which is populated by the
MSP. Whichever you pick, **record it in RUNBOOK.md** — an access complaint six
months from now is unanswerable if nobody knows which path is live.

## Delegation

Every gallery filters server-side on a column marked `"indexed": true` in
`schemas/lists.json`, then applies non-delegable predicates in memory over the
already-bounded set. That ordering is deliberate and load-bearing. The pattern
to preserve:

```
Filter(                                  // in memory — small set
    Filter(                              // delegated — indexed columns only
        eCAF_ReviewCases,
        Provider.Id = x, CaseStatus = "Complete",
        EncounterDate >= a, EncounterDate <= b
    ),
    CountsInDenominator(ReviewType, CaseStatus)
)
```

Putting `ReviewType` into the inner `Filter` looks tidier and silently caps the
result at the delegation limit, understating every denominator on every document
the app produces. `tools/lint_hard_rules.py` checks that the indexes exist; it
cannot check that you kept the nesting, so this is on the reviewer.

## Screen checklist for anyone adding a screen

- [ ] Instance of `cmpCUIFooter` (the linter fails the build without it)
- [ ] No encounter identifier other than FIN
- [ ] Any MET/NOT_MET/NA control uses those exact strings as its `Items`
- [ ] Any denominator count routes through `CountsInDenominator`
- [ ] Server-side filter on indexed columns before any in-memory work

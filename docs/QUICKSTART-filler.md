# Quickstart — filling DHA forms from a spreadsheet

Fifteen minutes, start to finish. Nothing here touches SharePoint, Power Apps, or
your tenant. It runs on one computer.

## What you need

**Two script files**, kept in the same folder as each other:

- `fill_dha_forms.py`
- `ecaf_normalize.py` ← the first one imports this; it will not run without it

**The blank DHA PDF** you want filled — `DHA_OPPE_Template.pdf` or
`DHA_Initial_FPPE_Template_OCT_2025.pdf`.

**Python 3.9 or newer.** Check by opening a terminal (Windows: press Start, type
`cmd`, Enter) and running:

```
python --version
```

If that errors, install Python from python.org or the Microsoft Store and tick
**"Add Python to PATH"** during setup.

**One library:**

```
pip install pypdf
```

> On a government machine `pip` may be blocked by the proxy. If it fails, ask
> your IT shop for the `pypdf` wheel, or run this on a non-DoD machine — the
> blank templates and a spreadsheet of counts are not CUI, though **anything you
> produce with real provider data is.**

---

## Step 1 — get a spreadsheet to fill in

```
python fill_dha_forms.py --blank-inputs my-oppe.csv --form OPPE
```

That writes `my-oppe.csv` with one column per fillable field and one example row.
It also prints which column goes to which part of the form.

Use `--form FPPE` for the FPPE template instead.

## Step 2 — fill it in

Open `my-oppe.csv` in Excel. **One row per provider.** Delete the example row and
type your own.

Leave anything you don't have blank — a blank cell is skipped, not written as an
empty value, so a half-filled row fills what it has and leaves the rest of the
form alone for you to complete by hand.

Column names are readable: `s3b_outpatient_encounters` is Section III item B.

Save it as CSV. (Excel will warn about keeping CSV format — keep it.)

## Step 3 — fill the forms

```
python fill_dha_forms.py --fill my-oppe.csv --form OPPE ^
    --template DHA_OPPE_Template.pdf --out filled
```

*(That `^` is a Windows line-continuation. On Mac/Linux use `\` instead, or just
type the whole thing on one line.)*

You get one PDF per row in a new `filled` folder, named after the provider.

## Step 4 — open it and finish it

Open the PDF in Adobe. The practice-volume numbers are already in. **You still
fill in by hand:**

- the 16 competency constructs (OPPE Section VII / FPPE Section 4)
- OPPE Section VI facility-wide monitors
- every signature block

That is deliberate — see below.

---

## Why it leaves those blank

**It fills what is counted. It never fills what is judged.**

Encounter counts and percentages are facts you already hold; retyping them is
transcription, and transcription is where errors get onto a signed document.

A competency rating is your professional judgement about a named provider. If
this tool pre-checked those boxes, the result on the signed page would be
indistinguishable from an assessment a human actually made. It won't do that,
and it refuses input that tries — by column name *and* by value, so a column
called `notes` containing `Satisfactory` is still rejected.

It also refuses any input containing an SSN, MRN, DOB, or patient name. FIN is
the only encounter identifier this system handles.

## When something goes wrong

The tool tells you and exits non-zero rather than quietly producing a form.

| Message | What it means |
|---|---|
| `no mapping for [...]` | A column name it doesn't recognise. Check spelling against the `--blank-inputs` header. Dropped, never guessed into a nearby field. |
| `refused '<col>'` | You tried to fill a judgement field. Working as intended. |
| `refused input containing a <label>` | A patient identifier in your spreadsheet. Remove it. |
| `field map says X -> Y, which is not in this PDF` | Your template is a different version from the one the map was built against. Run `--list-fields` on your PDF and fix `OPPE_MAP`/`FPPE_MAP` in the script. |

## Known gaps

**OPPE Section IV A–F** (surgical / invasive / noninvasive procedures, blood use,
medication use, record pertinence) is not filled. That PDF gives those boxes no
names — they are generic `Text195`-style fields — and guessing which anonymous
box is "blood use" would put a number on a credentialing document based on a
hunch. Fill them by hand, or run `--list-fields`, work out which is which by
opening the PDF, and add them to `OPPE_MAP`.

**The DHA 455 is not supported.** It is an XFA/LiveCycle form that cannot be
filled reliably outside Adobe, and the copy supplied is watermarked DRAFT
(`DHA FORM 455 (TEST), OCT 2025`). That one stays manual.

## Handling what comes out

The moment you put a real provider in the spreadsheet, **both the spreadsheet and
the filled PDFs are CUI** and carry the § 1102 protection printed on the form.
Store them accordingly. `dist/filled/` and `dist/ingest/` are gitignored so they
never reach the repository, but that protects the repo, not your Downloads
folder.

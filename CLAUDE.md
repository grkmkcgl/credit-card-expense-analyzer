# CLAUDE.md

Context for working on this repo. The owner (Görkem) writes in Turkish; answer in Turkish unless he writes in English. The UI and all user-facing text are Turkish.

## What this is

A single-file, fully offline web app (`index.html`) that analyzes Turkish credit-card statements (PDF, including password-protected) and bank exports (xlsx/xls/csv). No build step, no server, no network calls.

**Non-negotiable privacy rules** (the whole reason the tool exists — the owner didn't want to upload statements anywhere):
- Never add network requests, analytics, CDNs or external fonts. Libraries are embedded.
- Never use localStorage/sessionStorage/IndexedDB. Data lives only in the user's `harcama-verisi.json`.
- Never commit real statements or data files. `.gitignore` blocks them. Test fixtures must be synthetic.
- PDF passwords live only in memory (`lastPw`) for the page session.

## Layout of index.html

- Lines ~100–110: SheetJS (`xlsx.core.min.js` 0.18.5), PDF.js (3.11.174 `pdf.min.js` + worker) embedded as **gzip+base64** strings, unpacked with `DecompressionStream` into `window.libsReady`. Do not inline raw library JS: sequences like `<!--` inside a `<script>` broke HTML parsing before ("page shows as text").
- `<style>`: dark theme (`--bg:#000`). Categorical palette `PAL` (6 colors + `GRAY`) was validated for CVD/contrast on black — keep it.
- App script (after the libs): storage → PDF parsing → rules/categorize → import → render.

### Storage
- Desktop (Chrome/Edge): `showDirectoryPicker` → writes `harcama-verisi.json` (+ `.onceki.json` backup) in the chosen folder.
- Phone/other (`MOBILE = !showDirectoryPicker`): open the JSON via file input, "Kaydet" downloads it.
- `snapshot()` / `applyData()` define the file schema: `history, statements, overrides, excluded, viewMode, rules, lastMap`. `applyData` also merges new default rules/keywords into saved rules and runs `migrate()` + `expandInstallments()`. Keep old files loadable.

### PDF parsing (`pdfToRows` → `linesToRows`)
- Text items grouped into lines by y; items joined with a space only when there is a real x-gap (handles letter-by-letter PDFs).
- Rotated text and vertically stacked single letters (margin document info) are dropped before line grouping.
- `dropNonTxSections`: skips points sections (Worldpuan/ParafPara/Chip-Para/Bonus details) until the next transaction table header.
- Each date starts a transaction; text until the next date = description + amounts. Dates: `26.07.2026`, `26/07/26`, `2026-07-26`, `26 Temmuz 2026`, year-less at line start.
- Amounts: Turkish format `1.234,56`. Numbers after the amount without `,dd` are bonus points (ignored), e.g. `500,00 10`.
- Installments: `4.964,93 TL'lik işlemin 2 / 3 taksidi` (same or next line) or a bare `2/6` column. When a row has several amounts, the one where `amount × count ≈ total` is the installment (e.g. `1.624,27 6.497,08 / 4` → 1.624,27; the second is remaining balance / remaining count).
- Sign: on card statements purchases are unsigned; `+` amounts are payments/refunds. `PAY_RE` separates payments (kept as `kind:"payment"`, never counted as spending) from refunds (`kind:"refund"`, negative, reduce spending).
- Statement summary: `findStmtDate` (cut-off date: same line, table header with values on the next line by x-column, label-below, "Ekstre Dönemi a - b", spaced letters; must be plausible vs transaction dates, so "Son Ödeme Tarihi" is never picked). `findLabeledAmount` for `due` (Dönem Borcu) and `prev` (Önceki Dönem Borcu). Amount x-position is taken from its first digit.

### Periods, installments, reconciliation
- Grouping is by **statement period**, not calendar month: every transaction from a PDF gets `stmt` (cut-off date); `periodKey(t) = (t.stmt || t.date).slice(0,7)`. Banks post late, so a 25 Jul purchase can legitimately be on the 26 Aug statement.
- Installments are billed in the statement month, not the purchase month (banks print the original purchase date on every installment line). `expandInstallments()` rebuilds the whole series every time: real rows from statements, `est:"past"` for missing earlier ones, `est:"future"` for upcoming ones. Estimates are never saved as real and are replaced when the real statement arrives. `sameInst` matches series by description + count + total.
- Re-importing the same statement must not duplicate; it updates `stmt` on existing rows (repairs records saved by older versions).
- `renderRecon`: prev − payments + purchases − refunds must equal the statement's Dönem Borcu; shows the diff and unread lines with an "Ekle" button. This check is the main correctness signal — keep it green.

### Categorization
- Rules are editable text `Kategori: KEY1, KEY2`; `categorize` picks the **longest** matching keyword; keys ≤4 chars match whole words only (so `PET` ≠ `PETROL`, `DIS` ≠ `YURT DISI`). Per-description `overrides` win.
- Special categories: `Taksitler` (all installments; sub-category = rule category), `İadeler ve indirimler`, `Diğer` (unmatched).

### UI features
Period selector (all time / each statement / custom date range with presets), category include/exclude checkboxes (affects totals, charts, lists), bar or donut chart (top 6 colored, rest folded to gray), "Dönemlere göre" chart, merchant analysis (`renderQuery`, scoped to the selected period; items in every list are clickable via `data-an`), multi-file upload with per-file summary table.

## Testing

No test suite is committed yet. During development everything was verified with Playwright (Chromium) against synthetic PDFs built with reportlab, and every change was re-run against all earlier scenarios:
- 143 transactions over 3 pages (letter-by-letter lines, right-aligned amounts, installments, wrapped descriptions) → all read, totals exact.
- Installment series across 6 statements uploaded in any order, only the last one, or twice → one installment per period, totals exact.
- Cut-off date in 6 layouts (same line, table, label-below, spaced letters, period range, missing) → never confused with Son Ödeme Tarihi.
- Reconciliation: statement with prev balance, payment, late-posted purchase, installment, refund, interest/BSMV → "Tutuyor"; one undated fee line → exact diff, fixed via "Ekle".
- Worldpuan detail section (split and glued layouts) → ignored; "Worldpuan kullanımı +50,00" inside the table still counts as a refund.
- Mobile width (390px) with `showDirectoryPicker` removed → open/save JSON flow.

Useful next step: commit these as `tests/` (a small Python script that generates the synthetic PDFs + Playwright checks). Use `/opt/pw-browsers` Chromium if present; Safari/WebKit was never tested (iOS needs 16.4+ for `DecompressionStream` and regex lookbehind).

## Deployment

Repo is private. Live page: Cloudflare Pages or Netlify connected to this repo, no build command, output = root. On iOS, opening the HTML from the Files app shows a Quick Look preview that doesn't run JS; use the live URL.

## Commits

Commit messages in Turkish, short subject + body explaining why.

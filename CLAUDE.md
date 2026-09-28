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
- `mergeRules(base, incoming)` adds missing keywords/categories without removing anything; used for default-rule merge in `applyData` and for category import.
- Sharing between people (each has their own data file): "Kategorileri paylaş" downloads `harcama-kategorileri.json` = `{type:"kategoriler", version, updated, rules, overrides}` — no transactions/amounts. "Kategorileri içe aktar" accepts that file or a full `harcama-verisi.json` (only `rules`/`overrides` are read). `planImport` computes the diff without changing anything (new keywords in existing categories, new categories, new merchant picks, conflicting picks); the user sees it in `#sharePreview` with a checkbox per item (new items ticked, conflicts unticked = keep own) and nothing is saved until "Uygula". `applyImport` applies only the ticked items via `mergeRules`.
- Special categories: `Taksitler` (all installments; sub-category = rule category), `İadeler ve indirimler`, `Diğer` (unmatched).

### UI features
Period selector (all time / each statement / custom date range with presets), category include/exclude checkboxes (affects totals, charts, lists), bar or donut chart (top 6 colored, rest folded to gray), "Dönemlere göre" chart, merchant analysis (`renderQuery`, scoped to the selected period; items in every list are clickable via `data-an`), multi-file upload with per-file summary table, category share export/import. "Tüm işlemler" and "Kategorisi bulunamayanlar" are native `<details class="fold">` sections (`#allFold`, `#unkFold`), closed by default, with counts in the title (`#allCount`, `#unkCount`); open state is not saved and survives re-render because `render()` only rewrites the tables.

## Testing

End-to-end tests drive the real `index.html` in headless Chromium against **synthetic** statement PDFs (no real data anywhere; merchant names in fixtures are invented).

```bash
pip install -r tests/requirements.txt
python -m playwright install chromium      # skip if Chromium is already available (e.g. /opt/pw-browsers)
python tests/run_tests.py                   # all tests, ~2-3 min
python tests/run_tests.py taksit            # only tests whose name contains "taksit"
VERBOSE=1 python tests/run_tests.py         # print tracebacks
```

- `tests/fixtures.py` generates the PDFs into `tests/out/` (git-ignored) with reportlab. It needs a TTF with Turkish glyphs; it finds DejaVu/Arial automatically, or set `TEST_FONT=/path/font.ttf`.
- `tests/run_tests.py` has one function per scenario (`@test`). Each test opens a fresh page (`App` helper), fixes the clock to 2026-09-28 (installment past/future split depends on "today"), imports files, and asserts on visible UI text or on in-page state (`history`, `raw`, `pdfMissed`, …) via `page.evaluate`.
- **Run the whole suite before every commit that touches `index.html`.** The reconciliation tests ("Tutuyor") and exact totals are the main guard against parser regressions.
- When fixing a new statement layout: add a generator to `fixtures.py` reproducing the layout with invented names/amounts, add a test with the expected totals, see it fail, then fix.
- The tests were mutation-checked: breaking payment detection or short-keyword word boundaries makes tests fail.

Scenarios covered: 143-transaction 3-page statement (letter-by-letter lines, wrapped descriptions); installment formats and rotated/vertical margin text; "+" payments/refunds; cut-off date in 6 layouts; statement-period grouping with late-posted purchases; installment series in order, shuffled, last-only and duplicate upload; reconciliation (match, exact diff + "Ekle", no previous balance); real-statement layout with bonus-point column, multi-amount installment lines and Worldpuan sections (split and glued); repair of records saved by older versions; multi-file upload with encrypted + broken files (password asked once); category matching and rule merge; category share export (no transactions) / import preview (nothing changes before "Uygula", per-item accept/reject, conflicts, cancel, already up to date, full data file, broken file); collapsible sections (closed by default, counts, stay open on re-render); category exclusion + date range; donut chart click; merchant analysis scopes and click-to-analyze from every list; phone open/save/reopen flow; nothing written to browser storage.

Not covered: Safari/WebKit (iOS needs 16.4+ for `DecompressionStream` and regex lookbehind), real bank PDFs other than the layouts above, the desktop folder picker (`showDirectoryPicker` can't be automated; tests bypass it).

## Deployment

Live page: GitHub Pages from the `gh-pages` branch, built by `.github/workflows/pages.yml` on every push/branch delete: `main`'s `index.html` at the root, every other branch at `/onizleme/<branch, / → ->/`, list at `/onizleme/`. Only `index.html` is published. Never commit to `gh-pages` by hand; it is force-rewritten. Pages setting: Source = Deploy from a branch, `gh-pages`, `/ (root)`. On iOS, opening the HTML from the Files app shows a Quick Look preview that doesn't run JS; use the live URL.

## Commits

Ask the owner for the branch name before creating a new branch.

Commit messages in Turkish, short subject + body explaining why.

# How the JSON-PDF Compare Tool Works

A plain-language walkthrough of every file and function in the codebase — what it does, what goes in, what comes back out, and who calls it.

---

## 1. The big picture, in one paragraph

You pick a folder full of PDF/JSON pairs. The tool figures out which PDF goes with which JSON (even if their filenames aren't identical), pulls the plain text out of each PDF, and then checks every single value inside the JSON to see if it can find that same value somewhere in the PDF's text — tolerating things like different date formats, different capitalization, and text that wraps across lines. Every JSON value ends up bucketed into one of three outcomes (Matched / Unverifiable / Discrepancy), and finally everything gets written out into one readable Markdown report.

There are three files involved, each with a distinct job:

| File | Job |
| :--- | :--- |
| `auditor.py` | The actual engine: finds file pairs, reads PDFs, compares values, writes the report. Has zero UI code — it can run entirely from a terminal. |
| `auditor_gui.py` | A window (built with a library called `customtkinter`) that lets you click buttons instead of typing commands. It doesn't do any comparing itself — it just calls into `auditor.py` and displays what happens. |
| `setup.py` | Not run by the app itself — it's a build recipe used once, by you, to package everything into the standalone double-clickable `.app`. |

---

## 2. A few terms, explained simply

You don't need a programming background for what follows, but these words come up constantly:

**Function** — a named, reusable block of code that does one job. You "call" it by name, optionally hand it some input, and it optionally hands you back a result. Think of it like a recipe: you give it ingredients (its *parameters*), it gives you back a dish (its *return value*).

**Parameter / argument** — the input(s) a function expects. E.g. a function that extracts text from a PDF needs to know *which* PDF — that's its parameter.

**Return value** — what a function hands back once it's done. Some functions return nothing meaningful (they just *do* something, like printing a message); most of the important ones here return data the rest of the program then uses.

**String** — a piece of text, e.g. `"Mario Rossi"`.

**List** — an ordered collection of items, written like `[item1, item2, item3]`. E.g. the list of all mismatches found in a document.

**Dictionary (dict)** — a collection of labeled values, like a small filing system: each value is stored under a label (called a "key"). JSON files are essentially nested dictionaries, which is exactly why the tool can walk through one automatically regardless of what fields it happens to contain.

**Tuple** — a small fixed pair (or group) of values bundled together, e.g. `(field_name, field_value)`. Used here to keep a JSON field's path and its value glued together as one unit inside a list.

**Class / object** — a template for bundling related data and behavior together. `AuditorApp` (the whole GUI window) and `_QueueWriter` (explained later) are both classes.

**Exception / `try`/`except`** — Python's way of handling things that might fail (a corrupt PDF, a malformed date) without crashing the whole program. `try: ... except: ...` means "attempt this; if it blows up, do something sensible instead of dying."

**Regex (regular expression)** — a pattern-matching syntax for text, more flexible than a plain "does this text contain that text" check. Used here to match a value "as a whole word, allowing any amount of whitespace between words, ignoring capitalization" instead of requiring an exact character-for-character match.

---

## 3. `auditor.py` — the engine

This is the file that does all the real work. Nothing in here touches the screen or a window — it's pure logic, which is also why it can be tested and run from a plain terminal command.

### `extract_pdf_text(pdf_path)`

**What it does:** Opens a PDF file and pulls out all of its plain text, page by page, concatenated into one long string.

**Parameter:** `pdf_path` — the file path to a PDF.

**Returns:** A single string containing all the text found in the PDF. If the PDF can't be read for any reason (corrupted file, unsupported format, etc.), it prints an error and returns an empty string instead of crashing the program.

**Used by:** `audit_directory_recursively`, once per PDF, right before that PDF's paired JSON gets compared against it.

---

### `_build_phrase_regex(value_str)`

*(Functions starting with an underscore, like this one, are "internal helpers" — not meant to be called from outside this file, just used by the other functions around them.)*

**What it does:** Takes a JSON value (e.g. `"Mario Rossi"`) and builds a search pattern that will find it inside PDF text even if: the capitalization differs, there's extra/different whitespace or a line break between the words, but *not* if it's just part of a longer word (so searching for `"Italia"` won't wrongly match inside `"Italiana"`).

**Parameter:** `value_str` — the text value to build a search pattern for.

**Returns:** A compiled regex pattern object, ready to search PDF text with — or `None` if the input was empty.

**Used by:** `_value_matches_text`.

---

### `_value_matches_text(pdf_text, value_str)`

**What it does:** The actual "is this value present?" check — builds the flexible pattern (via `_build_phrase_regex`) and searches for it inside the given PDF text.

**Parameters:** `pdf_text` (the full extracted PDF text) and `value_str` (the value being searched for).

**Returns:** `True` if a whole-word, whitespace-tolerant, case-insensitive match was found; `False` otherwise.

**Used by:** `compare_json_with_pdf`, and by `_all_words_present` below (to check each individual word).

---

### `_strip_diacritics(text)`

**What it does:** Removes accent marks and similar diacritics (á→a, í→i, ñ→n, ç→c, and so on), so a name or place spelled with or without its accents in either the JSON or the PDF still counts as the same value. This came directly from testing against real documents: a JSON of `"Maria"` should confidently match a PDF that prints `"María"` — a person looking at that wouldn't consider it a real discrepancy, just a different way of writing the same name, and the tool shouldn't either.

**Parameter:** `text` — any string to strip accents from.

**Returns:** The same text with diacritics removed (a plain string).

**Used by:** `_accent_insensitive_hit` below, and internally by `compare_json_with_pdf` (once per document, to pre-strip the full PDF text — see below).

---

### `_accent_insensitive_hit(pdf_text_stripped, variants)`

**What it does:** The same idea as `_confident_variant_hit` (below), but comparing accent-stripped versions of both the value and the PDF text, so accent-only differences don't prevent a confident Match.

**Parameters:** `pdf_text_stripped` (the PDF text with diacritics already removed) and `variants` (the value's acceptable forms — see `generate_value_variants` below).

**Returns:** `True` if any variant, with its own accents stripped, is found as a whole word in the stripped PDF text; `False` otherwise.

**Used by:** `compare_json_with_pdf`, as one more way (alongside the strict check and the word-order-independent fallback) that a field can reach a confident Match.

---

### `_all_words_present(pdf_text, value_str, min_word_length=3)`

**What it does:** A fallback for multi-word values where the exact phrase never appears together, but every word making it up does appear *somewhere* in the document — just not adjacent, and possibly in a different order. This is what makes the tool robust to documents that, say, print "Cognome" (surname) and "Nome" (given name) as two separate fields in reverse order, while the JSON stores them combined as one "full name" string. Very short words (like "di" or "de") are ignored so they can't produce a false match on their own.

**Parameters:** `pdf_text`, `value_str`, and `min_word_length` (defaults to 3 characters — words shorter than this are skipped).

**Returns:** `True` only if there are at least two significant words *and* every one of them was found individually; `False` otherwise.

**Used by:** `compare_json_with_pdf`, as the second thing tried after an exact phrase match fails.

---

### `_loose_trace_present(pdf_text_lower, variants)`

**What it does:** The weakest, most permissive check — a plain "does this text appear anywhere at all" search, with no word-boundary rules. This is deliberately how the *very first* version of the tool used to match everything (before the tool was made smarter) — which is exactly why it's dangerous to trust on its own; it's the reason "Italia" could wrongly seem to match inside "Italiana". It's kept around, but demoted to a last-resort signal.

**Parameters:** `pdf_text_lower` (the PDF text, already lower-cased) and `variants` (a list of acceptable forms of the value — see `generate_value_variants` below).

**Returns:** `True` if any variant appears anywhere in the text at all, however loosely.

**Used by:** `compare_json_with_pdf`, only as the last check, and its result routes the field to "Unverifiable" rather than "Matched" — because a hit here is a hint, not proof.

---

### `compare_json_with_pdf(json_data, pdf_text)` — the heart of the tool

**What it does:** Walks through every single value inside a JSON document (however deeply nested it is) and decides, for each one, whether it counts as Matched, Unverifiable, or a Discrepancy against the PDF text. It contains two small helper functions defined *inside* it:

- **`generate_value_variants(value_str)`** — for a given value, produces a list of acceptable alternate forms it's also willing to accept as a match. It knows a few kinds of variation: numbers (tries European `1.234,56` and alternate `1.234.56` formatting; for whole numbers, also tries the bare integer with no decimals at all, since round percentages and totals are often printed as `100%` rather than `100,00%`; and for values with more than 2 decimal places — e.g. an investment fund's number of shares, `0.685843` — also tries a variant that preserves the value's full original precision, since forcing the usual 2-decimal currency rounding there would turn it into `0,69` and it would never match) and ISO dates like `2026-08-04` (tries `04/08/2026` and `04-08-2026`). Anything that isn't a number or a date just gets itself back as the only "variant."
- **`search_recursive(obj, path="")`** — the actual recursion. JSON can nest dictionaries inside lists inside dictionaries arbitrarily deep; this function keeps calling itself on whatever it finds until it reaches an actual value (a string, number, etc.), at which point it runs the matching checks and records the outcome. `path` is how it builds a human-readable trail like `person.address.city` so the final report can tell you exactly *where* in the JSON a problem was found, not just that "something" was wrong.

For each actual value found, a Match can be reached three ways: an exact-ish match (`_value_matches_text` across all variants), the word-order-independent fallback (`_all_words_present`), or the accent-insensitive check (`_accent_insensitive_hit`) — if all three fail, it tries the loose trace check (`_loose_trace_present`) and marks it Unverifiable if that hits, otherwise it's a genuine Discrepancy. Boolean-looking values (`"true"`/`"false"`) are skipped entirely, since those are structural flags rather than facts you'd expect to see printed in a PDF.

**One extra rule for very short values:** structured data is full of short internal codes — a `"clave"` of `"A"`, a `"tipo"` of `"3"`. Real-world testing against Spanish tax documents (`data/`) showed this cuts both ways. A bare text hit on something this short is nearly meaningless in one direction — in a document of any real length, a lone letter or digit is overwhelmingly likely to appear *somewhere* by pure coincidence (a lone "A" matched constantly, purely because "a" is a common Spanish word, with zero relation to the actual code being checked) — but the *absence* of a hit is just as unreliable in the other direction: short classification codes are frequently never printed verbatim at all, because the PDF prints a human-readable label instead (a `claveSubclavePercepcion` of `"F1"` is printed as "Cursos, conferencias, obras lit., art. o científicas", never as "F1"), which would otherwise look exactly like a confident Discrepancy for something that was never wrong. So values shorter than `MIN_CONFIDENT_MATCH_LENGTH` (3 characters) are never allowed to reach "Matched" *or* "Discrepancy" — they always land in "Unverifiable," regardless of whether a trace was found. This doesn't change how longer values are judged; a 3+ character value can still confidently land in any of the three outcomes (testing also turned up 3-4 character codes with this same "never printed literally" problem, like `"C13"` or `"0521"` — but genuine facts of that same length, like cadastral parcel numbers, are correctly confirmed elsewhere in the same documents, so the length-based rule intentionally stops at 3 rather than being pushed further, to avoid hiding real errors in those longer codes).

**Parameters:** `json_data` (the parsed JSON — a Python dictionary/list structure) and `pdf_text` (the full extracted PDF text).

**Returns:** Three lists, in this order: `matches`, `mismatches`, `unverifiable`. Each list is full of `(path, value)` pairs, e.g. `("person.name", "Mario Rossi")`.

**Used by:** `audit_directory_recursively`, once per document pair.

---

### `generate_markdown_report(results, reports_dir)`

**What it does:** Takes the results from every document that was audited and writes one Markdown (`.md`) file containing an executive summary, a status table (one row per document), and a detailed breakdown per document listing every discrepancy and every unverifiable field, with a note explaining what each category means and what action to take. For discrepancies whose value is short (`SHORT_CODE_HINT_LENGTH`, 5 characters or fewer), the action text gets an extra sentence explaining that short values are sometimes classification/regime codes the PDF replaces with a descriptive label — the field still shows up as a ❌ Discrepancy (this is a reporting hint only, not a change to how the field was categorized), but with enough context that a reviewer knows to double-check before treating it as a real problem.

**Parameters:** `results` (a list — one entry per document — of dictionaries with keys `name`, `matches`, `mismatches`, `unverifiable`) and `reports_dir` (the folder to save the report into).

**Returns:** The full file path of the report it just wrote (a string).

**Used by:** `audit_directory_recursively`, once, after every document pair has been processed.

---

### `derive_base_key(stem)`

**What it does:** This is what makes "batch mode" possible. PDF/JSON pairs from the source system share a common filename but each has its own 13-character system-generated code tacked onto the end (e.g. `..._W2IWIZ2W_DBS.pdf` and `..._W2IWIZ9C_4US.json`) — so the filenames are *almost* identical but not quite. This function strips that trailing code off so both files reduce to the same "base name," which is then used to pair them up. If a filename is too short to safely strip 13 characters from, it prints a warning and just uses the whole name as-is rather than mangling it.

**Parameter:** `stem` — a filename without its extension (e.g. `report_ABC123` from `report_ABC123.pdf`).

**Returns:** The base name used for pairing (a string).

**Used by:** `audit_directory_recursively`, once per file found.

---

### `audit_directory_recursively(root_dir, reports_dir)` — the conductor

**What it does:** This is the one function everything else in the file exists to support, and the only one called from outside `auditor.py` (both the command-line entry point and the GUI call this directly). Step by step:

1. Walks every file inside `root_dir`, including subfolders, and sorts every `.pdf` and `.json` file it finds into two lookup tables, keyed by their "base name" (via `derive_base_key`). If two different files reduce to the same base name, it prints a warning and keeps only the first one found — rather than silently overwriting or dropping data without telling you.
2. Finds the file names that exist in *both* tables — i.e. the actual pairs.
3. For each pair: extracts the PDF's text (`extract_pdf_text`), loads the JSON, runs the comparison (`compare_json_with_pdf`), and prints a one-line progress summary.
4. Once every pair has been processed, generates the final report (`generate_markdown_report`).

**Parameters:** `root_dir` (the folder to search for PDF/JSON pairs) and `reports_dir` (where to save the generated report).

**Returns:** A tuple of `(results, report_path)` — the full results list described above, and the file path of the generated report. If nothing could be processed (bad folder, no pairs found), it returns `([], None)` instead.

**Used by:** The `if __name__ == "__main__":` block at the very bottom of the file (this is what runs when you launch `auditor.py` directly from a terminal), and by `auditor_gui.py`'s `_run_audit_thread` method (this is what runs when you click "Run Audit" in the app).

---

## 4. `auditor_gui.py` — the window

This file adds a clickable window around `auditor.py`. It deliberately contains no comparison logic of its own — its only job is to collect a folder from you, hand it to `audit_directory_recursively`, and show you what comes back.

### `_QueueWriter` (a small helper class)

**The problem it solves:** Running the audit can take a few seconds, and while it's running, the window must stay responsive (so you can still move/resize it, and so it doesn't look "frozen"). To do that, the audit runs on a separate background thread — a bit like a second worker running in parallel. But there's a rule with this GUI toolkit: only the main thread is allowed to update what's on screen. `auditor.py`'s functions communicate progress the simplest way possible — by using Python's built-in `print()` — and normally `print()` output has nowhere sensible to go once you're inside a window app.

**What it does instead:** `_QueueWriter` is a stand-in for the normal output destination. While the audit is running, the app temporarily redirects `print()` so that anything printed gets pushed onto a thread-safe "queue" (a first-in-first-out waiting line) instead of vanishing. The main thread then checks that queue roughly ten times a second and copies whatever's waiting into the on-screen log box. This lets every existing `print()` statement inside `auditor.py` keep working completely unchanged, while still being thread-safe.

- **`write(text)`** — called automatically every time something would normally be printed; pushes that text onto the queue.
- **`flush()`** — required by Python's rules for anything standing in for normal output, but there's nothing to do here, so it's empty on purpose.

---

### `AuditorApp` (the window itself)

This is the main class — the whole visible application. A few of its methods worth knowing about:

**`_build_layout()`** — builds every visible piece: the title, the "Select Data Folder…" button, the "Run Audit" button, the scrolling log box, and the "Open Report" / "Reveal Reports Folder" buttons at the bottom. Runs once, when the window first opens.

**`_select_folder()`** — opens the native macOS folder picker. Once you pick a folder, it also decides where the report will be saved: a sibling folder next to the one you picked, named `<YourFolderName>_reports`, so reports never get mixed in with your source documents and you always know where to find them.

**`_start_audit()`** — runs when you click "Run Audit." Disables the button (so you can't double-click it mid-run), clears the log, and kicks off `_run_audit_thread` on a background thread.

**`_run_audit_thread()`** — the actual work, running in the background. Redirects `print()` output through `_QueueWriter` for the duration, calls `auditor.audit_directory_recursively(...)` (the exact same function described above — nothing different happens when you use the app versus the terminal), and once it's done, puts a special `"__DONE__"` marker (along with the results) onto the queue so the main thread knows the run has finished.

**`_poll_log_queue()`** — runs automatically about every 100 milliseconds. Drains whatever's waiting in the queue: ordinary text gets appended to the log box; the `"__DONE__"` marker triggers `_on_audit_finished`.

**`_on_audit_finished(results, report_path)`** — re-enables the "Run Audit" button, tallies up the total matched/unverifiable/mismatched counts across every document, displays that summary, and enables the "Open Report" and "Reveal Reports Folder" buttons.

**`_open_report()` / `_reveal_reports_folder()`** — thin wrappers around macOS's built-in `open` command, used to open the finished report (in whatever app handles `.md` files) or reveal the reports folder in Finder.

**`main()`** — creates the window (`AuditorApp()`) and starts it running (`.mainloop()`); this is the single line that actually launches the app. It's called from the very bottom of the file, when you either run `python auditor_gui.py` directly or double-click the packaged `.app`.

---

## 5. `setup.py` — the build recipe (not run by the app)

This file is never executed while you're using the tool — it's a one-time (or once-per-change) recipe you run yourself, from a terminal, to turn the Python source files into the standalone double-clickable `JSON-PDF Compare Tool.app`. It uses a packaging tool called `py2app`.

The important part is the `OPTIONS` dictionary near the top:

- **`packages`** — the external libraries (`pypdf`, `customtkinter`, `darkdetect`) that must be bundled *inside* the app so it works on a Mac with no separate Python install.
- **`includes`** — makes sure `auditor.py` itself gets bundled in (since `auditor_gui.py` imports it).
- **`plist`** — the app's identity: its display name, version number, and unique bundle identifier. This is the *only* place that persists — editing the built app's `Info.plist` directly inside `dist/` does nothing permanent, because every build wipes and fully regenerates `dist/`/`build/` from this file.

Running `python setup.py py2app` (see `buildApp.md` for the exact steps) reads this recipe and produces the finished app in the `dist/` folder.

---

## 6. Quick reference: the three outcomes

| Outcome | Icon | Meaning | What it tells you |
| :--- | :---: | :--- | :--- |
| **Matched** | ✅ | The value (or an equivalent format/spelling of it) was confidently found in the PDF. | No action needed. |
| **Unverifiable** | 🟡 | Only a weak, coincidental trace was found — not a confident match, but not proof of a real error either. | Worth a quick manual glance; may simply not be stated explicitly in the document. |
| **Discrepancy** | ❌ | No trace of the value was found anywhere in the PDF text, in any form. | The strongest signal something may genuinely be wrong — check formatting, truncation, or missing pages. |

# Building the standalone macOS app

`auditor_gui.py` is a small desktop wrapper around `auditor.py`'s audit
engine, built with `customtkinter`. This guide packages it into a
standalone `IRS Audit Tool.app` using [py2app](https://py2app.readthedocs.io/),
so anyone can run it on a Mac **without installing Python**.

> ⚠️ This build must be run **on macOS** — py2app bundles a real macOS
> Python framework into the app and cannot cross-build from another
> platform. Run every step below in a Terminal on your Mac.

## 1. Prerequisites

* macOS
* Python 3.9+ (your existing `venv` works)

If you're on a very new Python version (3.13+) and `py2app` fails to
install or build below, it's likely a compatibility lag — create a fresh
venv on Python 3.11 or 3.12 instead and retry.

## 2. Install build dependencies

```bash
cd json_pdf_compare_tool
source venv/bin/activate
pip install -r requirements.txt
pip install py2app
```

## 3. Build

```bash
rm -rf build dist
python setup.py py2app
```

This creates the app inside `dist/` — look for `IRS Audit Tool.app` (py2app
may name it after the script instead, e.g. `auditor_gui.app`, depending on
version; either way it's the only `.app` under `dist/`).

## 4. Test it standalone

Before distributing, quit Terminal (or at least deactivate the venv) and
double-click the `.app` in Finder directly. Confirm:

* It opens with no Python/Terminal window involved.
* "Select Data Folder…" opens a real folder picker.
* "Run Audit" processes a real PDF/JSON pair and produces a report.
* "Open Report" and "Reveal Reports Folder" both work.

If something fails only in the bundled app (not when running
`python auditor_gui.py` directly), it's usually a missing package —
add it to the `packages` list in `setup.py` and rebuild.

## 5. Package for distribution

Zip it with `ditto` rather than Finder's "Compress" or plain `zip`, so the
app bundle's structure survives intact:

```bash
ditto -c -k --sequesterRsrc --keepParent "dist/IRS Audit Tool.app" "IRS-Audit-Tool.zip"
```

Send `IRS-Audit-Tool.zip` to whoever needs it.

## 6. First-run instructions for recipients

The app isn't signed with an Apple Developer ID (that requires a paid
account), so macOS Gatekeeper will initially block it as being from an
"unidentified developer." This only needs to be done once per Mac:

1. Unzip the file.
2. **Right-click** (or Control-click) `IRS Audit Tool.app` → **Open**.
3. Click **Open** in the confirmation dialog.

If step 2 doesn't offer an "Open" option (recent macOS versions sometimes
hide it on first double-click instead): go to **System Settings → Privacy
& Security**, scroll down to the blocked-app notice, click **Open Anyway**,
then open the app again.

After that first approval, it opens normally like any other app.

# 🛠️ How to Run the App on macOS
Because this is a custom-built internal tool and not distributed through the Mac App Store, macOS Gatekeeper might block it from opening the first time, showing a "damaged" or "unexpectedly quit" error.

To fix this and trust the app locally on your machine, just follow these quick steps:

1. Unzip and move the app
Make sure the JSON-PDF Compare Tool.app is extracted and placed in a stable location (like your Desktop or Applications folder).

2. Open your Terminal
Press Cmd + Space, type Terminal, and hit Enter.

3. Run the following two commands
(Pro tip: Type the command, add a space at the end, and then drag & drop the app into the Terminal to auto-fill the correct file path!)

Clear the Apple quarantine:

```Bash
xattr -cr "/path/to/your/JSON-PDF Compare Tool.app"
```
Sign the app locally:

```Bash
codesign --force --deep -s - "/path/to/your/JSON-PDF Compare Tool.app"
```
Note: You should see a message saying "replacing existing signature".

4. Launch the App
You can now close the Terminal and double-click the app to open it normally. Happy testing!
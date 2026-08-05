"""
py2app build script.

Produces a standalone macOS .app that bundles its own Python interpreter,
so it runs on a Mac with no separate Python install. Must be built ON
macOS (py2app cannot cross-build a Mac app from another platform) — see
buildApp.md for the exact commands to run.
"""

from setuptools import setup

APP = ["auditor_gui.py"]
DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,
    "packages": ["pypdf", "customtkinter", "darkdetect"],
    "includes": ["auditor"],
    "plist": {
        "CFBundleName": "JSON-PDF Compare Tool",
        "CFBundleDisplayName": "JSON-PDF Compare Tool",
        "CFBundleIdentifier": "com.octavirodriguez.jsonpdfcomparetool",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHumanReadableCopyright": "MIT License",
        "NSHighResolutionCapable": True,
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

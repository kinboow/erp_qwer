"""
cx_Freeze MSI build script for ERP Print Client.

Usage:
    python setup_msi.py bdist_msi
"""
import sys
from pathlib import Path
from cx_Freeze import setup, Executable

base_dir = Path(__file__).parent

# Include files to bundle
include_files = [
    (str(base_dir / "logo.ico"), "logo.ico"),
]

# Bundle SumatraPDF installer if present
sumatra_files = list((base_dir / "deps").glob("SumatraPDF-*.exe"))
if sumatra_files:
    include_files.append((str(sumatra_files[0]), sumatra_files[0].name))

build_options = {
    "packages": ["requests", "tkinter", "pystray", "PIL"],
    "includes": ["win32print", "win32api"],
    "include_files": include_files,
    "excludes": ["unittest", "email", "xmlrpc", "http.server"],
}

shortcut_table = [
    (
        "DesktopShortcut",          # Shortcut
        "DesktopFolder",            # Directory
        "ERP\u6253\u5370\u5ba2\u6237\u7aef",  # Name: ERP打印客户端
        "TARGETDIR",                # Component
        "[TARGETDIR]print_client.exe",  # Target
        None,                       # Arguments
        None,                       # Description
        None,                       # Hotkey
        "[TARGETDIR]logo.ico",      # Icon
        None,                       # IconIndex
        None,                       # ShowCmd
        "TARGETDIR",                # WkDir
    ),
    (
        "StartMenuShortcut",
        "StartMenuFolder",
        "ERP\u6253\u5370\u5ba2\u6237\u7aef",
        "TARGETDIR",
        "[TARGETDIR]print_client.exe",
        None, None, None,
        "[TARGETDIR]logo.ico",
        None, None, "TARGETDIR",
    ),
]

msi_data = {
    "Shortcut": shortcut_table,
}

bdist_msi_options = {
    "data": msi_data,
    "install_icon": str(base_dir / "logo.ico"),
    "upgrade_code": "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}",
}

exe = Executable(
    script=str(base_dir / "print_client.py"),
    base="Win32GUI",
    target_name="print_client.exe",
    icon=str(base_dir / "logo.ico"),
    shortcut_name="ERP\u6253\u5370\u5ba2\u6237\u7aef",
    shortcut_dir="DesktopFolder",
)

setup(
    name="ERP-PrintClient",
    version="1.0.0",
    description="ERP Print Client",
    options={
        "build_exe": build_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=[exe],
)

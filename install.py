#!/usr/bin/env python3
"""EDK_AI — Cross-Platform One-Command Installer.

Usage:
    python3 -c "$(curl -fsSL https://raw.githubusercontent.com/edkai/edkai/main/install.py)"
    python3 install.py
    python3 install.py --dev    # Install from current directory (local dev)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

TS_VERSION = "0.3.0"
TS_REPO = "https://github.com/edkai/edkai.git"
TS_DIR = Path.home() / ".local" / "share" / "edkai"
BIN_DIR = Path.home() / ".local" / "bin"


def banner() -> None:
    print(
        """
╔══════════════════════════════════════════════════════════╗
║            Cross-Platform Installer                      ║
╚══════════════════════════════════════════════════════════╝
"""
    )


def check_python() -> str:
    """Verify Python >= 3.9 is available."""
    print("[INFO] Checking Python...")
    py = sys.executable
    version = sys.version_info
    if version < (3, 9):
        print(f"[ERROR] Python >= 3.9 required, found {version.major}.{version.minor}")
        sys.exit(1)
    print(f"[OK] Python {version.major}.{version.minor}.{version.micro}")
    return py


def check_pip(py: str) -> None:
    """Verify pip is available."""
    print("[INFO] Checking pip...")
    try:
        subprocess.run([py, "-m", "pip", "--version"], check=True, capture_output=True)
    except Exception:
        print("[ERROR] pip not found. Run: python3 -m ensurepip --upgrade")
        sys.exit(1)
    print("[OK] pip OK")


def clone_or_update(dev_mode: bool) -> Path:
    """Clone repo or use local directory."""
    if dev_mode:
        cwd = Path.cwd()
        if (cwd / "edkai" / "main.py").exists():
            print(f"[INFO] Local dev install from {cwd}")
            return cwd
        print("[ERROR] --dev specified but edkai/main.py not found in current directory")
        sys.exit(1)

    print(f"[INFO] Installing EDK_AI v{TS_VERSION}...")
    if TS_DIR.exists() and (TS_DIR / ".git").exists():
        print("[INFO] Existing installation found, updating...")
        subprocess.run(["git", "-C", str(TS_DIR), "pull", "--ff-only"], capture_output=True)
    else:
        print("[INFO] Cloning repository...")
        if TS_DIR.exists():
            shutil.rmtree(TS_DIR)
        TS_DIR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", TS_REPO, str(TS_DIR)],
            check=True,
        )
    return TS_DIR


def install_deps(py: str, src: Path) -> None:
    """Install Python dependencies and package."""
    print("[INFO] Installing dependencies...")
    subprocess.run([py, "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([py, "-m", "pip", "install", "-e", str(src)], check=True)
    print("[OK] Dependencies installed")


def ensure_path(py: str) -> None:
    """Ensure edkai command is available."""
    print("[INFO] Ensuring edkai is in PATH...")
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    # Check if edkai is already available
    if shutil.which("edkai"):
        print("[OK] edkai command found")
        return

    # Create wrapper script
    is_win = platform.system() == "Windows"
    if is_win:
        wrapper = BIN_DIR / "edkai.bat"
        wrapper.write_text(f'@echo off\n"{py}" -m edkai %*\n')
    else:
        wrapper = BIN_DIR / "edkai"
        wrapper.write_text(f'#!/usr/bin/env bash\nexec "{py}" -m edkai "$@"\n')
        wrapper.chmod(0o755)

    print(f"[OK] Wrapper created at {wrapper}")

    # Add to PATH in shell config
    if not is_win:
        shell_rc: Path | None = None
        if Path.home().joinpath(".zshrc").exists():
            shell_rc = Path.home() / ".zshrc"
        elif Path.home().joinpath(".bashrc").exists():
            shell_rc = Path.home() / ".bashrc"

        if shell_rc:
            content = shell_rc.read_text()
            if str(BIN_DIR) not in content:
                with shell_rc.open("a") as f:
                    f.write(f'\nexport PATH="{BIN_DIR}:$PATH"\n')
                print(f"[WARN] Added {BIN_DIR} to PATH in {shell_rc}")
                print(f"[WARN] Please run: source {shell_rc}  (or restart terminal)")

    # Add to current session PATH
    os.environ["PATH"] = f"{BIN_DIR}{os.pathsep}{os.environ.get('PATH', '')}"


def verify_install() -> None:
    """Verify edkai works."""
    print("[INFO] Verifying installation...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "edkai", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print(f"[OK] {result.stdout.strip()}")
        else:
            print(f"[WARN] Version check failed: {result.stderr.strip()}")
    except Exception as exc:
        print(f"[WARN] Could not verify: {exc}")


def print_done() -> None:
    print(
        """
╔══════════════════════════════════════════════════════════╗
║              Installation Complete!                      ║
╚══════════════════════════════════════════════════════════╝

Usage:
  edkai                          # Launch IDE
  edkai /path/to/project         # Open project
  edkai scan <url>               # Security scan
  edkai --version                # Version

Key IDE Bindings:
  Ctrl+O        Open file
  Ctrl+P        Quick open
  Ctrl+G        AI generate from comment
  Ctrl+Space    Ghost text (AI autocomplete)
  Ctrl+Shift+X  Security scanner panel
  Ctrl+Shift+T  Test panel
  F1            Natural language command palette

Security CLI:
  edkai scan https://example.com

Config: ~/.config/edkai/config.json
"""
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="EDK_AI Cross-Platform Installer",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Install from current directory (development mode)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show installer version and exit",
    )
    args = parser.parse_args()

    if args.version:
        print(f"EDK_AI Installer v{TS_VERSION}")
        sys.exit(0)

    banner()
    py = check_python()
    check_pip(py)
    src = clone_or_update(args.dev)
    install_deps(py, src)
    ensure_path(py)
    verify_install()
    print_done()


if __name__ == "__main__":
    main()

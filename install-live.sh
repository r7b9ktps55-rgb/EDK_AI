#!/usr/bin/env bash
# EDK_AI v4 — Self-Contained Installer
# Downloads and installs from live deployment (no GitHub required)
# Usage: curl -fsSL https://dufvuralvq3zm.kimi.page/install-live.sh | bash

set -euo pipefail

TS_URL="https://dufvuralvq3zm.kimi.page/project.tar.gz"
TS_DIR="${HOME}/.local/share/edkai"
TS_STAGE="${HOME}/.local/share/edkai-stage"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

print_banner() {
    echo -e "${CYAN}"
    cat <<'EOF'
╔══════════════════════════════════════════════════════════╗
║            One-Command Installer                         ║
╚══════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

check_python() {
    log_info "Checking Python..."
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        log_err "Python 3 not found. Please install Python >= 3.9"
        exit 1
    fi
    if ! $PYTHON -c 'import sys; exit(0 if sys.version_info >= (3,9) else 1)'; then
        log_err "Python >= 3.9 required"
        exit 1
    fi
    PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log_ok "Python $PY_VERSION OK"
}

check_tools() {
    log_info "Checking curl / tar / pip..."
    if ! command -v curl &>/dev/null; then
        log_err "curl not found. Install curl first."
        exit 1
    fi
    if ! command -v tar &>/dev/null; then
        log_err "tar not found. Install tar first."
        exit 1
    fi
    if ! $PYTHON -m pip --version &>/dev/null; then
        log_err "pip not found. Run: $PYTHON -m ensurepip --upgrade"
        exit 1
    fi
    log_ok "All tools present"
}

download_and_extract() {
    log_info "Downloading EDK_AI v4 (~1MB)..."
    rm -rf "$TS_STAGE"
    mkdir -p "$TS_STAGE"
    local tarball="$TS_STAGE/project.tar.gz"
    curl -fsSL "$TS_URL" -o "$tarball"
    log_ok "Download complete ($(du -h "$tarball" | cut -f1))"
    log_info "Extracting..."
    tar xzf "$tarball" -C "$TS_STAGE"
    mv "$TS_STAGE/project" "$TS_DIR"
    rm -rf "$TS_STAGE"
    log_ok "Extracted to $TS_DIR"
}

install_package() {
    log_info "Installing Python dependencies..."
    cd "$TS_DIR"
    $PYTHON -m pip install --upgrade pip -q
    $PYTHON -m pip install -e "." -q
    log_ok "Package installed"
}

ensure_path() {
    local bin_dir="$HOME/.local/bin"
    mkdir -p "$bin_dir"
    if ! command -v edkai &>/dev/null; then
        log_info "Creating edkai wrapper..."
        cat > "$bin_dir/edkai" <<EOF
#!/usr/bin/env bash
exec $PYTHON -m edkai "\$@"
EOF
        chmod +x "$bin_dir/edkai"
    fi
    # Add to PATH in shell config
    local shell_rc=""
    if [ -f "$HOME/.zshrc" ]; then shell_rc="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then shell_rc="$HOME/.bashrc"
    fi
    if [ -n "$shell_rc" ] && ! grep -q "\.local/bin" "$shell_rc" 2>/dev/null; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_rc"
        log_warn "Added ~/.local/bin to PATH in $shell_rc"
        log_warn "Run: source $shell_rc   (or restart terminal)"
    fi
    log_ok "edkai command ready"
}

verify() {
    log_info "Verifying installation..."
    if $PYTHON -m edkai --version &>/dev/null; then
        local ver=$($PYTHON -m edkai --version 2>/dev/null)
        log_ok "$ver installed successfully!"
    else
        log_warn "Version check failed, but installation may still work"
    fi
}

print_done() {
    echo -e "${GREEN}"
    cat <<EOF

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
  Ctrl+P        Quick open / Fuzzy search
  Ctrl+G        AI generate from comment
  Ctrl+Space    Ghost text (AI autocomplete)
  Ctrl+Shift+X  Security scanner panel
  Ctrl+Shift+T  Test panel
  F1            Natural language command palette

Security CLI:
  edkai scan https://example.com

Config: ~/.config/edkai/config.json
EOF
    echo -e "${NC}"
}

main() {
    print_banner
    check_python
    check_tools
    download_and_extract
    install_package
    ensure_path
    verify
    print_done
}

main "$@"

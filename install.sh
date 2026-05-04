#!/usr/bin/env bash
# EDK_AI v5 — Universal AI Code Agent
# One-Command Installer
set -euo pipefail

TS_VERSION="0.5.0"
TS_REPO="https://github.com/r7b9ktps55-rgb/tstudio.git"
TS_DIR="${HOME}/.local/share/edkai"

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
║     EDK_AI v5 — Universal AI Code Agent        ║
║     Free AI · Agent Mode · Skills System · TUI IDE      ║
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
    PY_VERSION=$($PYTHON -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if ! $PYTHON -c 'import sys; exit(0 if sys.version_info >= (3,9) else 1)'; then
        log_err "Python >= 3.9 required, found $PY_VERSION"
        exit 1
    fi
    log_ok "Python $PY_VERSION OK"
}

clone_or_update() {
    if [ -d "$TS_DIR/.git" ]; then
        log_info "Updating existing installation..."
        cd "$TS_DIR"
        git pull --ff-only || true
    else
        log_info "Cloning EDK_AI v${TS_VERSION}..."
        rm -rf "$TS_DIR"
        git clone --depth 1 "$TS_REPO" "$TS_DIR"
    fi
}

install_deps() {
    log_info "Installing dependencies..."
    cd "$TS_DIR"
    $PYTHON -m pip install --upgrade pip -q
    $PYTHON -m pip install -e "." -q
}

ensure_path() {
    local bin_dir="$HOME/.local/bin"
    mkdir -p "$bin_dir"
    if ! command -v edkai &>/dev/null; then
        cat > "$bin_dir/edkai" <<EOF
#!/usr/bin/env bash
exec $PYTHON -m edkai "\$@"
EOF
        chmod +x "$bin_dir/edkai"
    fi
    local shell_rc=""
    if [ -n "${ZSH_VERSION:-}" ] || [ -f "$HOME/.zshrc" ]; then
        shell_rc="$HOME/.zshrc"
    elif [ -n "${BASH_VERSION:-}" ] || [ -f "$HOME/.bashrc" ]; then
        shell_rc="$HOME/.bashrc"
    fi
    if [ -n "$shell_rc" ] && [ -f "$shell_rc" ]; then
        if ! grep -q "\.local/bin" "$shell_rc" 2>/dev/null; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_rc"
            log_warn "Please run: source $shell_rc (or restart terminal)"
        fi
    fi
}

main() {
    print_banner
    check_python
    clone_or_update
    install_deps
    ensure_path
    log_ok "EDK_AI v${TS_VERSION} installed!"
    echo ""
    echo "Usage:"
    echo "  edkai                    # Launch TUI IDE"
    echo "  edkai /path/to/project   # Open project"
    echo "  edkai --agent            # Launch AI agent"
    echo "  edkai config --test      # Test AI connection"
    echo ""
    echo "Free AI Providers:"
    echo "  • GitHub Models (phi-4, Llama, Mistral) — 150 req/day free"
    echo "  • Ollama (local) — run models on your machine"
    echo "  • Google Gemini — 60 req/min free tier"
    echo ""
    echo "Config: ~/.config/edkai/config.json"
}

main "$@"

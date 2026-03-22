#!/usr/bin/env bash
set -euo pipefail

echo "================================================="
echo " Devcontainer postCreate"
echo "================================================="

# --- Sanity checks ---------------------------------------------------------

echo "User: $(whoami)"
echo "Home: $HOME"

# Docker (via docker-outside-of-docker)
echo "==> Checking Docker access"
if docker version >/dev/null 2>&1; then
  echo "Docker: OK"
else
  echo "WARNING: Docker not accessible from container"
fi

# Python
echo "==> Checking Python"
python --version

# Node
echo "==> Checking Node"
node --version
npm --version

# --- System dependencies ---------------------------------------------------

echo "==> Installing system dependencies (mpv, ffmpeg, Qt runtime libs)"
packages=(
  mpv
  ffmpeg
  libgl1
  libegl1
  libxkbcommon0
  libxkbcommon-x11-0
  libxcb-cursor0
  libxcb-icccm4
  libxcb-keysyms1
  libxcb-shape0
  libxcb-xkb1
  libdbus-1-3
  libglib2.0-0
  yt-dlp
)

missing_packages=()
for pkg in "${packages[@]}"; do
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    missing_packages+=("$pkg")
  fi
done

if [ "${#missing_packages[@]}" -gt 0 ]; then
  sudo apt-get update
  sudo apt-get install -y "${missing_packages[@]}"
else
  echo "System packages already installed"
fi

# --- Python dependencies ---------------------------------------------------

echo "==> Skipping Python dependency install (use scripts to install on demand)"

# --- Install AI CLIs --------------------------------------------------------

echo "==> Installing Claude Code (Anthropic CLI)"
if ! command -v claude >/dev/null 2>&1; then
  npm install -g @anthropic-ai/claude-code
else
  echo "Claude Code already installed"
fi

echo "==> Installing OpenAI / Codex CLI"
if ! command -v openai >/dev/null 2>&1; then
  npm install -g @openai/codex
else
  echo "OpenAI CLI already installed"
fi

# --- Verify installs --------------------------------------------------------

echo "==> Verifying AI CLIs"
claude --version || echo "Claude CLI installed but not yet authenticated"
openai --version || echo "OpenAI CLI installed but not yet authenticated"

# --- Friendly auth reminder ------------------------------------------------

echo ""
echo "-------------------------------------------------"
echo " Next steps (one-time per machine):"
echo ""
echo "  • Sign in to Claude Code:"
echo "      claude auth login"
echo ""
echo "  • Sign in to OpenAI / Codex:"
echo "      openai auth login"
echo ""
echo " Credentials are stored in your persisted home"
echo " volume (not tracked by git)."
echo "-------------------------------------------------"

echo "postCreate complete"

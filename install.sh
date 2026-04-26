#!/usr/bin/env bash
set -euo pipefail

# check Python 3.9+
if ! command -v python3 &>/dev/null; then
    echo "error: python3 is not installed. Install Python 3.9 or later and try again." >&2
    exit 1
fi

version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
major=$(echo "$version" | cut -d. -f1)
minor=$(echo "$version" | cut -d. -f2)

if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 9 ]; }; then
    echo "error: Python 3.9 or later is required (found Python $version)." >&2
    exit 1
fi

echo "Python $version found."

# install
if command -v pip3 &>/dev/null; then
    PIP=pip3
elif python3 -m pip --version &>/dev/null 2>&1; then
    PIP="python3 -m pip"
else
    echo "error: pip is not installed. Install pip and try again." >&2
    exit 1
fi

echo "installing autodeploy..."
$PIP install --quiet autodeploy

echo ""
echo "done. next step:"
echo "  cd /path/to/your/repo && autodeploy init"

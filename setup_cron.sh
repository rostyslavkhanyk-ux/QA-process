#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Brighterly QA Agent — macOS Launch Agent Setup
# Runs qa_agent.py every day at 08:00 Kyiv time (UTC+3 = 05:00 UTC)
#
# Usage:
#   chmod +x setup_cron.sh
#   ./setup_cron.sh install    # install and activate cron
#   ./setup_cron.sh uninstall  # remove cron
#   ./setup_cron.sh status     # check if loaded
# ─────────────────────────────────────────────────────────────────────────────

PLIST_LABEL="com.brighterly.qa-agent"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$(which python3)"
LOG_DIR="${SCRIPT_DIR}/logs"

mkdir -p "${LOG_DIR}"

install() {
    echo "Installing Brighterly QA Agent cron..."

    if [ -z "${ANTHROPIC_API_KEY}" ]; then
        echo "ERROR: ANTHROPIC_API_KEY is not set."
        echo "Set it in your shell profile before running:"
        echo "  export ANTHROPIC_API_KEY=sk-ant-..."
        exit 1
    fi

    cat > "${PLIST_PATH}" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${SCRIPT_DIR}/qa_agent.py</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>ANTHROPIC_API_KEY</key>
        <string>${ANTHROPIC_API_KEY}</string>
        <key>GOOGLE_APPLICATION_CREDENTIALS</key>
        <string>/Users/rostyslav.khanyk/Desktop/MD files /gcp-key.json</string>
    </dict>

    <!-- 08:00 Kyiv time = 05:00 UTC -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/qa_agent.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/qa_agent_err.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

    launchctl unload "${PLIST_PATH}" 2>/dev/null || true
    launchctl load -w "${PLIST_PATH}"

    echo "✓ Installed: ${PLIST_LABEL}"
    echo "✓ Runs daily at 08:00 local time (ensure system timezone = Kyiv)"
    echo "✓ Logs: ${LOG_DIR}/qa_agent.log"
    echo ""
    echo "To run immediately for testing:"
    echo "  launchctl start ${PLIST_LABEL}"
}

uninstall() {
    echo "Removing Brighterly QA Agent cron..."
    launchctl unload "${PLIST_PATH}" 2>/dev/null || true
    rm -f "${PLIST_PATH}"
    echo "✓ Removed."
}

status() {
    if launchctl list | grep -q "${PLIST_LABEL}"; then
        echo "✓ Running: ${PLIST_LABEL}"
        launchctl list "${PLIST_LABEL}" 2>/dev/null
    else
        echo "✗ Not loaded: ${PLIST_LABEL}"
        [ -f "${PLIST_PATH}" ] && echo "  Plist exists but not loaded: ${PLIST_PATH}"
    fi
}

case "${1}" in
    install)   install ;;
    uninstall) uninstall ;;
    status)    status ;;
    *)
        echo "Usage: $0 {install|uninstall|status}"
        echo ""
        echo "Before installing, set your API key:"
        echo "  export ANTHROPIC_API_KEY=sk-ant-..."
        echo "  ./setup_cron.sh install"
        exit 1
        ;;
esac

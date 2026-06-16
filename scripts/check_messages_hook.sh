#!/bin/bash
# Agent Hub Message Check Hook
#
# This hook checks for pending messages from other agents when you submit a prompt.
# Install by adding to ~/.claude/settings.json under "hooks"
#
# Configuration:
#   AGENT_HUB_URL - URL of the hub server (default: http://localhost:8765)
#   AGENT_ID - Your agent ID (default: read from ~/.projectz.yaml)

AGENT_HUB_URL="${AGENT_HUB_URL:-http://localhost:8765}"

# Get agent ID from projectz config
get_agent_id() {
    if [ -f ~/.projectz.yaml ]; then
        grep "^computer_id:" ~/.projectz.yaml | cut -d: -f2 | tr -d ' '
    else
        # Fallback: get MAC address
        if [[ "$OSTYPE" == "darwin"* ]]; then
            ifconfig en0 | grep ether | awk '{print $2}' | tr -d ':'
        else
            cat /sys/class/net/eth0/address 2>/dev/null | tr -d ':'
        fi
    fi
}

AGENT_ID=$(get_agent_id)

# Check for pending messages
check_pending() {
    response=$(curl -s --connect-timeout 2 "${AGENT_HUB_URL}/messages/${AGENT_ID}/pending" 2>/dev/null)

    if [ $? -ne 0 ]; then
        # Hub not reachable, silently skip
        return
    fi

    pending=$(echo "$response" | grep -o '"pending":[0-9]*' | cut -d: -f2)

    if [ -n "$pending" ] && [ "$pending" -gt 0 ]; then
        echo ""
        echo "=========================================="
        echo "  You have $pending message(s) from other agents"
        echo "  Ask me to 'check messages' to read them"
        echo "=========================================="
        echo ""
    fi
}

check_pending

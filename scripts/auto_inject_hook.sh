#!/bin/bash
# Agent Hub Auto-Inject Hook
#
# This hook runs on every prompt submission and injects pending messages
# into the conversation so the agent can address them naturally.
#
# Install via ~/.claude/settings.json under "hooks.UserPromptSubmit"

AGENT_HUB_URL="${AGENT_HUB_URL:-http://localhost:8765}"

# Get computer ID (MAC address)
get_computer_id() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        ifconfig en0 | grep ether | awk '{print $2}' | tr -d ':'
    else
        # Try common Linux network interfaces
        for iface in eth0 enp0s3 wlan0 ens33; do
            if [ -f "/sys/class/net/${iface}/address" ]; then
                cat "/sys/class/net/${iface}/address" 2>/dev/null | tr -d ':'
                return
            fi
        done
        # Last resort: first non-lo interface
        ip link | grep -v 'lo:' | grep 'link/ether' | head -1 | awk '{print $2}' | tr -d ':'
    fi
}

COMPUTER_ID=$(get_computer_id)

# Check for pending messages (with short timeout to not slow down prompts)
# Use computer-based endpoint to get messages for all sessions on this machine
response=$(curl -s --connect-timeout 1 --max-time 2 "${AGENT_HUB_URL}/messages/computer/${COMPUTER_ID}" 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$response" ] || [ "$response" = "[]" ]; then
    # No messages or hub not reachable - exit silently
    exit 0
fi

# Parse messages and format for injection
message_count=$(echo "$response" | python3 -c "import sys,json; msgs=json.load(sys.stdin); print(len(msgs))" 2>/dev/null)

if [ -z "$message_count" ] || [ "$message_count" = "0" ]; then
    exit 0
fi

# Format messages for the agent
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  📬 INCOMING MESSAGES FROM OTHER AGENTS                          ║"
echo "╠══════════════════════════════════════════════════════════════════╣"

echo "$response" | python3 -c "
import sys, json
from datetime import datetime

msgs = json.load(sys.stdin)
for msg in msgs:
    sender = msg.get('from_name', 'Unknown')
    content = msg.get('content', '')
    msg_id = msg.get('id', '?')
    ts = msg.get('timestamp', '')[:16].replace('T', ' ')
    is_reply = ' (reply)' if msg.get('reply_to') else ''
    to_agent = msg.get('to_agent', '')
    session = to_agent.split(':')[1][:8] if ':' in to_agent else '?'

    print(f'║  [{msg_id}] From: {sender}{is_reply} → session:{session}')
    print(f'║  Time: {ts}')
    print(f'║  Message: {content[:60]}...' if len(content) > 60 else f'║  Message: {content}')
    print('║  ─────────────────────────────────────────────────────────────')
"

echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "Please address these messages. Use 'reply' tool to respond, or 'mark_read' to dismiss."
echo ""

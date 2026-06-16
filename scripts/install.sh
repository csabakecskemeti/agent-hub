#!/bin/bash
# Agent Hub Installation Script
#
# This script installs the MCP tools and hook for Claude Code.
# Run on each machine that should be able to communicate.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
AGENT_HUB_URL="${AGENT_HUB_URL:-http://localhost:8765}"

echo "=== Agent Hub Installation ==="
echo ""

# 1. Install Python dependencies
echo "[1/4] Installing Python dependencies..."
pip install -r "$PROJECT_DIR/requirements.txt" --quiet

# 2. Create MCP config for Claude Code
echo "[2/4] Configuring MCP tools..."

CLAUDE_CONFIG_DIR="$HOME/.claude"
mkdir -p "$CLAUDE_CONFIG_DIR"

# Check if settings.json exists and has mcpServers
SETTINGS_FILE="$CLAUDE_CONFIG_DIR/settings.json"

if [ -f "$SETTINGS_FILE" ]; then
    # Backup existing config
    cp "$SETTINGS_FILE" "$SETTINGS_FILE.backup"
    echo "  Backed up existing settings to settings.json.backup"
fi

# Create or update MCP server config
# Note: This creates a standalone config that needs to be merged manually
MCP_CONFIG=$(cat <<EOF
{
  "mcpServers": {
    "agent-hub": {
      "command": "python",
      "args": ["$PROJECT_DIR/src/mcp_tools.py"],
      "env": {
        "AGENT_HUB_URL": "$AGENT_HUB_URL"
      }
    }
  }
}
EOF
)

echo "$MCP_CONFIG" > "$CLAUDE_CONFIG_DIR/agent-hub-mcp.json"
echo "  Created $CLAUDE_CONFIG_DIR/agent-hub-mcp.json"
echo ""
echo "  Add this to your ~/.claude/settings.json mcpServers section:"
echo '  "agent-hub": {'
echo '    "command": "python",'
echo "    \"args\": [\"$PROJECT_DIR/src/mcp_tools.py\"],"
echo '    "env": {'
echo "      \"AGENT_HUB_URL\": \"$AGENT_HUB_URL\""
echo '    }'
echo '  }'

# 3. Install hook
echo ""
echo "[3/4] Installing message check hook..."

HOOKS_DIR="$CLAUDE_CONFIG_DIR/hooks"
mkdir -p "$HOOKS_DIR"

cp "$PROJECT_DIR/scripts/check_messages_hook.sh" "$HOOKS_DIR/agent-hub-check.sh"
chmod +x "$HOOKS_DIR/agent-hub-check.sh"
echo "  Installed hook to $HOOKS_DIR/agent-hub-check.sh"
echo ""
echo "  Add this to your ~/.claude/settings.json hooks section:"
echo '  "hooks": {'
echo '    "PreToolUse": ['
echo '      {'
echo '        "matcher": "Bash",'
echo "        \"hooks\": [\"$HOOKS_DIR/agent-hub-check.sh\"]"
echo '      }'
echo '    ]'
echo '  }'

# 4. Register with hub
echo ""
echo "[4/4] Registering with hub..."

# Get agent info
if [ -f ~/.projectz.yaml ]; then
    AGENT_ID=$(grep "^computer_id:" ~/.projectz.yaml | cut -d: -f2 | tr -d ' ')
    AGENT_NAME=$(grep "^computer_name:" ~/.projectz.yaml | cut -d: -f2 | tr -d ' ')
else
    if [[ "$OSTYPE" == "darwin"* ]]; then
        AGENT_ID=$(ifconfig en0 | grep ether | awk '{print $2}' | tr -d ':')
    else
        AGENT_ID=$(cat /sys/class/net/eth0/address 2>/dev/null | tr -d ':')
    fi
    AGENT_NAME=$(hostname)
fi

echo "  Agent ID: $AGENT_ID"
echo "  Agent Name: $AGENT_NAME"

# Try to register (will fail if hub not running, that's ok)
curl -s -X POST "$AGENT_HUB_URL/agents/register" \
    -H "Content-Type: application/json" \
    -d "{\"id\": \"$AGENT_ID\", \"name\": \"$AGENT_NAME\"}" \
    --connect-timeout 2 > /dev/null 2>&1 && \
    echo "  Registered with hub" || \
    echo "  Hub not reachable (will register when first used)"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. Start the hub server: python src/server.py --port 8765"
echo "2. Add MCP config to ~/.claude/settings.json"
echo "3. Restart Claude Code"
echo "4. Try: list_agents, send_message, check_messages"

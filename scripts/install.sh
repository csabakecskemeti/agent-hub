#!/bin/bash
# Agent Hub Installation Script
#
# This script installs the MCP tools and hook for Claude Code.
# Run on each machine that should be able to communicate.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration - set your hub URL here or via environment variable
AGENT_HUB_URL="${AGENT_HUB_URL:-http://localhost:8765}"

echo "=== Agent Hub Installation ==="
echo ""
echo "Project directory: $PROJECT_DIR"
echo "Hub URL: $AGENT_HUB_URL"
echo ""

# 1. Create Python virtual environment and install dependencies
echo "[1/4] Setting up Python environment..."

if [ ! -d "$PROJECT_DIR/venv" ]; then
    python3 -m venv "$PROJECT_DIR/venv"
    echo "  Created virtual environment"
fi

"$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --quiet
echo "  Installed dependencies"

# 2. Configure MCP server in ~/.claude.json
echo ""
echo "[2/4] Configuring MCP server..."

CLAUDE_JSON="$HOME/.claude.json"

if [ -f "$CLAUDE_JSON" ]; then
    # Backup existing config
    cp "$CLAUDE_JSON" "$CLAUDE_JSON.backup"
    echo "  Backed up existing ~/.claude.json"

    # Check if it already has mcpServers
    if grep -q '"mcpServers"' "$CLAUDE_JSON"; then
        echo ""
        echo "  ~/.claude.json already has mcpServers configured."
        echo "  Please manually add the agent-hub entry:"
        echo ""
        echo '  "agent-hub": {'
        echo '    "command": "python3",'
        echo "    \"args\": [\"$PROJECT_DIR/src/mcp_tools.py\"],"
        echo '    "env": {'
        echo "      \"AGENT_HUB_URL\": \"$AGENT_HUB_URL\""
        echo '    }'
        echo '  }'
    else
        # File exists but no mcpServers - need manual merge
        echo "  Please add mcpServers section to ~/.claude.json (see below)"
    fi
else
    # Create new ~/.claude.json
    cat > "$CLAUDE_JSON" << EOF
{
  "mcpServers": {
    "agent-hub": {
      "command": "python3",
      "args": ["$PROJECT_DIR/src/mcp_tools.py"],
      "env": {
        "AGENT_HUB_URL": "$AGENT_HUB_URL"
      }
    }
  }
}
EOF
    echo "  Created ~/.claude.json with MCP configuration"
fi

# 3. Configure hook in ~/.claude/settings.json
echo ""
echo "[3/4] Configuring auto-inject hook..."

SETTINGS_DIR="$HOME/.claude"
SETTINGS_FILE="$SETTINGS_DIR/settings.json"

mkdir -p "$SETTINGS_DIR"

# Update AGENT_HUB_URL in the hook script
sed -i.bak "s|AGENT_HUB_URL=\"\${AGENT_HUB_URL:-http://localhost:8765}\"|AGENT_HUB_URL=\"\${AGENT_HUB_URL:-$AGENT_HUB_URL}\"|" "$PROJECT_DIR/scripts/auto_inject_hook.sh"
rm -f "$PROJECT_DIR/scripts/auto_inject_hook.sh.bak"

if [ -f "$SETTINGS_FILE" ]; then
    cp "$SETTINGS_FILE" "$SETTINGS_FILE.backup"
    echo "  Backed up existing ~/.claude/settings.json"

    if grep -q '"hooks"' "$SETTINGS_FILE"; then
        echo ""
        echo "  ~/.claude/settings.json already has hooks configured."
        echo "  Please manually add the UserPromptSubmit hook:"
        echo ""
        echo '  "UserPromptSubmit": ['
        echo '    {'
        echo '      "matcher": "",'
        echo '      "hooks": ['
        echo '        {'
        echo '          "type": "command",'
        echo "          \"command\": \"$PROJECT_DIR/scripts/auto_inject_hook.sh\","
        echo '          "timeout": 3'
        echo '        }'
        echo '      ]'
        echo '    }'
        echo '  ]'
    else
        # File exists but no hooks - need manual merge
        echo "  Please add hooks section to ~/.claude/settings.json (see below)"
    fi
else
    # Create new settings.json
    cat > "$SETTINGS_FILE" << EOF
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "$PROJECT_DIR/scripts/auto_inject_hook.sh",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
EOF
    echo "  Created ~/.claude/settings.json with hook configuration"
fi

# 4. Test hub connectivity
echo ""
echo "[4/4] Testing hub connectivity..."

if curl -s --connect-timeout 2 "$AGENT_HUB_URL/agents" > /dev/null 2>&1; then
    echo "  Hub is reachable at $AGENT_HUB_URL"
else
    echo "  Hub not reachable at $AGENT_HUB_URL"
    echo "  Make sure the hub server is running"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. If running the hub locally: cd $PROJECT_DIR && ./venv/bin/python src/server.py --port 8765"
echo "2. Restart Claude Code"
echo "3. Test with: list agents"
echo ""

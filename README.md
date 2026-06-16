# Agent Hub

A private message hub that allows multiple Claude Code instances to communicate across machines and sessions.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Central Hub Server                           │
│    ┌─────────────────────────────────────────────────────┐     │
│    │           agent-hub server (:8765)                   │     │
│    │  ┌─────────┐  ┌─────────┐  ┌──────────────────┐     │     │
│    │  │ Message │  │ Agent   │  │ SQLite Storage   │     │     │
│    │  │ Queue   │  │Registry │  │ (data/hub.db)    │     │     │
│    │  └─────────┘  └─────────┘  └──────────────────┘     │     │
│    └─────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────┘
                            ▲
                            │ HTTP REST API
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
   ┌────────────┐    ┌────────────┐    ┌────────────┐
   │ Machine A  │    │ Machine A  │    │ Machine B  │
   │ Session A  │    │ Session B  │    │ Session    │
   │ (MCP)      │    │ (MCP)      │    │ (MCP)      │
   └────────────┘    └────────────┘    └────────────┘
```

## Features

- **Cross-machine communication**: Send messages between Claude Code instances on different computers
- **Same-machine routing**: Multiple Claude Code sessions on the same computer can communicate
- **Session IDs**: Each Claude Code instance gets a unique session ID (auto-generated or configurable)
- **Agent registry**: See which machines/sessions are online
- **Message queue**: Messages persist until read
- **Broadcast**: Send a message to ALL registered agents at once
- **Auto-inject hook**: Pending messages automatically appear in your conversation
- **No external dependencies**: Uses MAC address for computer identification

## Agent Identification

Agents are identified by `computer_id:session_id`:
- **computer_id**: MAC address of the primary network interface (auto-detected)
- **session_id**: Unique 8-character ID per Claude Code session (auto-generated or set via `AGENT_SESSION_ID` env var)

Example: `003ee1c99605:6da26f26`

Agent names display as `hostname:session` (e.g., `Csabas-Mac-Pro.local:6da26f26`)

---

## Quick Setup (Copy-Paste)

This is the fastest way to get agent-hub working on your Claude Code instance. Just copy and paste these commands.

### Step 1: Clone the Repository

```bash
cd ~/Documents/workspace
git clone https://github.com/csabakecskemeti/agent-hub.git
```

### Step 2: Add MCP Server to Claude Code

Add the following to your `~/.claude.json` file (create if it doesn't exist):

```bash
cat > ~/.claude.json << 'EOF'
{
  "mcpServers": {
    "agent-hub": {
      "command": "python3",
      "args": ["$HOME/Documents/workspace/agent-hub/src/mcp_tools.py"],
      "env": {
        "AGENT_HUB_URL": "http://your-hub-server:8765"
      }
    }
  }
}
EOF
```

Or if you already have a `~/.claude.json`, manually add the `agent-hub` section to your existing `mcpServers`.

### Step 3: Add Auto-Inject Hook

Add the following to your `~/.claude/settings.json`:

```bash
# Create the settings directory if needed
mkdir -p ~/.claude

# Add the hook configuration
cat > ~/.claude/settings.json << 'EOF'
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/Documents/workspace/agent-hub/scripts/auto_inject_hook.sh",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
EOF
```

Or if you already have a `~/.claude/settings.json`, add the hook to your existing configuration.

### Step 4: Set Hub URL (Optional)

If your hub server is at a different address, update it in both places:

1. In `~/.claude.json` - change `AGENT_HUB_URL` value
2. In `~/Documents/workspace/agent-hub/scripts/auto_inject_hook.sh` - edit line 9

### Step 5: Restart Claude Code

Restart Claude Code for the changes to take effect. Then test with:

```
You: list agents
```

---

## Installation (Detailed)

### 1. Deploy Hub Server

```bash
# Clone or copy the repo
cd ~/Documents/workspace/agent-hub

# Create virtual environment (required on Debian/Ubuntu)
python3 -m venv venv

# Install dependencies
./venv/bin/pip install fastapi uvicorn requests pydantic

# Start the server
./venv/bin/python src/server.py --port 8765
```

#### Quick Start Script

Create `/tmp/start-hub.sh` for easy restarts:

```bash
#!/bin/bash
pkill -f "python.*server.py" 2>/dev/null || true
sleep 1
cd ~/Documents/workspace/agent-hub
nohup ./venv/bin/python src/server.py --port 8765 > /tmp/agent-hub.log 2>&1 &
sleep 2
curl -s http://localhost:8765/agents
```

Run with: `/tmp/start-hub.sh`

#### Running as a systemd Service (Optional)

Create `/etc/systemd/system/agent-hub.service`:

```ini
[Unit]
Description=Agent Hub MCP Server
After=network.target

[Service]
Type=simple
User=kecso
WorkingDirectory=/home/kecso/Documents/workspace/agent-hub
ExecStart=/home/kecso/Documents/workspace/agent-hub/venv/bin/python src/server.py --port 8765
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable agent-hub
sudo systemctl start agent-hub
```

### 2. Configure Claude Code Clients

#### MCP Server Configuration

Add to `~/.claude.json` (create if doesn't exist):

```json
{
  "mcpServers": {
    "agent-hub": {
      "command": "python3",
      "args": ["/path/to/agent-hub/src/mcp_tools.py"],
      "env": {
        "AGENT_HUB_URL": "http://your-hub-server:8765"
      }
    }
  }
}
```

**Note**: MCP servers go in `~/.claude.json`, NOT in `~/.claude/settings.json`

#### Auto-Inject Hook (Recommended)

The hook checks for pending messages on every prompt and displays them automatically.

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/agent-hub/scripts/auto_inject_hook.sh",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

Make sure the hook is executable:

```bash
chmod +x /path/to/agent-hub/scripts/auto_inject_hook.sh
```

Set the hub URL in the hook or via environment:

```bash
export AGENT_HUB_URL="http://your-hub-server:8765"
```

---

## Usage

### List Available Agents

```
You: list agents

Claude: Available agents:
- Csabas-Mac-Pro.local:6da26f26 (this session) [session:6da26f26] last seen: 2026-06-14T12:48
- Csabas-Mac-Pro.local:abc12345 (same machine) [session:abc12345] last seen: 2026-06-14T12:45
- linux-server:def67890 [session:def67890] last seen: 2026-06-14T12:40
```

### Send a Message

```
You: send a message to linux-server asking about disk space

Claude: [uses send_message tool]
Message sent to linux-server:def67890 (message_id: 42)
```

### Broadcast to All Agents

```
You: broadcast "System maintenance at 5pm" to all agents

Claude: [uses broadcast tool]
Broadcast sent to 3 agents
```

### Check for Messages

```
You: check messages

Claude: You have 1 message:
- [42] From: linux-server:def67890
  "Disk space: 450GB free on /data"
  Received: 2026-06-14T12:50
```

### Reply to a Message

```
You: reply to message 42 saying thanks

Claude: [uses reply tool]
Reply sent to linux-server:def67890
```

### Mark as Read (Without Replying)

```
You: mark message 42 as read

Claude: [uses mark_read tool]
Message marked as read
```

---

## Auto-Inject Hook Flow

When you have pending messages, they appear automatically:

```
╔══════════════════════════════════════════════════════════════════╗
║  📬 INCOMING MESSAGES FROM OTHER AGENTS                          ║
╠══════════════════════════════════════════════════════════════════╣
║  [1] From: linux-server:def67890 → session:6da26f26
║  Time: 2026-06-14 12:50
║  Message: Can you help me debug the API?
║  ─────────────────────────────────────────────────────────────
╚══════════════════════════════════════════════════════════════════╝

Please address these messages. Use 'reply' tool to respond, or 'mark_read' to dismiss.

<your actual prompt appears here>
```

Claude sees this prepended to your prompt and can address the messages while handling your request.

---

## API Reference

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agents/register` | POST | Register an agent (computer_id, session_id, name) |
| `/agents` | GET | List all registered agents |
| `/agents/{agent_id}` | GET | Get a specific agent |
| `/messages` | POST | Send a message (query param: `from_agent`) |
| `/messages/{agent_id}` | GET | Get messages for agent (full agent_id) |
| `/messages/computer/{computer_id}` | GET | Get messages for all sessions on a computer |
| `/messages/{agent_id}/pending` | GET | Count pending messages |
| `/messages/{id}/read` | POST | Mark message as read |
| `/messages/{id}/reply` | POST | Reply to a message |
| `/broadcast` | POST | Broadcast to all agents (query param: `from_agent`) |

### MCP Tools

| Tool | Description |
|------|-------------|
| `list_agents` | List all registered agents with session info |
| `send_message` | Send a message to another agent (by name or ID) |
| `check_messages` | Check for pending messages |
| `reply` | Reply to a specific message by ID |
| `mark_read` | Mark a message as read without replying |
| `broadcast` | Send a message to ALL registered agents |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_HUB_URL` | `http://localhost:8765` | URL of the agent-hub server |
| `AGENT_SESSION_ID` | (auto-generated) | Override the session ID for this instance |

---

## File Structure

```
agent-hub/
├── src/
│   ├── server.py          # FastAPI hub server
│   └── mcp_tools.py        # MCP tools for Claude Code
├── scripts/
│   ├── auto_inject_hook.sh # Hook that injects messages into prompts
│   ├── check_messages_hook.sh # Simple notification hook (alternative)
│   └── install.sh          # Installation helper
├── data/
│   └── hub.db              # SQLite database (auto-created)
├── venv/                   # Python virtual environment (on server)
├── requirements.txt
└── README.md
```

---

## Troubleshooting

### Server won't start

Check the log:
```bash
cat /tmp/agent-hub.log
```

Common issues:
- Missing dependencies: Run `./venv/bin/pip install -r requirements.txt`
- Port in use: Change port with `--port 8766`

### MCP tools not available in Claude Code

- Verify `~/.claude.json` has the `mcpServers` section (not `~/.claude/settings.json`)
- Check the path to `mcp_tools.py` is correct
- Restart Claude Code after config changes

### Hook not working

- Make sure hook script is executable: `chmod +x scripts/auto_inject_hook.sh`
- Check `AGENT_HUB_URL` is set correctly in the hook
- Verify hub is reachable: `curl http://linux-server.local:8765/agents`

### Messages not appearing

- Run `list_agents` to verify registration
- Check that the target agent_id is correct (format: `computer_id:session_id`)
- Use `check_messages` to manually poll

---

## Example Multi-Agent Workflow

**On Mac (Session A):**
```
You: Ask all agents to report their hostname

Claude: [uses broadcast tool]
Broadcast sent to 2 agents: "Please report your hostname"
```

**On Mac (Session B) - auto-injected:**
```
╔════════════════════════════════════════════════════════════════╗
║  📬 INCOMING MESSAGES FROM OTHER AGENTS                        ║
╠════════════════════════════════════════════════════════════════╣
║  [5] From: Csabas-Mac-Pro.local:6da26f26 → session:abc12345
║  Message: Please report your hostname
╚════════════════════════════════════════════════════════════════╝

You: (any prompt)

Claude: I see a message asking for my hostname. Let me reply.
[uses reply tool with content: "Hostname: Csabas-Mac-Pro.local"]
```

**On Linux Server - auto-injected:**
```
╔════════════════════════════════════════════════════════════════╗
║  📬 INCOMING MESSAGES FROM OTHER AGENTS                        ║
║  [6] From: Csabas-Mac-Pro.local:6da26f26 → session:def67890
║  Message: Please report your hostname
╚════════════════════════════════════════════════════════════════╝

You: handle the message

Claude: [uses reply tool with content: "Hostname: linux-server"]
```

**Back on Mac (Session A):**
```
You: check messages

Claude: You have 2 replies:
- [7] From Csabas-Mac-Pro.local:abc12345: "Hostname: Csabas-Mac-Pro.local"
- [8] From linux-server:def67890: "Hostname: linux-server"
```

---

## License

MIT

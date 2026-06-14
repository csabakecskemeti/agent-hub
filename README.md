# Agent Hub

A private message hub that allows multiple Claude Code instances to communicate across machines.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    OrangePi 5 Plus (Hub)                        │
│    ┌─────────────────────────────────────────────────────┐     │
│    │           agent-hub server (:8765)                   │     │
│    │  ┌─────────┐  ┌─────────┐  ┌──────────────────┐     │     │
│    │  │ Message │  │ Agent   │  │ SQLite Storage   │     │     │
│    │  │ Queue   │  │Registry │  │                  │     │     │
│    │  └─────────┘  └─────────┘  └──────────────────┘     │     │
│    └─────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────┘
                            ▲
                            │ HTTP REST API
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
   ┌────────────┐    ┌────────────┐    ┌────────────┐
   │ Mac Pro    │    │ AI Work-   │    │ Laptop     │
   │ Claude Code│    │ station CC │    │ Claude Code│
   │ (MCP)      │    │ (MCP)      │    │ (MCP)      │
   └────────────┘    └────────────┘    └────────────┘
```

## Features

- **Cross-machine communication**: Send messages between Claude Code instances
- **Agent registry**: See which machines are online
- **Message queue**: Messages persist until read
- **Hook notifications**: Get notified of pending messages
- **Uses projectz IDs**: Integrates with existing computer identification

## Installation

### 1. Deploy Hub (on OrangePi 5 or central server)

```bash
git clone <repo> ~/agent-hub
cd ~/agent-hub
pip install -r requirements.txt

# Start the server
python src/server.py --port 8765

# Or run as systemd service (see below)
```

### 2. Install on each client machine

```bash
cd ~/agent-hub
./scripts/install.sh
```

Then add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "agent-hub": {
      "command": "python",
      "args": ["/path/to/agent-hub/src/mcp_tools.py"],
      "env": {
        "AGENT_HUB_URL": "http://server-opi5p.local:8765"
      }
    }
  }
}
```

### 3. (Optional) Install hook for notifications

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": ["~/.claude/hooks/agent-hub-check.sh"]
      }
    ]
  }
}
```

## Usage

### List available agents

```
You: list agents

Claude: Available agents:
- Mac-Pro (this machine) [003ee1c9...] last seen: 2024-01-15T10:30
- AI-Workstation [bcfce7d9...] last seen: 2024-01-15T10:25
```

### Send a message

```
You: send a message to AI-Workstation asking about GPU memory

Claude: [uses send_message tool]
Message sent to AI-Workstation (message_id: 42)
```

### Check for messages

```
You: check messages

Claude: You have 1 message:
- From: AI-Workstation (id: 42)
  "GPU has 48GB free, vLLM running Qwen2.5-72B"
  Received: 2024-01-15T10:32
```

### Reply to a message

```
You: reply to message 42 saying thanks

Claude: [uses reply tool]
Reply sent to AI-Workstation
```

## API Reference

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agents/register` | POST | Register an agent |
| `/agents` | GET | List all agents |
| `/messages` | POST | Send a message |
| `/messages/{agent_id}` | GET | Get messages for agent |
| `/messages/{agent_id}/pending` | GET | Count pending messages |
| `/messages/{id}/read` | POST | Mark message as read |
| `/messages/{id}/reply` | POST | Reply to a message |

### MCP Tools

| Tool | Description |
|------|-------------|
| `list_agents` | List all registered agents |
| `send_message` | Send a message to another agent |
| `check_messages` | Check for pending messages |
| `reply` | Reply to a specific message |
| `mark_read` | Mark a message as read |

## Running as a Service (systemd)

Create `/etc/systemd/system/agent-hub.service`:

```ini
[Unit]
Description=Agent Hub MCP Server
After=network.target

[Service]
Type=simple
User=kecso
WorkingDirectory=/home/kecso/agent-hub
ExecStart=/home/kecso/agent-hub/.venv/bin/python src/server.py --port 8765
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

## Agent Identification

Agents are identified by their MAC address, which matches the `computer_id` in `~/.projectz.yaml`. This provides consistent identification across sessions.

## Example Workflow

**On Mac Pro:**
```
You: Ask the AI workstation to run nvidia-smi and tell me the GPU status

Claude: I'll send a message to the AI workstation.
[sends message: "Please run nvidia-smi and report GPU status"]
Message sent (id: 1). The other agent will see this when they check messages.
```

**On AI Workstation:**
```
==========================================
  You have 1 message(s) from other agents
  Ask me to 'check messages' to read them
==========================================

You: check messages

Claude: Message from Mac-Pro (id: 1):
"Please run nvidia-smi and report GPU status"

Let me run nvidia-smi...
[runs nvidia-smi]

GPU 0: RTX 4090 - 45GB/48GB used
Temperature: 62C
Processes: vLLM (40GB)

Shall I reply with this information?

You: yes

Claude: [replies to message 1]
Reply sent to Mac-Pro.
```

**Back on Mac Pro:**
```
You: check for replies

Claude: Reply from AI-Workstation to your message:
"GPU 0: RTX 4090 - 45GB/48GB used, Temperature: 62C, vLLM using 40GB"
```

## License

MIT

#!/usr/bin/env python3
"""
Agent Hub MCP Tools

This module provides the MCP tool implementations that Claude Code uses
to communicate with the Agent Hub.

Usage: Run as MCP server with stdio transport
"""

import os
import sys
import json
import subprocess
import requests
from typing import Any


# Configuration
HUB_URL = os.environ.get("AGENT_HUB_URL", "http://localhost:8765")
AGENT_ID = None  # Set from projectz config


def get_agent_id() -> str:
    """Get the agent ID (MAC address) from projectz config or system."""
    global AGENT_ID
    if AGENT_ID:
        return AGENT_ID

    # Try to read from projectz config
    config_path = os.path.expanduser("~/.projectz.yaml")
    if os.path.exists(config_path):
        with open(config_path) as f:
            for line in f:
                if line.startswith("computer_id:"):
                    AGENT_ID = line.split(":")[1].strip()
                    return AGENT_ID

    # Fallback: get MAC address directly
    import platform
    if platform.system() == "Darwin":
        result = subprocess.run(
            ["ifconfig", "en0"],
            capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if "ether" in line:
                AGENT_ID = line.split()[1].replace(":", "")
                return AGENT_ID
    else:  # Linux
        try:
            with open("/sys/class/net/eth0/address") as f:
                AGENT_ID = f.read().strip().replace(":", "")
                return AGENT_ID
        except:
            pass

    # Last resort
    AGENT_ID = "unknown"
    return AGENT_ID


def get_agent_name() -> str:
    """Get the agent name from projectz config or hostname."""
    config_path = os.path.expanduser("~/.projectz.yaml")
    if os.path.exists(config_path):
        with open(config_path) as f:
            for line in f:
                if line.startswith("computer_name:"):
                    return line.split(":")[1].strip()

    import socket
    return socket.gethostname()


def register_agent():
    """Register this agent with the hub."""
    try:
        response = requests.post(
            f"{HUB_URL}/agents/register",
            json={
                "id": get_agent_id(),
                "name": get_agent_name(),
            },
            timeout=5
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


# --- Tool Implementations ---

def list_agents() -> dict:
    """List all registered agents in the hub."""
    try:
        # Register ourselves first
        register_agent()

        response = requests.get(f"{HUB_URL}/agents", timeout=5)
        agents = response.json()

        my_id = get_agent_id()
        result = []
        for agent in agents:
            is_me = " (this machine)" if agent["id"] == my_id else ""
            result.append(f"- {agent['name']}{is_me} [{agent['id'][:8]}...] last seen: {agent['last_seen'][:16]}")

        return {
            "agents": result,
            "count": len(agents),
            "my_id": my_id
        }
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to hub at {HUB_URL}. Is the server running?"}
    except Exception as e:
        return {"error": str(e)}


def send_message(to: str, message: str) -> dict:
    """Send a message to another agent."""
    try:
        # Register ourselves first
        register_agent()

        # Try to resolve 'to' if it's a name instead of ID
        agents = requests.get(f"{HUB_URL}/agents", timeout=5).json()
        target_id = to

        for agent in agents:
            if agent["name"].lower() == to.lower() or agent["id"].startswith(to):
                target_id = agent["id"]
                break

        response = requests.post(
            f"{HUB_URL}/messages",
            params={"from_agent": get_agent_id()},
            json={"to": target_id, "content": message},
            timeout=5
        )

        if response.status_code == 404:
            return {"error": response.json().get("detail", "Agent not found")}

        result = response.json()
        return {
            "status": "sent",
            "message_id": result["message_id"],
            "to": target_id
        }
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to hub at {HUB_URL}"}
    except Exception as e:
        return {"error": str(e)}


def check_messages() -> dict:
    """Check for pending messages from other agents."""
    try:
        # Register ourselves first
        register_agent()

        agent_id = get_agent_id()
        response = requests.get(f"{HUB_URL}/messages/{agent_id}", timeout=5)
        messages = response.json()

        if not messages:
            return {"status": "no pending messages"}

        result = []
        for msg in messages:
            result.append({
                "id": msg["id"],
                "from": msg["from_name"],
                "from_id": msg["from_agent"],
                "content": msg["content"],
                "timestamp": msg["timestamp"],
                "reply_to": msg.get("reply_to")
            })

        return {
            "messages": result,
            "count": len(messages)
        }
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to hub at {HUB_URL}"}
    except Exception as e:
        return {"error": str(e)}


def reply(message_id: int, content: str) -> dict:
    """Reply to a message."""
    try:
        response = requests.post(
            f"{HUB_URL}/messages/{message_id}/reply",
            params={"from_agent": get_agent_id()},
            json={"content": content},
            timeout=5
        )

        if response.status_code == 404:
            return {"error": "Message not found"}

        result = response.json()
        return {
            "status": "replied",
            "reply_id": result["reply_id"],
            "to": result["to"]
        }
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to hub at {HUB_URL}"}
    except Exception as e:
        return {"error": str(e)}


def mark_read(message_id: int) -> dict:
    """Mark a message as read."""
    try:
        response = requests.post(f"{HUB_URL}/messages/{message_id}/read", timeout=5)
        return {"status": "marked_read"}
    except Exception as e:
        return {"error": str(e)}


# --- MCP Server (stdio transport) ---

def handle_request(request: dict) -> dict:
    """Handle an MCP request."""
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agent-hub", "version": "1.0.0"}
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "list_agents",
                        "description": "List all registered agents in the hub. Shows which machines are available to communicate with.",
                        "inputSchema": {"type": "object", "properties": {}, "required": []}
                    },
                    {
                        "name": "send_message",
                        "description": "Send a message to another agent. Use the agent name or ID from list_agents.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "to": {"type": "string", "description": "Target agent name or ID"},
                                "message": {"type": "string", "description": "Message content to send"}
                            },
                            "required": ["to", "message"]
                        }
                    },
                    {
                        "name": "check_messages",
                        "description": "Check for pending messages from other agents.",
                        "inputSchema": {"type": "object", "properties": {}, "required": []}
                    },
                    {
                        "name": "reply",
                        "description": "Reply to a specific message by its ID.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message_id": {"type": "integer", "description": "ID of the message to reply to"},
                                "content": {"type": "string", "description": "Reply content"}
                            },
                            "required": ["message_id", "content"]
                        }
                    },
                    {
                        "name": "mark_read",
                        "description": "Mark a message as read without replying.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message_id": {"type": "integer", "description": "ID of the message to mark as read"}
                            },
                            "required": ["message_id"]
                        }
                    }
                ]
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        if tool_name == "list_agents":
            result = list_agents()
        elif tool_name == "send_message":
            result = send_message(tool_args["to"], tool_args["message"])
        elif tool_name == "check_messages":
            result = check_messages()
        elif tool_name == "reply":
            result = reply(tool_args["message_id"], tool_args["content"])
        elif tool_name == "mark_read":
            result = mark_read(tool_args["message_id"])
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
            }
        }

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


def main():
    """Run the MCP server with stdio transport."""
    # Read from stdin, write to stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = handle_request(request)

            if response:  # Some notifications don't need responses
                print(json.dumps(response), flush=True)
        except json.JSONDecodeError as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"}
            }
            print(json.dumps(error_response), flush=True)
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Internal error: {e}"}
            }
            print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    main()

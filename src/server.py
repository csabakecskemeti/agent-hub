#!/usr/bin/env python3
"""
Agent Hub MCP Server

A message hub that allows multiple Claude Code instances to communicate.
Each agent is identified by its computer's MAC address.

Run with: python server.py --port 8765
"""

import json
import sqlite3
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn


# --- Database ---

DB_PATH = Path(__file__).parent.parent / "data" / "hub.db"

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            computer_id TEXT,
            session_id TEXT,
            name TEXT,
            ip TEXT,
            last_seen TEXT,
            registered TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent TEXT,
            to_agent TEXT,
            content TEXT,
            timestamp TEXT,
            read INTEGER DEFAULT 0,
            reply_to INTEGER,
            FOREIGN KEY (from_agent) REFERENCES agents(id),
            FOREIGN KEY (to_agent) REFERENCES agents(id)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_to ON messages(to_agent, read);
        CREATE INDEX IF NOT EXISTS idx_agents_computer ON agents(computer_id);
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --- Models ---

class AgentRegister(BaseModel):
    computer_id: str  # MAC address
    session_id: str   # Unique session identifier
    name: str         # Display name (e.g., "Mac-Pro:claude1")
    ip: Optional[str] = None

class Message(BaseModel):
    to: str  # Target agent ID (MAC address)
    content: str

class Reply(BaseModel):
    content: str

class Broadcast(BaseModel):
    content: str
    exclude_self: bool = True  # Don't send to yourself by default


# --- App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Agent Hub", lifespan=lifespan)


# --- REST Endpoints ---

@app.post("/agents/register")
def register_agent(agent: AgentRegister):
    """Register or update an agent."""
    conn = get_db()
    now = datetime.utcnow().isoformat()

    # Create combined agent ID: computer_id:session_id
    agent_id = f"{agent.computer_id}:{agent.session_id}"

    existing = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()

    if existing:
        conn.execute(
            "UPDATE agents SET name = ?, ip = ?, last_seen = ? WHERE id = ?",
            (agent.name, agent.ip, now, agent_id)
        )
    else:
        conn.execute(
            "INSERT INTO agents (id, computer_id, session_id, name, ip, last_seen, registered) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agent_id, agent.computer_id, agent.session_id, agent.name, agent.ip, now, now)
        )

    conn.commit()
    conn.close()
    return {"status": "registered", "agent_id": agent_id}


@app.get("/agents")
def list_agents():
    """List all registered agents."""
    conn = get_db()
    agents = conn.execute("SELECT * FROM agents ORDER BY last_seen DESC").fetchall()
    conn.close()
    return [dict(a) for a in agents]


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    """Get a specific agent."""
    conn = get_db()
    agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    conn.close()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return dict(agent)


@app.post("/messages")
def send_message(msg: Message, from_agent: str):
    """Send a message to another agent."""
    conn = get_db()

    # Verify both agents exist
    sender = conn.execute("SELECT * FROM agents WHERE id = ?", (from_agent,)).fetchone()
    if not sender:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Sender agent '{from_agent}' not registered")

    receiver = conn.execute("SELECT * FROM agents WHERE id = ?", (msg.to,)).fetchone()
    if not receiver:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Receiver agent '{msg.to}' not registered")

    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        "INSERT INTO messages (from_agent, to_agent, content, timestamp) VALUES (?, ?, ?, ?)",
        (from_agent, msg.to, msg.content, now)
    )
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {"status": "sent", "message_id": msg_id, "to": msg.to}


@app.post("/broadcast")
def broadcast_message(msg: Broadcast, from_agent: str):
    """Broadcast a message to all agents."""
    conn = get_db()

    # Verify sender exists
    sender = conn.execute("SELECT * FROM agents WHERE id = ?", (from_agent,)).fetchone()
    if not sender:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Sender agent '{from_agent}' not registered")

    # Get all agents (optionally excluding sender)
    if msg.exclude_self:
        agents = conn.execute("SELECT id FROM agents WHERE id != ?", (from_agent,)).fetchall()
    else:
        agents = conn.execute("SELECT id FROM agents").fetchall()

    if not agents:
        conn.close()
        return {"status": "no_recipients", "message_ids": [], "recipients": 0}

    now = datetime.utcnow().isoformat()
    message_ids = []

    for agent in agents:
        cursor = conn.execute(
            "INSERT INTO messages (from_agent, to_agent, content, timestamp) VALUES (?, ?, ?, ?)",
            (from_agent, agent["id"], msg.content, now)
        )
        message_ids.append(cursor.lastrowid)

    conn.commit()
    conn.close()

    return {"status": "broadcast", "message_ids": message_ids, "recipients": len(agents)}


@app.get("/messages/{agent_id}")
def get_messages(agent_id: str, unread_only: bool = True):
    """Get messages for an agent (full agent_id = computer_id:session_id)."""
    conn = get_db()

    if unread_only:
        messages = conn.execute("""
            SELECT m.*, a.name as from_name
            FROM messages m
            JOIN agents a ON m.from_agent = a.id
            WHERE m.to_agent = ? AND m.read = 0
            ORDER BY m.timestamp ASC
        """, (agent_id,)).fetchall()
    else:
        messages = conn.execute("""
            SELECT m.*, a.name as from_name
            FROM messages m
            JOIN agents a ON m.from_agent = a.id
            WHERE m.to_agent = ?
            ORDER BY m.timestamp DESC
            LIMIT 50
        """, (agent_id,)).fetchall()

    conn.close()
    return [dict(m) for m in messages]


@app.get("/messages/computer/{computer_id}")
def get_messages_by_computer(computer_id: str, unread_only: bool = True):
    """Get messages for all sessions on a computer (by computer_id/MAC address)."""
    conn = get_db()

    # Match messages where to_agent starts with computer_id:
    pattern = f"{computer_id}:%"

    if unread_only:
        messages = conn.execute("""
            SELECT m.*, a.name as from_name
            FROM messages m
            JOIN agents a ON m.from_agent = a.id
            WHERE m.to_agent LIKE ? AND m.read = 0
            ORDER BY m.timestamp ASC
        """, (pattern,)).fetchall()
    else:
        messages = conn.execute("""
            SELECT m.*, a.name as from_name
            FROM messages m
            JOIN agents a ON m.from_agent = a.id
            WHERE m.to_agent LIKE ?
            ORDER BY m.timestamp DESC
            LIMIT 50
        """, (pattern,)).fetchall()

    conn.close()
    return [dict(m) for m in messages]


@app.get("/messages/{agent_id}/pending")
def pending_count(agent_id: str):
    """Get count of pending messages for an agent."""
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) as count FROM messages WHERE to_agent = ? AND read = 0",
        (agent_id,)
    ).fetchone()["count"]
    conn.close()
    return {"agent_id": agent_id, "pending": count}


@app.post("/messages/{message_id}/read")
def mark_read(message_id: int):
    """Mark a message as read."""
    conn = get_db()
    conn.execute("UPDATE messages SET read = 1 WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    return {"status": "marked_read", "message_id": message_id}


@app.post("/messages/{message_id}/reply")
def reply_to_message(message_id: int, reply: Reply, from_agent: str):
    """Reply to a message."""
    conn = get_db()

    # Get original message
    original = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if not original:
        conn.close()
        raise HTTPException(status_code=404, detail="Original message not found")

    # Mark original as read
    conn.execute("UPDATE messages SET read = 1 WHERE id = ?", (message_id,))

    # Send reply
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        "INSERT INTO messages (from_agent, to_agent, content, timestamp, reply_to) VALUES (?, ?, ?, ?, ?)",
        (from_agent, original["from_agent"], reply.content, now, message_id)
    )
    reply_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {"status": "replied", "reply_id": reply_id, "to": original["from_agent"]}


# --- MCP Protocol (SSE Transport) ---

@app.get("/mcp")
async def mcp_endpoint(agent_id: str):
    """
    MCP endpoint using Server-Sent Events.
    The client connects with their agent_id and receives tool definitions.
    """
    async def event_stream():
        # Send server info
        yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'server/info', 'params': {'name': 'agent-hub', 'version': '1.0.0'}})}\n\n"

        # Send tool definitions
        tools = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {
                "tools": [
                    {
                        "name": "list_agents",
                        "description": "List all registered agents in the hub",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "send_message",
                        "description": "Send a message to another agent",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "to": {"type": "string", "description": "Target agent ID (MAC address) or name"},
                                "message": {"type": "string", "description": "Message content"}
                            },
                            "required": ["to", "message"]
                        }
                    },
                    {
                        "name": "check_messages",
                        "description": "Check for pending messages from other agents",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "reply",
                        "description": "Reply to a message",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message_id": {"type": "integer", "description": "ID of message to reply to"},
                                "content": {"type": "string", "description": "Reply content"}
                            },
                            "required": ["message_id", "content"]
                        }
                    }
                ]
            }
        }
        yield f"data: {json.dumps(tools)}\n\n"

        # Keep connection alive
        while True:
            await asyncio.sleep(30)
            yield f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'ping'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    print(f"Starting Agent Hub on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

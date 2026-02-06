# core/mcp/__init__.py
"""
MCP (Model Context Protocol) Client Integration Module

This module provides MCP client capabilities, allowing the agent to connect to
MCP servers and use their tools as actions alongside native actions.
"""

from core.mcp.mcp_config import MCPConfig, MCPServerConfig
from core.mcp.mcp_client import MCPClient, mcp_client
from core.mcp.mcp_server import MCPServerConnection
from core.mcp.mcp_action_adapter import MCPActionAdapter

__all__ = [
    "MCPConfig",
    "MCPServerConfig",
    "MCPClient",
    "mcp_client",
    "MCPServerConnection",
    "MCPActionAdapter",
]

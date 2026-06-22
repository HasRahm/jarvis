import sys
import os
import json
import logging
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

def get_config_paths() -> list[Path]:
    """Find MCP configs on any OS in priority order."""
    print(f"[TRACE] core.system.mcp_bridge.get_config_paths: enter", file=sys.stderr, flush=True)
    candidates = []
    
    # 1. Claude Desktop - Windows
    if appdata := os.environ.get("APPDATA"):
        candidates.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    
    # Claude Desktop - macOS
    candidates.append(Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    
    # Claude Desktop - Linux
    candidates.append(Path.home() / ".config" / "Claude" / "claude_desktop_config.json")
    
    # Project-level override
    candidates.append(Path.cwd() / ".claude.json")
    
    # Warp config
    candidates.append(Path.home() / ".warp" / "mcp.json")
    
    # Env var override
    if custom := os.environ.get("JARVIS_MCP_CONFIG"):
        candidates.insert(0, Path(custom))
        
    return [p for p in candidates if p.exists()]

class JarvisMCPBridge:
    def __init__(self):
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="mcp-worker"
        )
        self.available_servers: Dict[str, Dict[str, Any]] = {}
        self._load_configs()
        
    def _load_configs(self):
        """Loads and merges configs from Claude and Warp."""
        print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge._load_configs: enter", file=sys.stderr, flush=True)
        configured_servers = {}
        paths = get_config_paths()
        
        # Sort paths to process Warp, then .claude.json, then claude_desktop
        # This ensures Claude Desktop wins on conflicts as requested
        def get_priority(p: Path):
            print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge._load_configs.get_priority: enter", file=sys.stderr, flush=True)
            name = p.name
            if name == "claude_desktop_config.json": return 3
            if name == ".claude.json": return 2
            if name == "mcp.json": return 1
            return 4 # custom env var wins all
            
        sorted_paths = sorted(paths, key=get_priority)
        
        for path in sorted_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    servers = data.get("mcpServers", {})
                    for name, params in servers.items():
                        configured_servers[name] = params
            except Exception as e:
                print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge._load_configs: except {str(e)[:80]}", file=sys.stderr, flush=True)
                logger.warning(f"Failed to read MCP config from {path}: {e}")
                
        # Probe servers
        for name, params in configured_servers.items():
            try:
                tools = self._probe_server_sync(name, params)
                self.available_servers[name] = {
                    "params": params,
                    "tools": tools
                }
                logger.info(f"MCP server ready: {name} ({len(tools)} tools)")
            except Exception as e:
                print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge._load_configs: except {str(e)[:80]}", file=sys.stderr, flush=True)
                logger.warning(f"MCP server unavailable: {name} - {e} (skipping)")

    def _probe_server_sync(self, name: str, params: dict) -> list:
        print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge._probe_server_sync: enter", file=sys.stderr, flush=True)
        def run_in_thread():
            print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge._probe_server_sync.run_in_thread: enter", file=sys.stderr, flush=True)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._async_probe(params))
            finally:
                loop.close()
        
        future = self._executor.submit(run_in_thread)
        return future.result(timeout=15)
        
    async def _async_probe(self, params: dict) -> list:
        print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge._async_probe: enter", file=sys.stderr, flush=True)
        env = os.environ.copy()
        if "env" in params:
            # We must cast env values to string because StdioServerParameters expects dict[str, str]
            env.update({k: str(v) for k, v in params["env"].items()})
            
        server_params = StdioServerParameters(
            command=params["command"],
            args=params.get("args", []),
            env=env
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tool_list = await session.list_tools()
                return tool_list.tools
                
    def get_mcp_tool_definitions(self) -> list:
        """Convert all loaded MCP tools into LLM-compatible definitions."""
        print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge.get_mcp_tool_definitions: enter", file=sys.stderr, flush=True)
        definitions = []
        for server_name, server_data in self.available_servers.items():
            for tool in server_data["tools"]:
                safe_name = f"mcp__{server_name}__{tool.name}".replace("-", "_")
                definitions.append({
                    "type": "function",
                    "function": {
                        "name": safe_name,
                        "description": tool.description or f"Tool {tool.name} from {server_name}",
                        "parameters": tool.inputSchema or {"type": "object", "properties": {}}
                    }
                })
        return definitions

    def execute_mcp_tool(self, server: str, tool: str, args: dict) -> Any:
        print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge.execute_mcp_tool: enter", file=sys.stderr, flush=True)
        def run_in_thread():
            print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge.execute_mcp_tool.run_in_thread: enter", file=sys.stderr, flush=True)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._async_execute(server, tool, args))
            finally:
                loop.close()
                
        future = self._executor.submit(run_in_thread)
        return future.result(timeout=60)
        
    async def _async_execute(self, server: str, tool: str, args: dict) -> Any:
        print(f"[TRACE] core.system.mcp_bridge.JarvisMCPBridge._async_execute: enter", file=sys.stderr, flush=True)
        params = self.available_servers[server]["params"]
        env = os.environ.copy()
        if "env" in params:
            env.update({k: str(v) for k, v in params["env"].items()})
            
        server_params = StdioServerParameters(
            command=params["command"],
            args=params.get("args", []),
            env=env
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=args)
                
                # Check for errors in result object based on MCP spec
                if getattr(result, "isError", False):
                    return f"Error from MCP server: {result.content}"
                    
                # Concatenate text content
                if hasattr(result, "content") and isinstance(result.content, list):
                    texts = []
                    for c in result.content:
                        if getattr(c, "type", "") == "text":
                            texts.append(getattr(c, "text", ""))
                        else:
                            texts.append(str(c))
                    return "\n".join(texts)
                return str(result)

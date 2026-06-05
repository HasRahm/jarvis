import os
import json
import logging
import importlib.util
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class PluginLoader:
    def __init__(self, project_root: str = None):
        if project_root is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.project_root = project_root
        self.plugin_file = os.path.join(self.project_root, "jarvis.plugin.json")
        self.skills = []
        self.tool_definitions = []
        self.tool_dispatchers = {}
        self.agent_models = {}
        self.mcp_servers = []
        self._load_plugins()

    def _load_plugins(self):
        if not os.path.exists(self.plugin_file):
            logger.info("No jarvis.plugin.json manifest found. Operating with core defaults.")
            return

        try:
            with open(self.plugin_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            logger.info(f"Loading plugin manifest: {manifest.get('name', 'unnamed')} v{manifest.get('version', '1.0.0')}")
            
            # 1. Load Skills
            skills_paths = manifest.get("skills", [])
            for p in skills_paths:
                abs_path = os.path.normpath(os.path.join(self.project_root, p))
                if os.path.exists(abs_path):
                    self.skills.append(abs_path)
                    logger.info(f"Registered plugin skill: {p}")
                else:
                    logger.warning(f"Plugin skill file not found: {abs_path}")

            # 2. Load Tools
            tools_paths = manifest.get("tools", [])
            for p in tools_paths:
                abs_path = os.path.normpath(os.path.join(self.project_root, p))
                if os.path.exists(abs_path):
                    try:
                        module_name = f"jarvis_plugin_tool_{os.path.splitext(os.path.basename(p))[0]}"
                        spec = importlib.util.spec_from_file_location(module_name, abs_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Extract TOOL_DEFINITIONS and dispatch
                        defs = getattr(module, "TOOL_DEFINITIONS", [])
                        dispatch_fn = getattr(module, "dispatch", None)
                        
                        if defs and dispatch_fn:
                            self.tool_definitions.extend(defs)
                            for d in defs:
                                fn_name = d["function"]["name"]
                                self.tool_dispatchers[fn_name] = dispatch_fn
                            logger.info(f"Successfully loaded plugin tool module: {p}")
                        else:
                            logger.warning(f"Plugin tool {p} is missing TOOL_DEFINITIONS or dispatch function")
                    except Exception as e:
                        logger.error(f"Failed to load plugin tool {p}: {e}")
                else:
                    logger.warning(f"Plugin tool file not found: {abs_path}")

            # 3. Load Agent model mappings
            self.agent_models = manifest.get("agents", {})
            if self.agent_models:
                logger.info(f"Registered agent model overrides: {list(self.agent_models.keys())}")

            # 4. Load MCP servers list
            self.mcp_servers = manifest.get("mcp_servers", [])
            if self.mcp_servers:
                logger.info(f"Registered plugin MCP servers: {self.mcp_servers}")

        except Exception as e:
            logger.error(f"Failed to parse plugin manifest: {e}")

# Global plugin loader instance
plugin_loader = PluginLoader()

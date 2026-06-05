import pytest
import os
import json
from unittest.mock import patch, MagicMock
from core.system.plugin_loader import PluginLoader
from core.system.skills import SkillsEngine
from tools.dispatcher import dispatch, TOOL_DEFINITIONS

@pytest.fixture
def mock_plugin_json(tmp_path):
    manifest = {
        "name": "test-plugin",
        "version": "1.0.0",
        "skills": ["skills/test-skill.md"],
        "tools": ["tools/test-tool.py"],
        "agents": {
            "test_agent": {"model": "mock-model"}
        }
    }
    
    # Create files
    plugin_file = tmp_path / "jarvis.plugin.json"
    plugin_file.write_text(json.dumps(manifest, indent=2))
    
    # Create mock skill file
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir(exist_ok=True)
    skill_file = skill_dir / "test-skill.md"
    skill_file.write_text("---\nname: Test Plugin Skill\ndescription: A dynamic plugin skill\n---\n# Test Plugin Skill\nDo plugin tasks.")
    
    # Create mock tool file
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir(exist_ok=True)
    tool_file = tool_dir / "test-tool.py"
    tool_file.write_text("""
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "plugin_test_tool",
            "description": "A dynamic tool from plugin",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

def dispatch(fn_name, args):
    if fn_name == "plugin_test_tool":
        return "plugin_tool_success"
    return "unknown"
""")

    return {
        "root": str(tmp_path),
        "manifest": str(plugin_file),
        "skill": str(skill_file),
        "tool": str(tool_file)
    }

def test_plugin_loader_parses_manifest(mock_plugin_json):
    loader = PluginLoader(project_root=mock_plugin_json["root"])
    assert len(loader.skills) == 1
    import os
    assert os.path.normpath(mock_plugin_json["skill"]) in loader.skills
    
    assert len(loader.tool_definitions) == 1
    assert loader.tool_definitions[0]["function"]["name"] == "plugin_test_tool"
    assert "plugin_test_tool" in loader.tool_dispatchers
    assert loader.agent_models == {"test_agent": {"model": "mock-model"}}

def test_skills_engine_loads_plugin_skills(mock_plugin_json):
    loader = PluginLoader(project_root=mock_plugin_json["root"])
    
    with patch("core.system.skills.plugin_loader", loader):
        se = SkillsEngine(skills_dir=os.path.join(mock_plugin_json["root"], "skills"))
        loaded_names = [s["name"] for s in se.skills]
        assert "Test Plugin Skill" in loaded_names

def test_dispatcher_routes_plugin_tools(mock_plugin_json):
    loader = PluginLoader(project_root=mock_plugin_json["root"])
    
    with patch("core.system.plugin_loader.plugin_loader", loader):
        # Test routing
        res = dispatch("plugin_test_tool", {})
        assert res == "plugin_tool_success"

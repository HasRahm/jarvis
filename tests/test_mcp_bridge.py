import sys
import os

# Ensure the root project directory is on the python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.system.mcp_bridge import JarvisMCPBridge

def test_bridge_discovers_tools():
    bridge = JarvisMCPBridge()
    tools = bridge.get_mcp_tool_definitions()
    assert isinstance(tools, list)
    
    # Extract the tool names from the generated definitions
    tool_names = [t["function"]["name"] for t in tools]
    print(f"Discovered {len(tools)} MCP tools:")
    for name in tool_names:
        print(f"  - {name}")

if __name__ == "__main__":
    test_bridge_discovers_tools()

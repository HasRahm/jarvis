import json
from tools.filesystem import read_file, write_file, list_dir
from tools.shell import run_command
from tools.browser import browser_navigate, browser_extract_text, browser_click, browser_screenshot
from brain.query import brain_query
from brain.write import brain_write
from core.orchestrator.dag import run_dag
from tools.visual_servo import visual_servo_click
from tools.desktop_automation import desktop_smooth_click, desktop_type_text, desktop_press_keys, desktop_scroll, desktop_get_active_window, desktop_focus_window, desktop_batch_actions, desktop_screenshot
from tools.windows import get_3d_window_graph
from core.system.mcp_bridge import JarvisMCPBridge
from tools.desktop_ui_tree import desktop_get_ui_tree, desktop_interact_with_element


TOOL_DEFINITIONS = [
  {
    "type": "function",
    "function": {
      "name": "read_file",
      "description": "Read the contents of a file at the given path",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {"type": "string", "description": "Absolute or relative file path"}
        },
        "required": ["path"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "write_file",
      "description": "Write content to a file, creating it if it does not exist",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {"type": "string"},
          "content": {"type": "string"}
        },
        "required": ["path", "content"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "list_dir",
      "description": "List files and directories at a path",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {"type": "string"}
        },
        "required": ["path"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "run_command",
      "description": "Run a shell command and return stdout and stderr",
      "parameters": {
        "type": "object",
        "properties": {
          "command": {"type": "string", "description": "The bash command to run"},
          "cwd": {"type": "string", "description": "Working directory (optional)"}
        },
        "required": ["command"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "browser_navigate",
      "description": "Open a URL in the headless browser",
      "parameters": {
        "type": "object",
        "properties": {
          "url": {"type": "string"}
        },
        "required": ["url"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "browser_extract_text",
      "description": "Extract all visible text from the current browser page",
      "parameters": {"type": "object", "properties": {}}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "browser_click",
      "description": "Click an element on the page by CSS selector or text",
      "parameters": {
        "type": "object",
        "properties": {
          "selector": {"type": "string"}
        },
        "required": ["selector"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "browser_screenshot",
      "description": "Take a screenshot of the current page, returns path to image",
      "parameters": {"type": "object", "properties": {}}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "brain_query",
      "description": "Search GBrain memory for relevant context before answering",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {"type": "string"}
        },
        "required": ["query"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "brain_write",
      "description": "Store a note or result in GBrain for future recall",
      "parameters": {
        "type": "object",
        "properties": {
          "slug": {"type": "string", "description": "Unique key, e.g. 'project/checkout-api'"},
          "content": {"type": "string"}
        },
        "required": ["slug", "content"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "delegate_task",
      "description": "Delegate a complex build task to the multi-agent IDE. Use this for tasks that involve creating full features with database, API, and UI components. The orchestrator will decompose the task and route subtasks to specialized agents (backend, frontend, QA).",
      "parameters": {
        "type": "object",
        "properties": {
          "task": {"type": "string", "description": "Detailed description of what to build"},
          "dry_run": {"type": "boolean", "description": "If true, show the execution plan without running agents"}
        },
        "required": ["task"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "visual_servo_click",
      "description": "Perform closed-loop visual servo tracking to locate and smoothly click a visual template image on the screen in real-time.",
      "parameters": {
        "type": "object",
        "properties": {
          "target_template_path": {"type": "string", "description": "Absolute filesystem path to the PNG/JPG template image of the button or element to click"},
          "timeout_sec": {"type": "number", "description": "Maximum seconds to try tracking before timing out (optional, default 5.0)"},
          "Kp": {"type": "number", "description": "Proportional gain feedback coefficient (optional, default 0.3)"}
        },
        "required": ["target_template_path"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "desktop_smooth_click",
      "description": "Smoothly move the mouse cursor from its current position to coordinates (x, y) over a duration and perform a click.",
      "parameters": {
        "type": "object",
        "properties": {
          "x": {"type": "integer", "description": "Target X screen coordinate"},
          "y": {"type": "integer", "description": "Target Y screen coordinate"},
          "duration": {"type": "number", "description": "Duration in seconds for the smooth mouse movement (optional, default 1.5)"}
        },
        "required": ["x", "y"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "desktop_type_text",
      "description": "Type a string of text dynamically with natural human cadence, including random speed variation and punctuation pauses.",
      "parameters": {
        "type": "object",
        "properties": {
          "text": {"type": "string", "description": "The string of text to type"}
        },
        "required": ["text"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "desktop_press_keys",
      "description": "Press a single key or key combination/hotkey (e.g. ['ctrl', 'n'] or ['enter']).",
      "parameters": {
        "type": "object",
        "properties": {
          "keys": {
            "type": "array",
            "items": {"type": "string"},
            "description": "A list of keys to press concurrently, e.g. ['ctrl', 'c'] or ['win', 'up'] or ['escape']"
          }
        },
        "required": ["keys"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "desktop_scroll",
      "description": "Scroll the mouse wheel up (positive) or down (negative) smoothly.",
      "parameters": {
        "type": "object",
        "properties": {
          "amount": {"type": "integer", "description": "Scroll magnitude. Use positive values to scroll up, negative to scroll down (e.g. -500)"},
          "steps": {"type": "integer", "description": "Number of small incremental scroll steps to make it look smooth (optional, default 5)"}
        },
        "required": ["amount"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "desktop_get_active_window",
      "description": "Get the title of the currently active focused window in the foreground.",
      "parameters": {"type": "object", "properties": {}}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "desktop_focus_window",
      "description": "Find an open application window by matching its title (case-insensitive) and bring it to the active foreground.",
      "parameters": {
        "type": "object",
        "properties": {
          "title_query": {"type": "string", "description": "The case-insensitive substring of the window title to find (e.g. 'PowerPoint' or 'Notepad')"}
        },
        "required": ["title_query"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "desktop_batch_actions",
      "description": "Execute a list of multiple GUI actions (mouse moves, clicks, keypresses, typing, and wait delays) sequentially in a single tool call to eliminate LLM latencies.",
      "parameters": {
        "type": "object",
        "properties": {
          "actions": {
            "type": "array",
            "description": "A list of action objects to run in order.",
            "items": {
              "type": "object",
              "properties": {
                "type": {
                  "type": "string",
                  "description": "The type of action: 'focus', 'click', 'type_text', 'press_keys', 'scroll', or 'wait'"
                },
                "title_query": {"type": "string", "description": "Used with 'focus' action to search open window titles"},
                "x": {"type": "integer", "description": "Used with 'click' action for X coordinate"},
                "y": {"type": "integer", "description": "Used with 'click' action for Y coordinate"},
                "duration": {"type": "number", "description": "Optional click mouse glide duration in seconds (default 1.5)"},
                "text": {"type": "string", "description": "Used with 'type_text' action to type text with realistic human pauses"},
                "keys": {
                  "type": "array",
                  "items": {"type": "string"},
                  "description": "Used with 'press_keys' action (e.g. ['ctrl', 't'] or ['enter'])"
                },
                "amount": {"type": "integer", "description": "Used with 'scroll' action for magnitude (positive for up, negative for down)"},
                "steps": {"type": "integer", "description": "Optional scroll steps (default 5)"},
                "seconds": {"type": "number", "description": "Used with 'wait' action to pause execution for a float duration in seconds"}
              },
              "required": ["type"]
            }
          }
        },
        "required": ["actions"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "get_3d_window_graph",
      "description": "Returns the full active desktop window stack as a structured 3D graph representing spatial depth layers, cursor position, and occlusions.",
      "parameters": {
        "type": "object",
        "properties": {}
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "desktop_get_ui_tree",
      "description": "Gets the hierarchical interactive UI Automation accessibility tree of the currently active focused application window on Windows. Exposes element IDs (indexes), names, roles, absolute coordinate bounding boxes, and states so the agent can interact programmatically with high precision without using visual screenshots.",
      "parameters": {
        "type": "object",
        "properties": {
          "max_depth": {"type": "integer", "description": "Maximum tree depth to traverse (optional, default 8)"},
          "search_query": {"type": "string", "description": "Case-insensitive query string to filter elements by name, role, or automation ID (optional)"}
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "desktop_interact_with_element",
      "description": "Performs programmatic user action (click, hover, right_click, or type) on a specific cached control by its index retrieved from desktop_get_ui_tree.",
      "parameters": {
        "type": "object",
        "properties": {
          "index": {"type": "integer", "description": "The element index from the last desktop_get_ui_tree result"},
          "action": {"type": "string", "enum": ["click", "hover", "right_click", "type"], "description": "Action to perform (optional, default 'click')"},
          "text": {"type": "string", "description": "The text to type if the action is 'type' (optional)"}
        },
        "required": ["index"]
      }
    }
  }
]

mcp_bridge = JarvisMCPBridge()
TOOL_DEFINITIONS.extend(mcp_bridge.get_mcp_tool_definitions())

# Load dynamic plugin tool definitions
try:
    from core.system.plugin_loader import plugin_loader
    if plugin_loader.tool_definitions:
        TOOL_DEFINITIONS.extend(plugin_loader.tool_definitions)
except Exception as pe:
    logger.warning(f"Failed loading plugin tool definitions: {pe}")

_breakers = {}

_cortex = None

def get_cortex():
    global _cortex
    if _cortex is None:
        from core.system.spatial_cortex import SpatialContextCortex
        _cortex = SpatialContextCortex()
        _cortex.start()
    return _cortex

def get_breaker(tool_name: str):
    if tool_name not in _breakers:
        from core.system.circuit_breaker import CircuitBreaker
        _breakers[tool_name] = CircuitBreaker(tool_name)
    return _breakers[tool_name]

def dispatch(fn_name: str, args: dict):
    """Wrapped tool dispatch with circuit breaker protection and spatial context checks"""
    import os
    import time
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check spatial context home before executing any mutating tool
    if os.environ.get("JARVIS_CI") != "true" and fn_name not in ["brain_query", "brain_write", "read_file", "list_dir", "run_command"]:
        try:
            from core.orchestrator.dag import get_orchestrator
            orch = get_orchestrator()
            if orch and getattr(orch, "task_id", None):
                cortex = get_cortex()
                
                # If home context is not registered, register it
                if orch.task_id not in cortex.task_registry:
                    cortex.register_task(orch.task_id)
                
                # Check if we shifted context
                if not cortex.is_home_context(orch.task_id):
                    logger.warning(f"[Cortex] Context switch detected! Suspending tool '{fn_name}' until home context returns.")
                    
                    # Update status in AGENTS.md to SUSPENDED
                    if getattr(orch, "active_agent", None):
                        try:
                            from core.orchestrator.dag import _get_agent_instance
                            agent_instance = _get_agent_instance(orch.active_agent, user_id=orch.user_id)
                            agent_instance.update_status("SUSPENDED", "Context switched — waiting for home context")
                        except Exception as status_err:
                            logger.error(f"[Cortex] Failed to write SUSPENDED status: {status_err}")
                    
                    # Block execution and poll context
                    start_time = time.time()
                    timeout = 300  # 5 minutes
                    while not cortex.is_home_context(orch.task_id):
                        if time.time() - start_time > timeout:
                            raise TimeoutError(f"Context switch timeout: Original home context never returned for task '{orch.task_id}'")
                        time.sleep(0.5)
                        
                    logger.info(f"[Cortex] Home context restored for task '{orch.task_id}'. Resuming execution.")
                    
                    # Restore status back to WORKING
                    if getattr(orch, "active_agent", None):
                        try:
                            from core.orchestrator.dag import _get_agent_instance
                            agent_instance = _get_agent_instance(orch.active_agent, user_id=orch.user_id)
                            agent_instance.update_status("WORKING", "Resuming task")
                        except Exception as status_err:
                            logger.error(f"[Cortex] Failed to write WORKING status: {status_err}")
        except Exception as e:
            if isinstance(e, TimeoutError):
                return f"[ERROR] Context Switch Timeout: {e}"
            logger.warning(f"[Cortex] Context check warning: {e}")

    breaker = get_breaker(fn_name)
    if not breaker.is_available():
        return f"[ERROR] Circuit breaker is OPEN for tool '{fn_name}'. Tool is temporarily disabled due to repeated failures."
        
    try:
        result = _dispatch_raw(fn_name, args)
        if isinstance(result, str) and (result.startswith("[ERROR]") or result.startswith("ERROR:")):
            breaker.record_failure()
        else:
            breaker.record_success()
        return result
    except Exception as e:
        breaker.record_failure()
        raise e

def _dispatch_raw(fn_name: str, args: dict):
    """Route tool calls to their respective python functions"""
    # Route to plugin dispatchers if available
    try:
        from core.system.plugin_loader import plugin_loader
        if fn_name in plugin_loader.tool_dispatchers:
            return plugin_loader.tool_dispatchers[fn_name](fn_name, args)
    except Exception as pe:
        logger.warning(f"Failed routing to plugin dispatcher for {fn_name}: {pe}")

    if fn_name == "read_file":
        return read_file(args.get("path"))
    elif fn_name == "write_file":
        return write_file(args.get("path"), args.get("content"))
    elif fn_name == "list_dir":
        return list_dir(args.get("path"))
    elif fn_name == "run_command":
        return run_command(args.get("command"), args.get("cwd"))
    elif fn_name == "browser_navigate":
        return browser_navigate(args.get("url"))
    elif fn_name == "browser_extract_text":
        return browser_extract_text()
    elif fn_name == "browser_click":
        return browser_click(args.get("selector"))
    elif fn_name == "browser_screenshot":
        return browser_screenshot()
    elif fn_name == "brain_query":
        return brain_query(args.get("query"))
    elif fn_name == "brain_write":
        return brain_write(args.get("slug"), args.get("content"))
    elif fn_name == "delegate_task":
        result = run_dag(args.get("task"), dry_run=args.get("dry_run", False))
        return json.dumps(result, indent=2, default=str)
    elif fn_name == "visual_servo_click":
        return visual_servo_click(args.get("target_template_path"), args.get("timeout_sec", 5.0), args.get("Kp", 0.3))
    elif fn_name == "desktop_smooth_click":
        return desktop_smooth_click(args.get("x"), args.get("y"), args.get("duration", 1.5))
    elif fn_name == "desktop_type_text":
        return desktop_type_text(args.get("text"))
    elif fn_name == "desktop_press_keys":
        return desktop_press_keys(args.get("keys"))
    elif fn_name == "desktop_scroll":
        return desktop_scroll(args.get("amount"), args.get("steps", 5))
    elif fn_name == "desktop_get_active_window":
        return desktop_get_active_window()
    elif fn_name == "desktop_focus_window":
        return desktop_focus_window(args.get("title_query"))
    elif fn_name == "desktop_batch_actions":
        return desktop_batch_actions(args.get("actions"))
    elif fn_name == "desktop_screenshot":
        return desktop_screenshot()
    elif fn_name == "get_3d_window_graph":
        return json.dumps(get_3d_window_graph(), indent=2)
    elif fn_name == "desktop_get_ui_tree":
        return desktop_get_ui_tree(args.get("max_depth", 8), args.get("search_query"))
    elif fn_name == "desktop_interact_with_element":
        return desktop_interact_with_element(args.get("index"), args.get("action", "click"), args.get("text"))
    elif fn_name.startswith("mcp__"):
        parts = fn_name.split("__", 2)
        if len(parts) == 3:
            server, tool = parts[1], parts[2]
            return mcp_bridge.execute_mcp_tool(server, tool, args)
        else:
            raise ValueError(f"Invalid MCP tool name: {fn_name}")
    else:
        raise ValueError(f"Unknown tool function: {fn_name}")


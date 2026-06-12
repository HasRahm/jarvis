import json
import os
import sys
from tools.filesystem import read_file, write_file, list_dir
from tools.shell import run_command
from tools.browser import browser_navigate, browser_extract_text, browser_click, browser_screenshot
from brain.query import brain_query
from brain.write import brain_write
# Heavy modules (dag, mcp_bridge, visual_servo) imported lazily to prevent startup deadlocks
from tools.desktop_automation import desktop_smooth_click, desktop_type_text, desktop_press_keys, desktop_scroll, desktop_get_active_window, desktop_focus_window, desktop_batch_actions, desktop_screenshot
from tools.windows import get_3d_window_graph
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
      "name": "vocab_learn",
      "description": "Record a newly discovered UI pattern, icon location, or app-specific behavior to grow the visual vocabulary dataset. Call this after successfully automating something to help future sessions. Example: after clicking Figma's Community search bar, record its approximate location and what worked.",
      "parameters": {
        "type": "object",
        "properties": {
          "heading": {
            "type": "string",
            "description": "Short descriptive title for what was learned, e.g. 'Figma Community search bar location on 1920px screen' or 'VS Code command palette keyboard shortcut'"
          },
          "content": {
            "type": "string",
            "description": "Detailed description: what you found, where it was, what automation worked, any app-specific gotchas. Include coordinates if known."
          }
        },
        "required": ["heading", "content"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "vocab_lookup",
      "description": "Fetch the FULL visual-vocabulary table for a category when the quick-reference cheatsheet in your context isn't enough. Returns the complete table of icon shapes, app logos+ui_types, or UI layout patterns.",
      "parameters": {
        "type": "object",
        "properties": {
          "category": {
            "type": "string",
            "enum": ["icons", "logos", "patterns"],
            "description": "'icons' = full icon shape->meaning table; 'logos' = full app logo + ui_type + automation-notes table; 'patterns' = full UI layout pattern table."
          }
        },
        "required": ["category"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "smart_fill",
      "description": "GRAPH-FIRST form filling (preferred over visual_click+type for any native/HTML app): locates a field by description using the UI accessibility tree, fills it via virtual input (UIA ValuePattern/SendKeys — the physical mouse never moves), and verifies via OCR. Falls back to vision automatically only when the graph has no match (canvas/WebGL surfaces). Doctrine: the GRAPH locates and acts; VISION (visual_inspect) reads and verifies; reserve visual_click for canvas-only UIs.",
      "parameters": {
        "type": "object",
        "properties": {
          "field_description": {"type": "string", "description": "Natural description of the field, e.g. 'search box', 'email address field', 'first name input'"},
          "text": {"type": "string", "description": "The text to type into the field"},
          "window_hint": {"type": "string", "description": "Partial window title to focus first (e.g. 'Chrome', 'Notepad'). Strongly recommended."},
          "press_enter": {"type": "boolean", "description": "Press Enter after filling (submit). Default false."}
        },
        "required": ["field_description", "text"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "agent_view",
      "description": "Manage annotated 'what the agent sees' debug screenshots. When ON, every locate/click operation saves a PNG to scratch/agent_view/ showing window-graph rectangles, mouse-braille probe points (gray=miss, green=hit), matched element boxes, OCR word boxes, and vision crop+result coordinates. Actions: 'on', 'off', 'status', 'latest' (returns newest PNG path; set open_file true to open it for the user).",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {"type": "string", "enum": ["latest", "on", "off", "status"], "description": "What to do. Default 'latest'."},
          "open_file": {"type": "boolean", "description": "With 'latest': also open the PNG in the user's image viewer."}
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "agent_cursor",
      "description": "Control the visible agent-cursor overlay: a click-through teal ring showing where the agent is acting on screen, even during virtual input when the physical mouse never moves. Actions: 'on', 'off', 'status'.",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {"type": "string", "enum": ["on", "off", "status"], "description": "Default 'status'."}
        }
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
      "description": "Execute MULTIPLE GUI actions in ONE call to avoid a slow LLM round-trip per step. PREFER THIS for any sequence — e.g. focus a window, click a search bar (visual_click), type a query, press Enter — all in a single call. Each separate tool call is another LLM turn.",
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
                  "description": "Action type: 'focus', 'click', 'visual_click', 'visual_inspect', 'type_text', 'press_keys', 'scroll', or 'wait'"
                },
                "title_query": {"type": "string", "description": "Used with 'focus' action to search open window titles"},
                "x": {"type": "integer", "description": "Used with 'click' action for X coordinate"},
                "y": {"type": "integer", "description": "Used with 'click' action for Y coordinate"},
                "duration": {"type": "number", "description": "Optional click/visual_click mouse glide duration in seconds (default 0.4)"},
                "description": {"type": "string", "description": "Used with 'visual_click' — visual description of the element to find and click (for WebGL/canvas UIs)"},
                "window_hint": {"type": "string", "description": "Used with 'visual_click' — partial window title to crop the screenshot to (faster + more accurate). Always provide when known."},
                "question": {"type": "string", "description": "Used with 'visual_inspect' — what to look for on screen"},
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
  },
  {
    "type": "function",
    "function": {
      "name": "hybrid_locate_click",
      "description": "Locate a UI element and click it using a hybrid 3-layer approach: (1) Graph — confirms window exists and focuses it via Win32, (2) MouseBraille — ControlFromPoint grid scan INSIDE the window bounds (cursor acts as a braille finger; never probes taskbar/other windows), (3) Screenshot OCR — visual fallback using pytesseract. Supports verify_text to check the outcome and auto-retry if the expected result isn't visible.",
      "parameters": {
        "type": "object",
        "properties": {
          "target": {
            "type": "string",
            "description": "Text label of the UI element to click (e.g. 'Search', 'Community', 'Note taking app')"
          },
          "window_hint": {
            "type": "string",
            "description": "Partial window title (e.g. 'Figma', 'Spotify'). Optional but strongly recommended to avoid clicking the wrong window."
          },
          "verify_text": {
            "type": "string",
            "description": "Text expected to appear on screen AFTER clicking (e.g. 'scheduling' after clicking the search bar). If provided, the function verifies the outcome via OCR and retries automatically if not found."
          },
          "max_retries": {
            "type": "integer",
            "description": "How many times to retry the full click sequence if verification fails. Default 2."
          }
        },
        "required": ["target"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "screen_imprint",
      "description": "Capture the current screen density matrix, ASCII map, and changes.",
      "parameters": {"type": "object", "properties": {}}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "screen_ocr",
      "description": "Read all text currently visible on the screen using OCR.",
      "parameters": {"type": "object", "properties": {}}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "visual_inspect",
      "description": "Take a screenshot and ask a vision AI (Claude Sonnet) what it sees. Use this when screen_ocr fails — e.g. WebGL/canvas apps like Figma Community, Electron apps, or browser SPAs where OCR only returns sidebar/nav text. Returns natural-language description of what is visible on screen, including approximate pixel coordinates for UI elements. Example: visual_inspect('What Pokemon designs are shown in the Figma Community search results?')",
      "parameters": {
        "type": "object",
        "properties": {
          "question": {
            "type": "string",
            "description": "What to look for on screen, e.g. 'What search results are shown in the main area?' or 'Where is the search bar and what text is in it?'"
          },
          "resize_width": {
            "type": "integer",
            "description": "Width to resize screenshot before sending (default 1280). Lower = faster/cheaper; higher = more detail for small text."
          }
        },
        "required": ["question"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "visual_click",
      "description": "Find a UI element by visual description and click it using kimi-k2.6 Vision. Works for WebGL/canvas/Electron UIs where hybrid_locate_click fails (e.g. Figma Community search bar, Electron app content, browser SPA buttons). Provide window_hint to crop the screenshot to just that window before sending — more accurate, cheaper, and guaranteed to click inside the right window. Example: visual_click('search bar in Figma Community', window_hint='Figma')",
      "parameters": {
        "type": "object",
        "properties": {
          "description": {
            "type": "string",
            "description": "Visual description of what to find and click, e.g. 'search bar in Figma Community main area' or 'Community tab in left sidebar'"
          },
          "window_hint": {
            "type": "string",
            "description": "Partial window title to crop screenshot to (e.g. 'Figma', 'Chrome'). Uses the Win32 window graph to find the window bounds and crop before sending to vision. Strongly recommended for accuracy."
          },
          "resize_width": {
            "type": "integer",
            "description": "Width to resize image before sending to vision API (default 1280). Applied after cropping."
          },
          "duration": {
            "type": "number",
            "description": "Mouse movement smoothness in seconds (default 0.8). Higher = slower/more natural."
          }
        },
        "required": ["description"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "get_window_stack",
      "description": "Return the ordered list of windows with their z-depth, bounds, and titles.",
      "parameters": {"type": "object", "properties": {}}
    }
  }
]

# Lazy-loaded MCP bridge and plugin tools — initialized on first dispatch call
# to prevent asyncio thread deadlocks when Docker Desktop isn't running.
_mcp_bridge = None
_tools_extended = False

def _ensure_tools_loaded():
    global _mcp_bridge, _tools_extended, TOOL_DEFINITIONS
    if _tools_extended:
        return
    _tools_extended = True
    try:
        from core.system.mcp_bridge import JarvisMCPBridge
        _mcp_bridge = JarvisMCPBridge()
        TOOL_DEFINITIONS.extend(_mcp_bridge.get_mcp_tool_definitions())
    except Exception as me:
        import logging
        logging.getLogger(__name__).warning(f"MCP bridge init failed: {me}")
    try:
        from core.system.plugin_loader import plugin_loader
        if plugin_loader.tool_definitions:
            TOOL_DEFINITIONS.extend(plugin_loader.tool_definitions)
    except Exception as pe:
        import logging
        logging.getLogger(__name__).warning(f"Failed loading plugin tool definitions: {pe}")

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

def dispatch(fn_name: str, args: dict, orch_agent=None):
    """Wrapped tool dispatch with circuit breaker protection and spatial context checks"""
    _ensure_tools_loaded()
    import os
    import time
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Desktop/GUI automation tools deliberately change window context — exempt them from the Cortex.
    # The Cortex is designed to protect shell/file ops from running in wrong apps, not to block
    # intentional window navigation (pressing WIN, clicking apps, etc.)
    _CORTEX_EXEMPT = {
        "brain_query", "brain_write", "vocab_learn", "vocab_lookup", "read_file", "list_dir", "run_command",
        "smart_fill", "agent_view", "agent_cursor",
        # GUI tools — these ARE the context switching, exempting them is intentional:
        "desktop_smooth_click", "desktop_type_text", "desktop_press_keys", "desktop_scroll",
        "desktop_focus_window", "desktop_get_active_window", "desktop_batch_actions",
        "desktop_screenshot", "desktop_get_ui_tree", "desktop_interact_with_element",
        "hybrid_locate_click",
        "visual_servo_click", "browser_click", "browser_navigate", "browser_screenshot",
        "screen_imprint", "screen_ocr", "visual_inspect", "visual_click", "get_3d_window_graph", "get_window_stack",
    }
    # Check spatial context home before executing any mutating tool
    if os.environ.get("JARVIS_CI") != "true" and fn_name not in _CORTEX_EXEMPT:
        try:
            from core.orchestrator.dag import get_orchestrator
            orch = orch_agent or get_orchestrator()
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
    elif fn_name == "vocab_learn":                                     # Phase 22f
        from core.system.visual_vocab import vocab_learn
        return vocab_learn(args.get("heading", ""), args.get("content", ""))
    elif fn_name == "vocab_lookup":                                    # Phase 22h
        from core.system.visual_vocab import vocab_lookup
        return vocab_lookup(args.get("category", ""))
    elif fn_name == "smart_fill":                                      # Phase 24
        from tools.virtual_input import smart_fill
        return smart_fill(
            args.get("field_description", ""),
            args.get("text", ""),
            args.get("window_hint"),
            bool(args.get("press_enter", False)),
        )
    elif fn_name == "agent_view":                                      # Phase 24
        from tools.agent_view import agent_view_tool
        return agent_view_tool(args.get("action", "latest"), bool(args.get("open_file", False)))
    elif fn_name == "agent_cursor":                                    # Phase 24
        from tools.agent_cursor import agent_cursor_tool
        return agent_cursor_tool(args.get("action", "status"))
    elif fn_name == "delegate_task":
        from core.orchestrator.dag import run_dag
        result = run_dag(args.get("task"), dry_run=args.get("dry_run", False))
        return json.dumps(result, indent=2, default=str)
    elif fn_name == "visual_servo_click":
        from tools.visual_servo import visual_servo_click
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
    elif fn_name == "hybrid_locate_click":                          # Phase 22c
        from tools.hybrid_cursor import hybrid_locate_click
        return hybrid_locate_click(
            args.get("target", ""),
            args.get("window_hint"),
            args.get("verify_text"),
            int(args.get("max_retries", 2)),
        )
    elif fn_name == "screen_imprint":
        from core.system.screen_imprint import ScreenImprintGraph
        return json.dumps(ScreenImprintGraph().imprint(), indent=2)
    elif fn_name == "screen_ocr":
        # Fix: was calling async JarvisScreenReader().read_all_text() synchronously.
        # Replaced with direct mss + pytesseract sync implementation.
        try:
            import mss as _mss
            import pytesseract as _tess
            from PIL import Image as _Image
            if sys.platform == "win32":
                _tess_bin = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                if os.path.exists(_tess_bin):
                    if hasattr(_tess, "pytesseract"):
                        _tess.pytesseract.tesseract_cmd = _tess_bin
                    else:
                        _tess.tesseract_cmd = _tess_bin
            with _mss.mss() as _sct:
                _raw = _sct.grab(_sct.monitors[1])
                _img = _Image.frombytes("RGB", (_raw.width, _raw.height), _raw.bgra, "raw", "BGRX")
            _text = _tess.image_to_string(_img)
            _data = _tess.image_to_data(_img, output_type=_tess.Output.DICT)
            _words = [
                {"text": t, "x": l + w // 2, "y": tp + h // 2, "conf": c}
                for t, l, tp, w, h, c in zip(
                    _data["text"], _data["left"], _data["top"],
                    _data["width"], _data["height"], _data["conf"]
                )
                if t.strip() and int(c) > 40
            ]
            return json.dumps({"raw_text": _text, "words": _words}, indent=2)
        except Exception as _e:
            return json.dumps({"error": str(_e)}, indent=2)
    elif fn_name == "visual_inspect":                                 # Phase 22d
        from tools.visual_inspect import visual_inspect
        return visual_inspect(
            args.get("question", "What is currently visible on screen?"),
            int(args.get("resize_width", 1280)),
        )
    elif fn_name == "visual_click":                                   # Phase 22e/f
        from tools.visual_click import visual_click
        return visual_click(
            args.get("description", ""),
            args.get("window_hint"),                                 # Phase 22f
            int(args.get("resize_width", 1280)),
            float(args.get("duration", 0.8)),
        )
    elif fn_name == "get_window_stack":
        # Fix: was calling async JarvisScreenReader().read_window_stack() synchronously.
        # Replaced with existing sync ctypes implementation in tools/windows.py.
        from tools.windows import get_window_stack as _gws
        return json.dumps(_gws(), indent=2)
    elif fn_name.startswith("mcp__"):
        parts = fn_name.split("__", 2)
        if len(parts) == 3 and _mcp_bridge is not None:
            server, tool = parts[1], parts[2]
            return _mcp_bridge.execute_mcp_tool(server, tool, args)
        else:
            raise ValueError(f"Invalid MCP tool name: {fn_name}")
    else:
        raise ValueError(f"Unknown tool function: {fn_name}")


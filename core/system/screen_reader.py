import sys
# core/system/screen_reader.py
import win32gui
import win32process
import psutil
import asyncio
import aiohttp
import json
import websockets
from typing import Dict, List, Any
from core.system.llm_adapter import call_llm

class JarvisScreenReader:
    """
    Reads everything on screen using graph extraction.
    Uses Win32 window traversal and calls local LLM for visual semantic synthesis.
    """
    
    def __init__(self):
        pass

    async def read_screen(self) -> Dict[str, Any]:
        """
        Full screen understanding in one call.
        Returns structured semantic graph of everything visible.
        """
        print(f"[TRACE] core.system.screen_reader.JarvisScreenReader.read_screen: enter", file=sys.stderr, flush=True)
        active_hwnd = win32gui.GetForegroundWindow()
        
        screen_graph = {
            "active_app":  await self._read_active_app(active_hwnd),
            "windows":     await self._read_window_stack(),
            "native_ui":   await self._read_accessibility_tree(active_hwnd),
            "text":        await self._read_all_text(active_hwnd),
            "web_content": await self._read_web_content(),
            "summary":     None
        }
        
        # Let Gemma4 reason about what it all means
        screen_graph["summary"] = await self._synthesize_summary(screen_graph)
        return screen_graph

    async def _read_active_app(self, hwnd: int) -> Dict[str, Any]:
        print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_active_app: enter", file=sys.stderr, flush=True)
        if not hwnd:
            return {}
        try:
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            return {
                "hwnd": hwnd,
                "title": title,
                "process_name": proc.name(),
                "pid": pid,
                "rect": {"x": rect[0], "y": rect[1], "w": rect[2]-rect[0], "h": rect[3]-rect[1]}
            }
        except Exception as e:
            print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_active_app: except {str(e)[:80]}", file=sys.stderr, flush=True)
            return {"error": str(e)}

    async def _read_window_stack(self) -> List[Dict[str, Any]]:
        print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_window_stack: enter", file=sys.stderr, flush=True)
        windows = []
        def enum_win(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    try:
                        rect = win32gui.GetWindowRect(hwnd)
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        proc = psutil.Process(pid)
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "process_name": proc.name(),
                            "rect": {"x": rect[0], "y": rect[1], "w": rect[2]-rect[0], "h": rect[3]-rect[1]}
                        })
                    except Exception:
                        print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_window_stack.enum_win: except Exception", file=sys.stderr, flush=True)
                        pass
        try:
            win32gui.EnumWindows(enum_win, None)
        except Exception:
            print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_window_stack: except Exception", file=sys.stderr, flush=True)
            pass
        return windows

    async def _read_accessibility_tree(self, hwnd: int) -> List[Dict[str, Any]]:
        """Traverse child controls to extract semantic UI components recursively."""
        print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_accessibility_tree: enter", file=sys.stderr, flush=True)
        children = []
        if not hwnd:
            return children
            
        def enum_child(child_hwnd, extra):
            try:
                class_name = win32gui.GetClassName(child_hwnd)
                text = win32gui.GetWindowText(child_hwnd)
                rect = win32gui.GetWindowRect(child_hwnd)
                children.append({
                    "hwnd": child_hwnd,
                    "class": class_name,
                    "text": text,
                    "rect": {"x": rect[0], "y": rect[1], "w": rect[2]-rect[0], "h": rect[3]-rect[1]}
                })
            except Exception:
                print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_accessibility_tree.enum_child: except Exception", file=sys.stderr, flush=True)
                pass
        
        try:
            win32gui.EnumChildWindows(hwnd, enum_child, None)
        except Exception:
            print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_accessibility_tree: except Exception", file=sys.stderr, flush=True)
            pass
        return children

    async def _read_all_text(self, hwnd: int) -> List[str]:
        """Compile all structural texts from controls."""
        print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_all_text: enter", file=sys.stderr, flush=True)
        tree = await self._read_accessibility_tree(hwnd)
        texts = []
        for elem in tree:
            txt = elem.get("text", "").strip()
            if txt and txt not in texts:
                texts.append(txt)
        return texts

    async def _read_web_content(self) -> Dict[str, Any]:
        """Connect to Chrome/Edge via Chrome DevTools Protocol to extract browser DOM."""
        print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_web_content: enter", file=sys.stderr, flush=True)
        active_hwnd = win32gui.GetForegroundWindow()
        if not active_hwnd:
            return {"status": "no_active_window"}
            
        try:
            active_title = win32gui.GetWindowText(active_hwnd).lower()
        except Exception:
            print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_web_content: except Exception", file=sys.stderr, flush=True)
            return {"status": "cannot_read_window_title"}
            
        if not any(b in active_title for b in ["chrome", "edge", "chromium"]):
            return {"status": "no_browser_active"}
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:9222/json") as resp:
                    if resp.status != 200:
                        return {
                            "status": "cdp_not_available",
                            "hint": "Launch browser with --remote-debugging-port=9222"
                        }
                    tabs = await resp.json()
                    if not tabs:
                        return {"status": "no_tabs_found"}
                        
                    # Target the first active page tab
                    page_tab = None
                    for tab in tabs:
                        if tab.get("type") == "page":
                            page_tab = tab
                            break
                            
                    if not page_tab:
                        page_tab = tabs[0]
                        
                    ws_url = page_tab.get("webSocketDebuggerUrl")
                    if not ws_url:
                        return {"status": "no_websocket_url"}
                        
                    # Extract page interactive layout via CDP websockets
                    async with websockets.connect(ws_url) as ws:
                        # Extract DOM inputs, links, buttons, and full innerText
                        eval_expr = """
                        (function() {
                            const elements = Array.from(document.querySelectorAll('a, button, input, select, textarea')).map(el => {
                                return {
                                    tag: el.tagName,
                                    id: el.id || "",
                                    className: el.className || "",
                                    text: el.innerText || el.value || "",
                                    placeholder: el.placeholder || ""
                                };
                            }).filter(x => x.text || x.placeholder);
                            
                            return {
                                title: document.title,
                                url: document.location.href,
                                textSnippet: document.body.innerText.substring(0, 1000),
                                elements: elements.slice(0, 40)
                            };
                        })()
                        """
                        cmd = {
                            "id": 1,
                            "method": "Runtime.evaluate",
                            "params": {
                                "expression": eval_expr,
                                "returnByValue": True
                            }
                        }
                        await ws.send(json.dumps(cmd))
                        raw_res = await ws.recv()
                        res = json.loads(raw_res)
                        
                        result_payload = res.get("result", {}).get("result", {}).get("value", {})
                        return {
                            "status": "SUCCESS",
                            "title": result_payload.get("title", ""),
                            "url": result_payload.get("url", ""),
                            "text_snippet": result_payload.get("textSnippet", ""),
                            "interactive_elements": result_payload.get("elements", [])
                        }
        except aiohttp.ClientConnectionError:
            print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_web_content: except ClientConnectionError", file=sys.stderr, flush=True)
            return {"status": "cdp_not_available", "hint": "Launch browser with --remote-debugging-port=9222"}
        except Exception as e:
            print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._read_web_content: except {str(e)[:80]}", file=sys.stderr, flush=True)
            return {"status": "error", "message": str(e)}

    async def _synthesize_summary(self, graph: Dict[str, Any]) -> str:
        print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._synthesize_summary: enter", file=sys.stderr, flush=True)
        active = graph["active_app"]
        controls = [f"{c['class']}: '{c['text']}'" for c in graph["native_ui"][:30] if c.get("text")]
        
        web_info = ""
        if graph.get("web_content", {}).get("status") == "SUCCESS":
            web = graph["web_content"]
            web_info = (
                f"\nACTIVE WEBPAGE:\n"
                f"- Title: {web.get('title')}\n"
                f"- URL: {web.get('url')}\n"
                f"- Snippet: {web.get('text_snippet', '')[:300]}\n"
                f"- Interactive Nodes: {len(web.get('interactive_elements', []))} found"
            )
            
        prompt = f"""You are the visual cortex of an AI agent. Analyze the active screen structure and synthesize a concise, high-level summary of what the user is looking at and what action elements are visible.

ACTIVE APPLICATION:
- Title: {active.get('title')}
- Process: {active.get('process_name')}{web_info}

VISIBLE UI ELEMENTS & CONTROLS:
{chr(10).join(controls)}

Provide a single paragraph detailing:
1. The type of window/page open (e.g., "A VS Code window editing python files", "A Chrome browser viewing job search page").
2. Key actionable zones (buttons, fields, forms).
3. The overall user context/intent.
"""
        try:
            msg = [{"role": "user", "content": prompt}]
            response = call_llm(msg)
            return response.get("content", "").strip()
        except Exception as e:
            print(f"[TRACE] core.system.screen_reader.JarvisScreenReader._synthesize_summary: except {str(e)[:80]}", file=sys.stderr, flush=True)
            return f"Summary synthesis failed: {e}"

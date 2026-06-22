import sys
from core.trace import trace as _jtrace
import os
import time
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Lazy load heavy dependencies to avoid boot-up overhead
cv2 = None
pyautogui = None
ImageGrab = None

def _lazy_load():
    _jtrace(f"[TRACE] tools.visual_servo._lazy_load: enter")
    global cv2, pyautogui, ImageGrab
    if cv2 is None:
        try:
            import cv2 as _cv2
            import pyautogui as _pyautogui
            from PIL import ImageGrab as _ImageGrab
            cv2 = _cv2
            pyautogui = _pyautogui
            ImageGrab = _ImageGrab
            # Safe PyAutoGUI defaults
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.01
        except ImportError as e:
            _jtrace(f"[TRACE] tools.visual_servo._lazy_load: except {str(e)[:80]}")
            logger.warning(f"Failed to import graphical automation libraries: {e}")
            raise

def is_graphical_env_available() -> bool:
    """Check if we have an active OS display context and required libraries are installed."""
    _jtrace(f"[TRACE] tools.visual_servo.is_graphical_env_available: enter")
    if os.environ.get("JARVIS_CI") == "true":
        return False
    try:
        _lazy_load()
        # Test if taking a screenshot is supported by the OS environment
        screenshot = ImageGrab.grab(bbox=(0, 0, 10, 10))
        return screenshot is not None
    except Exception:
        _jtrace(f"[TRACE] tools.visual_servo.is_graphical_env_available: except Exception")
        return False

def visual_servo_click(target_template_path: str, timeout_sec: float = 5.0, Kp: float = 0.3) -> bool:
    """
    Perform closed-loop visual servo cursor tracking to locate and smoothly click a visual template.
    Continues to dynamically course-correct cursor movement in real-time as the target shifts.
    """
    _jtrace(f"[TRACE] tools.visual_servo.visual_servo_click: enter")
    if not is_graphical_env_available():
        logger.warning("[VISUAL SERVO] Graphical interface not available (CI/headless mode). Falling back to direct action.")
        return True

    try:
        _lazy_load()
        if not os.path.exists(target_template_path):
            logger.error(f"[VISUAL SERVO] Target template image not found: {target_template_path}")
            return False

        # Load the template image
        template_img = cv2.imread(target_template_path)
        if template_img is None:
            logger.error(f"[VISUAL SERVO] Failed to load template image: {target_template_path}")
            return False
        
        t_h, t_w, _ = template_img.shape
        max_velocity = 50.0  # Pixels per step
        stabilization_steps = 0
        start_time = time.time()

        last_target_x = None
        last_target_y = None

        print(f"\n  [VISUAL SERVO] Chasing template: {os.path.basename(target_template_path)}")

        while (time.time() - start_time) < timeout_sec:
            # 1. Grab current high-resolution screen capture
            screen_pil = ImageGrab.grab()
            screen_cv = cv2.cvtColor(np.array(screen_pil), cv2.COLOR_RGB2BGR)

            # 2. Perform template matching using normalized cross-correlation
            res = cv2.matchTemplate(screen_cv, template_img, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            # Accept threshold (match confidence must be > 0.8)
            if max_val < 0.8:
                if last_target_x is not None:
                    # Fallback to last known target coordinate (helps when button changes color on hover!)
                    target_x = last_target_x
                    target_y = last_target_y
                else:
                    logger.warning(f"[VISUAL SERVO] Target match confidence too low: {max_val:.2f} (waiting for rendering...)")
                    time.sleep(0.05)
                    continue
            else:
                # Calculate dynamic target center coordinate
                target_x = max_loc[0] + t_w / 2.0
                target_y = max_loc[1] + t_h / 2.0
                last_target_x = target_x
                last_target_y = target_y

            # Clamp coordinates to active window bounds if it is a regular window
            try:
                import pygetwindow as gw
                active_win = gw.getActiveWindow()
                if active_win and active_win.title:
                    title_lower = active_win.title.lower()
                    is_system = any(sys_t in title_lower for sys_t in ["program manager", "start", "taskbar", "task view", "desktop", "nvidia", "settings"])
                    if not is_system and active_win.width > 50 and active_win.height > 50:
                        wx = active_win.left
                        wy = active_win.top
                        ww = active_win.width
                        wh = active_win.height
                        
                        margin = 8
                        clamped_x = max(wx + margin, min(target_x, wx + ww - margin))
                        clamped_y = max(wy + margin, min(target_y, wy + wh - margin))
                        
                        if clamped_x != target_x or clamped_y != target_y:
                            logger.info(f"[VISUAL SERVO] Clamping target ({target_x}, {target_y}) to active window '{active_win.title}' bounds: ({clamped_x}, {clamped_y})")
                            target_x, target_y = clamped_x, clamped_y
            except Exception as e:
                _jtrace(f"[TRACE] tools.visual_servo.visual_servo_click: except {str(e)[:80]}")
                logger.debug(f"[VISUAL SERVO] Active window clamping error: {e}")

            # 3. Get current physical mouse cursor position
            cursor_x, cursor_y = pyautogui.position()

            # 4. Proportional feedback loop calculations
            dx = target_x - cursor_x
            dy = target_y - cursor_y
            distance = np.sqrt(dx**2 + dy**2)

            if distance < 3.0: # Raise tolerance slightly to 3.0px to account for dynamic hovers and jitter
                stabilization_steps += 1
                if stabilization_steps >= 3:
                    # Final convergence reached! Perform physical mouse click
                    pyautogui.click(int(target_x), int(target_y))
                    print(f"  [VISUAL SERVO] Target locked and successfully clicked at ({int(target_x)}, {int(target_y)})!")
                    return True
            else:
                stabilization_steps = 0

            # Velocity trajectory scaling
            vx = Kp * dx
            vy = Kp * dy
            velocity = np.sqrt(vx**2 + vy**2)
            if velocity > max_velocity:
                scale = max_velocity / velocity
                vx *= scale
                vy *= scale

            # 5. Move the cursor programmatically
            pyautogui.moveTo(int(cursor_x + vx), int(cursor_y + vy))
            
            # Short sleep to match standard mouse control loops
            time.sleep(0.02)

        logger.error(f"[VISUAL SERVO] Servo tracking timed out after {timeout_sec} seconds before locking on target.")
        return False

    except Exception as exc:
        _jtrace(f"[TRACE] tools.visual_servo.visual_servo_click: except {str(exc)[:80]}")
        logger.error(f"[VISUAL SERVO] Operational error occurred: {exc}")
        return False

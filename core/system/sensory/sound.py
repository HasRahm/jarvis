import sys
import os
import logging

logger = logging.getLogger(__name__)

HAS_WIN32 = False
win32gui = None
win32process = None
try:
    if os.name == "nt":
        import win32gui
        import win32process
        HAS_WIN32 = True
except ImportError:
    print(f"[TRACE] core.system.sensory.sound.<module>: except ImportError", file=sys.stderr, flush=True)
    pass

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    print(f"[TRACE] core.system.sensory.sound.<module>: except ImportError", file=sys.stderr, flush=True)
    HAS_PSUTIL = False

HAS_PYCAW = False
try:
    from pycaw.pycaw import AudioUtilities
    HAS_PYCAW = True
except ImportError:
    print(f"[TRACE] core.system.sensory.sound.<module>: except ImportError", file=sys.stderr, flush=True)
    pass

class SoundLayer:
    """Audio environment signals — spatial location via sound."""
    
    def read(self) -> dict:
        print(f"[TRACE] core.system.sensory.sound.SoundLayer.read: enter", file=sys.stderr, flush=True)
        active_audio = self._get_active_audio_sessions()
        keyboard_target = self._get_keyboard_target_process()
        recent_sounds = [] # Placeholder for system sound events
        
        return {
            "active_audio": active_audio,
            "keyboard_target": keyboard_target,
            "recent_sounds": recent_sounds,
            "sound_profile": self._classify_profile(active_audio)
        }
        
    def _get_active_audio_sessions(self) -> list:
        print(f"[TRACE] core.system.sensory.sound.SoundLayer._get_active_audio_sessions: enter", file=sys.stderr, flush=True)
        sessions_info = []
        if not HAS_PYCAW:
            return sessions_info
            
        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                volume = session.SimpleAudioVolume
                if session.Process and volume.GetMute() == 0:
                    sessions_info.append({
                        "process": session.Process.name(),
                        "volume": volume.GetMasterVolume()
                    })
        except Exception as e:
            print(f"[TRACE] core.system.sensory.sound.SoundLayer._get_active_audio_sessions: except {str(e)[:80]}", file=sys.stderr, flush=True)
            logger.debug(f"[Sound] Failed to get active audio sessions: {e}")
            
        return sessions_info
        
    def _get_keyboard_target_process(self) -> str:
        print(f"[TRACE] core.system.sensory.sound.SoundLayer._get_keyboard_target_process: enter", file=sys.stderr, flush=True)
        if not HAS_WIN32 or not HAS_PSUTIL:
            return "unknown"
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                return proc.name()
        except Exception:
            print(f"[TRACE] core.system.sensory.sound.SoundLayer._get_keyboard_target_process: except Exception", file=sys.stderr, flush=True)
            pass
        return "unknown"
        
    def _classify_profile(self, sessions: list) -> str:
        """Classify the audio environment signature."""
        print(f"[TRACE] core.system.sensory.sound.SoundLayer._classify_profile: enter", file=sys.stderr, flush=True)
        names = [s["process"].lower() for s in sessions if "process" in s]
        if "chrome.exe" in names or "msedge.exe" in names:
            return "browser"
        if "code.exe" in names:
            return "coding"
        if "slack.exe" in names:
            return "messaging"
        if not names:
            return "silent"
        return "mixed"

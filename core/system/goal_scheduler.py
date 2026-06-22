import sys
from core.trace import trace as _jtrace
import os
import json
import time
import logging
import threading
from datetime import datetime
from brain.query import brain_query

logger = logging.getLogger(__name__)

class GoalScheduler:
    def __init__(self, check_interval_sec: float = 60.0):
        self.check_interval = check_interval_sec
        self.running = False
        self.thread = None
        self.goals = []
        self.last_fired = {} # goal_name -> timestamp of last fire to prevent double firing in same minute

    def add_goal(self, name: str, trigger: dict, task: str):
        _jtrace(f"[TRACE] core.system.goal_scheduler.GoalScheduler.add_goal: enter")
        self.goals.append({
            "name": name,
            "trigger": trigger,
            "task": task
        })
        logger.info(f"[Scheduler] Registered goal: {name} (Trigger: {trigger})")

    def start(self):
        _jtrace(f"[TRACE] core.system.goal_scheduler.GoalScheduler.start: enter")
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True, name="jarvis-goal-scheduler")
        self.thread.start()
        logger.info("[Scheduler] Started background goal scheduler daemon.")

    def stop(self):
        _jtrace(f"[TRACE] core.system.goal_scheduler.GoalScheduler.stop: enter")
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("[Scheduler] Stopped background goal scheduler daemon.")

    def _loop(self):
        while self.running:
            try:
                self._check_triggers()
            except Exception as e:
                _jtrace(f"[TRACE] core.system.goal_scheduler.GoalScheduler._loop: except {str(e)[:80]}")
                logger.error(f"[Scheduler] Error checking triggers: {e}")
            # Sleep in small increments to respond quickly to shutdown/stop signals
            elapsed = 0.0
            while elapsed < self.check_interval and self.running:
                time.sleep(0.5)
                elapsed += 0.5

    def _check_triggers(self):
        _jtrace(f"[TRACE] core.system.goal_scheduler.GoalScheduler._check_triggers: enter")
        now = datetime.now()
        current_minute = now.strftime("%Y-%m-%d %H:%M")
        
        for goal in self.goals:
            name = goal["name"]
            trigger = goal["trigger"]
            trigger_type = trigger.get("type")
            
            # Prevent firing twice in the same minute
            if self.last_fired.get(name) == current_minute:
                continue
                
            fired = False
            if trigger_type == "cron":
                schedule = trigger.get("schedule", "")
                if self._match_cron(schedule, now):
                    fired = True
            elif trigger_type == "condition":
                check_str = trigger.get("check", "")
                if self._check_condition(check_str):
                    fired = True
            elif trigger_type == "github_event":
                # Simulated/mocked event listener
                # In prod, this can listen to webhooks or query GitHub API
                pass
                
            if fired:
                self.last_fired[name] = current_minute
                logger.info(f"[Scheduler] Trigger fired for goal '{name}': {goal['task']}")
                # Run the task asynchronously via run_dag
                threading.Thread(target=self._run_goal_task, args=(goal["task"],), daemon=True).start()

    def _match_cron(self, schedule: str, dt) -> bool:
        _jtrace(f"[TRACE] core.system.goal_scheduler.GoalScheduler._match_cron: enter")
        parts = schedule.split()
        if len(parts) != 5:
            return False
        
        # Minute
        if parts[0] != "*" and int(parts[0]) != dt.minute:
            return False
        # Hour
        if parts[1] != "*" and int(parts[1]) != dt.hour:
            return False
        # Day of month
        if parts[2] != "*" and int(parts[2]) != dt.day:
            return False
        # Month
        if parts[3] != "*" and int(parts[3]) != dt.month:
            return False
        # Day of week (0-6, Sunday=0 or 7 depending on standard, python is Monday=0 to Sunday=6)
        if parts[4] != "*":
            dow = int(parts[4])
            python_dow = dt.weekday()
            mapped_cron_dow = (python_dow + 1) % 7 # 0 is Sunday, 1 is Monday, 6 is Saturday
            if dow != mapped_cron_dow:
                return False
                
        return True

    def _check_condition(self, check_str: str) -> bool:
        _jtrace(f"[TRACE] core.system.goal_scheduler.GoalScheduler._check_condition: enter")
        try:
            from brain.write import _GBRAIN_PATH
            import subprocess
            if _GBRAIN_PATH:
                cmd = [_GBRAIN_PATH, "list", "--limit", "100"]
                if os.name == "nt" and _GBRAIN_PATH.endswith(".cmd"):
                    cmd = ["cmd.exe", "/c"] + cmd
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    parts = check_str.split()
                    prefix = ""
                    for p in parts:
                        if "/" in p:
                            prefix = p.replace("*", "")
                            break
                    
                    for line in lines:
                        line_parts = line.split()
                        if not line_parts:
                            continue
                        slug = line_parts[0]
                        if prefix and slug.startswith(prefix):
                            from brain.get import brain_get
                            content = brain_get(slug)
                            match_all = True
                            for filter_term in parts:
                                if ":" in filter_term:
                                    key, val = filter_term.split(":", 1)
                                    if key not in content or val not in content:
                                        match_all = False
                                        break
                            if match_all:
                                return True
        except Exception:
            _jtrace(f"[TRACE] core.system.goal_scheduler.GoalScheduler._check_condition: except Exception")
            pass
        return False

    def _run_goal_task(self, task: str):
        try:
            logger.info(f"[Scheduler] Executing goal task: '{task}'")
            from core.orchestrator.dag import run_dag
            task_id = f"scheduled_task_{int(time.time())}"
            run_dag(task, task_id=task_id)
            logger.info(f"[Scheduler] Goal task completed: '{task}'")
        except Exception as e:
            _jtrace(f"[TRACE] core.system.goal_scheduler.GoalScheduler._run_goal_task: except {str(e)[:80]}")
            logger.error(f"[Scheduler] Error executing goal task '{task}': {e}")

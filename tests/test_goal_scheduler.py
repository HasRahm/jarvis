import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from core.system.goal_scheduler import GoalScheduler

def test_cron_matcher():
    scheduler = GoalScheduler()
    
    # 2026-06-05 03:00:00 (Friday)
    # python weekday() is Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
    # cron weekday mapping in goal_scheduler: (python_dow + 1) % 7 -> (4+1)%7 = 5 (Friday)
    dt = datetime(2026, 6, 5, 3, 0, 0)
    
    # Match all
    assert scheduler._match_cron("* * * * *", dt) is True
    
    # Match specific minute/hour
    assert scheduler._match_cron("0 3 * * *", dt) is True
    assert scheduler._match_cron("5 3 * * *", dt) is False
    assert scheduler._match_cron("0 4 * * *", dt) is False
    
    # Match day/month
    assert scheduler._match_cron("0 3 5 6 *", dt) is True
    assert scheduler._match_cron("0 3 6 6 *", dt) is False
    assert scheduler._match_cron("0 3 5 7 *", dt) is False
    
    # Match day of week (Friday=5 in cron where Sunday=0, Monday=1, etc. -> mapped_cron_dow = (4+1)%7 = 5)
    assert scheduler._match_cron("* * * * 5", dt) is True
    assert scheduler._match_cron("* * * * 4", dt) is False

@patch("core.system.goal_scheduler.GoalScheduler._run_goal_task")
def test_check_triggers_cron(mock_run):
    scheduler = GoalScheduler()
    scheduler.add_goal(
        name="cleanup",
        trigger={"type": "cron", "schedule": "0 2 * * *"},
        task="run disk cleanup"
    )
    
    # Try with non-matching time
    with patch("core.system.goal_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 5, 3, 0, 0)
        scheduler._check_triggers()
        mock_run.assert_not_called()
        
    # Try with matching time
    with patch("core.system.goal_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 5, 2, 0, 0)
        scheduler._check_triggers()
        mock_run.assert_called_once_with("run disk cleanup")

@patch("subprocess.run")
@patch("brain.get.brain_get")
def test_check_condition_trigger(mock_get, mock_run):
    # Setup mock subprocess output for gbrain list
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "jobs/1/status [page] 2026-06-04 22:00:00\njobs/2/status [page] 2026-06-04 22:01:00\n"
    mock_run.return_value = mock_proc
    
    # Setup mock brain_get return value
    # Filter matches "jobs/* status:failed"
    mock_get.return_value = '{"status": "failed", "job_id": 1}'
    
    with patch("brain.write._GBRAIN_PATH", "mock_gbrain"):
        scheduler = GoalScheduler()
        
        # Test matching condition
        assert scheduler._check_condition("jobs/* status:failed") is True
        
        # Test non-matching condition
        assert scheduler._check_condition("jobs/* status:success") is False

def test_scheduler_lifecycle():
    scheduler = GoalScheduler(check_interval_sec=0.1)
    assert scheduler.running is False
    
    scheduler.start()
    assert scheduler.running is True
    assert scheduler.thread is not None
    assert scheduler.thread.is_alive() is True
    
    scheduler.stop()
    assert scheduler.running is False

import os
import sys
import psutil
import httpx
from dotenv import load_dotenv

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(project_root, ".env"))

# Configure sys.path so we can import tools and core modules
sys.path.insert(0, project_root)
from tools.disk_cleanup import scan, safe_clean
from core.gemma4_loop import run_pc_optimization

HERMES_SECRET = os.getenv("HERMES_SECRET", "jarvis_hermes_2026")
HERMES_PORT = int(os.getenv("HERMES_PORT", "9000"))

def notify_user(text):
    print(f"[NOTIFICATION] {text}")
    try:
        url = f"http://localhost:{HERMES_PORT}/api/notify"
        headers = {"Authorization": f"Bearer {HERMES_SECRET}"}
        resp = httpx.post(url, json={"text": text}, headers=headers, timeout=5.0)
        if resp.status_code == 200:
            print("Successfully sent notification to Hermes.")
        else:
            print(f"Hermes notification failed with status: {resp.status_code}")
    except Exception as e:
        print(f"Could not connect to Hermes to send notification: {e}")

def main():
    cpu_percent = psutil.cpu_percent(interval=1.0)
    virtual_memory = psutil.virtual_memory()
    mem_percent = virtual_memory.percent
    
    print(f"Checking PC performance: CPU={cpu_percent}%, Memory={mem_percent}%")
    
    notifications = []
    
    # 1. High Memory Check & PC Optimization (Zombie processes)
    # If memory usage is high (>80%), kill lingering zombie development processes
    if mem_percent > 80:
        print("Memory usage exceeds 80%. Running process optimization...")
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            run_pc_optimization()
        opt_output = f.getvalue()
        print(opt_output)
        
        if "terminated" in opt_output:
            notifications.append("Memory usage was high. Jarvis terminated lingering development processes to reclaim RAM.")
            
    # 2. Disk Space Check & Cleanup
    # Scan disk usage and safely clean if temp/cache is large (> 1 GB)
    try:
        disk_data = scan()
        total_safe_mb = disk_data.get("total_safe_mb", 0.0)
        
        if total_safe_mb > 1000:
            print(f"Safe-to-clean disk files are large: {total_safe_mb} MB. Cleaning...")
            clean_result = safe_clean(dry_run=False)
            freed_mb = clean_result.get("mb_freed", 0.0)
            files_deleted = clean_result.get("files_deleted", 0)
            if freed_mb > 0:
                notifications.append(f"Disk space cleanup triggered. Jarvis safely removed {files_deleted} temporary files, freeing {freed_mb:.1f} MB.")
    except Exception as e:
        print(f"Disk scan/cleanup failed: {e}")
            
    # 3. Notification Routing
    if notifications:
        full_notification = " ".join(notifications)
        notify_user(full_notification)
    else:
        # If CPU is extremely high, we warn the user
        if cpu_percent > 90:
            notify_user(f"Alert: High CPU usage detected ({cpu_percent}%). Please check active applications.")

if __name__ == "__main__":
    main()

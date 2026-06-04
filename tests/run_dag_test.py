import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator.dag import run_dag

if __name__ == "__main__":
    task = "Create a users table in Supabase with id, email, created_at columns, then expose a POST /api/users endpoint that inserts a row and returns the new user"

    print(f"Running DAG test for task: {task}")
    result = run_dag(task, dry_run=False)
    print(json.dumps(result, indent=2))


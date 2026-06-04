"""Remove the AGENT_MODEL_BACKEND override from .env"""
import os

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
with open(env_path, "r") as f:
    lines = f.readlines()

with open(env_path, "w") as f:
    for line in lines:
        if "AGENT_MODEL_BACKEND" not in line:
            f.write(line)

print("Removed AGENT_MODEL_BACKEND override from .env")

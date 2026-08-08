import os
import subprocess
import sys

SERVICE = os.environ.get("SERVICE_NAME", "unknown")

print(f"[ENTRYPOINT] Starting {SERVICE}")

subprocess.run(sys.argv[1:], check=True)
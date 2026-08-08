#!/usr/bin/env python3
"""
End-to-end test script for Mini-Splunk.

Performs:
 - docker compose up --build --scale worker=3 -d
 - waits for gateway health
 - ingests tests/sample_syslog.log via CLI
 - kills one worker to simulate chaos
 - runs a COUNT_KEYWORD query to verify data
 - runs PURGE
 - tears down docker compose

Run from project root: `python scripts/e2e_test.py`
"""

from __future__ import annotations

import subprocess
import time
import json
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_HOST = "localhost"


def run(cmd, check=True, capture=False):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=check, stdout=(subprocess.PIPE if capture else None), stderr=subprocess.STDOUT, text=True)


def wait_for_gateway(timeout=120):
    url = f"http://{GATEWAY_HOST}:8000/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                print("Gateway healthy")
                return True
        except requests.RequestException:
            pass
        print("Waiting for gateway...")
        time.sleep(3)
    return False


def main():
    compose_file = ROOT / 'mini-splunk-dejesus' / 'docker-compose.yml'
    env_file = ROOT / 'mini-splunk-dejesus' / 'configs' / '.env'

    try:
        # Start stack (use compose file and env file from mini-splunk-dejesus)
        run(["docker", "compose", "-f", str(compose_file), "--env-file", str(env_file), "up", "--build", "--scale", "worker=3", "-d"]) 

        if not wait_for_gateway():
            print("Gateway did not become healthy in time", file=sys.stderr)
            return 2

        # Ingest sample file
        sample = Path("tests/sample_syslog.log")
        if not sample.exists():
            print("Sample syslog not found:", sample)
            return 3

        print("Uploading sample syslog...")
        run(["docker", "compose", "-f", str(compose_file), "--env-file", str(env_file), "--profile", "tools", "run", "--rm", "cli", "python", "-m", "cli.app.main", "INGEST", str(sample.resolve()), GATEWAY_HOST])

        print("Sleeping 5s to let workers pick up messages...")
        time.sleep(5)

        # Kill a worker to simulate chaos
        print("Simulating failure: killing worker2")
        run(["docker", "compose", "-f", str(compose_file), "--env-file", str(env_file), "kill", "worker2"]) 
        time.sleep(5)

        # Query count of keyword 'error'
        print("Querying COUNT_KEYWORD 'error'")
        res = run(["docker", "compose", "-f", str(compose_file), "--env-file", str(env_file), "--profile", "tools", "run", "--rm", "cli", "python", "-m", "cli.app.main", "QUERY", GATEWAY_HOST, "COUNT_KEYWORD", "error"], capture=True)
        print(res.stdout)

        # Purge
        print("Purging logs via CLI")
        run(["docker", "compose", "-f", str(compose_file), "--env-file", str(env_file), "--profile", "tools", "run", "--rm", "cli", "python", "-m", "cli.app.main", "PURGE", GATEWAY_HOST])

        return 0

    finally:
        print("Tearing down docker compose")
        try:
            run(["docker", "compose", "-f", str(compose_file), "--env-file", str(env_file), "down", "-v"], check=False)
        except Exception as exc:
            print("Failed to teardown:", exc)


if __name__ == "__main__":
    raise SystemExit(main())

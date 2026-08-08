#!/usr/bin/env python3
"""
Smoke test for the syslog parser. Runs locally without Docker.
"""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'mini-splunk-dejesus'))

from worker.app.parser import SyslogParser


def main():
    p = SyslogParser()

    sample = Path(ROOT / 'tests' / 'sample_syslog.log')
    if not sample.exists():
        print('sample file missing:', sample)
        return 2

    for line in sample.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        parsed = p.parse(line)
        print(json.dumps({'raw': line, 'parsed': parsed}, ensure_ascii=False))


if __name__ == '__main__':
    raise SystemExit(main())

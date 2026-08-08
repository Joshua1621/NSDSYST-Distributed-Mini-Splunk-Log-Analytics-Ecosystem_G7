#!/usr/bin/env python3
"""
Generates a synthetic BSD-style syslog file for testing INGEST, QUERY, and
chaos scenarios. Produces realistic variety across hosts, daemons,
severities, and message content so every QUERY subcommand has something
meaningful to search for.

Usage:
    python generate_sample_logs.py --lines 5000 --out big_sample.log
    python generate_sample_logs.py --lines 50 --out sample.log --seed 42

The generated file is deterministic given the same --seed, which is
useful for chaos testing: you can diff "lines in file" vs "documents in
Mongo after recovery" and know exactly what the expected count should be.
"""

import argparse
import random
from datetime import datetime, timedelta

HOSTS = ["webserver01", "webserver02", "dbserver01", "mymachine", "authgw01", "cacheserver01"]

DAEMONS = [
    ("sshd", "Failed password for invalid user {user} from {ip} port {port} ssh2"),
    ("sshd", "Accepted password for {user} from {ip} port {port} ssh2"),
    ("su", "'su root' failed for {user} on /dev/pts/{n}"),
    ("cron", "({user}) CMD ({cmd})"),
    ("nginx", "GET /api/v1/{resource} HTTP/1.1 200"),
    ("nginx", "connection timed out while reading response header from upstream"),
    ("systemd", "Started {service}."),
    ("systemd", "{service}.service: Main process exited, code=exited, status=1/FAILURE"),
    ("kernel", "TCP: request_sock_TCP: Possible SYN flooding on port {port}. Sending cookies."),
    ("postgres", "connection received: host={ip} port={port}"),
    ("postgres", "FATAL:  password authentication failed for user \"{user}\""),
    ("dockerd", "Container {cid} OOM-killed (memory limit exceeded)"),
]

USERS = ["admin", "root", "deploy", "reyvin", "backup", "guest", "svc_monitor"]
RESOURCES = ["users", "orders", "sessions", "metrics", "healthz", "logs"]
SERVICES = ["nginx", "postgresql", "docker", "cron", "sshd"]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def random_ip(rng: random.Random) -> str:
    return ".".join(str(rng.randint(1, 254)) for _ in range(4))


def format_syslog_timestamp(dt: datetime) -> str:
    # BSD syslog format: "Mon DD HH:MM:SS" -- day is space-padded, not zero-padded
    day = f"{dt.day:2d}"
    return f"{MONTHS[dt.month - 1]} {day} {dt.strftime('%H:%M:%S')}"


def generate_line(rng: random.Random, dt: datetime) -> str:
    host = rng.choice(HOSTS)
    daemon, template = rng.choice(DAEMONS)
    pid = rng.randint(100, 65000)

    message = template.format(
        user=rng.choice(USERS),
        ip=random_ip(rng),
        port=rng.randint(1024, 65535),
        n=rng.randint(0, 9),
        cmd=rng.choice(["/usr/bin/backup.sh", "/usr/bin/certbot renew", "rm -rf /tmp/cache/*"]),
        resource=rng.choice(RESOURCES),
        service=rng.choice(SERVICES),
        cid=f"{rng.randint(0, 0xffffff):06x}",
    )

    timestamp = format_syslog_timestamp(dt)
    return f"{timestamp} {host} {daemon}[{pid}]: {message}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lines", type=int, default=1000, help="number of log lines to generate")
    parser.add_argument("--out", type=str, default="sample.log", help="output file path")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducibility")
    parser.add_argument(
        "--days-back", type=int, default=3,
        help="spread timestamps over this many days ending now (for SEARCH_DATE testing)",
    )
    parser.add_argument(
        "--malformed-rate", type=float, default=0.0,
        help="fraction (0-1) of lines to intentionally corrupt, to test parser error handling",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    now = datetime.now()
    start = now - timedelta(days=args.days_back)
    span_seconds = int((now - start).total_seconds())

    lines = []
    for _ in range(args.lines):
        offset = rng.randint(0, span_seconds)
        dt = start + timedelta(seconds=offset)
        line = generate_line(rng, dt)

        if rng.random() < args.malformed_rate:
            # Corrupt the line in a way that will fail the syslog regex,
            # to exercise the worker's SyslogParseError skip path.
            line = "GARBAGE LINE THAT DOES NOT MATCH SYSLOG FORMAT " + line[:20]

        lines.append(line)

    # Sort by embedded timestamp isn't required (syslog files aren't
    # always ordered), so we leave them in random order -- this also
    # exercises that the parser doesn't assume ordering.
    with open(args.out, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {len(lines)} lines to {args.out}")
    if args.malformed_rate > 0:
        expected_malformed = int(len(lines) * args.malformed_rate)
        print(f"  (~{expected_malformed} expected malformed lines at rate {args.malformed_rate}; "
              f"actual count varies randomly per run, use for parser error-path testing "
              f"not exact accounting)")
    print(f"Timestamp range: {start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}")
    print(f"Hosts used: {', '.join(HOSTS)}")
    print(f"Daemons used: {', '.join(sorted(set(d for d, _ in DAEMONS)))}")


if __name__ == "__main__":
    main()

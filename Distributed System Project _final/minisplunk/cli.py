from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from minisplunk.transport import GatewayClient, GatewayError, GatewayResponse


SEARCH_COMMANDS = {
    "SEARCH_DATE": "date",
    "SEARCH_HOST": "host",
    "SEARCH_DAEMON": "daemon",
    "SEARCH_SEVERITY": "severity",
    "SEARCH_KEYWORD": "keyword",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minisplunk",
        description="CLI forwarder for the distributed Mini-Splunk project.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("INGEST", help="Send a local syslog file to the gateway.")
    ingest.add_argument("file_path", type=Path)
    ingest.add_argument("gateway_ip")

    query = subparsers.add_parser("QUERY", help="Run a distributed search through the gateway.")
    query.add_argument("gateway_ip")
    query.add_argument("query_type", choices=[*SEARCH_COMMANDS.keys(), "COUNT_KEYWORD"])
    query.add_argument("value")

    purge = subparsers.add_parser("PURGE", help="Delete all indexed log entries.")
    purge.add_argument("gateway_ip")

    return parser


def run(argv: Sequence[str], client_factory: type[GatewayClient] = GatewayClient) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "INGEST":
            response = _run_ingest(args.file_path, args.gateway_ip, client_factory)
        elif args.command == "QUERY":
            response = _run_query(args.gateway_ip, args.query_type, args.value, client_factory)
        elif args.command == "PURGE":
            response = client_factory(args.gateway_ip).purge()
        else:
            parser.error(f"Unsupported command: {args.command}")
    except (GatewayError, FileNotFoundError, IsADirectoryError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(response.body, indent=2, sort_keys=True))
    return 0


def _run_ingest(
    file_path: Path,
    gateway_ip: str,
    client_factory: type[GatewayClient],
) -> GatewayResponse:
    if not file_path.is_file():
        raise FileNotFoundError(f"Syslog file does not exist: {file_path}")
    return client_factory(gateway_ip).ingest(file_path)


def _run_query(
    gateway_ip: str,
    query_type: str,
    value: str,
    client_factory: type[GatewayClient],
) -> GatewayResponse:
    client = client_factory(gateway_ip)
    if query_type == "COUNT_KEYWORD":
        return client.count_keyword(value)
    return client.search(SEARCH_COMMANDS[query_type], value)


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()

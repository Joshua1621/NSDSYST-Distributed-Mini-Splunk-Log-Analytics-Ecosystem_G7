"""
Command-line parser for the Mini-Splunk CLI.
"""

from __future__ import annotations

import argparse


class CLIParser:
    """
    Parse Mini-Splunk CLI commands.
    """

    @staticmethod
    def build() -> argparse.ArgumentParser:

        parser = argparse.ArgumentParser(
            prog="minisplunk",
            description="Mini-Splunk Distributed Log Analytics CLI",
        )

        subparsers = parser.add_subparsers(
            dest="command",
            required=True,
        )

        ####################################################
        # INGEST
        ####################################################

        ingest = subparsers.add_parser(
            "INGEST",
            help="Upload a syslog file.",
        )

        ingest.add_argument(
            "file_path",
            help="Path to the local syslog file.",
        )

        ingest.add_argument(
            "gateway_ip",
            help="Gateway IP address.",
        )

        ####################################################
        # QUERY
        ####################################################

        query = subparsers.add_parser(
            "QUERY",
            help="Execute a distributed query.",
        )

        query.add_argument(
            "gateway_ip",
            help="Gateway IP address.",
        )

        query.add_argument(
            "query_type",
            choices=[
                "SEARCH_DATE",
                "SEARCH_HOST",
                "SEARCH_DAEMON",
                "SEARCH_SEVERITY",
                "SEARCH_KEYWORD",
                "COUNT_KEYWORD",
            ],
        )

        query.add_argument(
            "value",
            help="Search value.",
        )

        ####################################################
        # PURGE
        ####################################################

        purge = subparsers.add_parser(
            "PURGE",
            help="Delete every indexed log.",
        )

        purge.add_argument(
            "gateway_ip",
            help="Gateway IP address.",
        )

        return parser
"""
CLI command dispatcher.
"""

from __future__ import annotations

import json

from cli.app.client import GatewayClient


class CommandDispatcher:
    """
    Executes CLI commands.
    """

    @staticmethod
    def execute(args) -> None:
        """
        Dispatch the requested command.
        """

        handlers = {
            "INGEST": CommandDispatcher.handle_ingest,
            "QUERY": CommandDispatcher.handle_query,
            "PURGE": CommandDispatcher.handle_purge,
        }

        handler = handlers.get(args.command)

        if handler is None:
            raise ValueError(
                f"Unsupported command: {args.command}"
            )

        handler(args)

    ########################################################
    # INGEST
    ########################################################

    @staticmethod
    def handle_ingest(args) -> None:
        """
        Handle INGEST command.
        """

        client = GatewayClient(args.gateway_ip)

        result = client.ingest(
            args.file_path,
        )

        print(
            json.dumps(
                result,
                indent=2,
            )
        )

    ########################################################
    # QUERY
    ########################################################

    @staticmethod
    def handle_query(args) -> None:
        """
        Handle QUERY command.
        """

        client = GatewayClient(args.gateway_ip)

        query_handlers = {
            "SEARCH_DATE": client.search_date,
            "SEARCH_HOST": client.search_host,
            "SEARCH_DAEMON": client.search_daemon,
            "SEARCH_SEVERITY": client.search_severity,
            "SEARCH_KEYWORD": client.search_keyword,
            "COUNT_KEYWORD": client.count_keyword,
        }

        handler = query_handlers.get(
            args.query_type
        )

        if handler is None:
            raise ValueError(
                f"Unsupported query type: {args.query_type}"
            )

        result = handler(args.value)

        print(
            json.dumps(
                result,
                indent=2,
            )
        )

    ########################################################
    # PURGE
    ########################################################

    @staticmethod
    def handle_purge(args) -> None:
        """
        Handle PURGE command.
        """

        client = GatewayClient(args.gateway_ip)

        result = client.purge()

        print(
            json.dumps(
                result,
                indent=2,
            )
        )
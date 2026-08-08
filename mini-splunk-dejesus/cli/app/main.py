"""
CLI entry point.
"""

from cli.app.commands import CommandDispatcher
from cli.app.parser import CLIParser

from shared.logging import get_logger

logger = get_logger("cli")


def main() -> None:
    """
    CLI application entry point.
    """

    parser = CLIParser.build()

    args = parser.parse_args()

    CommandDispatcher.execute(args)


if __name__ == "__main__":
    main()
import logging
import sys


def configure_logging() -> None:
    """Configure application logging for local development and deployment."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )

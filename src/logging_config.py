import logging


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging once for the whole app (replaces scattered print() calls)."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

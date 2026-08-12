"""Build LangGraph checkpointer: Postgres (Phase C) → SQLite → Memory."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def try_postgres_checkpointer():
    url = (
        os.environ.get("DATABASE_URL", "")
        or getattr(__import__("src.config", fromlist=["settings"]).settings, "database_url", "")
        or ""
    ).strip()
    if not url:
        return None
    if os.environ.get("CHECKPOINT_BACKEND", "").lower() in ("sqlite", "memory"):
        return None
    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
        import psycopg
        conn = psycopg.connect(url, autocommit=True)
        saver = PostgresSaver(conn)
        try:
            saver.setup()
        except Exception as e:
            logger.warning("PostgresSaver.setup: %s", e)
        logger.info("Using Postgres checkpointer")
        return saver
    except ImportError:
        logger.info("langgraph-checkpoint-postgres / psycopg not installed — skip Postgres checkpoint")
        return None
    except Exception as e:
        logger.warning("Postgres checkpointer failed (%s) — fallback SQLite/Memory", e)
        return None

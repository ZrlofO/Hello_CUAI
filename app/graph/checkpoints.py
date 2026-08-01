from __future__ import annotations

import os
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Iterator

from langgraph.checkpoint.sqlite import SqliteSaver


class CheckpointManager(AbstractContextManager):
    def __init__(self, database_path: str | None = None):
        path = Path(database_path or os.getenv("LANGGRAPH_CHECKPOINT_DB", ".data/workflows.db"))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._context = SqliteSaver.from_conn_string(str(path))
        self.saver = self._context.__enter__()
        self.saver.setup()

    def close(self):
        if self._context is not None:
            self._context.__exit__(None, None, None)
            self._context = None

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


checkpoint_manager = CheckpointManager()

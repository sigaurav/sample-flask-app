"""
ExportJobRepository — thread-safe in-memory store for export job records.

Phase 1: all state lives in a process-scoped singleton dict.
Phase 2: replace with a SQLAlchemy-backed repository targeting a
         ``export_jobs`` table in the application database.

Thread safety: a single ``threading.Lock`` guards all reads and writes.
The ``get_instance()`` classmethod provides the shared singleton used
by both the HTTP request handlers and the background worker threads.
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

from app.models.export_job import ExportJob

log = logging.getLogger(__name__)


class ExportJobRepository:
    """
    In-memory, thread-safe repository for ``ExportJob`` records.

    All public methods acquire the lock internally, so callers do not
    need to synchronise externally.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, ExportJob] = {}
        self._lock = threading.Lock()

    #  Writes ─

    def create(self, job: ExportJob) -> ExportJob:
        """Persist a new job record.  Returns the same object."""
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def update(self, job_id: str, **kwargs) -> None:
        """
        Atomically update one or more fields on an existing job.

        Unknown field names are silently ignored to avoid breaking callers
        when the model gains new optional fields.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
                else:
                    log.debug("ExportJobRepository.update: unknown field %r on job %s", key, job_id)

    #  Reads 

    def get(self, job_id: str) -> Optional[ExportJob]:
        """Return the job record or ``None`` if not found."""
        with self._lock:
            return self._jobs.get(job_id)

    #  Singleton 

    _instance: Optional["ExportJobRepository"] = None
    _init_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ExportJobRepository":
        """Return the process-level singleton.  Thread-safe double-check."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

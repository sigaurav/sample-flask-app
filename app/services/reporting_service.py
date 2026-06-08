"""
ReportingService — query facade for all FR Y-14Q entity types.

Sits on top of DataService and delegates to the entity-level services
(FacilityService, ObligorService, TransactionService).  Registered on
the Flask app object in create_app() so entity services — and their
repository caches — are shared for the lifetime of the process rather
than rebuilt on every request.

Usage (in routes):
    from flask import current_app
    result = current_app.reporting_service.get_facilities(search="acme")
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.data_service        import DataService
from app.services.facility_service    import FacilityService
from app.services.obligor_service     import ObligorService
from app.services.transaction_service import TransactionService

log = logging.getLogger(__name__)


class ReportingService:
    """
    Single entry point for all read-oriented reporting queries.

    Instantiate once (via create_app) and attach to the Flask app:
        app.reporting_service = ReportingService(app.data_service)
    """

    def __init__(self, data_service: DataService) -> None:
        data_dir = data_service._config.get("DATA_DIR", "")
        self._facility_svc    = FacilityService(data_dir)
        self._obligor_svc     = ObligorService(data_dir)
        self._transaction_svc = TransactionService(data_dir)
        log.info("ReportingService initialised (data_dir=%s)", data_dir)

    # ── Facilities ─────────────────────────────────────────────────────────────

    def get_facilities(self, search: str = "", page: int = 1, per_page: int = 50) -> dict[str, Any]:
        return self._facility_svc.get_facilities(search=search, page=page, per_page=per_page)

    def get_facility_by_id(self, facility_id: str) -> Optional[Any]:
        return self._facility_svc.get_facility_by_id(facility_id)

    # ── Obligors ───────────────────────────────────────────────────────────────

    def get_all_obligors(self, search: str = "", page: int = 1, per_page: int = 50) -> dict[str, Any]:
        return self._obligor_svc.get_all_obligors(search=search, page=page, per_page=per_page)

    def get_obligors_for_facility(
        self, facility_id: str, search: str = "", page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        return self._obligor_svc.get_obligors_for_facility(
            facility_id, search=search, page=page, per_page=per_page
        )

    def get_obligor_by_id(self, obligor_id: str) -> Optional[Any]:
        return self._obligor_svc.get_obligor_by_id(obligor_id)

    # ── Transactions ───────────────────────────────────────────────────────────

    def get_all_transactions(self, search: str = "", page: int = 1, per_page: int = 50) -> dict[str, Any]:
        return self._transaction_svc.get_all_transactions(search=search, page=page, per_page=per_page)

    def get_transactions_for_obligor(
        self, obligor_id: str, search: str = "", page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        return self._transaction_svc.get_transactions_for_obligor(
            obligor_id, search=search, page=page, per_page=per_page
        )

    def get_comments_for_transaction(
        self, transaction_id: str, search: str = "", page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        return self._transaction_svc.get_comments_for_transaction(
            transaction_id, search=search, page=page, per_page=per_page
        )

"""
ReportingService — generic data-access facade driven by the ENTITIES config graph.

Every entity is fetched via the same get_entity() method, which:
  1. Calls the entity's configured adapter.
  2. Enriches with child-count columns declared in ENTITIES[*]["children"].
  3. Paginates and coerces types via the JSON schema.

Adding a new entity requires only a config entry and schema JSON — no code changes here.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from app.services.data_service        import DataService
from app.repositories.base_repository import BaseRepository
from app.schemas                       import get_api_fields, get_numeric_fields

log = logging.getLogger(__name__)


def _schema_coerce_records(df: pd.DataFrame, entity_type: str) -> list[dict]:
    api_fields     = get_api_fields(entity_type)
    numeric_fields = set(get_numeric_fields(entity_type))
    present        = [f for f in api_fields if f in df.columns]
    records        = []
    for row in df[present].to_dict(orient="records"):
        for f in numeric_fields:
            if f in row:
                try:
                    row[f] = float(row[f])
                except (ValueError, TypeError):
                    row[f] = 0.0
        records.append(row)
    return records


class ReportingService:

    def __init__(self, data_service: DataService, config: dict = None) -> None:
        self._data_service = data_service
        self._entities     = (config or {}).get("ENTITIES", {})
        log.info(
            "ReportingService initialised (primary adapter: %s, entities: %s)",
            next(iter(data_service.adapters), "none"),
            list(self._entities),
        )

    def _ctx(self, sor: str, fic_mis_date: str) -> dict:
        return {"_sor": sor, "_fic_mis_date": fic_mis_date}

    # ── Generic entry point ────────────────────────────────────────────────────

    def get_entity(
        self,
        entity_type:  str,
        entity_key:   Optional[dict] = None,
        search:       str  = "",
        page:         int  = 1,
        per_page:     int  = 50,
        sor:          str  = "",
        fic_mis_date: str  = "",
    ) -> dict[str, Any]:
        adapter = self._data_service.get_adapter_for_entity(entity_type)
        ctx     = self._ctx(sor, fic_mis_date)

        df = adapter.fetch(entity_type, entity_key=entity_key,
                           filters={"quick_filter": search, **ctx})
        df = self._enrich_with_child_counts(df, entity_type, ctx)

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = _schema_coerce_records(df_page, entity_type)
        log.debug(
            "get_entity entity=%s entity_key=%s sor=%r -> %d/%d",
            entity_type, entity_key, sor, len(records), total,
        )
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    # ── Child-count enrichment ─────────────────────────────────────────────────

    def _enrich_with_child_counts(
        self, df: pd.DataFrame, entity_type: str, ctx: dict
    ) -> pd.DataFrame:
        children = self._entities.get(entity_type, {}).get("children", {})
        for child_entity, child_cfg in children.items():
            count_col = child_cfg.get("count_col", child_entity.upper() + "_COUNT")
            fk_cols   = child_cfg["fk"]
            child_adapter = self._data_service.get_adapter_for_entity(child_entity)
            child_df = child_adapter.fetch(child_entity, filters=ctx)
            if (not child_df.empty
                    and all(c in child_df.columns for c in fk_cols)
                    and all(c in df.columns for c in fk_cols)):
                if len(fk_cols) == 1:
                    counts = child_df.groupby(fk_cols[0]).size()
                    df[count_col] = df[fk_cols[0]].map(counts).fillna(0).astype(int)
                else:
                    counts = child_df.groupby(fk_cols).size()
                    df[count_col] = (
                        pd.MultiIndex.from_frame(df[fk_cols])
                        .map(counts)
                        .fillna(0)
                        .astype(int)
                    )
            else:
                df[count_col] = 0
        return df

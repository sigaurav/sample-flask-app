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
        self._config       = config or {}
        self._entities     = self._config.get("ENTITIES", {})
        log.info(
            "ReportingService initialised (primary adapter: %s, entities: %s)",
            next(iter(data_service.adapters), "none"),
            list(self._entities),
        )

    def _ctx(self, fic_mis_date: str) -> dict:
        return {"_fic_mis_date": fic_mis_date}

    #  Generic entry point 

    def get_entity(
        self,
        entity_type:  str,
        entity_key:   Optional[dict] = None,
        search:       str  = "",
        page:         int  = 1,
        per_page:     Optional[int]  = None,
        fic_mis_date: str  = "",
        sorts:        Optional[list] = None,
        col_filters:  Optional[dict] = None,
    ) -> dict[str, Any]:
        if per_page is None:
            per_page = self._config.get("DEFAULT_PAGE_SIZE", 50)
        adapter = self._data_service.get_adapter_for_entity(entity_type)
        ctx     = self._ctx(fic_mis_date)

        filters = {"quick_filter": search, "col_filters": col_filters or {}, **ctx}
        use_db_pagination = (
            hasattr(adapter, "fetch_count")
            and not search
        )

        if use_db_pagination:
            total  = adapter.fetch_count(entity_type, entity_key=entity_key,
                                         filters=dict(filters))
            active = self._count_active_db(adapter, entity_type, entity_key,
                                           filters)
            df = adapter.fetch(
                entity_type, entity_key=entity_key,
                filters=filters, sorts=sorts or [],
                page=page, per_page=per_page,
            )
            df = self._enrich_with_child_counts(df, entity_type, ctx)
            records = _schema_coerce_records(df, entity_type)
        else:
            df = adapter.fetch(
                entity_type, entity_key=entity_key,
                filters=filters, sorts=sorts or [],
            )
            df = self._enrich_with_child_counts(df, entity_type, ctx)
            total   = len(df)
            active  = self._count_active(df, entity_type)
            df_page = BaseRepository.paginate(df, page, per_page)
            records = _schema_coerce_records(df_page, entity_type)
        log.debug(
            "get_entity entity=%s entity_key=%s fic_mis_date=%r -> %d/%d",
            entity_type, entity_key, fic_mis_date, len(records), total,
        )
        return {
            "records": records, "total": total,
            "active": active,
            "page": page, "per_page": per_page,
        }

    #  KPI helpers ─

    def _count_active(self, df: pd.DataFrame, entity_type: str) -> int:
        cfg = self._entities.get(entity_type, {}).get("active_filter")
        if not cfg or df.empty:
            return 0
        field, value = cfg.get("field", ""), cfg.get("value", "")
        if field and field in df.columns:
            return int((df[field].astype(str) == str(value)).sum())
        return 0

    def _count_active_db(self, adapter, entity_type, entity_key, filters) -> int:
        cfg = self._entities.get(entity_type, {}).get("active_filter")
        if not cfg:
            return 0
        active_filters = dict(filters)
        cf = dict(active_filters.get("col_filters", {}))
        cf[cfg["field"]] = {"op": "equals", "val": cfg["value"]}
        active_filters["col_filters"] = cf
        return adapter.fetch_count(entity_type, entity_key=entity_key,
                                   filters=active_filters)

    #  Child-count enrichment ─

    def _enrich_with_child_counts(
        self, df: pd.DataFrame, entity_type: str, ctx: dict
    ) -> pd.DataFrame:
        children = self._entities.get(entity_type, {}).get("children", {})
        for child_entity, child_cfg in children.items():
            count_col     = child_cfg.get("count_col", child_entity.upper() + "_COUNT")
            fk_cols       = child_cfg["fk"]
            child_fk_cols = child_cfg["child_fk"]

            child_adapter = self._data_service.get_adapter_for_entity(child_entity)
            child_df      = child_adapter.fetch(child_entity, filters=ctx)

            parent_ok = all(c in df.columns for c in fk_cols)
            child_ok  = all(c in child_df.columns for c in child_fk_cols)

            if not child_df.empty and parent_ok and child_ok:
                if len(fk_cols) == 1:
                    counts = child_df.groupby(child_fk_cols[0]).size()
                    df[count_col] = df[fk_cols[0]].map(counts).fillna(0).astype(int)
                else:
                    # Rename child FK cols to parent names so groupby keys align
                    rename = {c: p for c, p in zip(child_fk_cols, fk_cols) if c != p}
                    child_keyed = child_df.rename(columns=rename)
                    counts = child_keyed.groupby(fk_cols).size()
                    df[count_col] = (
                        pd.MultiIndex.from_frame(df[fk_cols])
                        .map(counts)
                        .fillna(0)
                        .astype(int)
                    )
            else:
                df[count_col] = 0
        return df

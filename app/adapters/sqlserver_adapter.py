"""
SQL Server adapter — SQLAlchemy + pyodbc for FR Y-14Q data.

Requires:  pip install sqlalchemy pyodbc

Connection config keys (Flask uppercase):
    SQLSERVER_HOST   : SQL Server hostname / IP
    SQLSERVER_PORT   : TCP port (default 1433)
    SQLSERVER_DB     : Database name
    SQLSERVER_SCHEMA : Schema name (default 'dbo')
    SQLSERVER_DRIVER : ODBC driver string

Authentication uses SSO Windows Authentication (Trusted_Connection=yes).
No username or password is required or stored.

Each entity maps to a table via ENTITIES[entity_type]["table"] (config.py).
_build_query() builds a `SELECT ... FROM [schema].[table] WHERE ...` directly
from that mapping plus context/entity_key/col_filters — there is no per-entity
SQL string to maintain here (contrast with the Dremio/Teradata adapters, which
still use a _QUERY_MAP; see CLAUDE.md for the rationale for this adapter's
departure from that pattern).

When page/per_page are passed to fetch(), _build_query() appends ORDER BY +
OFFSET/FETCH directly onto the generated SQL so the database engine handles
pagination — only the requested page is transferred to Python.
"""

from __future__ import annotations
from dataclasses import field
import pandas as pd

from app.adapters.base_adapter import BaseAdapter
# Rolando added Tuple, Union and other imports.
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy import create_engine, text
from app.schemas import get_all_fields
from pathlib import Path
from datetime import datetime
import re

# Rolano's addition.
def _quote_identifier(name: str) -> str:
    """
    Quote a SQL Server identifier Allows only letters, numbers and underscore.

    Args:
        name: The identifier to quote.

    Returns:
        The quoted identifier.
    """
    if not name or not re.match(r"^[A-Za-z_][A-Za-z0-9]*$", name):
        raise ValueError(f"Invalid SQL Server identifier: {name}")
    return f"[{name}]"


# Rolano's addition.
def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]

# Rolano's addition.
def _get_record_value_case_insensitive(record: dict, field_name: str) -> Any:
    """
    Get a value from a record (dict) in a case-insensitive manner.

    Args:
        record: The record (dict) to search.
        field_name: The field name to look for.

    Returns:
        The value associated with the field name, or None if not found.
    """
    record_key_map = {str(k).lower(): k for k in record.keys()}
    lookup_key = field_name.lower()
    if lookup_key not in record_key_map:
        raise KeyError(f"Missing origin PK column '{field_name}' in record")
    
    original_key = record_key_map[lookup_key]
    return record.get(original_key)


class SQLServerAdapter(BaseAdapter):

    source_type = "sqlserver"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._host   = config.get("SQLSERVER_HOST", "")
        self._port   = int(config.get("SQLSERVER_PORT", 1433))
        self._db     = config.get("SQLSERVER_DB", "")
        self._schema = config.get("SQLSERVER_SCHEMA", "dbo")
        self._driver = config.get("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
        self._engine = None
        # Rolando's addition.
        self._entities = (config or {}).get("ENTITIES", {})

    def _get_engine(self):
        if self._engine is not None:
            return self._engine

        conn_str = (
            f"mssql+pyodbc://@{self._host}:{self._port}/{self._db}"
            f"?driver={self._driver.replace(' ', '+')}"
            f"&Trusted_Connection=yes"
        )
        self._engine = create_engine(conn_str, fast_executemany=True, pool_pre_ping=True)
        return self._engine

    # ── SQL builder helpers ──────────────────────────────────────────────────

    def _build_where_sql(self, clauses, params, param_offset=0):
        parts = []
        idx = param_offset
        for field, op, val in clauses:
            qcol = f"[{field}]"
            pname = f"_f{idx}"

            if op == "eq":
                parts.append(f"{qcol} = :{pname}")
                params[pname] = val
            elif op == "contains":
                parts.append(f"LOWER(CAST({qcol} AS NVARCHAR(MAX))) LIKE '%' + :{pname} + '%'")
                params[pname] = val.lower()
            elif op == "equals":
                parts.append(f"LOWER(CAST({qcol} AS NVARCHAR(MAX))) = :{pname}")
                params[pname] = val.lower()
            elif op == "startsWith":
                parts.append(f"LOWER(CAST({qcol} AS NVARCHAR(MAX))) LIKE :{pname} + '%'")
                params[pname] = val.lower()
            elif op in ("numEq", "gt", "gte", "lt", "lte"):
                sym = {"numEq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
                parts.append(f"TRY_CAST({qcol} AS FLOAT) {sym} :{pname}")
                params[pname] = float(val)
            elif op in ("dateEq", "dateBefore", "dateAfter"):
                sym = {"dateEq": "=", "dateBefore": "<", "dateAfter": ">"}[op]
                parts.append(f"TRY_CAST({qcol} AS DATE) {sym} :{pname}")
                params[pname] = val
            elif op == "inList":
                values = [v.strip().lower() for v in val.split(",") if v.strip()]
                in_names = []
                for v in values:
                    pn = f"_f{idx}"
                    in_names.append(f":{pn}")
                    params[pn] = v
                    idx += 1
                if in_names:
                    parts.append(f"LOWER(CAST({qcol} AS NVARCHAR(MAX))) IN ({', '.join(in_names)})")
                continue

            idx += 1
        return parts

    def _build_order_sql(self, sort_fields):
        if not sort_fields:
            return "ORDER BY (SELECT NULL)"
        return "ORDER BY " + ", ".join(f"[{f}] {d}" for f, d in sort_fields)

    # Rolando's _build_query function, extended to cover col_filters/sorts/pagination
    # so it can fully replace the old CTE-wrapper approach (fetch() and fetch_count()
    # both build their SQL through this single method now).
    def _build_query(
        self,
        entity_type: str,
        entity_key: Optional[Dict[str, str]] = None,
        period_dt: str = "",
        sql_query: Optional[str] = None,
        col_filters: Optional[Dict] = None,
        sorts: Optional[List] = None,
        page: Optional[int] = None,
        per_page: Optional[int] = None,
        count_only: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build a SQL query for the given entity type, filters, sort and page.

        Args:
            entity_type: The type of the entity to query.
            entity_key: Optional dictionary of entity key fields and values.
            period_dt: The period date to filter the query.
            sql_query: Optional custom SQL query to use instead of the default.
            col_filters: Optional column-filter spec (field -> {op, val}).
            sorts: Optional list of {field, dir} sort specs.
            page/per_page: When both given, appends OFFSET/FETCH pagination.
            count_only: When True, builds a COUNT(*) query with no ORDER BY/paging.
        """
        cols = self._get_select_cols(entity_type)
        if count_only:
            select = "COUNT(*) AS cnt"
        else:
            select = "*" if cols == ["*"] else ", ".join(f"[{c}]" for c in cols)

        table = self._entities[entity_type]["table"]
        params: Dict[str, Any] = {}

        clauses: List[Tuple[str, str, str]] = list(self._build_filter_clauses(col_filters or {}, entity_key))
        if period_dt:
            clauses = [("PERIOD_DT", "eq", period_dt)] + clauses

        where_parts = self._build_where_sql(clauses, params)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        if sql_query:
            sql = f"{sql_query} {where}"
        else:
            sql = f"SELECT {select} FROM [{self._schema}].[{table}] {where}"

        if not count_only:
            sql += f"\n{self._build_order_sql(self._build_sort_fields(sorts))}"
            if page is not None and per_page is not None:
                params["_offset"] = (page - 1) * per_page
                params["_limit"] = per_page
                sql += "\nOFFSET :_offset ROWS FETCH NEXT :_limit ROWS ONLY"

        return sql, params

    # ── Public interface ─────────────────────────────────────────────────────

    def fetch(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
        page:        Optional[int]            = None,
        per_page:    Optional[int]            = None,
        sql_query:   Optional[str]            = None,  # Rolando added this parameter to support custom SQL queries.
    ) -> pd.DataFrame:
        filters     = dict(filters or {})
        period_dt   = filters.pop("_period_dt", "")
        col_filters = filters.get("col_filters", {})
        quick       = filters.get("quick_filter", "")

        # quick_filter is full-text search — ReportingService only passes page/per_page
        # when there's no search term, so this naturally fetches the unpaginated,
        # unsorted-by-SQL result set for in-memory quick-filtering when quick is set.
        sql, params = self._build_query(
            entity_type, entity_key=entity_key, period_dt=period_dt,
            sql_query=sql_query, col_filters=col_filters, sorts=sorts,
            page=page, per_page=per_page,
        )
        self.log.debug("SQLServerAdapter SQL:\n%s\nparams=%s", sql, params)

        engine = self._get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)

        if quick:
            df = self._apply_quick_filter(df, quick)

        self.log.debug(
            "SQLServerAdapter.fetch entity=%s entity_key=%s rows=%d",
            entity_type, entity_key, len(df),
        )
        return df

    # Rolando's addition:
    def push(self, entity_type: str, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> int:
        """
        Push record/s to the database.  Returns the number of rows affected.

        Args:
            entity_type: The type of the entity to push.
            data: A dictionary or list row data to insert.

        Returns:
            The number of rows inserted.
        """
        if not data:
            return 0
        
        rows = data if isinstance(data, list) else [data]

        if not rows:
            return 0
        
        table_name = self._entities[entity_type]["table"]
        if not table_name:
            raise ValueError(f"Unsupported entity type: '{entity_type}'")
        
        schema_name = self._schema
        columns = get_all_fields(entity_type)

        if not columns:
            return 0
        
        for row in rows:
            missing = set(columns) - set(row.keys())
            extra = set(row.keys()) - set(columns)
            if missing or extra:
                raise ValueError(f"Inconsistent row columns. Missing: {missing}, Extra: {extra}")
            
        column_sql = ", ".join(f"[{c}]" for c in columns)
        values_sql = ", ".join(f":{c}" for c in columns)
            
        sql = text(f"""
                   INSERT INTO [{schema_name}].[{table_name}]
                   ({column_sql})
                   VALUES ({values_sql})
                   """)
        with self._engine.begin() as conn:
            result = conn.execute(sql, rows)
            return result.rowcount

    # Rolando's has removed the fetch_count function from his code.
    def fetch_count(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
    ) -> int:
        filters     = dict(filters or {})
        period_dt   = filters.pop("_period_dt", "")
        col_filters = filters.get("col_filters", {})

        sql, params = self._build_query(
            entity_type, entity_key=entity_key, period_dt=period_dt,
            col_filters=col_filters, count_only=True,
        )
        engine = self._get_engine()
        with engine.connect() as conn:
            row = conn.execute(text(sql), params).fetchone()
        return row[0] if row else 0

    # Rolando updated the introspect_columns function.
    def introspect_columns(self, entity_type: str) -> List[str]:
        
        cols = self._get_select_cols(entity_type)
        if cols != ["*"]:
            return cols
        
        table = self._entities[entity_type]["table"]
        if not table:
            raise ValueError(f"Unsupported entity type: '{entity_type}'")
        
        sql = text("""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = :schema 
                    AND TABLE_NAME = :table
                    ORDER BY ORDINAL_POSITION
                    """)
        
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(sql, {"schema": self._schema, "table": table})
            return [row[0] for row in result]
            

    def health_check(self) -> bool:
        try:
            from sqlalchemy import text
            with self._get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    # Rolando's addition:
    def export_reference_records_to_csv(self, 
                                        records: list[dict],
                                        reference_table: str,
                                        origin_pk_columns: list[str],
                                        reference_pk_columns: list[str],
                                        output_file: str,
                                        selected_columns: Optional[list[str]] = None,
                                        export_folder: str = "exports") -> str:
        """
        Exports records from a SQL Server reference table to CSV.

        The join is done by loading incoming records PK values into a temp table,
        then joining that temp table to the reference table.

        Parameters:
            records: List[Dict]
                Incoming records containing the origin PK columns.
            reference_table: str
                SQL Server reference table name (schema.table).
            origin_pk_columns: List[str]
                List of origin PK column names in the incoming records.
            reference_pk_columns: List[str]
                List of reference PK column names in SQL Server reference table.

            output_file: str
                Base CSV file name (without path).  The file will be saved in the export_folder.
            selected_columns: Optional[List[str]]
                List of columns to export from the reference table.  If None, all columns are exported.
            export_folder: str
                Folder where the CSV file will be saved.  Defaults to "exports".
        Returns:
            str: The full path to the exported CSV file.
        """
        if not records:
            raise ValueError("No records provided for export.")
        
        if not reference_table or not origin_pk_columns or not reference_pk_columns:
            raise ValueError("Reference table and PK columns must be provided.")
        
        if len(origin_pk_columns) != len(set(origin_pk_columns)):
            raise ValueError("Origin PK columns contains duplicates.")
        
        if len(reference_pk_columns) != len(set(reference_pk_columns)):
            raise ValueError("Reference PK columns contains duplicates.")
        
        if not output_file:
            raise ValueError("Output file name must be provided.")
        
        schema_sql = _quote_identifier(self._schema)
        table_sql = _quote_identifier(reference_table)

        if selected_columns:
            select_sql = ", ".join(f"r.{_quote_identifier(col)}" for col in selected_columns)
        else:
            select_sql = "r.*"
        

        temp_columns_sql = ",\n".join(f"{_quote_identifier(col)} NVARCHAR(1000) NOT NULL" for col in origin_pk_columns)
        drop_temp_sql = text("""IF OBJECT_ID('tempdb..#reference_keys') IS NOT NULL DROP TABLE #reference_keys""")

        create_temp_sql = text(f"""
            CREATE TABLE #reference_keys (
                {temp_columns_sql}
            )
        """)

        insert_columns_sql = ", ".join(f"{_quote_identifier(col)}" for col in origin_pk_columns)
        insert_values_sql = ", ".join(f":{col}" for col in origin_pk_columns)
        insert_temp_sql = text(f"""
            INSERT INTO #reference_keys ({insert_columns_sql})
            VALUES ({insert_values_sql})
        """)

        join_condition_sql = "\n AND ".join(
            f"r.{_quote_identifier(reference_col)} = k.{_quote_identifier(orig_col)}"
            for orig_col, reference_col in zip(origin_pk_columns, reference_pk_columns)
        )

        query_sql = text(f"""
            SELECT {select_sql}
            FROM {schema_sql}.{table_sql} r
            INNER JOIN #reference_keys k ON {join_condition_sql}
        """)

        rows_to_insert = []
        seen_keys = set()
        for record in records:
            row = {}

            for orig_col in origin_pk_columns:
                value = _get_record_value_case_insensitive(record, orig_col)
                
                if value is None or str(value).strip() == "":
                    raise ValueError(f"Origin PK column '{orig_col}' is missing or empty in record: {record}")

                row[orig_col] = str(value).strip()

            # Avoid duplicate PK combinations
            key_tuple = tuple(row[col] for col in origin_pk_columns)
            if key_tuple not in seen_keys:
                seen_keys.add(key_tuple)
                rows_to_insert.append(row)

        if not rows_to_insert:
            raise ValueError("No Valid PK records found.")

        with self._engine.begin() as conn:
            try:
                conn.execute(drop_temp_sql)
                conn.execute(create_temp_sql)

                for batch in _chunks(rows_to_insert, 1000):
                    conn.execute(insert_temp_sql, batch)

                df = pd.read_sql(query_sql, conn)

            except Exception as e:
                raise RuntimeError(f"Error during export: {e}")

            finally:
                conn.execute(drop_temp_sql)

            export_dir = Path(export_folder)
            export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_stem = Path(output_file).stem
            file_suffix = Path(output_file).suffix or ".csv"

            output_path = export_dir / f"{file_stem}_{timestamp}{file_suffix}"
            df.to_csv(output_path, index=False)
            return str(output_path.resolve())

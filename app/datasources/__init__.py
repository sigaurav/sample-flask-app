"""
Data source abstraction layer for FR Y-14Q analytical workflows.

Provides a unified interface for querying data from multiple backend
sources (CSV, Excel, Dremio, SQL Server) without leaking source-specific
logic into controllers or services.

Usage:
    from app.datasources.csv_datasource import CSVDataSource
    ds = CSVDataSource({'data_dir': '/path/to/data'})
    df = ds.fetch('facilities')
"""

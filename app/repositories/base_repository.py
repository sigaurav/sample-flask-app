import pandas as pd


class BaseRepository:
    @staticmethod
    def paginate(df: pd.DataFrame, page: int, per_page: int) -> pd.DataFrame:
        page     = max(1, page)
        per_page = max(1, per_page)
        start    = (page - 1) * per_page
        return df.iloc[start : start + per_page]

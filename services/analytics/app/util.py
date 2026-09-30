from __future__ import annotations

import datetime as dt
import math
from typing import Any

import numpy as np
import pandas as pd


def clean(obj: Any) -> Any:
    """Recursively convert numpy/pandas values into JSON-safe Python values (NaN/inf -> None)."""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, (pd.Timestamp, dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, dt.date):
        return obj.isoformat()
    if isinstance(obj, pd.Series):
        return clean(obj.tolist())
    if obj is pd.NaT:
        return None
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return str(obj)


def num(x: Any) -> float | None:
    """Coerce to float or None."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def pct_change(a: float | None, b: float | None) -> float | None:
    """(a / b - 1) as a fraction."""
    if a is None or b in (None, 0):
        return None
    return a / b - 1.0


def safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return a / b


def round_or_none(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)

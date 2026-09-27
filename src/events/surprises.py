"""High-frequency monetary policy surprises from the USMPD (Bauer and Foshee).

``mps.csv`` holds the published statement (STMT), press-conference (PC) and
monetary-event (ME) surprises. When ``USMPD.xlsx`` is available locally, the
same factors can be recomputed, together with the raw MP1 surprise, the
Guerkaynak-Sack-Swanson (2005) target/path factors, and a real-time variant
that uses only events up to each meeting. The factor code ports ``mps.R`` and
``gss.R`` from ``data/external/usmpd/source_scripts``.

Sign convention: positive values are hawkish (higher expected rates).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.utils.config import PROJECT_ROOT


USMPD_DIR = PROJECT_ROOT / "data" / "external" / "usmpd"
FUTNAMES = ("MP1", "MP2", "ED2", "ED3", "ED4")
USMPD_SHEETS = {"statement": "Statements", "press_conference": "Press Conferences"}


def load_mps(path: str | Path = USMPD_DIR / "mps.csv") -> pd.DataFrame:
    """Published STMT/PC/ME surprises, one row per FOMC event date."""
    data = pd.read_csv(path, na_values=["NA"])
    data["Date"] = pd.to_datetime(data["Date"]).dt.date
    return data


def load_y1_changes(path: str | Path = USMPD_DIR / "y1.csv") -> pd.DataFrame:
    """Daily changes in the one-year GSW zero-coupon yield (percentage points)."""
    y1 = pd.read_csv(path)
    y1["Date"] = pd.to_datetime(y1["Date"]).dt.date
    y1["dy1"] = y1["SVENY01"].diff()
    return y1[["Date", "dy1"]]


def load_usmpd_sheet(sheet: str, path: str | Path = USMPD_DIR / "USMPD.xlsx") -> pd.DataFrame:
    """Intraday futures-rate changes for one USMPD event sheet, complete cases only."""
    data = pd.read_excel(path, sheet_name=sheet, na_values=["", "NA", "N/A", "#N/A"])
    data["Date"] = pd.to_datetime(data["date_time"]).dt.date
    return data[["Date", *FUTNAMES]].dropna().reset_index(drop=True)


def _standardize(values: np.ndarray) -> np.ndarray:
    return (values - values.mean(axis=0)) / values.std(axis=0, ddof=1)


def _first_pc(values: np.ndarray) -> np.ndarray:
    """First principal-component scores of standardized data (prcomp, scale=TRUE)."""
    standardized = _standardize(values)
    eigenvalues, eigenvectors = np.linalg.eigh(np.cov(standardized, rowvar=False))
    return standardized @ eigenvectors[:, np.argmax(eigenvalues)]


def _ols(y: np.ndarray, x: np.ndarray, intercept: bool = True) -> np.ndarray:
    design = np.column_stack([np.ones(len(y)), x]) if intercept else x
    return np.linalg.lstsq(design, y, rcond=None)[0]


def compute_mps(futures: pd.DataFrame, y1: pd.DataFrame) -> pd.Series:
    """First PC of futures surprises, scaled to its effect on the one-year yield."""
    pc1 = _first_pc(futures[list(FUTNAMES)].to_numpy(float))
    merged = pd.DataFrame({"Date": futures["Date"], "PC1": pc1}).merge(y1, on="Date", how="left")
    usable = merged.dropna()
    slope = _ols(usable["dy1"].to_numpy(float), usable["PC1"].to_numpy(float))[1]
    return pd.Series(slope * pc1, index=futures["Date"], name="MPS")


def compute_mps_real_time(
    futures: pd.DataFrame, y1: pd.DataFrame, dates: list
) -> pd.Series:
    """MPS for each date using only events on or before that date (no look-ahead)."""
    values = {}
    for date in dates:
        history = futures.loc[futures["Date"].le(date)].reset_index(drop=True)
        if not history["Date"].eq(date).any():
            continue
        values[date] = compute_mps(history, y1).loc[date]
    return pd.Series(values, name="MPS_real_time", dtype=float)


def compute_gss(futures: pd.DataFrame) -> pd.DataFrame:
    """GSS (2005) target and path factors, normalized as in ``gss.R``."""
    mp1 = futures["MP1"].to_numpy(float)
    ed4 = futures["ED4"].to_numpy(float)
    fut = _standardize(futures[list(FUTNAMES)].to_numpy(float))

    eigenvalues, eigenvectors = np.linalg.eigh(np.cov(fut, rowvar=False))
    order = np.argsort(eigenvalues)[::-1][:2]
    factors = fut @ eigenvectors[:, order] / np.sqrt(eigenvalues[order])

    # Rotate so the second factor has no effect on MP1 (GSS appendix A8-A11).
    g = _ols(mp1, factors, intercept=False)
    if g[0] < 0:
        factors, g = -factors, -g
    alpha1 = 1 / np.sqrt(1 + (g[1] / g[0]) ** 2)
    alpha2 = alpha1 * g[1] / g[0]
    beta1 = 1 / np.sqrt(1 + (alpha1 / alpha2) ** 2)
    beta2 = -alpha1 / alpha2 * beta1
    rotated = factors @ np.array([[alpha1, beta1], [alpha2, beta2]])

    # Target moves MP1 one-for-one; path has the same ED4 effect as target.
    target = rotated[:, 0] * _ols(mp1, rotated[:, 0])[1]
    coef = _ols(ed4, np.column_stack([target, rotated[:, 1]]))
    path = rotated[:, 1] * coef[2] / coef[1]
    return pd.DataFrame({"Date": futures["Date"], "target": target, "path": path})


def build_surprise_panel(meetings: pd.DataFrame, usmpd_path: str | Path | None = None) -> pd.DataFrame:
    """Attach surprise measures to meetings (needs ``meeting`` and ``meeting_date``).

    Published STMT/PC/ME are always included. MP1, GSS target/path and real-time
    STMT/PC are added when ``USMPD.xlsx`` exists at ``usmpd_path``.
    """
    panel = meetings.copy()
    panel["Date"] = pd.to_datetime(panel["meeting_date"]).dt.date
    panel = panel.merge(load_mps(), on="Date", how="left")

    usmpd_path = Path(usmpd_path) if usmpd_path else USMPD_DIR / "USMPD.xlsx"
    if not usmpd_path.exists():
        return panel.drop(columns="Date")

    y1 = load_y1_changes()
    statements = load_usmpd_sheet(USMPD_SHEETS["statement"], usmpd_path)
    press = load_usmpd_sheet(USMPD_SHEETS["press_conference"], usmpd_path)
    dates = list(panel["Date"])
    extra = (
        statements[["Date", "MP1"]]
        .merge(compute_gss(statements), on="Date")
        .merge(compute_mps(statements, y1).rename("STMT_recomputed").reset_index(), on="Date")
        .merge(
            compute_mps_real_time(statements, y1, dates).rename("STMT_real_time")
            .rename_axis("Date").reset_index(),
            on="Date",
            how="left",
        )
    )
    pc_real_time = (
        compute_mps_real_time(press, y1, dates).rename("PC_real_time").rename_axis("Date").reset_index()
    )
    panel = panel.merge(extra, on="Date", how="left").merge(pc_real_time, on="Date", how="left")
    return panel.drop(columns="Date")

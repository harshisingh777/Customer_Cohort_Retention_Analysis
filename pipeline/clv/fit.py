# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportOptionalSubscript=false, reportAssignmentType=false
# (pandas-stubs types itertuples() rows as plain tuples and most frame ops as unions.)
"""Weekly CLV fit: BG/NBD (orders, P(alive)) + Gamma-Gamma (order value) via PyMC-Marketing.

Governance (spec §9.6):
- Holdout: calibrate on data up to cutoff - 180 days, predict the next 180 days, compare with
  actual revenue per acquisition cohort; MAPE goes on the Data page. Above 30% the API hides
  predicted LTV.
- Predictions are a p10-p90 range over posterior draws, never a bare point estimate.
- model_version is stored with every prediction.

Outputs land in raw.clv_* and reach the marts through the normal build-audit-publish refresh.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.db import Conn, connect

log = logging.getLogger(__name__)

HOLDOUT_DAYS = 180
HORIZON_DAYS = 365
MIN_CUSTOMERS = 200
MIN_REPEATERS = 50


@dataclass
class FitConfig:
    method: str = os.environ.get("CLV_FIT_METHOD", "mcmc")
    draws: int = int(os.environ.get("CLV_DRAWS", "400"))
    tune: int = int(os.environ.get("CLV_TUNE", "400"))
    chains: int = int(os.environ.get("CLV_CHAINS", "2"))
    seed: int = 20261005

    def sampler(self) -> dict:
        return {
            "draws": self.draws,
            "tune": self.tune,
            "chains": self.chains,
            "cores": 1,
            "random_seed": self.seed,
            "progressbar": False,
            "target_accept": 0.9,
        }


def load_orders(conn: Conn) -> tuple[pd.DataFrame, dt.date]:
    cutoff = conn.execute("select cutoff_date from analytics.mart_data_quality").fetchone()[
        "cutoff_date"
    ]  # type: ignore[index]
    rows = conn.execute(
        """
        select o.customer_key, o.order_date_local as order_date, o.net_revenue::float as net_revenue,
               a.cohort_month, a.acquisition_channel
        from analytics.int_orders o
        join analytics.int_customer_acquisition a using (customer_key)
        """
    ).fetchall()
    df = pd.DataFrame(
        rows,
        columns=[
            "customer_key",
            "order_date",
            "net_revenue",
            "cohort_month",
            "acquisition_channel",
        ],
    )
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df, cutoff


def rfm(df: pd.DataFrame, end: dt.date) -> pd.DataFrame:
    """frequency = repeat purchase days, recency/T in days, monetary = mean repeat order value."""
    from pymc_marketing.clv import rfm_summary

    out = rfm_summary(
        df,
        customer_id_col="customer_key",
        datetime_col="order_date",
        monetary_value_col="net_revenue",
        observation_period_end=pd.Timestamp(end),
        time_unit="D",
    )
    return out.astype({"frequency": float, "recency": float, "T": float, "monetary_value": float})


def fit(data: pd.DataFrame, cfg: FitConfig):
    from pymc_marketing.clv import BetaGeoModel, GammaGammaModel

    bg = BetaGeoModel(sampler_config=cfg.sampler())
    bg.fit(
        data[["customer_id", "frequency", "recency", "T"]],
        method=cfg.method,
        progressbar=False,
        random_seed=cfg.seed,
    )
    repeaters = data[(data["frequency"] > 0) & (data["monetary_value"] > 0)]
    gg = GammaGammaModel(sampler_config=cfg.sampler())
    gg.fit(
        repeaters[["customer_id", "frequency", "monetary_value"]],
        method=cfg.method,
        progressbar=False,
        random_seed=cfg.seed,
    )
    return bg, gg


def _draws(x) -> np.ndarray:
    """(customers, samples) from an xarray with chain/draw dims (or none, for MAP fits)."""
    dims = [d for d in ("chain", "draw") if d in x.dims]
    if dims:
        x = x.stack(sample=dims).transpose("customer_id", "sample")
        return np.asarray(x.values)
    return np.asarray(x.values).reshape(-1, 1)


def _param(model, name: str) -> np.ndarray:
    x = model.idata.posterior[name]
    dims = [d for d in ("chain", "draw") if d in x.dims]
    return np.asarray(x.stack(sample=dims).values if dims else x.values).reshape(-1)


def predict(
    bg, gg, data: pd.DataFrame, horizon_days: int, seed: int = 7, max_draws: int = 200
) -> tuple[pd.DataFrame, np.ndarray]:
    """Per-customer predictive range and per-draw expected values.

    The range is a *predictive* interval for that customer's revenue, not just parameter
    uncertainty: for each posterior draw, simulate whether they're alive (BG/NBD P(alive)),
    how many orders they place given alive (gamma-Poisson around the conditional mean, shape
    r + x), and what each order is worth (Gamma-Gamma with their posterior spend rate).
    Returns (frame, expected value per customer per draw) — the latter feeds group averages,
    whose uncertainty is the parameter uncertainty of a mean.
    """
    full = data[["customer_id", "frequency", "recency", "T", "monetary_value"]]
    orders = _draws(bg.expected_purchases(full, future_t=horizon_days))  # E[N] (C, S)
    alive = np.clip(_draws(bg.expected_probability_alive(full)), 1e-6, 1.0)  # (C, S)
    spend = _draws(gg.expected_customer_spend(full))  # E[z] (C, S)
    s = min(orders.shape[1], alive.shape[1], spend.shape[1])
    rng = np.random.default_rng(seed)
    idx = np.sort(rng.choice(s, size=min(s, max_draws), replace=False))
    expected = orders[:, idx] * spend[:, idx]

    x = full["frequency"].to_numpy(dtype=float)[:, None]
    mbar = full["monetary_value"].to_numpy(dtype=float)[:, None]
    r = _param(bg, "r")[idx][None, :]
    p, q, v = (_param(gg, k)[idx][None, :] for k in ("p", "q", "v"))

    is_alive = rng.random(expected.shape) < alive[:, idx]
    mean_if_alive = orders[:, idx] / alive[:, idx]
    shape = r + x
    lam = rng.gamma(shape, mean_if_alive / shape)
    n_orders = np.where(is_alive, rng.poisson(lam), 0)
    nu = rng.gamma(p * x + q, 1.0 / (v + x * mbar))  # spend rate
    total_shape = np.maximum(n_orders * p, 1e-12)
    value = np.where(n_orders > 0, rng.gamma(total_shape, 1.0 / nu), 0.0)

    frame = pd.DataFrame(
        {
            "customer_key": full["customer_id"].to_numpy(),
            "p_alive": alive.mean(axis=1),
            "pred_orders": orders.mean(axis=1),
            "p10": np.quantile(value, 0.1, axis=1),
            "p50": np.quantile(value, 0.5, axis=1),
            "p90": np.quantile(value, 0.9, axis=1),
            "mean": expected.mean(axis=1),
        }
    )
    return frame, expected


def holdout(df: pd.DataFrame, cutoff: dt.date, cfg: FitConfig) -> tuple[float | None, pd.DataFrame]:
    calib_end = cutoff - dt.timedelta(days=HOLDOUT_DAYS)
    calib = df[df["order_date"] < pd.Timestamp(calib_end)]
    if calib["customer_key"].nunique() < MIN_CUSTOMERS:
        return None, pd.DataFrame()
    data = rfm(calib, calib_end - dt.timedelta(days=1))
    if (data["frequency"] > 0).sum() < MIN_REPEATERS:
        return None, pd.DataFrame()
    bg, gg = fit(data, cfg)
    pred, _ = predict(bg, gg, data, HOLDOUT_DAYS)
    window = df[
        (df["order_date"] >= pd.Timestamp(calib_end)) & (df["order_date"] < pd.Timestamp(cutoff))
    ]
    actual = window.groupby("customer_key")["net_revenue"].sum()
    cohort = calib.groupby("customer_key")["cohort_month"].first()
    pred["actual"] = pred["customer_key"].map(actual).fillna(0.0)
    pred["cohort_month"] = pred["customer_key"].map(cohort)
    by_cohort = (
        pred.groupby("cohort_month")
        .agg(
            customers=("customer_key", "count"),
            predicted_revenue=("mean", "sum"),
            actual_revenue=("actual", "sum"),
        )
        .reset_index()
    )
    scored = by_cohort[(by_cohort["actual_revenue"] > 0) & (by_cohort["customers"] >= 30)]
    if scored.empty:
        return None, by_cohort
    mape = float(
        (
            abs(scored["predicted_revenue"] - scored["actual_revenue"]) / scored["actual_revenue"]
        ).mean()
    )
    return mape, by_cohort


def group_draws(df: pd.DataFrame, pred: pd.DataFrame, expected: np.ndarray) -> pd.DataFrame:
    """Per (channel, cohort month): customers and the sum of expected value for each posterior
    draw. Additive, so the API can sum any date range and read quantiles of the mean."""
    dims = df.groupby("customer_key")[["acquisition_channel", "cohort_month"]].first()
    keys = dims.loc[pred["customer_key"]].reset_index(drop=True)
    out = []
    for (channel, month), rows in keys.groupby(
        ["acquisition_channel", "cohort_month"]
    ).groups.items():
        ix = np.asarray(list(rows))
        out.append(
            {
                "acquisition_channel": channel,
                "cohort_month": month,
                "customers": len(ix),
                "draw_sums": expected[ix].sum(axis=0).round(2).tolist(),
            }
        )
    return pd.DataFrame(out)


def write(
    conn: Conn,
    version: str,
    cutoff: dt.date,
    cfg: FitConfig,
    pred: pd.DataFrame,
    mape: float | None,
    by_cohort: pd.DataFrame,
    diagnostics: dict,
    groups: pd.DataFrame | None = None,
) -> None:
    import json

    conn.execute(
        "insert into raw.clv_runs (model_version, cutoff_date, method, n_customers, holdout_days, holdout_mape, diagnostics) "
        "values (%s, %s, %s, %s, %s, %s, %s)",
        (version, cutoff, cfg.method, len(pred), HOLDOUT_DAYS, mape, json.dumps(diagnostics)),
    )
    with (
        conn.cursor() as cur,
        cur.copy(
            "copy raw.clv_predictions (model_version, customer_key, p_alive, pred_orders_12m, "
            "pred_ltv_12m_p10, pred_ltv_12m_p50, pred_ltv_12m_p90) from stdin"
        ) as copy,
    ):
        for r in pred.itertuples(index=False):
            copy.write_row(
                (
                    version,
                    r.customer_key,
                    float(r.p_alive),
                    float(r.pred_orders),
                    float(r.p10),
                    float(r.p50),
                    float(r.p90),
                )
            )
    for r in by_cohort.itertuples(index=False):
        conn.execute(
            "insert into raw.clv_holdout (model_version, cohort_month, customers, predicted_revenue, actual_revenue) "
            "values (%s, %s, %s, %s, %s)",
            (
                version,
                r.cohort_month,
                int(r.customers),
                float(r.predicted_revenue),
                float(r.actual_revenue),
            ),
        )
    for g in groups.itertuples(index=False) if groups is not None else []:
        conn.execute(
            "insert into raw.clv_group_draws (model_version, acquisition_channel, cohort_month, customers, draw_sums) "
            "values (%s, %s, %s, %s, %s)",
            (version, g.acquisition_channel, g.cohort_month, int(g.customers), g.draw_sums),
        )
    # Keep the last four fits; older predictions are dead weight.
    conn.execute(
        "delete from raw.clv_runs where model_version not in "
        "(select model_version from raw.clv_runs order by fitted_at desc limit 4)"
    )
    conn.commit()


def run_clv_fit(*, trigger: str, job_id: int | None = None, cfg: FitConfig | None = None) -> dict:
    from pipeline.ingest.core import ensure_raw_schema
    from pipeline.worker.refresh import Run, run_refresh

    cfg = cfg or FitConfig()
    with connect() as conn:
        ensure_raw_schema(conn)
        run = Run(conn, "clv_fit", trigger, job_id)
        try:
            df, cutoff = run.step("load", lambda: load_orders(conn))
            if df["customer_key"].nunique() < MIN_CUSTOMERS:
                raise RuntimeError(f"too few customers for a CLV model (need {MIN_CUSTOMERS})")
            t0 = time.monotonic()
            mape, by_cohort = run.step("holdout", lambda: holdout(df, cutoff, cfg))
            data = rfm(df, cutoff - dt.timedelta(days=1))
            bg, gg = run.step("fit", lambda: fit(data, cfg))
            pred, expected = run.step(
                "predict", lambda: predict(bg, gg, data, HORIZON_DAYS, seed=cfg.seed)
            )
            groups = group_draws(df, pred, expected)
            version = f"bgnbd-gg-{cutoff:%Y%m%d}-{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%S}"
            diagnostics = {
                "fit_seconds": round(time.monotonic() - t0, 1),
                "draws": cfg.draws,
                "chains": cfg.chains,
                "repeaters": int((data["frequency"] > 0).sum()),
            }
            run.step(
                "write",
                lambda: write(
                    conn, version, cutoff, cfg, pred, mape, by_cohort, diagnostics, groups
                ),
            )
            run.finish(
                "published",
                data_version=version,
                reconciliation={"holdout_mape": mape, "holdout_days": HOLDOUT_DAYS},
            )
        except Exception as e:
            conn.rollback()
            run.finish("failed", error=f"{type(e).__name__}: {e}"[:4000])
            log.exception("clv fit failed")
            raise
    log.info("clv fit written", extra={"model_version": version, "holdout_mape": mape})
    # Predictions reach the dashboard through the same build-audit-publish path.
    refresh = run_refresh(trigger=f"clv:{trigger}", skip_ingest=True)
    return {
        "model_version": version,
        "holdout_mape": mape,
        "customers": len(pred),
        "refresh": refresh["status"],
    }

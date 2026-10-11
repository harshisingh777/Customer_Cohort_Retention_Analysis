"""Store-level settings kept in ops.settings and passed to dbt as vars.

Changing any of these changes metric definitions, so a change triggers a rebuild.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

from pydantic import BaseModel, Field, field_validator


class StoreSettings(BaseModel):
    store_name: str = "Demo store"
    reporting_tz: str = "Europe/London"
    reporting_currency: str = "GBP"
    locale: str = "en-GB"
    qualifying_statuses: list[str] = Field(
        default_factory=lambda: [
            "paid",
            "completed",
            "processing",
            "fulfilled",
            "partially_refunded",
            "delivered",
            "shipped",
            "invoiced",
        ]
    )
    lapse_threshold_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description="Admin override. Null means derive from purchase gaps.",
    )
    gross_margin: float | None = Field(
        default=None, gt=0, le=1, description="Assumption used for payback. Null hides payback."
    )
    # Data cutoff. Null means "today in the reporting timezone"; static datasets pin it.
    as_of_date: dt.date | None = None
    refresh_time_local: str = "02:00"
    clv_weekday: int = Field(
        default=6, ge=0, le=6, description="0=Monday. Day of the weekly CLV fit."
    )

    @field_validator("reporting_tz")
    @classmethod
    def _tz(cls, v: str) -> str:
        if v not in available_timezones():
            raise ValueError(f"Unknown timezone {v!r}")
        return v

    @field_validator("reporting_currency")
    @classmethod
    def _ccy(cls, v: str) -> str:
        if len(v) != 3 or not v.isalpha():
            raise ValueError("Currency must be a 3-letter ISO code")
        return v.upper()

    @field_validator("refresh_time_local")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        dt.datetime.strptime(v, "%H:%M")
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.reporting_tz)

    def dbt_vars(self) -> dict[str, Any]:
        return {
            "reporting_tz": self.reporting_tz,
            "reporting_currency": self.reporting_currency,
            "qualifying_statuses": self.qualifying_statuses,
            "lapse_threshold_override": self.lapse_threshold_days,
            "gross_margin": self.gross_margin,
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
        }


def load_store_settings(rows: list[tuple[str, Any]]) -> StoreSettings:
    """Build settings from (key, jsonb value) rows of ops.settings."""
    return StoreSettings.model_validate({k: v for k, v in rows})

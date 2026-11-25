"""Typed model of the market configuration (config/atlas.yaml)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

Channel = Literal["TRADITIONAL", "MODERN_TRADE", "HORECA", "ECOMMERCE"]
CHANNELS: tuple[Channel, ...] = ("TRADITIONAL", "MODERN_TRADE", "HORECA", "ECOMMERCE")

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "atlas.yaml"


class Region(BaseModel):
    code: str
    name: str
    warehouse: str
    extra_lead_days: int = Field(default=0, ge=0)
    cities: dict[str, float]


class Warehouse(BaseModel):
    code: str
    name: str
    city: str
    lead_days: int = Field(ge=0)


class ChannelProfile(BaseModel):
    share: float = Field(gt=0, le=1)
    city_weight_exponent: float = Field(gt=0)
    orders_per_day: float = Field(gt=0)
    lines_per_order: float = Field(gt=0)
    units_per_line: float = Field(gt=0)
    weekday_factors: list[float] = Field(min_length=7, max_length=7)


class Category(BaseModel):
    key: str
    name: str
    weight: float = Field(gt=0)
    price: tuple[float, float]
    types: list[str] = Field(min_length=1)
    packs: list[str] = Field(min_length=1)


class Brand(BaseModel):
    name: str
    categories: list[str] = Field(min_length=1)


class Names(BaseModel):
    shop_prefixes: dict[Channel, list[str]]
    shop_words: list[str]
    first_names: list[str]
    last_names: list[str]


class EidEffect(BaseModel):
    week_before: float = Field(gt=0)
    first_day: float = Field(gt=0)
    following_days: float = Field(gt=0)


class RamadanEffect(BaseModel):
    channel_factors: dict[Channel, float]
    category_uplift: dict[str, float]


class Seasonality(BaseModel):
    amplitude: float = Field(ge=0, lt=1)
    peak_day: int = Field(ge=1, le=366)


class Lifecycle(BaseModel):
    cancellation_rate: float = Field(ge=0, lt=1)
    late_delivery_rate: float = Field(ge=0, lt=1)
    partial_delivery_rate: float = Field(ge=0, lt=1)
    return_rate: float = Field(ge=0, lt=1)


class HistorySettings(BaseModel):
    end: date
    promotions_per_month: float = Field(ge=0)
    price_increases_per_product: float = Field(ge=0)


class Demand(BaseModel):
    yearly_trend: float
    customer_size_sigma: float = Field(ge=0)
    market_shock_shape: float = Field(gt=0)
    public_holiday: float = Field(gt=0)
    eid: EidEffect
    ramadan: RamadanEffect
    seasonality: dict[str, Seasonality]
    popularity_exponent: float = Field(ge=0)
    promotion_uplift: float = Field(ge=1)
    volume_discounts: list[tuple[int, float]]
    lifecycle: Lifecycle
    history: HistorySettings


class MarketConfig(BaseModel):
    customers: int = Field(gt=0)
    sales_reps: int = Field(gt=0)
    products: int = Field(gt=0)
    regions: list[Region]
    warehouses: list[Warehouse]
    channels: dict[Channel, ChannelProfile]
    categories: list[Category]
    brands: list[Brand]
    names: Names
    demand: Demand

    @model_validator(mode="after")
    def check_references(self) -> MarketConfig:
        warehouse_codes = {w.code for w in self.warehouses}
        cities = {city for region in self.regions for city in region.cities}
        category_keys = {c.key for c in self.categories}
        for region in self.regions:
            if region.warehouse not in warehouse_codes:
                raise ValueError(f"region {region.code}: unknown warehouse {region.warehouse}")
        for warehouse in self.warehouses:
            if warehouse.city not in cities:
                raise ValueError(f"warehouse {warehouse.code}: unknown city {warehouse.city}")
        for brand in self.brands:
            unknown = set(brand.categories) - category_keys
            if unknown:
                raise ValueError(f"brand {brand.name}: unknown categories {sorted(unknown)}")
        orphan = category_keys - {c for b in self.brands for c in b.categories}
        if orphan:
            raise ValueError(f"categories without a brand: {sorted(orphan)}")
        if set(self.channels) != set(CHANNELS):
            raise ValueError(f"channels must be exactly {CHANNELS}")
        if abs(sum(p.share for p in self.channels.values()) - 1) > 1e-9:
            raise ValueError("channel shares must add up to 1")
        demand_categories = set(self.demand.ramadan.category_uplift) | set(self.demand.seasonality)
        if demand_categories - category_keys:
            raise ValueError(
                f"demand: unknown categories {sorted(demand_categories - category_keys)}"
            )
        return self


def load_config(path: Path = DEFAULT_CONFIG) -> MarketConfig:
    return MarketConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

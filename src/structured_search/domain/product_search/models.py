"""Product-search task domain models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import AnyUrl, BaseModel, ConfigDict

from structured_search.domain import BaseConstraints, BaseResult


class ProductSearchConstraints(BaseConstraints):
    domain: Literal["product_search"] = "product_search"


class MerchantInfo(BaseModel):
    name: str | None = None
    country: str | None = None


class PricingInfo(BaseModel):
    amount: float | None = None
    currency: str | None = None
    discounted_amount: float | None = None


class RatingInfo(BaseModel):
    value: float | None = None
    count: int | None = None


class ProductRecord(BaseResult):
    model_config = ConfigDict(extra="allow")

    title: str
    brand: str | None = None
    category: str | None = None
    availability: str | None = None
    product_url: AnyUrl | None = None
    image_url: AnyUrl | None = None
    pricing: PricingInfo | None = None
    rating: RatingInfo | None = None
    merchant: MerchantInfo | None = None
    published_at: date | datetime | None = None

"""Catalogue loading and the vocabulary derived from it.

The canonical record is the catalogue row exactly as supplied (attributes stay a dict, missing keys stay missing).
`product_text` is only a retrieval representation; facts are always read from the record itself.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import pandas as pd

from src.config import DATA_DIR

# Catalogue columns a shopper can ask about or constrain on (besides attribute keys).
COLUMN_FIELDS = ["price_inr", "mrp_inr", "discount_inr", "stock_status", "rating", "review_count", "brand", "category",
                 "sub_category"]


def load_catalogue(path: Path = DATA_DIR / "catalogue.jsonl") -> pd.DataFrame:
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    df = pd.DataFrame(rows)
    if df.product_id.duplicated().any():
        raise ValueError("duplicate product_id in catalogue")
    # Product line = the second title token by construction ("Ironnest RippleFlex Natural Rubber Yoga Mat ...").
    df["line_name"] = df.title.str.split().str[1]
    return df


def product_text(row) -> str:
    """Retrieval text: title + taxonomy + every attribute as `key: value`."""
    attrs = "; ".join(f"{k}: {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in row["attributes"].items())
    return f"{row['title']}. Brand: {row['brand']}. Category: {row['category']} > {row['sub_category']}. {attrs}"


@dataclass
class CatalogueVocab:
    catalogue: pd.DataFrame

    @cached_property
    def brands(self) -> list[str]:
        return sorted(self.catalogue.brand.unique())

    @cached_property
    def line_names(self) -> list[str]:
        return sorted(self.catalogue.line_name.unique())

    @cached_property
    def sub_categories(self) -> dict[str, list[str]]:
        """category -> sorted sub-categories"""
        return {c: sorted(g.unique()) for c, g in self.catalogue.groupby("category").sub_category}

    @cached_property
    def all_sub_categories(self) -> list[str]:
        return sorted(s for subs in self.sub_categories.values() for s in subs)

    @cached_property
    def attribute_keys(self) -> list[str]:
        return sorted({k for a in self.catalogue.attributes for k in a})

    @cached_property
    def fields(self) -> list[str]:
        return COLUMN_FIELDS + self.attribute_keys

    @cached_property
    def text_values(self) -> dict[str, set[str]]:
        """field -> every lowercase text value it takes in the catalogue (text and list-of-text fields only)."""
        out: dict[str, set[str]] = {}
        for col in ("brand", "category", "sub_category", "stock_status"):
            out[col] = set(self.catalogue[col].str.lower())
        for attrs in self.catalogue.attributes:
            for k, v in attrs.items():
                for item in v if isinstance(v, list) else [v]:
                    if isinstance(item, str):
                        out.setdefault(k, set()).add(item.lower())
        return out

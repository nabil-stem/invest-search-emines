"""Deduplicate facilities using name similarity, distance, category, and phone."""

import logging

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

log = logging.getLogger(__name__)


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def deduplicate(df: pd.DataFrame, distance_m: float = 50,
                name_threshold: float = 85) -> pd.DataFrame:
    """Flag and remove duplicates. Adds duplicate columns before removal."""
    if df.empty or len(df) < 2:
        return df

    df = df.copy()
    df["is_duplicate_suspect"] = False
    df["duplicate_group_id"] = -1
    df["duplicate_confidence"] = 0.0

    keep = [True] * len(df)
    indices = df.index.tolist()
    group_id = 0

    for i in range(len(indices)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(indices)):
            if not keep[j]:
                continue

            ri, rj = df.loc[indices[i]], df.loc[indices[j]]

            cat_i = str(ri.get("category", ""))
            cat_j = str(rj.get("category", ""))
            if cat_i != cat_j and cat_i != "unknown" and cat_j != "unknown":
                continue

            dist = haversine_m(ri["lat"], ri["lon"], rj["lat"], rj["lon"])
            if dist > distance_m:
                continue

            name_i = str(ri.get("name", "")).strip()
            name_j = str(rj.get("name", "")).strip()

            # Phone match is a strong signal
            phone_match = False
            pi = str(ri.get("phone", "")).strip()
            pj = str(rj.get("phone", "")).strip()
            if pi and pj and pi == pj:
                phone_match = True

            if name_i and name_j:
                sim = fuzz.token_sort_ratio(name_i.lower(), name_j.lower())
                if sim < name_threshold and not phone_match:
                    continue
                conf = sim / 100.0
            elif phone_match:
                conf = 0.85
            elif not name_i and not name_j:
                conf = 0.6
            else:
                continue

            df.at[indices[j], "is_duplicate_suspect"] = True
            df.at[indices[j], "duplicate_group_id"] = group_id
            df.at[indices[j], "duplicate_confidence"] = round(conf, 2)
            df.at[indices[i], "duplicate_group_id"] = group_id
            keep[j] = False
            group_id += 1

    removed = sum(1 for k in keep if not k)
    log.info("Deduplication: %d duplicates flagged out of %d", removed, len(df))

    deduped = df.loc[[indices[i] for i, k in enumerate(keep) if k]].reset_index(drop=True)
    return deduped

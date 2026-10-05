"""決定性 Seed（規格 §15）。

使用 hashlib.sha256，絕不使用 Python 內建 hash()（PYTHONHASHSEED 會讓結果每次不同）。
所有 RNG 都是獨立的 random.Random 實例，絕不使用全域 random。

各欄位以 "|" 分隔後再 hash，避免字串直接相接造成碰撞（例如 "ab"+"c" 與 "a"+"bc"）。
"""

from __future__ import annotations

import hashlib
import random
from datetime import date


def seed_from(*parts: object) -> int:
    key = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def character_seed(world_id: str, character_id: str, local_date: date, simulation_version: str) -> int:
    """Character-local seed = hash(world_id + character_id + local_date + simulation_version)。"""
    return seed_from(world_id, character_id, local_date.isoformat(), simulation_version)


def shared_seed(world_id: str, local_date: date, simulation_version: str) -> int:
    """World-level shared seed = hash(world_id + local_date + "shared" + simulation_version)。"""
    return seed_from(world_id, local_date.isoformat(), "shared", simulation_version)


def make_rng(seed: int, stage: str | None = None) -> random.Random:
    """由 seed 衍生一個獨立 RNG stream。

    stage 用來把同一 seed 拆成多條子 stream（meals / temporary / leisure ...），
    使得調整某一階段的設定不會連帶改變其他階段的結果。
    """
    if stage is None:
        return random.Random(seed)
    return random.Random(seed_from(seed, stage))


def weighted_choice(rng: random.Random, items: list[dict], key: str = "weight") -> dict:
    """依 weight 抽選；列表順序固定，因此結果可重現。"""
    total = sum(max(0.0, float(it.get(key, 0))) for it in items)
    if total <= 0:
        return items[rng.randrange(len(items))]
    x = rng.random() * total
    acc = 0.0
    for it in items:
        acc += max(0.0, float(it.get(key, 0)))
        if x < acc:
            return it
    return items[-1]

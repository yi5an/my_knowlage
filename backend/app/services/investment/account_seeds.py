"""Product-controlled cold-start account recommendations.

The catalog is deliberately small and conservative.  It gives a new workspace
an immediately useful starting point without pretending that a source is
profitable, authoritative for every question, or a substitute for evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

CATALOG_VERSION = "2026-09-15.v1"


@dataclass(frozen=True, slots=True)
class AccountSeed:
    platform: str
    handle: str
    display_name: str
    role_type: str
    theme_ids: tuple[str, ...]
    reason: str
    source_quality: float
    url: str


ACCOUNT_SEEDS: tuple[AccountSeed, ...] = (
    AccountSeed(
        platform="x",
        handle="federalreserve",
        display_name="Federal Reserve",
        role_type="official",
        theme_ids=("theme_macro",),
        reason="关注官方货币政策、金融稳定和监管信息的一手更新，适合建立宏观事件时间线；不代表收益或投资建议。",
        source_quality=0.95,
        url="https://x.com/federalreserve",
    ),
    AccountSeed(
        platform="x",
        handle="nvidia",
        display_name="NVIDIA",
        role_type="company",
        theme_ids=("theme_ai", "theme_semiconductors"),
        reason=(
            "关注公司官方产品、供应链和资本配置更新，帮助核对 AI 与半导体产业链的一手信息；"
            "不代表收益或投资建议。"
        ),
        source_quality=0.9,
        url="https://x.com/nvidia",
    ),
    AccountSeed(
        platform="youtube",
        handle="FederalReserve",
        display_name="Federal Reserve",
        role_type="official",
        theme_ids=("theme_macro",),
        reason="学习央行公开演讲、会议说明和教育内容，补充短消息之外的政策语境；不代表收益或投资建议。",
        source_quality=0.95,
        url="https://www.youtube.com/@FederalReserve",
    ),
    AccountSeed(
        platform="youtube",
        handle="IMF",
        display_name="International Monetary Fund",
        role_type="institution",
        theme_ids=("theme_macro", "theme_markets"),
        reason="学习全球增长、通胀和金融稳定研究，适合建立跨市场宏观观察框架；不代表收益或投资建议。",
        source_quality=0.9,
        url="https://www.youtube.com/@IMF",
    ),
    AccountSeed(
        platform="institution",
        handle="federalreserve.gov",
        display_name="Federal Reserve Board",
        role_type="official",
        theme_ids=("theme_macro",),
        reason="关注联储官网的声明、数据和会议材料，作为宏观情报的可追溯一手来源；不代表收益或投资建议。",
        source_quality=1.0,
        url="https://www.federalreserve.gov/",
    ),
    AccountSeed(
        platform="institution",
        handle="sec.gov",
        display_name="U.S. Securities and Exchange Commission",
        role_type="official",
        theme_ids=("theme_markets",),
        reason="关注监管公告、公司披露和执法信息，帮助验证上市公司与市场结构事实；不代表收益或投资建议。",
        source_quality=1.0,
        url="https://www.sec.gov/",
    ),
)


def seed_metadata(seed: AccountSeed) -> dict[str, object]:
    """Return the auditable metadata stored in a recommendation score breakdown."""

    return {
        "catalog_version": CATALOG_VERSION,
        "seeded": True,
        "source_quality": seed.source_quality,
        "url": seed.url,
        "caveat": "KnowPilot 内置关注建议，不代表收益、权威性或个性化投资建议。",
    }


def seed_candidates(theme_id: str | None = None) -> list[dict[str, object]]:
    """Build fresh mutable candidate dictionaries, optionally filtered by theme."""

    candidates: list[dict[str, object]] = []
    for seed in ACCOUNT_SEEDS:
        if theme_id and theme_id not in seed.theme_ids:
            continue
        candidates.append(
            {
                "platform": seed.platform,
                "handle": seed.handle,
                "display_name": seed.display_name,
                "role_type": seed.role_type,
                "theme_ids": list(seed.theme_ids),
                "reason": seed.reason,
                "source_quality": seed.source_quality,
                "url": seed.url,
                "seeded": True,
                "seed_metadata": seed_metadata(seed),
            }
        )
    return candidates

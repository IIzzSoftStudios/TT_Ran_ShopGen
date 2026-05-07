"""Phase 2 scaffold. Not wired to any handler in Phase 1.

Future ``wipe_campaign_world(campaign_id)`` will clear every generated entity
for one campaign so a regenerate-world UI can reissue a fresh world. Left as
a stub so follow-up work can extend it without adding new files.
"""

from __future__ import annotations


def wipe_campaign_world(campaign_id: int) -> bool:
    """Scaffold: do nothing, return False to signal "not implemented".

    In Phase 2 this will delete (in FK-safe order) ShopInventory,
    RegionalMarket, GlobalMarket, MarketEvent, Shop, Item,
    City, Region, CampaignWorldConfig rows owned by this campaign, then commit.
    """
    _ = campaign_id
    return False

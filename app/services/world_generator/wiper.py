"""Phase 2 scaffold. Not wired to any handler in Phase 1.

Future `wipe_gm_world(gm_profile_id)` will clear every generated entity
for a GM so a regenerate-world UI can reissue a fresh world. Left as a
stub so follow-up work can extend it without adding new files.
"""

from __future__ import annotations


def wipe_gm_world(gm_profile_id: int) -> bool:
    """Scaffold: do nothing, return False to signal "not implemented".

    In Phase 2 this will delete (in FK-safe order) ShopInventory,
    RegionalMarket, GlobalMarket, MarketEvent, Shop, Item,
    City, Region, CampaignWorldConfig rows owned by this GM, then commit.
    """
    _ = gm_profile_id
    return False

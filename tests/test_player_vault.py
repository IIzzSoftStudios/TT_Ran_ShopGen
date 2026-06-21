"""Solo vault + join validation (system type guard)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app import app
from app.routes import player_routes
from app.services.join_codes import (
    SystemMismatchError,
    assert_character_system_matches_campaign,
)


def test_assert_character_allows_when_no_concrete_sheet_type():
    player = MagicMock(id=1)
    campaign = MagicMock(system_type="pf2e")
    with app.app_context():
        with patch(
            "app.services.join_codes.effective_character_system_type_for_join",
            return_value=None,
        ):
            assert_character_system_matches_campaign(player, campaign)


def test_assert_character_blocks_mismatch():
    player = MagicMock(id=1)
    campaign = MagicMock(system_type="pf2e")
    with app.app_context():
        with patch(
            "app.services.join_codes.effective_character_system_type_for_join",
            return_value="dnd5e",
        ):
            with pytest.raises(SystemMismatchError):
                assert_character_system_matches_campaign(player, campaign)


def test_assert_character_allows_matching_types():
    player = MagicMock(id=1)
    campaign = MagicMock(system_type="dnd5e")
    with app.app_context():
        with patch(
            "app.services.join_codes.effective_character_system_type_for_join",
            return_value="dnd5e",
        ):
            assert_character_system_matches_campaign(player, campaign)


def test_assert_character_allows_generic_campaign():
    player = MagicMock(id=1)
    campaign = MagicMock(system_type="generic")
    with app.app_context():
        with patch(
            "app.services.join_codes.effective_character_system_type_for_join",
            return_value="dnd5e",
        ):
            assert_character_system_matches_campaign(player, campaign)


def test_buy_item_blocks_overdraft_when_campaign_debt_is_off():
    player = SimpleNamespace(id=7, campaign_id=3, currency=5)
    campaign = SimpleNamespace(id=3, allow_player_debt=False)
    inventory = SimpleNamespace(
        inventory_id=99,
        dynamic_price=10,
        stock=5,
        item=SimpleNamespace(name="Sword"),
    )

    with app.test_request_context(
        "/player/shop/11/buy/22", method="POST", data={"quantity": "1"}
    ):
        with patch("app.routes.player_routes.get_active_player", return_value=player), \
             patch("app.routes.player_routes.Campaign") as campaign_model, \
             patch("app.routes.player_routes.Shop") as shop_model, \
             patch("app.routes.player_routes.ShopInventory") as inventory_model, \
             patch("app.routes.player_routes.get_effective_price", return_value=10), \
             patch("app.routes.player_routes.get_effective_stock", return_value=5), \
             patch("app.routes.player_routes.db.session.commit") as commit_mock:
            campaign_model.query.filter_by.return_value.first.return_value = campaign
            shop_model.query.filter_by.return_value.first.return_value = SimpleNamespace(id=11)
            inventory_model.query.filter_by.return_value.first.return_value = inventory

            response = player_routes.buy_item.__wrapped__(11, 22)

    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error_code"] == "would_overdraft"
    assert "below 0 Credits" in payload["message"]
    assert payload["new_currency"] == 5
    assert player.currency == 5
    assert inventory.stock == 5
    commit_mock.assert_not_called()


def test_buy_item_allows_overdraft_when_campaign_debt_is_on():
    player = SimpleNamespace(id=7, campaign_id=3, currency=5)
    campaign = SimpleNamespace(id=3, allow_player_debt=True)
    inventory = SimpleNamespace(
        inventory_id=99,
        dynamic_price=10,
        stock=5,
        item=SimpleNamespace(name="Sword"),
    )
    player_inventory = SimpleNamespace(quantity=0)

    with app.test_request_context(
        "/player/shop/11/buy/22", method="POST", data={"quantity": "1"}
    ):
        with patch("app.routes.player_routes.get_active_player", return_value=player), \
             patch("app.routes.player_routes.Campaign") as campaign_model, \
             patch("app.routes.player_routes.Shop") as shop_model, \
             patch("app.routes.player_routes.ShopInventory") as inventory_model, \
             patch("app.routes.player_routes.PlayerInventory") as player_inventory_model, \
             patch("app.routes.player_routes.get_effective_price", return_value=10), \
             patch("app.routes.player_routes.get_effective_stock", return_value=5), \
             patch("app.routes.player_routes.db.session.commit") as commit_mock:
            campaign_model.query.filter_by.return_value.first.return_value = campaign
            shop_model.query.filter_by.return_value.first.return_value = SimpleNamespace(id=11)
            inventory_model.query.filter_by.return_value.first.return_value = inventory
            player_inventory_model.query.filter_by.return_value.first.return_value = (
                player_inventory
            )

            response = player_routes.buy_item.__wrapped__(11, 22)

    payload = response.get_json()
    assert payload["success"] is True
    assert payload["new_currency"] == -5
    assert player.currency == -5
    assert inventory.stock == 4
    assert player_inventory.quantity == 1
    commit_mock.assert_called_once()

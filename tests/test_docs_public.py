"""Public docs routing and onboarding funnel copy surfaces."""

from __future__ import annotations


def test_docs_roadmap_section_renders(client):
    resp = client.get("/docs?section=roadmap")
    assert resp.status_code == 200
    assert b"Product Roadmap" in resp.data
    assert b'id="section-roadmap"' in resp.data
    assert b"data-section=\"roadmap\"" in resp.data
    assert b"player map, population, and encounter parity" not in resp.data.lower()
    assert b"srd level-up/down" in resp.data.lower()
    assert b"battle-board spellcasting" in resp.data.lower()
    assert b"species and monster compendiums" in resp.data
    assert b"Population by species" in resp.data
    assert b"visibility filtering" in resp.data


def test_docs_product_guide_mentions_maps_and_encounters(client):
    resp = client.get("/docs?section=gm-hub")
    assert resp.status_code == 200
    assert b"Maps and player visibility" in resp.data
    assert b"Show to players" in resp.data
    assert b"D&amp;D 5e encounter tools" in resp.data
    assert b"Species and monster compendiums" in resp.data
    assert b"Population by species" in resp.data

    player_resp = client.get("/docs?section=player")
    assert player_resp.status_code == 200
    assert b"character creation wizard" in player_resp.data
    assert b"Dashboard tabs" in player_resp.data
    assert b"Shared maps and encounters" in player_resp.data


def test_docs_items_and_privacy_cover_compendium_data(client):
    items_resp = client.get("/docs?section=items")
    assert items_resp.status_code == 200
    assert b"Compendiums" in items_resp.data
    assert b"monster templates support" in items_resp.data

    privacy_resp = client.get("/docs?section=privacy")
    assert privacy_resp.status_code == 200
    assert b"species, monsters, settlement populations" in privacy_resp.data
    assert b"character creation" in privacy_resp.data


def test_docs_unknown_section_falls_back_to_getting_started(client):
    resp = client.get("/docs?section=not-a-real-section")
    assert resp.status_code == 200
    assert b"Getting Started" in resp.data or b"getting-started" in resp.data


def test_login_page_links_new_users_to_subscribe(client):
    resp = client.get("/auth/login")
    assert resp.status_code == 200
    assert b"/subscribe" in resp.data
    assert b"Register for access as a GM" in resp.data
    assert b"Register for access with a GM Code" in resp.data
    assert b"/auth/register?campaign_code=1" in resp.data


def test_landing_footer_roadmap_links_to_docs_section(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"section=roadmap" in resp.data or b"#roadmap" in resp.data
    assert b"canonical" in resp.data.lower()
    assert b"og:image" in resp.data.lower()

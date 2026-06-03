"""Public docs routing and onboarding funnel copy surfaces."""

from __future__ import annotations


def test_docs_roadmap_section_renders(client):
    resp = client.get("/docs?section=roadmap")
    assert resp.status_code == 200
    assert b"Product Roadmap" in resp.data
    assert b'id="section-roadmap"' in resp.data
    assert b"data-section=\"roadmap\"" in resp.data


def test_docs_unknown_section_falls_back_to_getting_started(client):
    resp = client.get("/docs?section=not-a-real-section")
    assert resp.status_code == 200
    assert b"Getting Started" in resp.data or b"getting-started" in resp.data


def test_login_page_links_new_users_to_access_request(client):
    resp = client.get("/auth/login")
    assert resp.status_code == 200
    assert b"/access-request" in resp.data
    assert b"Register For Access" in resp.data


def test_landing_footer_roadmap_links_to_docs_section(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"section=roadmap" in resp.data or b"#roadmap" in resp.data
    assert b"canonical" in resp.data.lower()
    assert b"og:image" in resp.data.lower()

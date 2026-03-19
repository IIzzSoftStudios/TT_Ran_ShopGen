---
name: Safe Access Form Parse
overview: Add robust numeric parsing/validation for `player_count` and `total_expected_users` in the access-request POST so non-numeric input returns a user-facing error instead of crashing.
todos:
  - id: todo-bugfix-safe-int
    content: Modify `access_request()` POST handler in `TT_Ran_ShopGen/app/routes/main_routes.py` to safely parse `player_count` and `total_expected_users` with try/except ValueError; on invalid input flash warning and redirect back to `main.access_request`.
    status: completed
  - id: todo-keep-business-rules
    content: Preserve existing validations (`player_count > 0` for GM/Both and `total_expected_users >= 1`) after safe parsing.
    status: in_progress
  - id: todo-verify
    content: Manually verify with one invalid crafted request (non-numeric) and one valid request; confirm no 500 and correct redirect/DB insert.
    status: pending
isProject: false
---

## Confirmed bug

- In `app/routes/main_routes.py`, the `/access-request` POST handler does:
  - `player_count = int(request.form.get("player_count") or 0)`
  - `total_expected_users = int(request.form.get("total_expected_users") or 1)`
- If a user submits non-numeric strings for either field (e.g., crafted request), `int(...)` raises `ValueError` and the request will error (500) because there is no local exception handling.

## Implementation (small + localized)

1. Update `c:\Users\Owner\Desktop\Code\Code\TT Shop Gen\TT_Ran_ShopGen\app\routes\main_routes.py` inside `access_request()` POST:
  - Replace direct `int(...)` calls with safe parsing helpers:
    - try/except `ValueError` for each field
    - on failure: `flash("Please enter valid numbers for player count and expected users.", "warning")` and redirect to `url_for("main.access_request")`
  - Keep existing business rules:
    - if `user_role` in `['GM','Both']` and `player_count <= 0`: flash + redirect (already present)
    - clamp/validate `total_expected_users >= 1` (already present)
2. (Optional but recommended) Small code hygiene:
  - Ensure parsed values are integers before constructing `AccessRequest`.

## Verification

- Reproduce by submitting a crafted POST where `player_count="abc"` and/or `total_expected_users="xyz"`.
- Expected result:
  - no 500
  - warning flash and redirect back to `/access-request`.
- Regression check:
  - valid numeric values still create an `AccessRequest` and redirect to `/thank-you`.

## Files changed

- `TT_Ran_ShopGen/app/routes/main_routes.py`


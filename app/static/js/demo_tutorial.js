/**
 * Econo-Forge Demo walkthrough
 * Step 1.x Nations → Step 2.x Cities → Step 3.x Shops → Step 4 Items
 */
(function () {
    'use strict';

    var root = document.getElementById('demo-tutorial-root');
    if (!root || !document.body.classList.contains('gm-dashboard--demo')) return;

    var NATION_HINT = root.getAttribute('data-nation-hint') || "Father's Castel-bari";

    var COPY = {
        point_nations: {
            h: 'Step 1 — Nations',
            t: 'Click Nations in the left rail to open the Nations compendium.'
        },
        draw_on_map: {
            h: 'Step 1.1 — Draw Boundary on map',
            t: 'Click Draw on map for "' + NATION_HINT + '" to start outlining its borders.'
        },
        draw_borders: {
            h: 'Step 1.2 — Nations Borders',
            t: 'Draw the borders for ' + NATION_HINT +
                ' on the world map. When the outline is ready, click Close boundary.'
        },
        open_nations_ruler: {
            h: 'Step 1.3 — Add Ruler',
            t: 'Click Nations again, then Add ruler for "' + NATION_HINT + '".'
        },
        add_ruler: {
            h: 'Step 1.3 — Add Ruler',
            t: 'Click Add ruler for "' + NATION_HINT + '" to open the NPC Creation wizard.'
        },
        wizard_identity: {
            h: 'Step 1.3.1 — Identity',
            t: 'Name the ruler, then click Next in the wizard.'
        },
        wizard_species: {
            h: 'Step 1.3.2 — Species',
            t: 'Choose a species (confirm in the modal if prompted), then Next.'
        },
        wizard_class: {
            h: 'Step 1.3.3 — Class',
            t: 'Choose a class and any required skill picks, then Next.'
        },
        wizard_background: {
            h: 'Step 1.3.4 — Background',
            t: 'Choose a background (confirm in the modal if prompted), then Next.'
        },
        wizard_abilities: {
            h: 'Step 1.3.5 — Abilities',
            t: 'Set ability scores for the ruler, then Next.'
        },
        wizard_review: {
            h: 'Step 1.3.6 — Review',
            t: 'Review the ruler, then click Create NPC to finish.'
        },
        point_cities: {
            h: 'Step 2 — City Placement',
            t: 'Click Cities in the left rail to open the City Compendium.'
        },
        place_cities: {
            h: 'Step 2.1 — Place cities',
            t: 'For each city in "' + NATION_HINT +
                '", click Add to map, then click the world map to place it.'
        },
        owners_info: {
            h: 'Step 2.2 — City owners',
            t: 'You can add Owners to cities the same way you added a Ruler to a nation. ' +
                'We will skip that for now — click Forward to continue.'
        },
        select_city: {
            h: 'Step 2.3 — Select a city',
            t: 'On the world map, click one of the highlighted cities you placed for "' +
                NATION_HINT + '".'
        },
        city_popout: {
            h: 'Step 2.3 — City popout',
            t: 'Review the city briefing beside the marker: population mix, top goods by price, and top goods by average volume.'
        },
        open_city: {
            h: 'Step 2.4 — Open the city',
            t: 'Click Open on the city popout to enter that city map.'
        },
        point_shops: {
            h: 'Step 3 — Shop Placement',
            t: 'Click Shops in the left rail to open the Shop Compendium.'
        },
        place_shops: {
            h: 'Step 3.1 — Place shops',
            t: 'For each shop linked to this city, click Add to map, then click the city map to place it.'
        },
        shop_owners_info: {
            h: 'Step 3.2 — Shop owners',
            t: 'You can add Owners to shops the same way you did for nations and cities. ' +
                'We will skip that for now — click Forward to continue.'
        },
        select_shop: {
            h: 'Step 3.3 — Select a shop',
            t: 'On the city map, click one of the highlighted shops you placed.'
        },
        shop_popout: {
            h: 'Step 3.3 — Shop popout',
            t: 'Review the shop briefing beside the marker: owner, top goods by price, and top goods by average volume.'
        },
        open_shop: {
            h: 'Step 3.4 — Open the shop',
            t: 'Click Open on the shop popout to enter that shop map.'
        },
        point_items: {
            h: 'Step 4 — Items',
            t: 'Click Items in the left rail to open the Item Compendium.'
        },
        items_briefing: {
            h: 'Step 4.1 — Item tools',
            t: 'Read the briefing beside the tools, then click Open full catalog.'
        },
        catalog_explain: {
            h: 'Step 4.2 — Item catalog',
            t: 'This is the full item catalog. Folders filter the list; select items, then stock them into shops. Click Forward when you are ready.'
        },
        catalog_select_item: {
            h: 'Step 4.4 — Select visible',
            t: 'Click the Select visible checkbox at the top of the list to select the items on this page.'
        },
        catalog_stock: {
            h: 'Step 4.4 — Stock in shops',
            t: 'Click Stock in shops to choose which Foundry shops receive the items.'
        },
        catalog_assign_shop: {
            h: 'Step 4.5 — Select Foundry shops',
            t: 'Check both highlighted Foundry shops (Thane\'s Foundry and Governor\'s Foundry).'
        },
        catalog_confirm_stock: {
            h: 'Step 4.6 — Stock items',
            t: 'Click Stock items to add the selected catalog rows into those Foundry shops.'
        },
        back_to_city: {
            h: 'Step 4.7 — Back to city',
            t: 'Click Back to city to return to the city map.'
        },
        select_shop_goods: {
            h: 'Step 4.8 — Review a shop',
            t: 'On the city map, click a shop marker to open its popout and see the updated goods.'
        },
        return_world_map: {
            h: 'Step 4.9 — World map',
            t: 'Click Back to world map to return to the campaign overview.'
        },
        select_city_goods: {
            h: 'Step 4.10 — City goods',
            t: 'Click a highlighted city marker on the world map to open its popout — top goods now reflect stocked inventory.'
        },
        point_market: {
            h: 'Step 5 — Market',
            t: 'Click Market in the left rail to open the market overview.'
        },
        market_explain: {
            h: 'Step 5.1 — Market overview',
            t: 'Read the market briefing, then click Forward to continue.'
        },
        point_calendar: {
            h: 'Step 6 — Calendar',
            t: 'Click Calendar in the left rail.'
        },
        calendar_explain: {
            h: 'Step 6 — Calendar',
            t: 'Read the calendar briefing, then click Forward to continue.'
        },
        sim_week: {
            h: 'Step 6.1 — Simulate one week',
            t: 'Click Week in the top bar to advance the market clock by one week.'
        },
        sim_result: {
            h: 'Step 6.2 — Simulation results',
            t: 'Read the simulation summary on the map, then click Forward to continue.'
        },
        point_species: {
            h: 'Step 7 — Species',
            t: 'Click Species in the left rail to open the Species Compendium.'
        },
        species_explain: {
            h: 'Step 7.1 — Species',
            t: 'Read the Species briefing, then click Forward to continue.'
        },
        point_traits: {
            h: 'Step 8 — Traits',
            t: 'Click Traits in the left rail.'
        },
        traits_explain: {
            h: 'Step 8.1 — Traits',
            t: 'Read the Traits briefing, then click Forward to continue.'
        },
        point_classes: {
            h: 'Step 9 — Classes',
            t: 'Click Classes in the left rail.'
        },
        classes_explain: {
            h: 'Step 9.1 — Classes',
            t: 'Read the Classes briefing, then click Forward to continue.'
        },
        point_spells: {
            h: 'Step 10 — Spells',
            t: 'Click Spells in the left rail.'
        },
        spells_explain: {
            h: 'Step 10.1 — Spells',
            t: 'Read the Spells briefing, then click Forward to continue.'
        },
        point_monsters: {
            h: 'Step 11 — Monsters',
            t: 'Click Monsters in the left rail.'
        },
        monsters_explain: {
            h: 'Step 11.1 — Monsters',
            t: 'Read the Monsters briefing, then click Forward to continue.'
        },
        invite_open: {
            h: 'Step 12 — Add a player',
            t: 'Click GM Campaign Code in the top bar to open the invite tools.'
        },
        invite_reveal: {
            h: 'Step 12 — Reveal the code',
            t: 'Click Reveal to show the CAMP- join code.'
        },
        invite_copy: {
            h: 'Step 12 — Copy the code',
            t: 'Select the revealed code and copy it (Ctrl+C / Cmd+C) so a player can join.'
        },
        point_profile: {
            h: 'Step 12 — Profile menu',
            t: 'Click your profile icon in the corner to open the account menu.'
        },
        switch_campaigns: {
            h: 'Step 12 — Switch campaigns',
            t: 'Click Switch campaigns to leave this demo campaign when you are ready.'
        }
    };

    var WIZARD_PHASES = [
        'wizard_identity',
        'wizard_species',
        'wizard_class',
        'wizard_background',
        'wizard_abilities',
        'wizard_review'
    ];
    var WIZARD_STEP_TO_PHASE = {
        identity: 'wizard_identity',
        species: 'wizard_species',
        class: 'wizard_class',
        background: 'wizard_background',
        abilities: 'wizard_abilities',
        review: 'wizard_review'
    };

    var modal = document.getElementById('demo-tutorial-modal');
    var coach = document.getElementById('demo-tutorial-coach');
    var coachHeading = document.getElementById('demo-coach-heading');
    var coachBody = document.getElementById('demo-coach-body');
    var unlockCountdownEl = document.getElementById('demo-unlock-countdown');
    var dismiss = document.getElementById('demo-tutorial-dismiss');
    var backBtn = document.getElementById('demo-coach-back');
    var forwardBtn = document.getElementById('demo-coach-forward');

    var arrowRoot = document.createElement('div');
    arrowRoot.id = 'demo-tutorial-arrow';
    arrowRoot.setAttribute('aria-hidden', 'true');
    arrowRoot.hidden = true;
    arrowRoot.innerHTML =
        '<div class="demo-arrow-shaft"></div><div class="demo-arrow-head"></div>';
    document.body.appendChild(arrowRoot);
    var arrowShaft = arrowRoot.querySelector('.demo-arrow-shaft');
    var arrowHeadEl = arrowRoot.querySelector('.demo-arrow-head');

    var phase = 'welcome';
    var mouse = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
    var arrowTarget = null;
    var arrowRaf = 0;
    var arrowIframeSync = null;
    var closeUnlockTimer = null;
    var closeArrowTimer = null;
    var drawingActive = false;
    var awaitingMapDraw = false;
    var cityPlacePoll = null;
    var citySelectDone = false;
    var cityOpenUnlockTimer = null;

    var STEP_TRAIL = [
        'point_nations',
        'draw_on_map',
        'draw_borders',
        'open_nations_ruler',
        'add_ruler',
        'wizard_identity',
        'wizard_species',
        'wizard_class',
        'wizard_background',
        'wizard_abilities',
        'wizard_review',
        'point_cities',
        'place_cities',
        'owners_info',
        'select_city',
        'city_popout',
        'open_city',
        'point_shops',
        'place_shops',
        'shop_owners_info',
        'select_shop',
        'shop_popout',
        'open_shop',
        'point_items',
        'items_briefing',
        'catalog_explain',
        'catalog_select_item',
        'catalog_stock',
        'catalog_assign_shop',
        'catalog_confirm_stock',
        'back_to_city',
        'select_shop_goods',
        'return_world_map',
        'select_city_goods',
        'point_market',
        'market_explain',
        'point_calendar',
        'calendar_explain',
        'sim_week',
        'sim_result',
        'point_species',
        'species_explain',
        'point_traits',
        'traits_explain',
        'point_classes',
        'classes_explain',
        'point_spells',
        'spells_explain',
        'point_monsters',
        'monsters_explain',
        'invite_open',
        'invite_reveal',
        'invite_copy',
        'point_profile',
        'switch_campaigns'
    ];
    var navIndex = -1;
    var maxNavIndex = -1;
    var navigating = false;
    var FORCE_FORWARD_PHASES = {
        owners_info: true,
        shop_owners_info: true,
        catalog_explain: true,
        market_explain: true,
        calendar_explain: true,
        sim_result: true,
        species_explain: true,
        traits_explain: true,
        classes_explain: true,
        spells_explain: true,
        monsters_explain: true
    };
    var demoSelectedCityName = '';
    var demoSelectedShopName = '';
    var shopPlacePoll = null;
    var shopSelectDone = false;
    var shopGoodsSelectDone = false;
    var cityGoodsSelectDone = false;
    var openUnlockNextPhase = 'open_city';
    var unlockCountdownInterval = null;
    var OPEN_UNLOCK_SECONDS = 5;
    var CLOSE_UNLOCK_SECONDS = 5;
    var catalogFrameBound = false;
    var FOUNDRY_HINT = 'foundry';

    function isElementVisible(el) {
        return !!(el && el.getClientRects && el.getClientRects().length);
    }

    function pointArrowAtAddOrTab(addBtn, tabId) {
        if (addBtn && isElementVisible(addBtn)) {
            pointArrowAt(addBtn);
            return;
        }
        pointArrowAt(document.getElementById(tabId));
    }

    function setPhase(next) {
        phase = next;
        document.body.setAttribute('data-demo-phase', next);
        root.setAttribute('data-demo-phase', next);
    }

    function updateNavButtons() {
        if (!backBtn || !forwardBtn) return;
        var showNav = navIndex >= 0;
        backBtn.hidden = !showNav;
        forwardBtn.hidden = !showNav;
        backBtn.disabled = !showNav || navIndex <= 0;
        // owners_info / city_popout use Forward to unlock the next step.
        var canForceForward = !!FORCE_FORWARD_PHASES[phase];
        forwardBtn.disabled = !showNav || (navIndex >= maxNavIndex && !canForceForward);
    }

    function showCoachFor(key) {
        var c = COPY[key];
        if (!coach || !c) return;
        if (coachHeading) coachHeading.textContent = c.h;
        if (coachBody) coachBody.textContent = c.t;
        coach.hidden = false;
        updateNavButtons();
    }

    function clearUnlockCountdown() {
        if (unlockCountdownInterval) {
            clearInterval(unlockCountdownInterval);
            unlockCountdownInterval = null;
        }
        setUnlockCountdownText('');
    }

    function setUnlockCountdownText(text) {
        if (unlockCountdownEl) {
            if (!text) {
                unlockCountdownEl.hidden = true;
                unlockCountdownEl.textContent = '';
            } else {
                unlockCountdownEl.hidden = false;
                unlockCountdownEl.textContent = text;
            }
        }
        var pop = document.getElementById('demo-city-view-popout');
        if (pop) {
            var popCd = pop.querySelector('.demo-unlock-countdown');
            if (!text) {
                if (popCd) popCd.remove();
            } else {
                if (!popCd) {
                    popCd = document.createElement('p');
                    popCd.className = 'demo-unlock-countdown';
                    pop.appendChild(popCd);
                }
                popCd.textContent = text;
            }
        }
    }

    function startUnlockCountdown(seconds, labelPrefix, onComplete) {
        clearUnlockCountdown();
        var left = Math.max(1, Number(seconds) || 1);
        var prefix = labelPrefix || 'Unlocks in';
        setUnlockCountdownText(prefix + ' ' + left + 's');
        unlockCountdownInterval = setInterval(function () {
            left -= 1;
            if (left <= 0) {
                clearUnlockCountdown();
                if (onComplete) onComplete();
                return;
            }
            setUnlockCountdownText(prefix + ' ' + left + 's');
        }, 1000);
    }

    function clearForwardHighlight() {
        if (!forwardBtn) return;
        forwardBtn.classList.remove('demo-draw-highlight', 'demo-allowed-forward');
    }

    function highlightForward() {
        if (!forwardBtn) return;
        forwardBtn.disabled = false;
        forwardBtn.hidden = false;
        forwardBtn.classList.add('demo-draw-highlight', 'demo-allowed-forward');
        pointArrowAt(forwardBtn);
    }

    function clearIframeArrowProxy() {
        arrowIframeSync = null;
        var proxy = document.getElementById('demo-iframe-arrow-proxy');
        if (proxy) proxy.remove();
    }

    function syncIframeArrowProxy() {
        if (!arrowIframeSync) return null;
        var frame = arrowIframeSync.frame;
        var target = arrowIframeSync.target;
        var proxy = arrowIframeSync.proxy;
        if (!frame || !target || !proxy || !document.body.contains(proxy)) return null;
        try {
            var fr = frame.getBoundingClientRect();
            var tr = target.getBoundingClientRect();
            proxy.style.left = (fr.left + tr.left) + 'px';
            proxy.style.top = (fr.top + tr.top) + 'px';
            proxy.style.width = Math.max(8, tr.width) + 'px';
            proxy.style.height = Math.max(8, tr.height) + 'px';
            return proxy;
        } catch (err) {
            return null;
        }
    }

    function hideArrow() {
        arrowTarget = null;
        clearIframeArrowProxy();
        arrowRoot.hidden = true;
        if (arrowRaf) {
            cancelAnimationFrame(arrowRaf);
            arrowRaf = 0;
        }
    }

    function pointArrowAt(el) {
        if (!el || el.id !== 'demo-iframe-arrow-proxy') {
            clearIframeArrowProxy();
        }
        arrowTarget = el || null;
        if (!arrowTarget) {
            hideArrow();
            return;
        }
        arrowRoot.hidden = false;
        drawArrow();
        if (!arrowRaf) {
            var tick = function () {
                if (!arrowTarget) {
                    arrowRaf = 0;
                    return;
                }
                drawArrow();
                arrowRaf = requestAnimationFrame(tick);
            };
            arrowRaf = requestAnimationFrame(tick);
        }
    }

    function drawArrow() {
        if (!arrowTarget || !arrowShaft || !arrowHeadEl) return;
        if (arrowIframeSync) {
            var synced = syncIframeArrowProxy();
            if (synced) arrowTarget = synced;
        }
        var rect = arrowTarget.getBoundingClientRect();
        if (rect.width < 2 && rect.height < 2) {
            arrowRoot.hidden = true;
            return;
        }
        arrowRoot.hidden = false;
        var tx = rect.left + rect.width / 2;
        var ty = rect.top + Math.min(rect.height / 2, 28);
        var x0 = mouse.x;
        var y0 = mouse.y;
        var dx = tx - x0;
        var dy = ty - y0;
        var len = Math.sqrt(dx * dx + dy * dy) || 1;
        var startPull = Math.min(28, len * 0.15);
        var endPull = Math.min(10, len * 0.08);
        var x1 = x0 + (dx / len) * startPull;
        var y1 = y0 + (dy / len) * startPull;
        var x2 = tx - (dx / len) * endPull;
        var y2 = ty - (dy / len) * endPull;
        var shaftLen = Math.sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1));
        if (shaftLen < 12) {
            arrowRoot.hidden = true;
            return;
        }
        var angleDeg = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
        arrowShaft.style.width = shaftLen + 'px';
        arrowShaft.style.left = x1 + 'px';
        arrowShaft.style.top = y1 + 'px';
        arrowShaft.style.transform = 'rotate(' + angleDeg + 'deg)';
        arrowHeadEl.style.left = x2 + 'px';
        arrowHeadEl.style.top = y2 + 'px';
        arrowHeadEl.style.transform = 'translate(-50%, -50%) rotate(' + angleDeg + 'deg)';
    }

    document.addEventListener('mousemove', function (ev) {
        mouse.x = ev.clientX;
        mouse.y = ev.clientY;
    }, { passive: true });
    window.addEventListener('resize', function () {
        if (arrowTarget) drawArrow();
    });

    function normalizeName(s) {
        return String(s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    }

    function findFathersRow() {
        var tbody = document.getElementById('regions-compendium-body');
        if (!tbody) return null;
        var target = normalizeName(NATION_HINT);
        var rows = tbody.querySelectorAll('tr');
        for (var i = 0; i < rows.length; i++) {
            var nameEl = rows[i].querySelector('td strong');
            if (nameEl && normalizeName(nameEl.textContent) === target) return rows[i];
        }
        return null;
    }

    function findFathersDrawButton() {
        var row = findFathersRow();
        return row ? row.querySelector('[data-compendium-map-region]') : null;
    }

    function findFathersAddRulerButton() {
        var row = findFathersRow();
        if (!row) return null;
        var buttons = row.querySelectorAll('[data-compendium-edit-url], [data-compendium-add-url]');
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            var title = (btn.getAttribute('data-compendium-title') || '').toLowerCase();
            var label = (btn.textContent || '').toLowerCase();
            if (title.indexOf('ruler') !== -1 || label.indexOf('add ruler') !== -1) return btn;
        }
        return null;
    }

    function findFatherCityRows() {
        var tbody = document.getElementById('cities-compendium-body');
        if (!tbody) return [];
        var target = normalizeName(NATION_HINT);
        var out = [];
        tbody.querySelectorAll('tr').forEach(function (row) {
            var tds = row.querySelectorAll('td');
            if (tds.length >= 2 && normalizeName(tds[1].textContent) === target) {
                out.push(row);
            }
        });
        return out;
    }

    function tagAllowedDrawButtons() {
        var tbody = document.getElementById('regions-compendium-body');
        if (!tbody) return;
        tbody.querySelectorAll('[data-compendium-map-region]').forEach(function (btn) {
            btn.classList.remove('demo-allowed-draw', 'demo-draw-highlight');
        });
        var allowed = findFathersDrawButton();
        if (allowed) allowed.classList.add('demo-allowed-draw', 'demo-draw-highlight');
    }

    function tagAllowedRulerButtons() {
        var tbody = document.getElementById('regions-compendium-body');
        if (!tbody) return;
        tbody.querySelectorAll('.demo-allowed-ruler').forEach(function (btn) {
            btn.classList.remove('demo-allowed-ruler', 'demo-draw-highlight');
        });
        var allowed = findFathersAddRulerButton();
        if (allowed) allowed.classList.add('demo-allowed-ruler', 'demo-draw-highlight');
    }

    function tagAllowedCityButtons() {
        var tbody = document.getElementById('cities-compendium-body');
        if (!tbody) return;
        tbody.querySelectorAll('[data-compendium-map-city]').forEach(function (btn) {
            btn.classList.remove('demo-allowed-city', 'demo-draw-highlight');
        });
        findFatherCityRows().forEach(function (row) {
            row.classList.add('demo-father-city-row');
            var btn = row.querySelector('[data-compendium-map-city]:not(.is-on-map):not([disabled])');
            if (btn) btn.classList.add('demo-allowed-city');
        });
        var next = document.querySelector('#cities-compendium-body .demo-allowed-city');
        if (next) next.classList.add('demo-draw-highlight');
        if (phase === 'place_cities') {
            // Placement closes the panel; send the arrow back to Cities until it is open again.
            pointArrowAtAddOrTab(next, 'cities-tab-btn');
        }
    }

    function fatherCitiesAllPlaced() {
        var rows = findFatherCityRows();
        if (!rows.length) return false;
        for (var i = 0; i < rows.length; i++) {
            var pending = rows[i].querySelector('[data-compendium-map-city]:not(.is-on-map):not([disabled])');
            if (pending) return false;
            var anyMapBtn = rows[i].querySelector('[data-compendium-map-city], .map-compendium-map-btn');
            if (!anyMapBtn) return false;
        }
        return true;
    }

    function highlightFatherCityMarkers() {
        document.querySelectorAll('.map-entity-wrap.demo-allowed-city-marker').forEach(function (w) {
            w.classList.remove('demo-allowed-city-marker');
            var m = w.querySelector('.map-marker');
            if (m) m.classList.remove('demo-draw-highlight');
        });
        var target = normalizeName(NATION_HINT);
        document.querySelectorAll('.map-entity-wrap[data-entity-type="city"]').forEach(function (wrap) {
            if (normalizeName(wrap.dataset.region) !== target) return;
            wrap.classList.add('demo-allowed-city-marker');
            var marker = wrap.querySelector('.map-marker');
            if (marker) marker.classList.add('demo-draw-highlight');
        });
    }

    function clearCloseTimers() {
        if (closeUnlockTimer) {
            clearTimeout(closeUnlockTimer);
            closeUnlockTimer = null;
        }
        if (closeArrowTimer) {
            clearTimeout(closeArrowTimer);
            closeArrowTimer = null;
        }
        clearUnlockCountdown();
    }

    function stopCityPlacePoll() {
        if (cityPlacePoll) {
            clearInterval(cityPlacePoll);
            cityPlacePoll = null;
        }
    }

    function stopShopPlacePoll() {
        if (shopPlacePoll) {
            clearInterval(shopPlacePoll);
            shopPlacePoll = null;
        }
    }

    function findTargetShopRows() {
        var tbody = document.getElementById('shops-compendium-body');
        if (!tbody) return [];
        var target = normalizeName(demoSelectedCityName);
        if (!target) return [];
        var out = [];
        tbody.querySelectorAll('tr').forEach(function (row) {
            var tds = row.querySelectorAll('td');
            // Name | Type | Cities | Owner | ...
            if (tds.length >= 3 && normalizeName(tds[2].textContent).indexOf(target) !== -1) {
                out.push(row);
            }
        });
        return out;
    }

    function tagAllowedShopButtons() {
        var tbody = document.getElementById('shops-compendium-body');
        if (!tbody) return;
        tbody.querySelectorAll('[data-compendium-map-shop]').forEach(function (btn) {
            btn.classList.remove('demo-allowed-shop', 'demo-draw-highlight');
        });
        tbody.querySelectorAll('tr').forEach(function (row) {
            row.classList.remove('demo-target-shop-row');
        });
        findTargetShopRows().forEach(function (row) {
            row.classList.add('demo-target-shop-row');
            var btn = row.querySelector('[data-compendium-map-shop]:not(.is-on-map):not([disabled])');
            if (btn) btn.classList.add('demo-allowed-shop');
        });
        var next = document.querySelector('#shops-compendium-body .demo-allowed-shop');
        if (next) next.classList.add('demo-draw-highlight');
        if (phase === 'place_shops') {
            // Placement closes the panel; send the arrow back to Shops until it is open again.
            pointArrowAtAddOrTab(next, 'shops-tab-btn');
        }
    }

    function targetShopsAllPlaced() {
        var rows = findTargetShopRows();
        if (!rows.length) return false;
        for (var i = 0; i < rows.length; i++) {
            var pending = rows[i].querySelector('[data-compendium-map-shop]:not(.is-on-map):not([disabled])');
            if (pending) return false;
            var anyMapBtn = rows[i].querySelector('[data-compendium-map-shop], .map-compendium-map-btn');
            if (!anyMapBtn) return false;
        }
        return true;
    }

    function highlightTargetShopMarkers() {
        document.querySelectorAll('.map-entity-wrap.demo-allowed-shop-marker').forEach(function (w) {
            w.classList.remove('demo-allowed-shop-marker');
            var m = w.querySelector('.map-marker');
            if (m) m.classList.remove('demo-draw-highlight');
        });
        document.querySelectorAll('.map-entity-wrap[data-entity-type="shop"]').forEach(function (wrap) {
            wrap.classList.add('demo-allowed-shop-marker');
            var marker = wrap.querySelector('.map-marker');
            if (marker) marker.classList.add('demo-draw-highlight');
        });
    }

    function clearCityOpenTimer() {
        if (cityOpenUnlockTimer) {
            clearTimeout(cityOpenUnlockTimer);
            cityOpenUnlockTimer = null;
        }
        clearUnlockCountdown();
        document.body.classList.remove('demo-city-open-ready');
        document.querySelectorAll('.map-entity-popout .demo-allowed-open, .map-entity-popout .demo-draw-highlight').forEach(function (el) {
            el.classList.remove('demo-allowed-open', 'demo-draw-highlight');
        });
    }

    function hideCityViewExplainPopout() {
        var el = document.getElementById('demo-city-view-popout');
        if (el) el.remove();
    }

    function positionViewExplainPopout(el, anchorEl) {
        var left = 24;
        var top = 96;
        var anchor = anchorEl || document.querySelector('.map-entity-popout');
        if (anchor) {
            var r = anchor.getBoundingClientRect();
            left = Math.min(window.innerWidth - 340, Math.max(12, r.right + 12));
            top = Math.max(12, Math.min(window.innerHeight - 220, r.top));
            if (left + 320 > window.innerWidth - 8 && r.left > 340) {
                left = Math.max(12, r.left - 332);
            }
        }
        el.style.left = left + 'px';
        el.style.top = top + 'px';
    }

    function showCityViewExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Reading the city briefing</strong>' +
            '<p>The card on the map summarizes this settlement:</p>' +
            '<ul>' +
            '<li><strong>Population</strong> — how many people live here, plus the species mix.</li>' +
            '<li><strong>Goods by price</strong> — the top goods with the highest average prices.</li>' +
            '<li><strong>Goods by average volume</strong> — the top goods that move the most through the market.</li>' +
            '</ul>';
        document.body.appendChild(el);
        positionViewExplainPopout(el);
    }

    function showShopViewExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Reading the shop briefing</strong>' +
            '<p>The card on the map summarizes this shop:</p>' +
            '<ul>' +
            '<li><strong>Owner</strong> — who runs the shop (if assigned).</li>' +
            '<li><strong>Goods by price</strong> — the top goods with the highest average prices.</li>' +
            '<li><strong>Goods by average volume</strong> — the top goods that move the most through this shop.</li>' +
            '</ul>';
        document.body.appendChild(el);
        positionViewExplainPopout(el);
    }

    function showItemsToolsExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Item Compendium tools</strong>' +
            '<p>Two ways to work with items from this panel:</p>' +
            '<ul>' +
            '<li><strong>Add / Stock Item</strong> — open a form to create a new catalog item or stock an existing one into a shop.</li>' +
            '<li><strong>Open full catalog</strong> — open the full item catalog view for browsing, folders, and deeper editing.</li>' +
            '</ul>';
        document.body.appendChild(el);
        var tools = document.querySelector('#items-pane-content .species-compendium-actions');
        positionViewExplainPopout(el, tools || document.getElementById('items-pane-content'));
    }

    function clearItemsCatalogTags() {
        document.querySelectorAll(
            '#items-pane-content .demo-allowed-items-catalog, #items-pane-content .demo-draw-highlight'
        ).forEach(function (el) {
            el.classList.remove('demo-allowed-items-catalog', 'demo-draw-highlight');
        });
    }

    function findItemsOpenFullCatalog() {
        var links = document.querySelectorAll('#items-pane-content a.button');
        for (var i = 0; i < links.length; i++) {
            if (normalizeName(links[i].textContent) === 'open full catalog') {
                return links[i];
            }
        }
        return null;
    }

    function tagItemsCatalogActions() {
        clearItemsCatalogTags();
        var catalog = findItemsOpenFullCatalog();
        if (!catalog) return;
        catalog.classList.add('demo-allowed-items-catalog', 'demo-draw-highlight');
        if (phase === 'items_briefing') pointArrowAt(catalog);
    }

    function getItemsCatalogFrame() {
        return document.querySelector('#items-pane-content .gm-compendium-embed-frame');
    }

    function getItemsCatalogDoc() {
        var frame = getItemsCatalogFrame();
        if (!frame) return null;
        try {
            return frame.contentDocument || null;
        } catch (err) {
            return null;
        }
    }

    function ensureCatalogDemoStyle(doc) {
        if (!doc || !doc.head) return;
        if (doc.getElementById('demo-catalog-lock-style')) return;
        var style = doc.createElement('style');
        style.id = 'demo-catalog-lock-style';
        style.textContent =
            /* Force readable stock modal in embed (iframe may not inherit parent dark-mode). */
            '#bulk-stock-modal .modal-content{' +
            'background:#1e2430!important;color:#e2e8f0!important;' +
            'box-shadow:0 12px 40px rgba(0,0,0,.55)!important;}' +
            '#bulk-stock-modal .modal-content h3{color:#f8fafc!important;}' +
            '#bulk-stock-modal .modal-content label,' +
            '#bulk-stock-modal .modal-content .shop-picker,' +
            '#bulk-stock-modal .modal-content .shop-picker summary,' +
            '#bulk-stock-modal .modal-content .shop-picker strong,' +
            '#bulk-stock-modal .modal-content p{color:#e2e8f0!important;}' +
            '#bulk-stock-modal .modal-content input[type="number"]{' +
            'background:#0f1419!important;color:#f1f5f9!important;border:1px solid #475569!important;}' +
            /* Keep folder/toolbar labels readable while locked (opacity wash made dark-mode text vanish). */
            'body[data-demo-cat] .folder-link,' +
            'body[data-demo-cat] #selected-count,' +
            'body[data-demo-cat] .bulk-toolbar > label {' +
            'opacity:1!important;filter:none!important;}' +
            'body[data-demo-cat="explain"] button,' +
            'body[data-demo-cat="explain"] a,' +
            'body[data-demo-cat="explain"] input,' +
            'body[data-demo-cat="explain"] select,' +
            'body[data-demo-cat="explain"] summary,' +
            'body[data-demo-cat="explain"] label {' +
            'pointer-events:none!important;cursor:not-allowed!important;}' +
            'body[data-demo-cat="explain"] button,' +
            'body[data-demo-cat="explain"] .button,' +
            'body[data-demo-cat="explain"] input,' +
            'body[data-demo-cat="explain"] select {' +
            'opacity:.45!important;}' +
            'body[data-demo-cat="select"] button,' +
            'body[data-demo-cat="select"] a,' +
            'body[data-demo-cat="select"] select,' +
            'body[data-demo-cat="select"] summary,' +
            'body[data-demo-cat="select"] input:not(#select-all-items) {' +
            'pointer-events:none!important;cursor:not-allowed!important;}' +
            'body[data-demo-cat="select"] button,' +
            'body[data-demo-cat="select"] .button,' +
            'body[data-demo-cat="select"] select,' +
            'body[data-demo-cat="select"] input:not(#select-all-items) {' +
            'opacity:.45!important;}' +
            'body[data-demo-cat="select"] #select-all-items,' +
            'body[data-demo-cat="select"] .bulk-toolbar > label:first-child {' +
            'pointer-events:auto!important;opacity:1!important;cursor:pointer!important;' +
            'outline:2px solid #9ecbff;outline-offset:2px;}' +
            'body[data-demo-cat="stock"] button:not(#bulk-stock-btn),' +
            'body[data-demo-cat="stock"] a,' +
            'body[data-demo-cat="stock"] select,' +
            'body[data-demo-cat="stock"] input {' +
            'pointer-events:none!important;opacity:.45!important;cursor:not-allowed!important;}' +
            'body[data-demo-cat="stock"] #bulk-stock-btn {' +
            'pointer-events:auto!important;opacity:1!important;cursor:pointer!important;' +
            'outline:2px solid #9ecbff;outline-offset:2px;}' +
            'body[data-demo-cat="assign"] button,' +
            'body[data-demo-cat="assign"] a,' +
            'body[data-demo-cat="assign"] select,' +
            'body[data-demo-cat="assign"] input:not(.bulk-shop-checkbox.demo-allowed-shop-stock):not(#bulk-stock-qty) {' +
            'pointer-events:none!important;opacity:.45!important;cursor:not-allowed!important;}' +
            'body[data-demo-cat="assign"] .bulk-shop-checkbox.demo-allowed-shop-stock,' +
            'body[data-demo-cat="assign"] label.demo-allowed-shop-stock-label,' +
            'body[data-demo-cat="assign"] details.demo-allowed-shop-city,' +
            'body[data-demo-cat="assign"] details.demo-allowed-shop-city > summary {' +
            'pointer-events:auto!important;opacity:1!important;cursor:pointer!important;}' +
            'body[data-demo-cat="assign"] label.demo-allowed-shop-stock-label {' +
            'outline:2px solid #9ecbff;outline-offset:2px;}' +
            'body[data-demo-cat="confirm"] button:not(#confirm-bulk-stock),' +
            'body[data-demo-cat="confirm"] a,' +
            'body[data-demo-cat="confirm"] select,' +
            'body[data-demo-cat="confirm"] input {' +
            'pointer-events:none!important;opacity:.45!important;cursor:not-allowed!important;}' +
            'body[data-demo-cat="confirm"] #confirm-bulk-stock.demo-allowed-stock-confirm {' +
            'pointer-events:auto!important;opacity:1!important;cursor:pointer!important;' +
            'outline:2px solid #9ecbff;outline-offset:2px;}' +
            'body[data-demo-cat="assign"] #bulk-stock-modal .modal-content,' +
            'body[data-demo-cat="confirm"] #bulk-stock-modal .modal-content,' +
            'body[data-demo-cat="assign"] #bulk-stock-modal label,' +
            'body[data-demo-cat="confirm"] #bulk-stock-modal label,' +
            'body[data-demo-cat="assign"] #bulk-stock-modal summary,' +
            'body[data-demo-cat="confirm"] #bulk-stock-modal summary,' +
            'body[data-demo-cat="assign"] #bulk-stock-modal strong,' +
            'body[data-demo-cat="confirm"] #bulk-stock-modal strong {' +
            'opacity:1!important;filter:none!important;color:#e2e8f0!important;}';
        doc.head.appendChild(style);
    }

    function showCatalogExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>How the item catalog works</strong>' +
            '<p>Use this page to manage the campaign item library and push stock into shops:</p>' +
            '<ul>' +
            '<li><strong>Folders</strong> — filter the catalog by category.</li>' +
            '<li><strong>Select items</strong> — check one or more rows in the list.</li>' +
            '<li><strong>Stock in shops</strong> — assign the selected items into one or more shops.</li>' +
            '</ul>';
        document.body.appendChild(el);
        var panel = document.getElementById('items-pane-content');
        positionViewExplainPopout(el, panel);
    }

    function applyCatalogFramePhase(catPhase) {
        var doc = getItemsCatalogDoc();
        if (!doc || !doc.body) return;
        ensureCatalogDemoStyle(doc);
        doc.body.setAttribute('data-demo-cat', catPhase);
        bindCatalogFrameListeners(doc);
    }

    function pointArrowAtCatalogTarget(selector) {
        var doc = getItemsCatalogDoc();
        var frame = getItemsCatalogFrame();
        if (!doc || !frame) {
            hideArrow();
            return;
        }
        var target = doc.querySelector(selector);
        if (!target) {
            hideArrow();
            return;
        }
        if (target.tagName === 'INPUT') {
            var labelWrap = target.closest('label');
            if (labelWrap) target = labelWrap;
        }
        target.classList.add('demo-draw-highlight');
        try {
            target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        } catch (err) { /* ignore */ }
        var proxy = document.getElementById('demo-iframe-arrow-proxy');
        if (!proxy) {
            proxy = document.createElement('div');
            proxy.id = 'demo-iframe-arrow-proxy';
            proxy.setAttribute('aria-hidden', 'true');
            proxy.style.cssText =
                'position:fixed;pointer-events:none;z-index:2147482999;margin:0;padding:0;border:0;';
            document.body.appendChild(proxy);
        }
        arrowIframeSync = { frame: frame, target: target, proxy: proxy };
        syncIframeArrowProxy();
        pointArrowAt(proxy);
    }

    function findFoundryShopCheckboxes(doc) {
        if (!doc) return [];
        var out = [];
        doc.querySelectorAll('.bulk-shop-checkbox').forEach(function (cb) {
            var label = cb.closest('label');
            var text = normalizeName(label && label.textContent);
            if (text.indexOf(FOUNDRY_HINT) !== -1) out.push(cb);
        });
        return out;
    }

    function foundryShopsAllChecked(doc) {
        var boxes = findFoundryShopCheckboxes(doc);
        if (boxes.length < 2) return boxes.length > 0 && boxes.every(function (cb) { return cb.checked; });
        var checked = 0;
        boxes.forEach(function (cb) { if (cb.checked) checked += 1; });
        return checked >= 2;
    }

    function prepareCatalogShopAssignment() {
        var doc = getItemsCatalogDoc();
        if (!doc) return;
        var modal = doc.getElementById('bulk-stock-modal');
        if (modal) modal.style.display = 'block';
        doc.querySelectorAll(
            '.demo-allowed-shop-stock, .demo-allowed-shop-stock-label, .demo-allowed-stock-confirm, .demo-allowed-shop-city'
        ).forEach(function (el) {
            el.classList.remove(
                'demo-allowed-shop-stock',
                'demo-allowed-shop-stock-label',
                'demo-allowed-stock-confirm',
                'demo-allowed-shop-city'
            );
        });
        var foundryBoxes = findFoundryShopCheckboxes(doc);
        foundryBoxes.forEach(function (shopCb) {
            shopCb.classList.add('demo-allowed-shop-stock');
            var label = shopCb.closest('label');
            if (label) label.classList.add('demo-allowed-shop-stock-label');
            var picker = doc.querySelector('.shop-picker');
            if (picker) {
                Array.prototype.forEach.call(picker.children, function (d) {
                    if (d.tagName === 'DETAILS' && d.contains(shopCb)) {
                        d.open = true;
                        d.classList.add('demo-allowed-shop-city');
                    }
                });
            }
        });
        var firstFoundryLabel = doc.querySelector('.demo-allowed-shop-stock-label');
        if (firstFoundryLabel) {
            pointArrowAtCatalogTarget('.demo-allowed-shop-stock-label');
        } else {
            hideArrow();
        }
        var confirmBtn = doc.getElementById('confirm-bulk-stock');
        if (confirmBtn) confirmBtn.classList.remove('demo-allowed-stock-confirm', 'demo-draw-highlight');
    }

    function prepareCatalogConfirmStock() {
        var doc = getItemsCatalogDoc();
        if (!doc) return;
        applyCatalogFramePhase('confirm');
        var confirmBtn = doc.getElementById('confirm-bulk-stock');
        if (confirmBtn) {
            confirmBtn.classList.add('demo-allowed-stock-confirm', 'demo-draw-highlight');
            pointArrowAtCatalogTarget('#confirm-bulk-stock');
        }
    }

    function bindCatalogFrameListeners(doc) {
        if (!doc || doc.documentElement.getAttribute('data-demo-bound') === '1') return;
        doc.documentElement.setAttribute('data-demo-bound', '1');
        catalogFrameBound = true;

        doc.addEventListener('change', function (ev) {
            var t = ev.target;
            if (!t) return;
            if (phase === 'catalog_select_item' && t.id === 'select-all-items' && t.checked) {
                enterCatalogStock();
                return;
            }
            if (phase === 'catalog_assign_shop' && t.classList && t.classList.contains('bulk-shop-checkbox') &&
                    t.classList.contains('demo-allowed-shop-stock')) {
                if (foundryShopsAllChecked(doc)) {
                    enterCatalogConfirmStock();
                }
                return;
            }
        });

        var stockBtn = doc.getElementById('bulk-stock-btn');
        if (stockBtn) {
            stockBtn.addEventListener('click', function () {
                if (phase !== 'catalog_stock') return;
                setTimeout(function () {
                    enterCatalogAssignShop();
                }, 60);
            });
        }

        var confirmBtn = doc.getElementById('confirm-bulk-stock');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', function () {
                if (phase !== 'catalog_confirm_stock') return;
                if (!confirmBtn.classList.contains('demo-allowed-stock-confirm')) return;
                var modal = doc.getElementById('bulk-stock-modal');
                if (modal) modal.style.display = 'none';
                var frame = getItemsCatalogFrame();
                var advanced = false;
                function goBackToCity() {
                    if (advanced) return;
                    advanced = true;
                    enterBackToCity();
                }
                if (frame) {
                    frame.addEventListener('load', function onStockLoad() {
                        frame.removeEventListener('load', onStockLoad);
                        goBackToCity();
                    });
                }
                // Fallback if the stock POST does not reload the frame.
                setTimeout(goBackToCity, 1200);
            }, true);
        }
    }

    function waitForCatalogFrame(cb, tries) {
        tries = tries == null ? 40 : tries;
        var doc = getItemsCatalogDoc();
        if (doc && doc.body && doc.getElementById('bulk-stock-btn')) {
            cb(doc);
            return;
        }
        if (tries <= 0) return;
        setTimeout(function () {
            waitForCatalogFrame(cb, tries - 1);
        }, 150);
    }

    function openItemsCatalogEmbed() {
        var link = findItemsOpenFullCatalog();
        var panel = document.getElementById('items-pane-content');
        if (!link || !panel || !window.gmCompendiumEmbed) return false;
        var href = link.getAttribute('href');
        if (!href) return false;
        window.gmCompendiumEmbed.open(panel, href, 'Item Catalog');
        catalogFrameBound = false;
        var frame = getItemsCatalogFrame();
        if (frame) {
            frame.addEventListener('load', function onLoad() {
                frame.removeEventListener('load', onLoad);
                catalogFrameBound = false;
                if (getItemsCatalogDoc()) {
                    getItemsCatalogDoc().documentElement.removeAttribute('data-demo-bound');
                }
                waitForCatalogFrame(function () {
                    if (phase === 'catalog_explain' || phase === 'items_briefing') {
                        applyPhaseKey('catalog_explain');
                    }
                });
            });
        }
        return true;
    }

    function closeItemsCatalogEmbed() {
        var panel = document.getElementById('items-pane-content');
        if (!panel) return;
        var doc = getItemsCatalogDoc();
        if (doc) {
            var modal = doc.getElementById('bulk-stock-modal');
            if (modal) modal.style.display = 'none';
        }
        if (window.gmCompendiumEmbed && typeof window.gmCompendiumEmbed.close === 'function') {
            window.gmCompendiumEmbed.close(panel, 'items', true);
        } else {
            var embed = panel.querySelector('.gm-compendium-embed');
            var iframe = embed && embed.querySelector('.gm-compendium-embed-frame');
            if (embed) embed.hidden = true;
            if (iframe) iframe.src = 'about:blank';
            panel.classList.remove('is-compendium-embed-open');
        }
        catalogFrameBound = false;
    }

    function closeSlidePanelsForMap() {
        closeItemsCatalogEmbed();
        if (window.gmDashboard && typeof window.gmDashboard.closeAllPanels === 'function') {
            window.gmDashboard.closeAllPanels();
        }
    }

    function showMarketExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Market overview</strong>' +
            '<p>The Market tab summarizes campaign-wide prices and volumes so you can spot shortages, gluts, and trade pressure at a glance.</p>' +
            '<ul>' +
            '<li><strong>Top movers</strong> — goods with the strongest price or volume signals.</li>' +
            '<li><strong>City comparison</strong> — where inventory is concentrating.</li>' +
            '</ul>' +
            '<p>Click Forward when you are ready to continue.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el, document.getElementById('market-pane-content') || document.getElementById('market-tab-btn'));
    }

    function showCalendarExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Calendar</strong>' +
            '<p>The Calendar tracks the market clock for this campaign. Simulations advance day-by-day from here.</p>' +
            '<ul>' +
            '<li><strong>Current date</strong> — where the economy sits on the timeline.</li>' +
            '<li><strong>Advance controls</strong> — Day / Week / Month in the top bar push the simulation forward.</li>' +
            '</ul>' +
            '<p>Click Forward when you are ready to simulate one week.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el, document.getElementById('sim-pane-content') || document.getElementById('calendar-tab-btn'));
    }

    function showShopGoodsExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Shop goods updated</strong>' +
            '<p>The shop card now reflects stocked inventory — check goods by price and volume.</p>' +
            '<p>Click Forward to return toward the world map.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el);
    }

    function showCityGoodsExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>City goods updated</strong>' +
            '<p>City top goods now include the items you stocked into Foundry shops.</p>' +
            '<p>Click Forward to open the Market tab.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el);
    }

    function showMonstersExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Monsters</strong>' +
            '<p>The Monsters tab holds GM-authored and generated stat blocks for encounters.</p>' +
            '<ul>' +
            '<li><strong>Generate</strong> — create a monster from a seed and challenge rating (same inputs → same result).</li>' +
            '<li><strong>Create / edit</strong> — hand-author HP, AC, attack, and damage for custom foes.</li>' +
            '</ul>' +
            '<p>Click Forward when you are ready to invite a player.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el, document.getElementById('monsters-pane-content') || document.getElementById('monsters-tab-btn'));
    }

    function pointArrowAtCityGoodsMarker() {
        highlightFatherCityMarkers();
        var marker = document.querySelector('.map-entity-wrap.demo-allowed-city-marker .map-marker');
        if (marker) {
            pointArrowAt(marker);
            return;
        }
        hideArrow();
        var tries = 0;
        var poll = setInterval(function () {
            tries += 1;
            if (phase !== 'select_city_goods') {
                clearInterval(poll);
                return;
            }
            highlightFatherCityMarkers();
            var next = document.querySelector('.map-entity-wrap.demo-allowed-city-marker .map-marker');
            if (next) {
                pointArrowAt(next);
                clearInterval(poll);
            } else if (tries > 40) {
                clearInterval(poll);
            }
        }, 200);
    }

    function clearInviteHighlights() {
        document.querySelectorAll(
            '.demo-allowed-campaign-code, .demo-allowed-invite-reveal, .demo-allowed-invite-copy, ' +
            '.demo-allowed-profile, .demo-allowed-switch-campaigns'
        ).forEach(function (el) {
            el.classList.remove(
                'demo-allowed-campaign-code',
                'demo-allowed-invite-reveal',
                'demo-allowed-invite-copy',
                'demo-allowed-profile',
                'demo-allowed-switch-campaigns',
                'demo-draw-highlight'
            );
        });
        document.body.classList.remove('demo-invite-switch-ready');
    }

    function getCampaignCodeDetails() {
        return document.getElementById('gm-campaign-code-details') ||
            document.querySelector('#gm-top-hud details.gm-join-tools');
    }

    function getInviteRevealBtn() {
        return document.querySelector('.gm-campaign-invite-block .invite-reveal-btn');
    }

    function getInviteCodeInput() {
        return document.querySelector('.gm-campaign-invite-block .code-display');
    }

    function prepareInviteOpen() {
        clearInviteHighlights();
        var details = getCampaignCodeDetails();
        if (details) {
            details.open = false;
            var summary = document.getElementById('gm-campaign-code-summary') || details.querySelector('summary');
            if (summary) {
                summary.classList.add('demo-allowed-campaign-code', 'demo-draw-highlight');
                pointArrowAt(summary);
            }
        } else {
            hideArrow();
        }
    }

    function prepareInviteReveal() {
        clearInviteHighlights();
        var details = getCampaignCodeDetails();
        if (details) details.open = true;
        var revealBtn = getInviteRevealBtn();
        if (revealBtn) {
            revealBtn.classList.add('demo-allowed-invite-reveal', 'demo-draw-highlight');
            pointArrowAt(revealBtn);
        } else {
            hideArrow();
        }
    }

    function prepareInviteCopy() {
        clearInviteHighlights();
        var details = getCampaignCodeDetails();
        if (details) details.open = true;
        var input = getInviteCodeInput();
        if (input) {
            input.classList.add('demo-allowed-invite-copy', 'demo-draw-highlight');
            try {
                input.focus();
                input.select();
            } catch (err) { /* ignore */ }
            pointArrowAt(input);
        } else {
            hideArrow();
        }
    }

    function preparePointProfile() {
        clearInviteHighlights();
        var details = getCampaignCodeDetails();
        if (details) details.open = false;
        var avatar = document.getElementById('accountAvatarBtn');
        if (avatar) {
            avatar.classList.add('demo-allowed-profile', 'demo-draw-highlight');
            pointArrowAt(avatar);
        } else {
            hideArrow();
        }
    }

    function prepareSwitchCampaigns() {
        clearInviteHighlights();
        document.body.classList.add('demo-invite-switch-ready');
        persistDemoBridge({ phase: 'campaigns_redeem', active: true });
        var avatar = document.getElementById('accountAvatarBtn');
        var panel = document.getElementById('accountPopoverPanel');
        function highlightSwitch() {
            var link = document.querySelector('#accountPopoverPanel a.account-menu-nav-link');
            if (link) {
                link.classList.add('demo-allowed-switch-campaigns', 'demo-draw-highlight');
                link.addEventListener('click', function () {
                    persistDemoBridge({ phase: 'campaigns_redeem', active: true });
                }, { once: true });
                pointArrowAt(link);
            } else {
                hideArrow();
            }
        }
        if (panel && panel.classList.contains('account-menu-hidden') && avatar) {
            avatar.click();
            setTimeout(highlightSwitch, 100);
        } else {
            highlightSwitch();
        }
    }

    function persistDemoBridge(partial) {
        if (window.EFDemoBridge && typeof window.EFDemoBridge.write === 'function') {
            window.EFDemoBridge.write(partial);
            return;
        }
        try {
            var cur = {};
            try {
                cur = JSON.parse(sessionStorage.getItem('ef_demo_bridge') || '{}') || {};
            } catch (err) {
                cur = {};
            }
            Object.keys(partial || {}).forEach(function (k) {
                cur[k] = partial[k];
            });
            sessionStorage.setItem('ef_demo_bridge', JSON.stringify(cur));
        } catch (err2) { /* ignore */ }
    }

    function storeDemoCampCodeFromInput() {
        var input = getInviteCodeInput();
        if (!input) return;
        var code = String(input.value || '').trim();
        if (!code || code.indexOf('•') !== -1) return;
        persistDemoBridge({ campCode: code, phase: 'campaigns_redeem', active: true });
    }

    function showSimResultExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        var fb = document.getElementById('map-feedback');
        var resultText = fb ? String(fb.textContent || '').trim() : '';
        el.innerHTML =
            '<strong>What just happened</strong>' +
            '<p>The market clock advanced one week. Sales, restocks, and price pressure ran across your shops.</p>' +
            (resultText
                ? '<p><em>' + resultText.replace(/</g, '&lt;') + '</em></p>'
                : '') +
            '<ul>' +
            '<li><strong>Units sold</strong> — simulated demand pulled stock from shelves.</li>' +
            '<li><strong>Restocks</strong> — shops may refill on a schedule when Supply is On.</li>' +
            '</ul>' +
            '<p>Click Forward to tour the Species Compendium.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el, fb || document.getElementById('map-feedback'));
    }

    function waitForSimFinishedThenContinue() {
        /* Kept for compatibility; Week click now advances immediately via enterSimResult(). */
        enterSimResult();
    }

    function showSpeciesExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Species</strong>' +
            '<p>The Species Compendium stores campaign species used by players, NPCs, monsters, and generators.</p>' +
            '<ul>' +
            '<li><strong>Mechanical shells</strong> — ability mods, population tags, and combat effects you control.</li>' +
            '<li><strong>Editable</strong> — add or tweak species without bundled book text.</li>' +
            '</ul>' +
            '<p>Click Forward when you are ready to continue.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el, document.getElementById('species-pane-content') || document.getElementById('species-tab-btn'));
    }

    function showTraitsExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Traits</strong>' +
            '<p>Traits are reusable combat effects — speed, resistances, senses, and similar mechanics.</p>' +
            '<ul>' +
            '<li><strong>Attach by key</strong> — link traits to species or monsters without writing JSON.</li>' +
            '<li><strong>Compendium-backed</strong> — edit once, reuse across the campaign.</li>' +
            '</ul>' +
            '<p>Click Forward when you are ready to continue.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el, document.getElementById('traits-pane-content') || document.getElementById('traits-tab-btn'));
    }

    function showClassesExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Classes</strong>' +
            '<p>The Classes Compendium covers campaign classes and subclasses with level progression.</p>' +
            '<ul>' +
            '<li><strong>Progression</strong> — level 1–20 rows and subclass branches.</li>' +
            '<li><strong>Traits</strong> — attach combat traits from the Traits tab.</li>' +
            '</ul>' +
            '<p>Click Forward when you are ready to continue.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el, document.getElementById('classes-pane-content') || document.getElementById('classes-tab-btn'));
    }

    function showSpellsExplainPopout() {
        hideCityViewExplainPopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Spells</strong>' +
            '<p>The Spell Compendium is the campaign spell catalog — search by name, level, school, or class.</p>' +
            '<ul>' +
            '<li><strong>GM-approved</strong> — player requests can be reviewed before spells become usable.</li>' +
            '<li><strong>Mechanical shells</strong> — editable entries without bundled book text.</li>' +
            '</ul>' +
            '<p>Click Forward when you are ready to continue.</p>';
        document.body.appendChild(el);
        positionViewExplainPopout(el, document.getElementById('spells-pane-content') || document.getElementById('spells-tab-btn'));
    }

    function findCityPopoutOpenButton() {
        var pop = document.querySelector('.map-entity-popout');
        if (!pop) return null;
        var buttons = pop.querySelectorAll('button.button');
        for (var i = 0; i < buttons.length; i++) {
            if (normalizeName(buttons[i].textContent) === 'open') {
                return buttons[i];
            }
        }
        return null;
    }

    function findCityPopoutMoveButton() {
        var pop = document.querySelector('.map-entity-popout');
        if (!pop) return null;
        var buttons = pop.querySelectorAll('button.button');
        for (var i = 0; i < buttons.length; i++) {
            if (normalizeName(buttons[i].textContent) === 'move') {
                return buttons[i];
            }
        }
        return null;
    }

    function lockCityPopoutActions() {
        document.body.classList.remove('demo-city-open-ready');
        var openBtn = findCityPopoutOpenButton();
        var moveBtn = findCityPopoutMoveButton();
        if (openBtn) openBtn.classList.remove('demo-allowed-open', 'demo-draw-highlight');
        if (moveBtn) moveBtn.classList.remove('demo-allowed-open', 'demo-draw-highlight');
    }

    function unlockCityPopoutOpen() {
        clearUnlockCountdown();
        document.body.classList.add('demo-city-open-ready');
        var openBtn = findCityPopoutOpenButton();
        if (openBtn) {
            openBtn.classList.add('demo-allowed-open', 'demo-draw-highlight');
            pointArrowAt(openBtn);
        }
        var nextKey = openUnlockNextPhase || 'open_city';
        unlockTrailKey(nextKey);
        setPhase(nextKey);
        showCoachFor(nextKey);
    }

    function startCityOpenUnlockTimer(nextPhase) {
        clearCityOpenTimer();
        openUnlockNextPhase = nextPhase || 'open_city';
        lockCityPopoutActions();
        startUnlockCountdown(OPEN_UNLOCK_SECONDS, 'Open unlocks in', function () {
            cityOpenUnlockTimer = null;
            if (phase !== 'city_popout' && phase !== 'shop_popout') return;
            unlockCityPopoutOpen();
        });
    }

    function unlockCloseBoundary() {
        document.body.classList.add('demo-close-boundary-ready');
        var closeBtn = document.getElementById('map-region-boundary-close-btn');
        if (closeBtn) closeBtn.classList.add('demo-close-highlight');
    }

    function isDrawPhase(p) {
        return p === 'draw_on_map' || p === 'draw_borders' || p === 'drawing' || p === 'close_ready';
    }

    function isWizardPhase(p) {
        return WIZARD_PHASES.indexOf(p) !== -1;
    }

    function trailIndexOf(key) {
        return STEP_TRAIL.indexOf(key);
    }

    function unlockTrailKey(key) {
        var idx = trailIndexOf(key);
        if (idx < 0) return;
        if (idx > maxNavIndex) maxNavIndex = idx;
        navIndex = idx;
        updateNavButtons();
    }

    function applyPhaseKey(key) {
        // Keep briefing tips through Open; hide once the next section starts.
        var keepCityBrief = key === 'city_popout' || key === 'open_city';
        var keepShopBrief = key === 'shop_popout' || key === 'open_shop';
        var keepItemsBrief = key === 'items_briefing' || key.indexOf('catalog_') === 0;
        if (!keepCityBrief && !keepShopBrief && key !== 'items_briefing') {
            if (!keepItemsBrief || key === 'point_items') {
                hideCityViewExplainPopout();
            }
            if (key !== 'open_city' && key !== 'open_shop') clearCityOpenTimer();
        }
        if (
            key !== 'owners_info' &&
            key !== 'shop_owners_info' &&
            key !== 'catalog_explain' &&
            key !== 'market_explain' &&
            key !== 'calendar_explain' &&
            key !== 'sim_result' &&
            key !== 'species_explain' &&
            key !== 'traits_explain' &&
            key !== 'classes_explain' &&
            key !== 'spells_explain' &&
            key !== 'monsters_explain'
        ) {
            clearForwardHighlight();
        }
        if (key.indexOf('catalog_') !== 0 && key !== 'items_briefing') {
            clearUnlockCountdown();
        }
        setPhase(key);
        showCoachFor(key);

        if (key === 'point_nations') {
            pointArrowAt(document.getElementById('regions-tab-btn'));
        } else if (key === 'draw_on_map') {
            tagAllowedDrawButtons();
            pointArrowAt(findFathersDrawButton());
        } else if (key === 'draw_borders') {
            tagAllowedDrawButtons();
            hideArrow();
            awaitingMapDraw = true;
        } else if (key === 'open_nations_ruler') {
            hideArrow();
            pointArrowAt(document.getElementById('regions-tab-btn'));
        } else if (key === 'add_ruler') {
            tagAllowedRulerButtons();
            var ruler = findFathersAddRulerButton();
            if (ruler) pointArrowAt(ruler);
            else {
                hideArrow();
                var tries = 0;
                var poll = setInterval(function () {
                    tries += 1;
                    tagAllowedRulerButtons();
                    var btn = findFathersAddRulerButton();
                    if (btn) {
                        pointArrowAt(btn);
                        clearInterval(poll);
                    } else if (tries > 40) clearInterval(poll);
                }, 250);
            }
        } else if (isWizardPhase(key)) {
            hideArrow();
        } else if (key === 'point_cities') {
            stopCityPlacePoll();
            pointArrowAt(document.getElementById('cities-tab-btn'));
        } else if (key === 'place_cities') {
            if (window.gmWorldCompendiums && typeof window.gmWorldCompendiums.ensureLoaded === 'function') {
                window.gmWorldCompendiums.ensureLoaded('cities');
            }
            tagAllowedCityButtons();
            stopCityPlacePoll();
            cityPlacePoll = setInterval(function () {
                tagAllowedCityButtons();
                if (fatherCitiesAllPlaced()) {
                    stopCityPlacePoll();
                    enterOwnersInfo();
                }
            }, 500);
        } else if (key === 'owners_info') {
            stopCityPlacePoll();
            hideCityViewExplainPopout();
            highlightForward();
        } else if (key === 'select_city') {
            stopCityPlacePoll();
            hideCityViewExplainPopout();
            citySelectDone = false;
            highlightFatherCityMarkers();
            var first = document.querySelector('.map-entity-wrap.demo-allowed-city-marker .map-marker');
            pointArrowAt(first);
        } else if (key === 'city_popout') {
            stopCityPlacePoll();
            stopShopPlacePoll();
            showCityViewExplainPopout();
            hideArrow();
            startCityOpenUnlockTimer('open_city');
        } else if (key === 'open_city') {
            stopCityPlacePoll();
            stopShopPlacePoll();
            document.body.classList.add('demo-city-open-ready');
            var openBtn = findCityPopoutOpenButton();
            if (openBtn) {
                openBtn.classList.add('demo-allowed-open', 'demo-draw-highlight');
                pointArrowAt(openBtn);
            } else {
                hideArrow();
            }
        } else if (key === 'point_shops') {
            stopCityPlacePoll();
            stopShopPlacePoll();
            pointArrowAt(document.getElementById('shops-tab-btn'));
        } else if (key === 'place_shops') {
            stopCityPlacePoll();
            if (window.gmWorldCompendiums && typeof window.gmWorldCompendiums.ensureLoaded === 'function') {
                window.gmWorldCompendiums.ensureLoaded('shops');
            }
            tagAllowedShopButtons();
            stopShopPlacePoll();
            shopPlacePoll = setInterval(function () {
                tagAllowedShopButtons();
                if (targetShopsAllPlaced()) {
                    stopShopPlacePoll();
                    enterShopOwnersInfo();
                }
            }, 500);
        } else if (key === 'shop_owners_info') {
            stopShopPlacePoll();
            highlightForward();
        } else if (key === 'select_shop') {
            stopShopPlacePoll();
            shopSelectDone = false;
            highlightTargetShopMarkers();
            var firstShop = document.querySelector('.map-entity-wrap.demo-allowed-shop-marker .map-marker');
            pointArrowAt(firstShop);
        } else if (key === 'shop_popout') {
            stopShopPlacePoll();
            showShopViewExplainPopout();
            hideArrow();
            startCityOpenUnlockTimer('open_shop');
        } else if (key === 'open_shop') {
            stopShopPlacePoll();
            document.body.classList.add('demo-city-open-ready');
            var openShopBtn = findCityPopoutOpenButton();
            if (openShopBtn) {
                openShopBtn.classList.add('demo-allowed-open', 'demo-draw-highlight');
                pointArrowAt(openShopBtn);
            } else {
                hideArrow();
            }
        } else if (key === 'point_items') {
            stopShopPlacePoll();
            hideCityViewExplainPopout();
            clearCityOpenTimer();
            clearItemsCatalogTags();
            pointArrowAt(document.getElementById('items-tab-btn'));
        } else if (key === 'items_briefing') {
            stopShopPlacePoll();
            showItemsToolsExplainPopout();
            tagItemsCatalogActions();
        } else if (key === 'catalog_explain') {
            showCatalogExplainPopout();
            applyCatalogFramePhase('explain');
            highlightForward();
        } else if (key === 'catalog_select_item') {
            hideCityViewExplainPopout();
            applyCatalogFramePhase('select');
            pointArrowAtCatalogTarget('#select-all-items');
        } else if (key === 'catalog_stock') {
            hideCityViewExplainPopout();
            applyCatalogFramePhase('stock');
            pointArrowAtCatalogTarget('#bulk-stock-btn');
        } else if (key === 'catalog_assign_shop') {
            hideCityViewExplainPopout();
            applyCatalogFramePhase('assign');
            prepareCatalogShopAssignment();
        } else if (key === 'catalog_confirm_stock') {
            hideCityViewExplainPopout();
            prepareCatalogConfirmStock();
        } else if (key === 'back_to_city') {
            hideCityViewExplainPopout();
            clearUnlockCountdown();
            closeSlidePanelsForMap();
            var shopBack = document.getElementById('map-shop-back-btn');
            if (shopBack) {
                shopBack.hidden = false;
                shopBack.classList.add('demo-allowed-shop-back', 'demo-draw-highlight');
                pointArrowAt(shopBack);
            } else {
                hideArrow();
            }
        } else if (key === 'select_shop_goods') {
            hideCityViewExplainPopout();
            shopGoodsSelectDone = false;
            highlightTargetShopMarkers();
            var firstGoodsShop = document.querySelector('.map-entity-wrap.demo-allowed-shop-marker .map-marker');
            pointArrowAt(firstGoodsShop);
        } else if (key === 'return_world_map') {
            hideCityViewExplainPopout();
            clearUnlockCountdown();
            document.querySelectorAll('.demo-allowed-shop-back, .demo-allowed-world-back').forEach(function (el) {
                el.classList.remove('demo-allowed-shop-back', 'demo-allowed-world-back', 'demo-draw-highlight');
            });
            var worldBack = document.getElementById('map-world-back-btn');
            if (worldBack && !worldBack.hidden) {
                worldBack.classList.add('demo-allowed-world-back', 'demo-draw-highlight');
                pointArrowAt(worldBack);
            } else {
                pointArrowAt(document.getElementById('map-world-back-btn'));
            }
        } else if (key === 'select_city_goods') {
            hideCityViewExplainPopout();
            cityGoodsSelectDone = false;
            highlightFatherCityMarkers();
            pointArrowAtCityGoodsMarker();
        } else if (key === 'point_market') {
            hideCityViewExplainPopout();
            pointArrowAt(document.getElementById('market-tab-btn'));
        } else if (key === 'market_explain') {
            showMarketExplainPopout();
            highlightForward();
        } else if (key === 'point_calendar') {
            hideCityViewExplainPopout();
            pointArrowAt(document.getElementById('calendar-tab-btn'));
        } else if (key === 'calendar_explain') {
            showCalendarExplainPopout();
            highlightForward();
        } else if (key === 'sim_week') {
            hideCityViewExplainPopout();
            var weekBtn = document.getElementById('gm-run-week-btn');
            if (weekBtn) {
                weekBtn.classList.add('demo-allowed-sim-week', 'demo-draw-highlight');
                pointArrowAt(weekBtn);
            } else {
                hideArrow();
            }
        } else if (key === 'sim_result') {
            var fbEl = document.getElementById('map-feedback');
            if (fbEl) {
                fbEl.classList.add('demo-allowed-sim-result', 'demo-draw-highlight');
                pointArrowAt(fbEl);
            }
            showSimResultExplainPopout();
            highlightForward();
        } else if (key === 'point_species') {
            hideCityViewExplainPopout();
            pointArrowAt(document.getElementById('species-tab-btn'));
        } else if (key === 'species_explain') {
            showSpeciesExplainPopout();
            highlightForward();
        } else if (key === 'point_traits') {
            hideCityViewExplainPopout();
            pointArrowAt(document.getElementById('traits-tab-btn'));
        } else if (key === 'traits_explain') {
            showTraitsExplainPopout();
            highlightForward();
        } else if (key === 'point_classes') {
            hideCityViewExplainPopout();
            pointArrowAt(document.getElementById('classes-tab-btn'));
        } else if (key === 'classes_explain') {
            showClassesExplainPopout();
            highlightForward();
        } else if (key === 'point_spells') {
            hideCityViewExplainPopout();
            pointArrowAt(document.getElementById('spells-tab-btn'));
        } else if (key === 'spells_explain') {
            showSpellsExplainPopout();
            highlightForward();
        } else if (key === 'point_monsters') {
            hideCityViewExplainPopout();
            pointArrowAt(document.getElementById('monsters-tab-btn'));
        } else if (key === 'monsters_explain') {
            showMonstersExplainPopout();
            highlightForward();
        } else if (key === 'invite_open') {
            hideCityViewExplainPopout();
            if (window.gmDashboard && typeof window.gmDashboard.closeAllPanels === 'function') {
                window.gmDashboard.closeAllPanels();
            }
            prepareInviteOpen();
        } else if (key === 'invite_reveal') {
            prepareInviteReveal();
        } else if (key === 'invite_copy') {
            prepareInviteCopy();
        } else if (key === 'point_profile') {
            preparePointProfile();
        } else if (key === 'switch_campaigns') {
            prepareSwitchCampaigns();
        }
    }

    function goToTrailIndex(idx, fromNav) {
        if (idx < 0 || idx > maxNavIndex || idx >= STEP_TRAIL.length) return;
        navigating = !!fromNav;
        navIndex = idx;
        var key = STEP_TRAIL[idx];
        if (key === 'point_nations' || key === 'draw_on_map' || key === 'draw_borders' ||
            key === 'open_nations_ruler' || key === 'add_ruler') {
            clearCloseTimers();
            drawingActive = false;
            awaitingMapDraw = false;
            document.body.classList.remove('demo-close-boundary-ready');
            stopCityPlacePoll();
        }
        applyPhaseKey(key);
        navigating = false;
        updateNavButtons();
    }

    function onDrawingStarted() {
        if (drawingActive) return;
        drawingActive = true;
        setPhase('drawing');
        document.body.classList.remove('demo-close-boundary-ready');
        var closeBtn = document.getElementById('map-region-boundary-close-btn');
        if (closeBtn) closeBtn.classList.remove('demo-close-highlight');
        hideArrow();
        clearCloseTimers();
        clearUnlockCountdown();
        showCoachFor('draw_borders');
        startUnlockCountdown(CLOSE_UNLOCK_SECONDS, 'Close boundary unlocks in', function () {
            unlockCloseBoundary();
            setPhase('close_ready');
        });
        closeArrowTimer = setTimeout(function () {
            var btn = document.getElementById('map-region-boundary-close-btn');
            var tools = document.getElementById('map-region-boundary-tools');
            if (!btn || btn.disabled || !tools || tools.hidden) return;
            unlockCloseBoundary();
            setPhase('close_ready');
            clearUnlockCountdown();
            pointArrowAt(btn);
            showCoachFor('draw_borders');
            if (coachBody) {
                coachBody.textContent =
                    'Click Close boundary to finish the nation border for ' + NATION_HINT + '.';
            }
        }, 10000);
    }

    function enterOpenNationsRuler() {
        unlockTrailKey('open_nations_ruler');
        applyPhaseKey('open_nations_ruler');
    }

    function enterAddRuler() {
        unlockTrailKey('add_ruler');
        applyPhaseKey('add_ruler');
    }

    function enterWizardPhase(wizardStep) {
        var key = WIZARD_STEP_TO_PHASE[wizardStep] || 'wizard_identity';
        unlockTrailKey(key);
        applyPhaseKey(key);
    }

    function clearRegionsDemoTags() {
        var pane = document.getElementById('regions-pane-content');
        if (!pane) return;
        pane.querySelectorAll('.demo-allowed-ruler, .demo-allowed-draw, .demo-draw-highlight').forEach(function (el) {
            el.classList.remove('demo-allowed-ruler', 'demo-allowed-draw', 'demo-draw-highlight');
        });
    }

    function closeRegionsEmbed() {
        var panel = document.getElementById('regions-pane-content');
        if (!panel) return;
        if (window.gmCompendiumEmbed && typeof window.gmCompendiumEmbed.close === 'function') {
            window.gmCompendiumEmbed.close(panel, 'regions', true);
        } else {
            var embed = panel.querySelector('.gm-compendium-embed');
            var iframe = embed && embed.querySelector('.gm-compendium-embed-frame');
            if (embed) embed.hidden = true;
            if (iframe) iframe.src = 'about:blank';
            panel.classList.remove('is-compendium-embed-open');
        }
        clearRegionsDemoTags();
    }

    function enterPointCities() {
        closeRegionsEmbed();
        clearRegionsDemoTags();
        unlockTrailKey('point_cities');
        applyPhaseKey('point_cities');
    }

    function enterPlaceCities() {
        unlockTrailKey('place_cities');
        applyPhaseKey('place_cities');
    }

    function enterOwnersInfo() {
        unlockTrailKey('owners_info');
        applyPhaseKey('owners_info');
    }

    function enterSelectCity() {
        unlockTrailKey('select_city');
        applyPhaseKey('select_city');
    }

    function enterCityPopout() {
        unlockTrailKey('city_popout');
        applyPhaseKey('city_popout');
    }

    function enterOpenCity() {
        unlockTrailKey('open_city');
        applyPhaseKey('open_city');
    }

    function enterPointShops() {
        hideCityViewExplainPopout();
        unlockTrailKey('point_shops');
        applyPhaseKey('point_shops');
    }

    function enterPlaceShops() {
        unlockTrailKey('place_shops');
        applyPhaseKey('place_shops');
    }

    function enterShopOwnersInfo() {
        unlockTrailKey('shop_owners_info');
        applyPhaseKey('shop_owners_info');
    }

    function enterSelectShop() {
        unlockTrailKey('select_shop');
        applyPhaseKey('select_shop');
    }

    function enterShopPopout() {
        unlockTrailKey('shop_popout');
        applyPhaseKey('shop_popout');
    }

    function enterOpenShop() {
        unlockTrailKey('open_shop');
        applyPhaseKey('open_shop');
    }

    function enterPointItems() {
        hideCityViewExplainPopout();
        clearCityOpenTimer();
        unlockTrailKey('point_items');
        applyPhaseKey('point_items');
    }

    function enterItemsBriefing() {
        unlockTrailKey('items_briefing');
        applyPhaseKey('items_briefing');
    }

    function enterCatalogExplain() {
        unlockTrailKey('catalog_explain');
        applyPhaseKey('catalog_explain');
    }

    function enterCatalogSelectItem() {
        clearForwardHighlight();
        unlockTrailKey('catalog_select_item');
        applyPhaseKey('catalog_select_item');
    }

    function enterCatalogStock() {
        unlockTrailKey('catalog_stock');
        applyPhaseKey('catalog_stock');
    }

    function enterCatalogAssignShop() {
        unlockTrailKey('catalog_assign_shop');
        applyPhaseKey('catalog_assign_shop');
    }

    function enterCatalogConfirmStock() {
        unlockTrailKey('catalog_confirm_stock');
        applyPhaseKey('catalog_confirm_stock');
    }

    function enterBackToCity() {
        hideCityViewExplainPopout();
        unlockTrailKey('back_to_city');
        applyPhaseKey('back_to_city');
    }

    function enterSelectShopGoods() {
        unlockTrailKey('select_shop_goods');
        applyPhaseKey('select_shop_goods');
    }

    function enterReturnWorldMap() {
        hideCityViewExplainPopout();
        unlockTrailKey('return_world_map');
        applyPhaseKey('return_world_map');
    }

    function enterSelectCityGoods() {
        unlockTrailKey('select_city_goods');
        applyPhaseKey('select_city_goods');
    }

    function enterPointMarket() {
        hideCityViewExplainPopout();
        unlockTrailKey('point_market');
        applyPhaseKey('point_market');
    }

    function enterMarketExplain() {
        unlockTrailKey('market_explain');
        applyPhaseKey('market_explain');
    }

    function enterPointCalendar() {
        hideCityViewExplainPopout();
        unlockTrailKey('point_calendar');
        applyPhaseKey('point_calendar');
    }

    function enterCalendarExplain() {
        unlockTrailKey('calendar_explain');
        applyPhaseKey('calendar_explain');
    }

    function enterSimWeek() {
        hideCityViewExplainPopout();
        unlockTrailKey('sim_week');
        applyPhaseKey('sim_week');
    }

    function enterSimResult() {
        unlockTrailKey('sim_result');
        applyPhaseKey('sim_result');
    }

    function enterPointSpecies() {
        hideCityViewExplainPopout();
        unlockTrailKey('point_species');
        applyPhaseKey('point_species');
    }

    function enterSpeciesExplain() {
        unlockTrailKey('species_explain');
        applyPhaseKey('species_explain');
    }

    function enterPointTraits() {
        hideCityViewExplainPopout();
        unlockTrailKey('point_traits');
        applyPhaseKey('point_traits');
    }

    function enterTraitsExplain() {
        unlockTrailKey('traits_explain');
        applyPhaseKey('traits_explain');
    }

    function enterPointClasses() {
        hideCityViewExplainPopout();
        unlockTrailKey('point_classes');
        applyPhaseKey('point_classes');
    }

    function enterClassesExplain() {
        unlockTrailKey('classes_explain');
        applyPhaseKey('classes_explain');
    }

    function enterPointSpells() {
        hideCityViewExplainPopout();
        unlockTrailKey('point_spells');
        applyPhaseKey('point_spells');
    }

    function enterSpellsExplain() {
        unlockTrailKey('spells_explain');
        applyPhaseKey('spells_explain');
    }

    function enterPointMonsters() {
        hideCityViewExplainPopout();
        unlockTrailKey('point_monsters');
        applyPhaseKey('point_monsters');
    }

    function enterMonstersExplain() {
        unlockTrailKey('monsters_explain');
        applyPhaseKey('monsters_explain');
    }

    function enterInviteOpen() {
        hideCityViewExplainPopout();
        unlockTrailKey('invite_open');
        applyPhaseKey('invite_open');
    }

    function enterInviteReveal() {
        unlockTrailKey('invite_reveal');
        applyPhaseKey('invite_reveal');
    }

    function enterInviteCopy() {
        unlockTrailKey('invite_copy');
        applyPhaseKey('invite_copy');
    }

    function enterPointProfile() {
        unlockTrailKey('point_profile');
        applyPhaseKey('point_profile');
    }

    function enterSwitchCampaigns() {
        unlockTrailKey('switch_campaigns');
        applyPhaseKey('switch_campaigns');
    }

    if (dismiss) {
        dismiss.addEventListener('click', function () {
            if (modal) modal.hidden = true;
            unlockTrailKey('point_nations');
            applyPhaseKey('point_nations');
        });
    }

    if (backBtn) {
        backBtn.addEventListener('click', function () {
            if (navIndex <= 0) return;
            goToTrailIndex(navIndex - 1, true);
        });
    }

    if (forwardBtn) {
        forwardBtn.addEventListener('click', function () {
            if (phase === 'owners_info') {
                enterSelectCity();
                return;
            }
            if (phase === 'shop_owners_info') {
                enterSelectShop();
                return;
            }
            if (phase === 'catalog_explain') {
                enterCatalogSelectItem();
                return;
            }
            if (phase === 'select_shop_goods' && shopGoodsSelectDone) {
                enterReturnWorldMap();
                return;
            }
            if (phase === 'select_city_goods' && cityGoodsSelectDone) {
                enterPointMarket();
                return;
            }
            if (phase === 'market_explain') {
                enterPointCalendar();
                return;
            }
            if (phase === 'calendar_explain') {
                enterSimWeek();
                return;
            }
            if (phase === 'sim_result') {
                enterPointSpecies();
                return;
            }
            if (phase === 'species_explain') {
                enterPointTraits();
                return;
            }
            if (phase === 'traits_explain') {
                enterPointClasses();
                return;
            }
            if (phase === 'classes_explain') {
                enterPointSpells();
                return;
            }
            if (phase === 'spells_explain') {
                enterPointMonsters();
                return;
            }
            if (phase === 'monsters_explain') {
                enterInviteOpen();
                return;
            }
            if (navIndex >= maxNavIndex) return;
            goToTrailIndex(navIndex + 1, true);
        });
    }

    var nationsTab = document.getElementById('regions-tab-btn');
    if (nationsTab) {
        nationsTab.addEventListener('click', function () {
            if (navigating) return;
            if (phase === 'point_nations' || phase === 'welcome') {
                unlockTrailKey('draw_on_map');
                applyPhaseKey('draw_on_map');
            } else if (phase === 'open_nations_ruler') {
                enterAddRuler();
            }
        });
    }

    var citiesTab = document.getElementById('cities-tab-btn');
    if (citiesTab) {
        citiesTab.addEventListener('click', function () {
            if (navigating) return;
            if (phase === 'point_cities') {
                enterPlaceCities();
            } else if (phase === 'place_cities') {
                tagAllowedCityButtons();
            }
        });
    }

    var shopsTab = document.getElementById('shops-tab-btn');
    if (shopsTab) {
        shopsTab.addEventListener('click', function () {
            if (navigating) return;
            if (phase === 'point_shops') {
                enterPlaceShops();
            } else if (phase === 'place_shops') {
                tagAllowedShopButtons();
            }
        });
    }

    var marketTab = document.getElementById('market-tab-btn');
    if (marketTab) {
        marketTab.addEventListener('click', function () {
            if (navigating) return;
            if (phase === 'point_market') {
                setTimeout(function () {
                    enterMarketExplain();
                }, 80);
            }
        });
    }

    var calendarTab = document.getElementById('calendar-tab-btn');
    if (calendarTab) {
        calendarTab.addEventListener('click', function () {
            if (navigating) return;
            if (phase === 'point_calendar') {
                setTimeout(function () {
                    enterCalendarExplain();
                }, 80);
            }
        });
    }

    function bindCompendiumTourTab(tabId, pointPhase, enterExplainFn) {
        var tab = document.getElementById(tabId);
        if (!tab) return;
        tab.addEventListener('click', function () {
            if (navigating) return;
            if (phase === pointPhase) {
                setTimeout(enterExplainFn, 80);
            }
        });
    }
    bindCompendiumTourTab('species-tab-btn', 'point_species', enterSpeciesExplain);
    bindCompendiumTourTab('traits-tab-btn', 'point_traits', enterTraitsExplain);
    bindCompendiumTourTab('classes-tab-btn', 'point_classes', enterClassesExplain);
    bindCompendiumTourTab('spells-tab-btn', 'point_spells', enterSpellsExplain);
    bindCompendiumTourTab('monsters-tab-btn', 'point_monsters', enterMonstersExplain);

    var itemsTab = document.getElementById('items-tab-btn');
    if (itemsTab) {
        itemsTab.addEventListener('click', function () {
            if (navigating) return;
            if (phase === 'point_items') {
                // Wait a beat for the panel to open before anchoring the tip + arrow.
                setTimeout(function () {
                    enterItemsBriefing();
                }, 80);
            }
        });
    }

    document.addEventListener('click', function (ev) {
        var drawBtn = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-draw[data-compendium-map-region]')
            : null;
        if (drawBtn) {
            if (phase === 'draw_on_map') {
                unlockTrailKey('draw_borders');
                applyPhaseKey('draw_borders');
            } else if (isDrawPhase(phase)) {
                awaitingMapDraw = true;
                hideArrow();
            }
            return;
        }

        var rulerBtn = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-ruler')
            : null;
        if (rulerBtn && phase === 'add_ruler') {
            setTimeout(function () {
                enterWizardPhase('identity');
            }, 80);
            return;
        }

        var cityBtn = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-city[data-compendium-map-city]')
            : null;
        if (cityBtn && phase === 'place_cities') {
            hideArrow();
            return;
        }

        var shopBtn = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-shop[data-compendium-map-shop]')
            : null;
        if (shopBtn && phase === 'place_shops') {
            hideArrow();
            return;
        }

        if (
            (phase === 'place_cities' || phase === 'place_shops') &&
            ev.target && ev.target.closest &&
            ev.target.closest('#map-stage, #map-viewport-layer, #map-marker-layer')
        ) {
            // After a drop, panels are closed — retarget the Cities/Shops tab for the next Add.
            setTimeout(function () {
                if (phase === 'place_cities') tagAllowedCityButtons();
                else if (phase === 'place_shops') tagAllowedShopButtons();
            }, 350);
        }

        var cityMarker = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-city-marker .map-marker, .map-entity-wrap.demo-allowed-city-marker')
            : null;
        if (cityMarker && phase === 'select_city' && !citySelectDone) {
            citySelectDone = true;
            setTimeout(function () {
                var titleEl = document.querySelector('.map-entity-popout h3');
                if (titleEl) demoSelectedCityName = String(titleEl.textContent || '').trim();
                enterCityPopout();
            }, 60);
            return;
        }

        var shopMarker = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-shop-marker .map-marker, .map-entity-wrap.demo-allowed-shop-marker')
            : null;
        if (shopMarker && phase === 'select_shop' && !shopSelectDone) {
            shopSelectDone = true;
            setTimeout(function () {
                var titleEl = document.querySelector('.map-entity-popout h3');
                if (titleEl) demoSelectedShopName = String(titleEl.textContent || '').trim();
                enterShopPopout();
            }, 60);
            return;
        }
        if (shopMarker && phase === 'select_shop_goods' && !shopGoodsSelectDone) {
            shopGoodsSelectDone = true;
            setTimeout(function () {
                showShopGoodsExplainPopout();
                highlightForward();
            }, 60);
            return;
        }

        if (cityMarker && phase === 'select_city_goods' && !cityGoodsSelectDone) {
            cityGoodsSelectDone = true;
            setTimeout(function () {
                showCityGoodsExplainPopout();
                highlightForward();
            }, 60);
            return;
        }

        var catalogLink = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-items-catalog')
            : null;
        if (catalogLink && phase === 'items_briefing') {
            ev.preventDefault();
            ev.stopPropagation();
            hideArrow();
            if (openItemsCatalogEmbed()) {
                enterCatalogExplain();
                waitForCatalogFrame(function () {
                    applyCatalogFramePhase('explain');
                    showCatalogExplainPopout();
                    highlightForward();
                });
            }
            return;
        }

        var openEntityBtn = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-open')
            : null;
        if (openEntityBtn && phase === 'open_city') {
            hideArrow();
            var titleEl = document.querySelector('.map-entity-popout h3');
            demoSelectedCityName = titleEl ? String(titleEl.textContent || '').trim() : demoSelectedCityName;
            // City map loads async; then start shop placement coaching.
            setTimeout(function () {
                enterPointShops();
            }, 400);
            return;
        }
        if (openEntityBtn && phase === 'open_shop') {
            hideArrow();
            var shopTitle = document.querySelector('.map-entity-popout h3');
            if (shopTitle) demoSelectedShopName = String(shopTitle.textContent || '').trim() || demoSelectedShopName;
            // Shop map loads async; then start items coaching.
            setTimeout(function () {
                enterPointItems();
            }, 400);
            return;
        }

        var shopBackBtn = ev.target && ev.target.closest
            ? ev.target.closest('#map-shop-back-btn, .demo-allowed-shop-back')
            : null;
        if (shopBackBtn && phase === 'back_to_city') {
            hideArrow();
            setTimeout(function () {
                enterSelectShopGoods();
            }, 350);
            return;
        }

        var worldBackBtn = ev.target && ev.target.closest
            ? ev.target.closest('#map-world-back-btn, .demo-allowed-world-back')
            : null;
        if (worldBackBtn && phase === 'return_world_map') {
            hideArrow();
            clearUnlockCountdown();
            setTimeout(function () {
                enterSelectCityGoods();
            }, 350);
            return;
        }

        var weekBtn = ev.target && ev.target.closest
            ? ev.target.closest('#gm-run-week-btn, .demo-allowed-sim-week')
            : null;
        if (weekBtn && phase === 'sim_week') {
            hideArrow();
            // Defer phase change so this same click is not blocked by the sim_result lock
            // (which would prevent onclick="runSimulationPeriod('week')").
            setTimeout(function () {
                if (phase === 'sim_week') enterSimResult();
            }, 0);
            return;
        }

        var campaignCodeSummary = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-campaign-code, details.gm-join-tools > summary')
            : null;
        if (campaignCodeSummary && phase === 'invite_open') {
            setTimeout(function () {
                enterInviteReveal();
            }, 80);
            return;
        }

        var inviteReveal = ev.target && ev.target.closest
            ? ev.target.closest('.demo-allowed-invite-reveal, .invite-reveal-btn')
            : null;
        if (inviteReveal && phase === 'invite_reveal') {
            setTimeout(function () {
                if (phase === 'invite_reveal') {
                    storeDemoCampCodeFromInput();
                    enterInviteCopy();
                }
            }, 350);
            return;
        }

        var profileBtn = ev.target && ev.target.closest
            ? ev.target.closest('#accountAvatarBtn, .demo-allowed-profile')
            : null;
        if (profileBtn && phase === 'point_profile') {
            setTimeout(function () {
                enterSwitchCampaigns();
            }, 100);
            return;
        }
    }, true);

    document.addEventListener('copy', function () {
        if (phase !== 'invite_copy') return;
        storeDemoCampCodeFromInput();
        enterPointProfile();
    });

    document.addEventListener('keydown', function (ev) {
        if (phase !== 'invite_copy') return;
        var key = ev.key || '';
        if ((ev.ctrlKey || ev.metaKey) && (key === 'c' || key === 'C')) {
            setTimeout(function () {
                if (phase === 'invite_copy') {
                    storeDemoCampCodeFromInput();
                    enterPointProfile();
                }
            }, 50);
        }
    });

    var campaignDetails = document.getElementById('gm-campaign-code-details') ||
        document.querySelector('#gm-top-hud details.gm-join-tools');
    if (campaignDetails) {
        campaignDetails.addEventListener('toggle', function () {
            if (phase === 'invite_open' && campaignDetails.open) {
                enterInviteReveal();
            }
        });
    }

    // Profile dropdown: block everything except Sign out until Switch campaigns unlocks.
    document.addEventListener('click', function (ev) {
        var t = ev.target;
        if (!t || !t.closest) return;
        if (!t.closest('#accountMenuWrapper') && !t.closest('#accountPopoverPanel')) return;
        if (t.closest('#accountAvatarBtn')) return;
        if (t.closest('#accountPopoverPanel a.menu-btn-danger-outline')) return;
        if (
            (phase === 'switch_campaigns' || document.body.classList.contains('demo-invite-switch-ready')) &&
            t.closest('#accountPopoverPanel a.account-menu-nav-link')
        ) return;
        if (t.closest('#accountPopoverPanel')) {
            ev.preventDefault();
            ev.stopPropagation();
        }
    }, true);

    document.addEventListener('pointerdown', function (ev) {
        if (!awaitingMapDraw || drawingActive) return;
        if (phase !== 'draw_borders' && phase !== 'drawing') return;
        var onMap = ev.target && ev.target.closest
            ? ev.target.closest('#map-stage, #map-viewport-layer, #map-region-boundary-layer')
            : null;
        if (!onMap) return;
        onDrawingStarted();
    }, true);

    var closeBtn = document.getElementById('map-region-boundary-close-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', function () {
            if (!document.body.classList.contains('demo-close-boundary-ready')) return;
            clearCloseTimers();
            hideArrow();
            document.body.classList.remove('demo-close-boundary-ready');
            closeBtn.classList.remove('demo-close-highlight');
            drawingActive = false;
            awaitingMapDraw = false;
            enterOpenNationsRuler();
        });
    }

    window.addEventListener('message', function (ev) {
        if (ev.origin !== window.location.origin) return;
        var data = ev.data || {};
        if (data.type === 'demo-wizard-step' && (isWizardPhase(phase) || phase === 'add_ruler')) {
            enterWizardPhase(data.step || 'identity');
            return;
        }
        if (data.type === 'demo-wizard-complete' && data.ok) {
            var bridgePartial = { active: true };
            if (data.name) bridgePartial.npcName = String(data.name);
            if (data.draft && typeof data.draft === 'object') {
                bridgePartial.characterDraft = data.draft;
            }
            persistDemoBridge(bridgePartial);
            enterPointCities();
            return;
        }
        // Backup: ruler finalize also notifies players-changed; leave Nations for Cities.
        if (
            data.type === 'gm-players-changed' &&
            (isWizardPhase(phase) || phase === 'add_ruler')
        ) {
            enterPointCities();
        }
    });

    document.addEventListener('click', function (ev) {
        var t = ev.target;
        if (!t || !t.closest) return;
        if (t.closest('#demo-tutorial-root') || t.closest('#demo-tutorial-arrow')) return;

        function blockInteractive() {
            var interactive = t.closest(
                'button, a, input, select, textarea, label.button, .gm-nav-rail-btn, .sim-action-btn, .map-world-nav-btn, .map-stage-upload-label'
            );
            if (!interactive || !interactive.closest('.gm-paradox-shell')) return;
            ev.preventDefault();
            ev.stopPropagation();
        }

        if (phase === 'point_nations' || phase === 'open_nations_ruler') {
            if (t.closest('#regions-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'point_cities') {
            if (t.closest('#cities-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#regions-pane-content') || t.closest('#regions-tab-btn')) {
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
            blockInteractive();
            return;
        }

        if (phase === 'point_shops') {
            if (t.closest('#shops-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#regions-pane-content') || t.closest('#cities-pane-content') ||
                t.closest('#regions-tab-btn') || t.closest('#cities-tab-btn')) {
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
            blockInteractive();
            return;
        }

        if (isDrawPhase(phase)) {
            if (t.closest('#map-stage, #map-viewport-layer, #map-region-boundary-layer')) return;
            if (t.closest('#regions-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#map-region-boundary-tools')) {
                if (
                    t.closest('#map-region-boundary-close-btn') &&
                    document.body.classList.contains('demo-close-boundary-ready')
                ) return;
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
            if (t.closest('#regions-pane-content')) {
                if (t.closest('.demo-allowed-draw')) return;
                if (t.closest('button, a, input, select, textarea, label.button')) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                return;
            }
            blockInteractive();
            return;
        }

        if (phase === 'add_ruler') {
            if (t.closest('#regions-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('.demo-allowed-ruler')) return;
            if (t.closest('#regions-pane-content') && t.closest('button, a')) {
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
            blockInteractive();
            return;
        }

        if (isWizardPhase(phase)) {
            if (t.closest('#regions-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('.gm-compendium-embed')) return;
            if (t.closest('#regions-pane-content')) {
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
            blockInteractive();
            return;
        }

        if (phase === 'place_cities') {
            if (t.closest('#cities-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#map-stage, #map-viewport-layer, #map-marker-layer')) return;
            if (t.closest('.demo-allowed-city')) return;
            if (t.closest('#regions-pane-content') || t.closest('#regions-tab-btn')) {
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
            if (t.closest('#cities-pane-content')) {
                if (t.closest('button, a, input, select, textarea, label.button')) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                return;
            }
            blockInteractive();
            return;
        }

        if (phase === 'owners_info' || phase === 'shop_owners_info' || phase === 'catalog_explain' ||
            phase === 'market_explain' || phase === 'calendar_explain' || phase === 'sim_result' ||
            phase === 'species_explain' || phase === 'traits_explain' || phase === 'classes_explain' ||
            phase === 'spells_explain' || phase === 'monsters_explain') {
            if (t.closest('#demo-coach-forward') || t.closest('#demo-tutorial-root')) return;
            if (t.closest('#demo-city-view-popout')) return;
            blockInteractive();
            return;
        }

        if (phase === 'select_city' || phase === 'select_city_goods') {
            if (t.closest('.demo-allowed-city-marker')) return;
            if (t.closest('#demo-city-view-popout') || t.closest('#demo-coach-forward')) return;
            if (t.closest('#map-stage, #map-viewport-layer, #map-marker-layer')) {
                if (t.closest('.map-marker') && !t.closest('.demo-allowed-city-marker')) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                return;
            }
            blockInteractive();
            return;
        }

        if (phase === 'city_popout' || phase === 'shop_popout') {
            if (t.closest('#demo-city-view-popout')) return;
            if (t.closest('.map-entity-popout')) {
                // Open/Move locked until the timer unlocks Open.
                if (t.closest('button')) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                return;
            }
            if (t.closest('.demo-allowed-city-marker') || t.closest('.demo-allowed-shop-marker')) return;
            blockInteractive();
            return;
        }

        if (phase === 'open_city' || phase === 'open_shop') {
            if (t.closest('#demo-city-view-popout')) return;
            if (t.closest('.demo-allowed-open')) return;
            if (t.closest('.map-entity-popout')) {
                if (t.closest('button')) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                return;
            }
            if (t.closest('.demo-allowed-city-marker') || t.closest('.demo-allowed-shop-marker')) return;
            blockInteractive();
            return;
        }

        if (phase === 'place_shops') {
            if (t.closest('#shops-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#map-stage, #map-viewport-layer, #map-marker-layer')) return;
            if (t.closest('.demo-allowed-shop')) return;
            if (t.closest('#shops-pane-content')) {
                if (t.closest('button, a, input, select, textarea, label.button')) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                return;
            }
            blockInteractive();
            return;
        }

        if (phase === 'select_shop' || phase === 'select_shop_goods') {
            if (t.closest('.demo-allowed-shop-marker')) return;
            if (t.closest('#demo-city-view-popout') || t.closest('#demo-coach-forward')) return;
            if (t.closest('#map-stage, #map-viewport-layer, #map-marker-layer')) {
                if (t.closest('.map-marker') && !t.closest('.demo-allowed-shop-marker')) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                return;
            }
            blockInteractive();
            return;
        }

        if (phase === 'point_items') {
            if (t.closest('#items-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'items_briefing') {
            if (t.closest('#demo-city-view-popout')) return;
            if (t.closest('#items-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('.demo-allowed-items-catalog')) return;
            if (t.closest('#items-pane-content')) {
                if (t.closest('button, a, input, select, textarea, label.button')) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                return;
            }
            blockInteractive();
            return;
        }

        if (
            phase === 'catalog_select_item' ||
            phase === 'catalog_stock' ||
            phase === 'catalog_assign_shop' ||
            phase === 'catalog_confirm_stock'
        ) {
            if (t.closest('#demo-city-view-popout')) return;
            if (t.closest('#demo-tutorial-root')) return;
            if (t.closest('#items-pane-content')) return;
            if (t.closest('#items-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'back_to_city') {
            if (t.closest('#map-shop-back-btn') || t.closest('.demo-allowed-shop-back')) return;
            if (t.closest('#demo-tutorial-root')) return;
            if (t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'return_world_map') {
            if (t.closest('#map-world-back-btn') || t.closest('.demo-allowed-world-back')) return;
            if (t.closest('#demo-tutorial-root')) return;
            if (t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'point_market') {
            if (t.closest('#market-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'point_calendar') {
            if (t.closest('#calendar-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'point_species') {
            if (t.closest('#species-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'point_traits') {
            if (t.closest('#traits-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'point_classes') {
            if (t.closest('#classes-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'point_spells') {
            if (t.closest('#spells-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'point_monsters') {
            if (t.closest('#monsters-tab-btn') || t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'sim_week') {
            if (t.closest('#gm-run-week-btn') || t.closest('.demo-allowed-sim-week')) return;
            if (t.closest('#demo-tutorial-root')) return;
            if (t.closest('#gm-section-menu-btn')) return;
            blockInteractive();
            return;
        }

        if (phase === 'sim_result') {
            if (t.closest('#demo-coach-forward') || t.closest('#demo-tutorial-root')) return;
            if (t.closest('#demo-city-view-popout') || t.closest('#map-feedback')) return;
            blockInteractive();
            return;
        }

        if (phase === 'invite_open') {
            if (t.closest('.demo-allowed-campaign-code') || t.closest('details.gm-join-tools > summary')) return;
            if (t.closest('#demo-tutorial-root') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#accountAvatarBtn')) return;
            if (t.closest('#accountPopoverPanel a.menu-btn-danger-outline')) return;
            blockInteractive();
            return;
        }

        if (phase === 'invite_reveal') {
            if (t.closest('.demo-allowed-invite-reveal') || t.closest('.invite-reveal-btn')) return;
            if (t.closest('details.gm-join-tools')) return;
            if (t.closest('#demo-tutorial-root') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#accountAvatarBtn')) return;
            if (t.closest('#accountPopoverPanel a.menu-btn-danger-outline')) return;
            blockInteractive();
            return;
        }

        if (phase === 'invite_copy') {
            if (t.closest('.demo-allowed-invite-copy') || t.closest('.gm-campaign-invite-block .code-display')) return;
            if (t.closest('details.gm-join-tools')) return;
            if (t.closest('#demo-tutorial-root') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#accountAvatarBtn')) return;
            if (t.closest('#accountPopoverPanel a.menu-btn-danger-outline')) return;
            blockInteractive();
            return;
        }

        if (phase === 'point_profile') {
            if (t.closest('#accountAvatarBtn') || t.closest('.demo-allowed-profile')) return;
            if (t.closest('#demo-tutorial-root') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#accountPopoverPanel a.menu-btn-danger-outline')) return;
            blockInteractive();
            return;
        }

        if (phase === 'switch_campaigns') {
            if (t.closest('.demo-allowed-switch-campaigns') || t.closest('#accountPopoverPanel a.account-menu-nav-link')) return;
            if (t.closest('#accountAvatarBtn')) return;
            if (t.closest('#demo-tutorial-root') || t.closest('#gm-section-menu-btn')) return;
            if (t.closest('#accountPopoverPanel a.menu-btn-danger-outline')) return;
            blockInteractive();
        }
    }, true);

    var regionsBody = document.getElementById('regions-compendium-body');
    if (regionsBody && window.MutationObserver) {
        new MutationObserver(function () {
            if (isDrawPhase(phase)) tagAllowedDrawButtons();
            if (phase === 'add_ruler') {
                tagAllowedRulerButtons();
                var btn = findFathersAddRulerButton();
                if (btn) pointArrowAt(btn);
            }
        }).observe(regionsBody, { childList: true, subtree: true });
    }

    var citiesBody = document.getElementById('cities-compendium-body');
    if (citiesBody && window.MutationObserver) {
        new MutationObserver(function () {
            if (phase === 'place_cities') tagAllowedCityButtons();
        }).observe(citiesBody, { childList: true, subtree: true });
    }

    var shopsBody = document.getElementById('shops-compendium-body');
    if (shopsBody && window.MutationObserver) {
        new MutationObserver(function () {
            if (phase === 'place_shops') tagAllowedShopButtons();
        }).observe(shopsBody, { childList: true, subtree: true });
    }

    var markerLayer = document.getElementById('map-marker-layer');
    if (markerLayer && window.MutationObserver) {
        new MutationObserver(function () {
            if (phase === 'select_city') highlightFatherCityMarkers();
            if (phase === 'select_city_goods') highlightFatherCityMarkers();
            if (phase === 'select_shop') highlightTargetShopMarkers();
            if (phase === 'select_shop_goods') highlightTargetShopMarkers();
        }).observe(markerLayer, { childList: true, subtree: true });
    }

    if (root.getAttribute('data-demo-step') === '2' || root.getAttribute('data-register-cta') === '1') {
        setPhase('register');
        updateNavButtons();
    } else {
        setPhase('welcome');
        updateNavButtons();
    }
})();

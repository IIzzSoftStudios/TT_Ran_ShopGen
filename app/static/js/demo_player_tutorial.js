/**
 * Demo walkthrough on the player dashboard (compendium-style; skip Encounter).
 */
(function () {
    'use strict';
    if (!window.EFDemoBridge || !window.EFDemoBridge.isActive()) return;
    var bridge = window.EFDemoBridge.read();
    var resumeComplete = bridge.phase === 'complete';
    if (
        bridge.phase &&
        bridge.phase !== 'player_tour' &&
        bridge.phase !== 'character_create' &&
        !resumeComplete
    ) {
        return;
    }
    if (!resumeComplete) {
        window.EFDemoBridge.write({ phase: 'player_tour', active: true });
    }

    function injectStyles() {
        if (document.getElementById('demo-player-tutorial-style')) return;
        var style = document.createElement('style');
        style.id = 'demo-player-tutorial-style';
        style.textContent =
            '.demo-tutorial-coach{position:fixed;z-index:2147483002;right:16px;bottom:16px;width:min(340px,calc(100vw - 24px));' +
            'padding:0.9rem 1rem;border-radius:10px;background:rgba(22,27,34,.97);color:#f3f5f7;}' +
            '.demo-tutorial-coach h2{margin:0 0 .35rem;color:#9ecbff;}' +
            '.demo-city-view-popout{position:fixed;z-index:2147483001;width:min(320px,calc(100vw - 24px));' +
            'padding:.85rem 1rem;border-radius:10px;background:rgba(22,27,34,.97);color:#f3f5f7;box-shadow:0 8px 28px rgba(0,0,0,.45);}' +
            '.demo-city-view-popout--center{left:50%;top:50%;transform:translate(-50%,-50%);text-align:center;}' +
            '.demo-city-view-popout--center .demo-register-cta{display:inline-block;margin-top:0.85rem;}' +
            '.demo-complete-modal{position:fixed!important;inset:0!important;z-index:2147483010!important;display:flex!important;' +
            'align-items:center!important;justify-content:center!important;padding:1.25rem!important;' +
            'background:rgba(8,10,14,.62)!important;margin:0!important;}' +
            '.demo-complete-dialog{width:min(420px,100%);padding:1.25rem 1.35rem 1.15rem;border-radius:12px;' +
            'border:1px solid rgba(255,255,255,.14);background:#161b22;color:#f3f5f7;' +
            'box-shadow:0 18px 48px rgba(0,0,0,.45);text-align:center;}' +
            '.demo-complete-dialog strong{display:block;margin:0 0 .35rem;font-size:1.25rem;color:#f3f5f7;}' +
            '.demo-complete-dialog p{margin:0 0 1rem;font-size:.95rem;line-height:1.45;color:#c8d0d8;}' +
            '.demo-complete-dialog .demo-register-cta{display:inline-block;}' +
            'body.player-dashboard--demo.demo-tour-complete #demo-tutorial-coach,' +
            'body.demo-tour-complete #demo-tutorial-coach{display:none!important;visibility:hidden!important;}' +
            'body.demo-tour-complete #demo-tutorial-arrow{display:none!important;}' +
            '.demo-draw-highlight{outline:2px solid #9ecbff!important;outline-offset:2px;}' +
            'body.player-dashboard--demo #player-encounter-tab{opacity:.35!important;pointer-events:none!important;}';
        document.head.appendChild(style);
    }

    function ensureCoach() {
        if (document.getElementById('demo-tutorial-root')) return;
        var root = document.createElement('div');
        root.id = 'demo-tutorial-root';
        root.innerHTML =
            '<aside id="demo-tutorial-coach" class="demo-tutorial-coach" role="status">' +
            '<div class="demo-coach-nav">' +
            '<button type="button" class="button" id="demo-coach-forward" hidden disabled>Forward</button>' +
            '</div>' +
            '<h2 id="demo-coach-heading">Demo</h2>' +
            '<p id="demo-coach-body"></p></aside>';
        document.body.appendChild(root);
    }
    injectStyles();
    ensureCoach();

    var root = document.getElementById('demo-tutorial-root');
    if (!root) return;
    document.body.classList.add('player-dashboard--demo');
    document.body.setAttribute('data-demo-phase', 'point_sheet');

    var coachHeading = document.getElementById('demo-coach-heading');
    var coachBody = document.getElementById('demo-coach-body');
    var forwardBtn = document.getElementById('demo-coach-forward');

    var STEPS = [
        {
            key: 'point_sheet',
            tab: 'player-character-tab',
            h: 'Step 13 — Character sheet',
            t: 'Click Sheet to open your character panel.',
            explain: {
                h: 'Step 13.1 — Sheet',
                t: 'This is your live character sheet — abilities, HP, and identity for play.',
                html:
                    '<strong>Character sheet</strong><p>Manage your PC stats and identity here. Click Forward to continue.</p>'
            }
        },
        {
            key: 'point_spells',
            tab: 'player-spells-tab',
            h: 'Step 14 — Spells',
            t: 'Click Spells in the left rail.',
            explain: {
                h: 'Step 14.1 — Spells',
                t: 'Prepared and known spells live here when your class grants them.',
                html:
                    '<strong>Spells</strong><p>Browse and prepare campaign spells available to your character. Click Forward to continue.</p>'
            }
        },
        {
            key: 'point_inventory',
            tab: 'player-inventory-tab',
            h: 'Step 15 — Inventory',
            t: 'Click Inventory in the left rail.',
            explain: {
                h: 'Step 15.1 — Inventory',
                t: 'Gear and currency you carry show up in Inventory.',
                html:
                    '<strong>Inventory</strong><p>Track coins and items you own. Click Forward to continue.</p>'
            }
        },
        {
            key: 'point_npcs',
            tab: 'player-npcs-tab',
            h: 'Step 16 — NPCs',
            t: 'Click NPCs to see known contacts.',
            explain: {
                h: 'Step 16.1 — NPCs',
                t: 'NPCs the GM has revealed appear in this journal.',
                html:
                    '<strong>Known NPCs</strong><p>Characters you have met in the campaign. Click Forward to continue.</p>'
            }
        },
        {
            key: 'point_monsters',
            tab: 'player-monsters-tab',
            h: 'Step 17 — Monsters',
            t: 'Click Monsters for your bestiary.',
            explain: {
                h: 'Step 17.1 — Monsters',
                t: 'Monster notes unlock as you encounter foes.',
                html:
                    '<strong>Monster bestiary</strong><p>Remembered creatures and notes from play. Click Forward to continue.</p>'
            }
        },
        {
            key: 'point_market',
            tab: 'player-market-tab',
            h: 'Step 18 — Market',
            t: 'Click Market to see city shops and prices.',
            explain: null,
            marketExpand: true
        }
    ];

    var stepIndex = 0;
    var mode = 'point'; /* point | explain | market_city | market_shop | done */

    var arrowRoot = document.createElement('div');
    arrowRoot.id = 'demo-tutorial-arrow';
    arrowRoot.setAttribute('aria-hidden', 'true');
    arrowRoot.innerHTML = '<div class="demo-arrow-shaft"></div><div class="demo-arrow-head"></div>';
    document.body.appendChild(arrowRoot);
    var arrowShaft = arrowRoot.querySelector('.demo-arrow-shaft');
    var arrowHead = arrowRoot.querySelector('.demo-arrow-head');
    var arrowTarget = null;
    var mouse = { x: window.innerWidth * 0.5, y: window.innerHeight * 0.5 };
    document.addEventListener('mousemove', function (ev) {
        mouse.x = ev.clientX;
        mouse.y = ev.clientY;
    });

    function pointArrowAt(el) {
        arrowTarget = el || null;
        if (!arrowTarget) {
            arrowRoot.hidden = true;
            return;
        }
        arrowRoot.hidden = false;
        (function tick() {
            if (!arrowTarget) return;
            var rect = arrowTarget.getBoundingClientRect();
            if (rect.width < 2 && rect.height < 2) {
                arrowRoot.hidden = true;
                requestAnimationFrame(tick);
                return;
            }
            arrowRoot.hidden = false;
            var tx = rect.left + rect.width / 2;
            var ty = rect.top + Math.min(rect.height / 2, 28);
            var dx = tx - mouse.x;
            var dy = ty - mouse.y;
            var len = Math.sqrt(dx * dx + dy * dy) || 1;
            var x1 = mouse.x + (dx / len) * Math.min(28, len * 0.15);
            var y1 = mouse.y + (dy / len) * Math.min(28, len * 0.15);
            var x2 = tx - (dx / len) * Math.min(10, len * 0.08);
            var y2 = ty - (dy / len) * Math.min(10, len * 0.08);
            var shaftLen = Math.sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1));
            if (shaftLen < 12) {
                arrowRoot.hidden = true;
            } else {
                var angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
                arrowShaft.style.width = shaftLen + 'px';
                arrowShaft.style.left = x1 + 'px';
                arrowShaft.style.top = y1 + 'px';
                arrowShaft.style.transform = 'rotate(' + angle + 'deg)';
                arrowHead.style.left = x2 + 'px';
                arrowHead.style.top = y2 + 'px';
                arrowHead.style.transform = 'translate(-50%, -50%) rotate(' + angle + 'deg)';
            }
            requestAnimationFrame(tick);
        })();
    }

    function hidePopout() {
        var el = document.getElementById('demo-city-view-popout');
        if (el) el.remove();
    }

    function positionPlayerPopout(el) {
        var left = Math.max(12, window.innerWidth - 340 - 24);
        var top = 96;
        var panel = document.querySelector('.player-tab-panel:not([hidden])');
        if (panel) {
            var r = panel.getBoundingClientRect();
            left = Math.min(window.innerWidth - 340, Math.max(12, r.right + 12));
            top = Math.max(12, Math.min(window.innerHeight - 220, r.top));
            if (left + 320 > window.innerWidth - 8 && r.left > 340) {
                left = Math.max(12, r.left - 332);
            }
        }
        el.style.left = left + 'px';
        el.style.top = top + 'px';
    }

    function showPopout(html, centered) {
        hidePopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout' + (centered ? ' demo-city-view-popout--center' : '');
        el.innerHTML = html;
        document.body.appendChild(el);
        if (!centered) positionPlayerPopout(el);
    }

    function clearTabHighlights() {
        document.querySelectorAll('.player-panel-tab.demo-draw-highlight').forEach(function (el) {
            el.classList.remove('demo-draw-highlight', 'demo-allowed-player-tab');
        });
        document.querySelectorAll('.demo-allowed-market-expand').forEach(function (el) {
            el.classList.remove('demo-allowed-market-expand', 'demo-draw-highlight');
        });
    }

    function setCoach(h, t) {
        if (coachHeading) coachHeading.textContent = h;
        if (coachBody) coachBody.textContent = t;
    }

    function setForward(on) {
        if (!forwardBtn) return;
        forwardBtn.hidden = !on;
        forwardBtn.disabled = !on;
        if (on) forwardBtn.classList.add('demo-allowed-forward', 'demo-draw-highlight');
        else forwardBtn.classList.remove('demo-allowed-forward', 'demo-draw-highlight');
    }

    function applyPoint() {
        mode = 'point';
        clearTabHighlights();
        hidePopout();
        setForward(false);
        var step = STEPS[stepIndex];
        if (!step) return finishTour();
        document.body.setAttribute('data-demo-phase', step.key);
        setCoach(step.h, step.t);
        var tab = document.getElementById(step.tab);
        if (tab) {
            tab.classList.add('demo-draw-highlight', 'demo-allowed-player-tab');
            pointArrowAt(tab);
        }
    }

    function applyExplain() {
        mode = 'explain';
        var step = STEPS[stepIndex];
        if (!step || !step.explain) {
            advance();
            return;
        }
        clearTabHighlights();
        setCoach(step.explain.h, step.explain.t);
        showPopout(step.explain.html);
        setForward(true);
        pointArrowAt(forwardBtn);
    }

    var REGION_HINT = "father's castel";
    var DEMO_CITY_HINTS = [
        "castellan's corso-parma",
        "corso-parma",
        "regent's isola-napoli",
        "isola-napoli"
    ];

    function normalizeText(s) {
        return String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();
    }

    function regionMatchesHint(text) {
        var t = normalizeText(text);
        return t.indexOf(REGION_HINT) !== -1 ||
            t.indexOf('castel-bari') !== -1 ||
            t.indexOf('castelbari') !== -1;
    }

    function cityNameMatchesDemo(nameText) {
        var t = normalizeText(nameText);
        if (!t) return false;
        for (var i = 0; i < DEMO_CITY_HINTS.length; i++) {
            if (t.indexOf(DEMO_CITY_HINTS[i]) !== -1) return true;
        }
        return false;
    }

    function selectFatherRegionFilter() {
        var sel = document.getElementById('player-shops-region-filter');
        if (!sel) return;
        var options = sel.options;
        for (var i = 0; i < options.length; i++) {
            var opt = options[i];
            if (!opt.value) continue;
            if (regionMatchesHint(opt.textContent) || regionMatchesHint(opt.value)) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                if (typeof window.applyPlayerCityRegionFilter === 'function') {
                    window.applyPlayerCityRegionFilter();
                } else {
                    try { applyPlayerCityRegionFilter(); } catch (err) { /* ignore */ }
                }
                return;
            }
        }
    }

    function cityBlockName(block) {
        if (!block) return '';
        var nameEl = block.querySelector('.city-name');
        return nameEl ? nameEl.textContent : '';
    }

    function isDemoPlacedCity(block) {
        return cityNameMatchesDemo(cityBlockName(block));
    }

    var GOVERNOR_FOUNDRY_HINTS = ["governor's foundry", "governors foundry", "governer's foundry", "governor foundry"];

    function shopTextMatchesGovernorFoundry(text) {
        var t = normalizeText(text);
        for (var i = 0; i < GOVERNOR_FOUNDRY_HINTS.length; i++) {
            if (t.indexOf(GOVERNOR_FOUNDRY_HINTS[i]) !== -1) return true;
        }
        return t.indexOf('governor') !== -1 && t.indexOf('foundry') !== -1;
    }

    function cityHasGovernorFoundry(block) {
        if (!block) return false;
        var shops = block.querySelectorAll('.shop-name, details.shop-block > summary');
        for (var i = 0; i < shops.length; i++) {
            if (shopTextMatchesGovernorFoundry(shops[i].textContent)) return true;
        }
        return false;
    }

    function findDemoCityBlocks() {
        selectFatherRegionFilter();
        var blocks = document.querySelectorAll('#player-shops-browse details.city-block');
        var matches = [];
        blocks.forEach(function (block) {
            if (block.style.display === 'none') return;
            if (isDemoPlacedCity(block)) matches.push(block);
        });
        if (!matches.length) {
            blocks.forEach(function (block) {
                if (isDemoPlacedCity(block)) matches.push(block);
            });
        }
        return matches;
    }

    function findDemoCityBlock() {
        var matches = findDemoCityBlocks();
        if (!matches.length) return null;
        for (var i = 0; i < matches.length; i++) {
            if (cityHasGovernorFoundry(matches[i])) return matches[i];
        }
        return matches[0];
    }

    function findGovernorFoundrySummary(cityBlock) {
        var scope = cityBlock || document.getElementById('player-shops-browse');
        if (!scope) return null;
        var shops = scope.querySelectorAll('details.shop-block');
        for (var i = 0; i < shops.length; i++) {
            var summary = shops[i].querySelector(':scope > summary') || shops[i].querySelector('summary');
            if (summary && shopTextMatchesGovernorFoundry(summary.textContent)) return summary;
        }
        return null;
    }

    function isGovernorFoundryShop(detailsEl) {
        if (!detailsEl) return false;
        var summary = detailsEl.querySelector(':scope > summary') || detailsEl.querySelector('summary');
        return !!(summary && shopTextMatchesGovernorFoundry(summary.textContent));
    }

    function applyMarketExpandCity() {
        mode = 'market_city';
        clearTabHighlights();
        hidePopout();
        setForward(false);
        setCoach(
            'Step 18.1 — Expand a demo city',
            'Open the city that holds Governor\'s Foundry (Castellan\'s Corso-parma or Regent\'s Isola-napoli).'
        );
        showPopout(
            '<strong>Market browse</strong><p>Expand the demo city that contains <strong>Governor\'s Foundry</strong> — that is where you stocked items as GM.</p>'
        );
        selectFatherRegionFilter();
        var preferred = findDemoCityBlock();
        var arrowTarget = null;
        findDemoCityBlocks().forEach(function (block) {
            if (!cityHasGovernorFoundry(block)) return;
            var summary = block.querySelector(':scope > summary') || block.querySelector('summary');
            if (!summary) return;
            summary.classList.add('demo-allowed-market-expand', 'demo-draw-highlight');
            if (!arrowTarget || block === preferred) arrowTarget = summary;
        });
        if (!arrowTarget && preferred) {
            var fallback = preferred.querySelector(':scope > summary') || preferred.querySelector('summary');
            if (fallback) {
                fallback.classList.add('demo-allowed-market-expand', 'demo-draw-highlight');
                arrowTarget = fallback;
            }
        }
        if (arrowTarget) {
            try {
                arrowTarget.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (err) { /* ignore */ }
            pointArrowAt(arrowTarget);
        }
    }

    function applyMarketExpandShop() {
        mode = 'market_shop';
        clearTabHighlights();
        setForward(false);
        setCoach(
            'Step 18.2 — Expand Governor\'s Foundry',
            'Open Governor\'s Foundry to browse the items you stocked in the demo.'
        );
        showPopout(
            '<strong>Governor\'s Foundry</strong><p>This is the shop you stocked during the GM catalog step. Expand it to see prices and stock.</p>'
        );
        var openCity = document.querySelector('#player-shops-browse details.city-block[open]');
        if (!openCity || !isDemoPlacedCity(openCity) || !cityHasGovernorFoundry(openCity)) {
            openCity = findDemoCityBlock();
            if (openCity) {
                try { openCity.open = true; } catch (err) { /* ignore */ }
            }
        }
        var shop = findGovernorFoundrySummary(openCity) || findGovernorFoundrySummary(null);
        if (shop) {
            shop.classList.add('demo-allowed-market-expand', 'demo-draw-highlight');
            try {
                shop.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (err2) { /* ignore */ }
            pointArrowAt(shop);
        }
    }

    function showCompletionPopout() {
        hidePopout();
        injectStyles();
        var existing = document.getElementById('demo-complete-modal');
        if (existing) existing.remove();
        var modal = document.createElement('div');
        modal.id = 'demo-complete-modal';
        modal.className = 'demo-complete-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.style.cssText =
            'position:fixed;inset:0;z-index:2147483010;display:flex;align-items:center;' +
            'justify-content:center;padding:1.25rem;background:rgba(8,10,14,0.62);margin:0;';
        modal.innerHTML =
            '<div class="demo-complete-dialog" style="width:min(420px,100%);padding:1.25rem 1.35rem 1.15rem;' +
            'border-radius:12px;border:1px solid rgba(255,255,255,0.14);background:#161b22;color:#f3f5f7;' +
            'box-shadow:0 18px 48px rgba(0,0,0,0.45);text-align:center;">' +
            '<strong style="display:block;margin:0 0 0.35rem;font-size:1.25rem;">Demo complete</strong>' +
            '<p style="margin:0 0 1rem;font-size:0.95rem;line-height:1.45;color:#c8d0d8;">' +
            'You have toured GM and player surfaces. Register For Access to run your own campaigns.</p>' +
            '<a class="button demo-register-cta demo-draw-highlight" href="/access-request"' +
            ' style="display:inline-block;">Register For Access</a>' +
            '</div>';
        document.body.appendChild(modal);
    }

    function hideArrow() {
        arrowTarget = null;
        if (arrowRoot) arrowRoot.hidden = true;
    }

    function applyMarketDone() {
        mode = 'done';
        clearTabHighlights();
        hidePopout();
        hideArrow();
        document.body.classList.add('demo-tour-complete', 'player-dashboard--demo');
        var coach = document.getElementById('demo-tutorial-coach');
        if (coach) {
            coach.hidden = true;
            coach.style.display = 'none';
        }
        setForward(false);
        var backBtn = document.getElementById('demo-coach-back');
        if (backBtn) {
            backBtn.hidden = true;
            backBtn.disabled = true;
        }
        showCompletionPopout();
        window.EFDemoBridge.write({ phase: 'complete', active: true });
    }

    function finishTour() {
        applyMarketDone();
    }

    function advance() {
        stepIndex += 1;
        if (stepIndex >= STEPS.length) {
            finishTour();
            return;
        }
        applyPoint();
    }

    function onTabOpened(step) {
        if (step.marketExpand) {
            applyMarketExpandCity();
            return;
        }
        if (step.explain) applyExplain();
        else advance();
    }

    STEPS.forEach(function (step) {
        var tab = document.getElementById(step.tab);
        if (!tab) return;
        tab.addEventListener('click', function () {
            if (mode !== 'point') return;
            if (STEPS[stepIndex] !== step) return;
            setTimeout(function () {
                onTabOpened(step);
            }, 80);
        });
    });

    document.addEventListener('toggle', function (ev) {
        var details = ev.target;
        if (!details || details.tagName !== 'DETAILS') return;
        if (mode === 'market_city' && details.classList.contains('city-block') && details.open) {
            if (!isDemoPlacedCity(details) || !cityHasGovernorFoundry(details)) {
                details.open = false;
                return;
            }
            setTimeout(applyMarketExpandShop, 60);
            return;
        }
        if (mode === 'market_shop' && details.classList.contains('shop-block') && details.open) {
            var cityRoot = details.closest('details.city-block');
            if (!cityRoot || !isDemoPlacedCity(cityRoot) || !isGovernorFoundryShop(details)) {
                details.open = false;
                return;
            }
            setTimeout(function () {
                mode = 'explain';
                setCoach('Step 18.3 — Shop goods', 'Item rows show name, stock, and price. Click Forward when finished.');
                showPopout(
                    '<strong>Shop inventory</strong>' +
                    '<p>These prices reflect the living market after your one-week simulation.</p>' +
                    '<p>Click Forward to finish the tour.</p>'
                );
                setForward(true);
                pointArrowAt(forwardBtn);
            }, 60);
        }
    }, true);

    if (forwardBtn) {
        forwardBtn.addEventListener('click', function () {
            if (mode === 'done') {
                applyMarketDone();
                return;
            }
            if (mode === 'explain') {
                hidePopout();
                if (STEPS[stepIndex] && STEPS[stepIndex].marketExpand) {
                    applyMarketDone();
                    return;
                }
                advance();
                return;
            }
            if (mode === 'market_shop' || mode === 'market_city') {
                /* Allow finishing from Forward if the shop step already unlocked it. */
                if (!forwardBtn.disabled && !forwardBtn.hidden) {
                    applyMarketDone();
                }
            }
        });
    }

    /* Lock rail except allowed tab / market expand / coach / sign out. */
    document.addEventListener('click', function (ev) {
        var t = ev.target;
        if (!t || !t.closest) return;
        if (t.closest('#demo-tutorial-root') || t.closest('#demo-city-view-popout')) return;
        if (t.closest('#demo-complete-modal')) return;
        if (t.closest('#accountAvatarBtn')) return;
        if (t.closest('#accountPopoverPanel a.menu-btn-danger-outline')) return;
        if (mode === 'point' && t.closest('.demo-allowed-player-tab')) return;
        if ((mode === 'market_city' || mode === 'market_shop') && t.closest('.demo-allowed-market-expand')) return;
        if (mode === 'done') return;
        if (t.closest('#player-encounter-tab')) {
            ev.preventDefault();
            ev.stopPropagation();
            return;
        }
        var interactive = t.closest('button, a, input, select, textarea, summary, .gm-nav-rail-btn');
        if (!interactive) return;
        if (mode === 'explain' && t.closest('#demo-coach-forward')) return;
        if (mode === 'point' || mode === 'explain' || mode === 'market_city' || mode === 'market_shop') {
            if (t.closest('.demo-allowed-player-tab') || t.closest('.demo-allowed-market-expand')) return;
            if (t.closest('#demo-coach-forward')) return;
            ev.preventDefault();
            ev.stopPropagation();
        }
    }, true);

    if (resumeComplete) {
        applyMarketDone();
    } else {
        applyPoint();
    }
})();

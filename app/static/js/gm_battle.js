/* D&D 5e tactical battle board (GM Battle tab + player encounter panel).
 *
 * Reads window.BATTLE_CONFIG:
 *   { role: 'gm'|'player', ownPlayerIds: [], players: [{id,name}],
 *     apiBase: '/api/combat', csrfToken: '...', initialEncounterId: null }
 *
 * All mutations send turn_version; a 409 means another client acted first,
 * so we refetch and surface a gentle notice. Elements are looked up by id
 * and skipped when absent, so the GM and player templates can include
 * different subsets of the UI.
 */
(function () {
    'use strict';

    var cfg = window.BATTLE_CONFIG || {};
    var API = cfg.apiBase || '/api/combat';
    var IS_GM = cfg.role === 'gm';
    var OWN_PLAYER_IDS = cfg.ownPlayerIds || [];
    var SPELL_AUTOMATION_MANUAL = 'manual';
    var SPELL_AUTOMATION_DIRECT_NUMERIC = 'direct_numeric';

    function normalizeSpellAutomation(value) {
        var raw = String(value || SPELL_AUTOMATION_MANUAL).toLowerCase();
        if (raw === 'auto' || raw === SPELL_AUTOMATION_DIRECT_NUMERIC) {
            return SPELL_AUTOMATION_DIRECT_NUMERIC;
        }
        return SPELL_AUTOMATION_MANUAL;
    }

    function isDirectNumericSpell(spell) {
        return normalizeSpellAutomation(spell && spell.automation) === SPELL_AUTOMATION_DIRECT_NUMERIC;
    }

    function castableSpells(spells) {
        return (spells || []).filter(isDirectNumericSpell);
    }

    function spellCastButtonLabel(spell) {
        return 'Cast';
    }

    function spellAutomationHint(spell) {
        if (spell.area && spell.area.shape && spell.attack_type === 'save' && spell.damage) {
            return 'Auto-resolves area save and damage on all targets in range.';
        }
        if (spell.attack_type === 'spell_attack' && spell.damage) {
            return 'Auto-resolves spell attack and damage.';
        }
        if (spell.save_ability && spell.damage) {
            return 'Auto-resolves save and damage.';
        }
        if (spell.healing) {
            return 'Auto-resolves healing.';
        }
        return 'Auto-resolves on the target.';
    }

    function spellManualMetadataLines(spell) {
        var lines = [];
        if (!spell) return lines;
        if (spell.area) {
            lines.push('Area: ' + esc(String(spell.area.shape || 'area')) +
                ' ' + esc(String(spell.area.size_ft || '?')) + ' ft');
        }
        if (spell.ritual) lines.push('Ritual');
        if (spell.concentration) lines.push('Concentration');
        if (spell.conditions && spell.conditions.length) {
            lines.push('Also applies: ' + spell.conditions.map(esc).join(', '));
        }
        return lines;
    }

    function canEndConcentration(c) {
        if (!c || !c.concentration) return false;
        if (IS_GM) return true;
        return !!(state.settings && state.settings.player_concentration_end) &&
            isOwnPlayerCombatant(c);
    }

    var state = {
        loadedOnce: false,
        monstersLoadedOnce: false,
        encounterId: cfg.initialEncounterId || null,
        encounters: [],
        data: null,          // last GET /encounters/<id> payload
        monsters: [],
        settings: null,
        mode: 'idle',        // idle | move | attack | cast_spell
        actorId: null,       // combatant acting via radial menu
        placement: null,     // { type, playerId|monsterId, count, label }
        pendingDeleteEncounter: null,
        pollTimer: null,
        busy: false,
        controlsBound: false,
        monsterSourceFilter: 'all',
        mapData: null,
        mapVersionLoaded: null,
        mapChunks: {},
        suppressStageClick: false,
        renderPending: false,
        setupMode: 'create'
    };

    function $(id) { return document.getElementById(id); }

    function esc(text) {
        var d = document.createElement('div');
        d.textContent = text == null ? '' : String(text);
        return d.innerHTML;
    }

    function feedback(msg, isError) {
        var el = $('battle-feedback');
        if (!el) return;
        el.textContent = msg || '';
        el.classList.toggle('battle-feedback-error', !!isError);
        if (msg) {
            clearTimeout(feedback._t);
            feedback._t = setTimeout(function () { el.textContent = ''; }, 6000);
        }
    }

    async function api(path, method, body) {
        var opts = {
            method: method || 'GET',
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' }
        };
        if (body !== undefined) {
            opts.headers['Content-Type'] = 'application/json';
            if (cfg.csrfToken) opts.headers['X-CSRFToken'] = cfg.csrfToken;
            opts.body = JSON.stringify(body);
        } else if ((method || 'GET') !== 'GET' && cfg.csrfToken) {
            opts.headers['X-CSRFToken'] = cfg.csrfToken;
            opts.headers['Content-Type'] = 'application/json';
            opts.body = '{}';
        }
        var resp = await fetch(API + path, opts);
        var data = null;
        try { data = await resp.json(); } catch (e) { /* non-JSON error */ }
        if (!resp.ok) {
            var err = new Error((data && data.error) || ('Request failed (' + resp.status + ')'));
            err.status = resp.status;
            throw err;
        }
        return data;
    }

    /* Wrap a mutation: handles 409 stale-turn by refetching. */
    async function mutate(path, body) {
        if (state.busy) return null;
        state.busy = true;
        try {
            body = body || {};
            if (state.data) body.turn_version = state.data.turn_version;
            var out = await api(path, 'POST', body);
            await loadEncounter(state.encounterId);
            resetBattleUiAfterMutation();
            return out;
        } catch (err) {
            if (err.status === 409) {
                feedback('Battle state changed elsewhere - refreshed.', true);
                await loadEncounter(state.encounterId);
                resetBattleUiAfterMutation();
            } else {
                feedback(err.message, true);
            }
            return null;
        } finally {
            state.busy = false;
        }
    }

    /* ------------------------------------------------------------------
     * Loading
     * ------------------------------------------------------------------ */
    async function loadEncounters() {
        if (!IS_GM) return;
        try {
            var data = await api('/encounters');
            var encounters = data.encounters || [];
            state.encounters = encounters;
            if (!state.encounterId && encounters.length) {
                state.encounterId = encounters[0].id;
            }
            renderEncounterMenu();
        } catch (err) {
            feedback(err.message, true);
        }
    }

    async function loadEncounter(id) {
        if (!id) { state.data = null; renderAll(); return; }
        try {
            var prevMapVer = currentMapVersion();
            var prevId = state.encounterId;
            state.data = await api('/encounters/' + id);
            state.encounterId = id;
            if (prevId !== id) {
                state.mapChunks = {};
            }
            if (!state.data.map || Number(state.data.map.map_version) !== Number(prevMapVer)) {
                state.mapVersionLoaded = null;
                state.mapChunks = {};
            }
            renderAll();
            if (prevId !== id && battleViewport) {
                battleViewport.fitToView();
            }
        } catch (err) {
            feedback(err.message, true);
        }
    }

    async function loadMonsters() {
        if (!IS_GM || (!$('battle-monsters-body') && !$('battle-monster-select'))) return;
        try {
            var data = await api('/monsters');
            state.monsters = data.monsters || [];
            renderMonsters();
            renderMonsterPicker();
        } catch (err) {
            feedback(err.message, true);
        }
    }

    async function loadSettings() {
        if (!IS_GM || !$('battle-settings-popout')) return;
        try {
            var data = await api('/settings');
            state.settings = data.settings || {};
            renderSettings();
        } catch (err) {
            feedback(err.message, true);
        }
    }

    /* ------------------------------------------------------------------
     * Permissions
     * ------------------------------------------------------------------ */
    function combatantById(id) {
        if (!state.data) return null;
        return (state.data.combatants || []).find(function (c) { return c.id === id; }) || null;
    }

    function isCurrentTurn(c) {
        return state.data && state.data.current_combatant_id === c.id;
    }

    function canAct(c) {
        if (!state.data || state.data.status !== 'active') return false;
        if (!isCurrentTurn(c)) return false;
        if (IS_GM) return true;
        return OWN_PLAYER_IDS.indexOf(c.player_id) !== -1;
    }

    function isOwnPlayerCombatant(c) {
        return !IS_GM && OWN_PLAYER_IDS.indexOf(c.player_id) !== -1;
    }

    function ownPlayerCombatant() {
        if (!state.data) return null;
        return (state.data.combatants || []).find(function (c) {
            return c.status !== 'removed' && isOwnPlayerCombatant(c);
        }) || null;
    }

    /* ------------------------------------------------------------------
     * Rendering
     * ------------------------------------------------------------------ */
    function ensureCurrentCombatantInView() {
        if (!state.data || !state.data.current_combatant_id) return;
        var c = combatantById(state.data.current_combatant_id);
        if (!c) return;
        var bounds = visibleCellBounds();
        if (c.x < bounds.x0 || c.x >= bounds.x1 || c.y < bounds.y0 || c.y >= bounds.y1) {
            focusCameraOnCell(c.x, c.y);
        }
    }

    function renderAll() {
        syncBattleViewportWorldSize();
        ensureCurrentCombatantInView();
        renderGrid();
        renderTracker();
        renderLog();
        renderToolbar();
        renderMonsterPicker();
        loadEncounterMap(false);
    }

    function refreshMapEncounters() {
        if (window.gmMap && typeof window.gmMap.refreshEncounters === 'function') {
            window.gmMap.refreshEncounters();
        }
    }

    function getFixedPanelRoot(panel) {
        var node = panel ? panel.parentElement : null;
        while (node && node !== document.documentElement) {
            var style = window.getComputedStyle(node);
            var transform = style.transform || style.webkitTransform;
            if (transform && transform !== 'none') return node;
            if (style.filter && style.filter !== 'none') return node;
            if (style.perspective && style.perspective !== 'none') return node;
            node = node.parentElement;
        }
        return null;
    }

    function viewportToPanelLocal(panel, viewportLeft, viewportTop) {
        var root = getFixedPanelRoot(panel);
        if (!root) return { left: viewportLeft, top: viewportTop };
        var rootRect = root.getBoundingClientRect();
        return {
            left: viewportLeft - rootRect.left,
            top: viewportTop - rootRect.top
        };
    }

    function positionBattleRenamePopout(popout, anchor) {
        if (!popout) return;
        var margin = 12;
        var root = getFixedPanelRoot(popout);
        var boundsRect = root ? root.getBoundingClientRect() : {
            left: margin,
            top: margin,
            right: (window.innerWidth || document.documentElement.clientWidth || 0) - margin,
            bottom: (window.innerHeight || document.documentElement.clientHeight || 0) - margin,
            width: (window.innerWidth || document.documentElement.clientWidth || 0) - 2 * margin,
            height: (window.innerHeight || document.documentElement.clientHeight || 0) - 2 * margin
        };
        var popRect = popout.getBoundingClientRect();
        var width = popRect.width || 320;
        var height = popRect.height || 280;
        var anchorRect = anchor && anchor.getBoundingClientRect
            ? anchor.getBoundingClientRect()
            : null;
        var viewportLeft;
        var viewportTop;

        if (anchorRect) {
            viewportLeft = anchorRect.left + (anchorRect.width / 2) - (width / 2);
            viewportTop = anchorRect.bottom + margin;
            if (viewportTop + height > boundsRect.bottom - margin) {
                viewportTop = anchorRect.top - height - margin;
            }
        }
        if (!anchorRect || viewportTop < boundsRect.top + margin ||
            viewportTop + height > boundsRect.bottom - margin) {
            viewportLeft = boundsRect.left + (boundsRect.width - width) / 2;
            viewportTop = boundsRect.top + (boundsRect.height - height) / 2;
        }
        viewportLeft = Math.min(
            Math.max(boundsRect.left + margin, viewportLeft),
            boundsRect.right - width - margin
        );
        viewportTop = Math.min(
            Math.max(boundsRect.top + margin, viewportTop),
            boundsRect.bottom - height - margin
        );

        var local = viewportToPanelLocal(popout, viewportLeft, viewportTop);
        popout.style.left = local.left + 'px';
        popout.style.top = local.top + 'px';
        popout.style.transform = 'none';
    }

    function renderToolbar() {
        var title = $('battle-encounter-title');
        if (title) {
            title.textContent = state.data ? state.data.name : 'Encounters';
        }
        var renameBtn = $('battle-rename-btn');
        if (renameBtn) renameBtn.disabled = !state.encounterId;
        var placeBtn = $('battle-place-map-btn');
        if (placeBtn) placeBtn.disabled = !state.encounterId || !state.data;
        var label = $('battle-round-label');
        if (label) {
            if (state.data) {
                label.textContent = state.data.status === 'active'
                    ? ('Round ' + state.data.round_number)
                    : (state.data.status === 'setup' ? 'Setup' : 'Ended');
            } else {
                label.textContent = '';
            }
        }
        var endTurnBtn = $('battle-end-turn-btn');
        if (endTurnBtn) {
            var current = state.data ? combatantById(state.data.current_combatant_id) : null;
            endTurnBtn.disabled = !state.data || state.data.status !== 'active' ||
                (!IS_GM && (!current || OWN_PLAYER_IDS.indexOf(current.player_id) === -1));
        }
        var placeOwnBtn = $('battle-place-own-character-btn');
        if (placeOwnBtn) {
            var ownPlaced = !!ownPlayerCombatant();
            placeOwnBtn.disabled = !state.data || !OWN_PLAYER_IDS.length || ownPlaced || !!state.placement;
            placeOwnBtn.textContent = ownPlaced ? 'Character placed' : 'Place character';
        }
        var initBtn = $('battle-initiative-btn');
        if (initBtn) initBtn.disabled = !state.data || state.data.status === 'ended';
        var endEncBtn = $('battle-end-encounter-btn');
        if (endEncBtn) endEncBtn.disabled = !state.data || state.data.status === 'ended';
        var setupEditBtn = $('battle-setup-edit-btn');
        if (setupEditBtn) setupEditBtn.disabled = !state.data || !isSetupEditable();
        renderEncounterMenu();
    }

    function renderEncounterMenu() {
        var list = $('battle-encounter-list');
        if (!list) return;
        list.innerHTML = '';
        if (!state.encounters.length) {
            list.innerHTML = '<div class="battle-encounter-list-empty">No encounters yet. Create one to begin.</div>';
            return;
        }
        state.encounters.forEach(function (enc) {
            var row = document.createElement('div');
            row.className = 'battle-encounter-list-row';

            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'battle-encounter-list-btn' +
                (Number(enc.id) === Number(state.encounterId) ? ' active' : '');
            btn.innerHTML = '<span>' + esc(enc.name) + '</span>';
            btn.addEventListener('click', function () {
                state.encounterId = enc.id;
                loadEncounter(enc.id);
                var menu = $('battle-encounter-menu');
                if (menu) menu.open = false;
            });

            var removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'button battle-encounter-remove-btn';
            removeBtn.textContent = 'Remove';
            removeBtn.setAttribute('aria-label', 'Remove encounter ' + (enc.name || enc.id));
            removeBtn.title = 'Permanently delete this ' + enc.status + ' encounter';
            removeBtn.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                showDeleteEncounterPopout(enc, removeBtn);
            });

            row.appendChild(btn);
            row.appendChild(removeBtn);
            list.appendChild(row);
        });
    }

    function showDeleteEncounterPopout(encounter, anchor) {
        var popout = $('battle-delete-popout');
        var message = $('battle-delete-message');
        if (!popout || !encounter) return;
        state.pendingDeleteEncounter = encounter;
        if (message) {
            message.textContent = 'This permanently deletes "' +
                (encounter.name || 'this encounter') +
                '", its combatants, and its battle log. This cannot be undone.';
        }
        popout.hidden = false;
        positionBattleRenamePopout(popout, anchor);
    }

    function closeDeleteEncounterPopout() {
        var popout = $('battle-delete-popout');
        if (popout) popout.hidden = true;
        state.pendingDeleteEncounter = null;
    }

    async function deleteEncounter(encounterId) {
        if (!encounterId || state.busy) return;
        state.busy = true;
        try {
            await api('/encounters/' + encounterId, 'DELETE');
            var deletedCurrent = Number(state.encounterId) === Number(encounterId);
            if (deletedCurrent) {
                state.encounterId = null;
                state.data = null;
            }
            await loadEncounters();
            if (state.encounterId) {
                await loadEncounter(state.encounterId);
            } else {
                renderAll();
            }
            refreshMapEncounters();
            feedback('Encounter deleted.');
        } catch (err) {
            feedback(err.message, true);
        } finally {
            state.busy = false;
        }
    }

    async function setEncounterPlayerVisibility(encounterId, visible) {
        try {
            var out = await api('/encounters/' + encounterId + '/visibility', 'POST', {
                visible_to_players: !!visible
            });
            state.encounters = state.encounters.map(function (enc) {
                return Number(enc.id) === Number(encounterId) ? out.encounter : enc;
            });
            if (state.data && Number(state.data.id) === Number(encounterId)) {
                state.data.visible_to_players = !!out.encounter.visible_to_players;
            }
            renderEncounterMenu();
            feedback(visible ? 'Players can see this encounter.' : 'Encounter hidden from players.');
        } catch (err) {
            feedback(err.message, true);
            await loadEncounters();
        }
    }

    async function apiMultipart(path, formData) {
        var opts = {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' }
        };
        if (cfg.csrfToken) opts.headers['X-CSRFToken'] = cfg.csrfToken;
        opts.body = formData;
        var resp = await fetch(API + path, opts);
        var data = null;
        try { data = await resp.json(); } catch (e) { /* non-JSON */ }
        if (!resp.ok) {
            var err = new Error((data && data.error) || ('Request failed (' + resp.status + ')'));
            err.status = resp.status;
            throw err;
        }
        return data;
    }

    function currentMapVersion() {
        return state.data && state.data.map ? Number(state.data.map.map_version) : null;
    }

    async function loadEncounterMap(force) {
        if (!state.encounterId || !state.data) {
            state.mapData = null;
            state.mapVersionLoaded = null;
            state.mapChunks = {};
            renderBattleMapBackground();
            return;
        }
        var ver = currentMapVersion();
        if (!force && ver !== null && ver === state.mapVersionLoaded && state.mapData) {
            if (state.mapData.chunked) {
                await loadVisibleMapChunks(false);
            }
            renderBattleMapBackground();
            return;
        }
        try {
            var out = await api('/encounters/' + state.encounterId + '/map');
            state.mapData = out.map || null;
            state.mapVersionLoaded = ver;
            state.mapChunks = {};
            if (state.mapData && state.mapData.chunked) {
                await loadVisibleMapChunks(true);
            }
            renderBattleMapBackground();
        } catch (err) {
            feedback(err.message, true);
        }
    }

    function syncMapBackgroundLayout(bg, bounds) {
        if (!bg || !bounds) return;
        var visW = (bounds.x1 - bounds.x0) * TILE;
        var visH = (bounds.y1 - bounds.y0) * TILE;
        bg.style.position = 'absolute';
        bg.style.inset = 'auto';
        bg.style.left = (bounds.x0 * TILE) + 'px';
        bg.style.top = (bounds.y0 * TILE) + 'px';
        bg.style.width = visW + 'px';
        bg.style.height = visH + 'px';
        bg.style.pointerEvents = 'none';
    }

    function renderBattleMapBackground() {
        var bg = $('battle-map-bg');
        if (!bg) return;
        bg.innerHTML = '';
        if (!state.data || !state.mapData) return;
        var map = state.mapData;
        var gw = state.data.grid_width || 20;
        var gh = state.data.grid_height || 20;
        var bounds = visibleCellBounds();
        syncMapBackgroundLayout(bg, bounds);

        if (map.has_image && map.image_url) {
            var wrap = document.createElement('div');
            wrap.className = 'battle-map-image-window';
            wrap.style.width = '100%';
            wrap.style.height = '100%';
            wrap.style.overflow = 'hidden';
            var img = document.createElement('img');
            img.alt = '';
            img.src = map.image_url + '?v=' + (map.map_version || 0);
            img.style.display = 'block';
            img.style.width = (gw * TILE) + 'px';
            img.style.height = (gh * TILE) + 'px';
            img.style.marginLeft = (-bounds.x0 * TILE) + 'px';
            img.style.marginTop = (-bounds.y0 * TILE) + 'px';
            img.style.objectFit = 'fill';
            wrap.appendChild(img);
            bg.appendChild(wrap);
            return;
        }

        if (map.chunked) {
            loadVisibleMapChunks(false).then(function () {
                renderChunkedMapBackground(bg, gw, gh, bounds);
            });
            return;
        }

        var meta = map.terrain_metadata || {};
        var svg = buildTerrainSvg(meta, gw, gh, bounds);
        bg.appendChild(svg);
    }

    function isSetupEditable() {
        return state.data && state.data.status === 'setup';
    }

    function updateSetupSourceVisibility() {
        var source = ($('battle-setup-source') || {}).value || 'generated';
        var gen = $('battle-setup-generated-actions');
        var up = $('battle-setup-upload-row');
        if (gen) gen.hidden = source !== 'generated';
        if (up) up.hidden = source !== 'uploaded';
    }

    function openSetupPopout(mode) {
        var popout = $('battle-setup-popout');
        if (!popout) return;
        state.setupMode = mode || 'create';
        var title = $('battle-setup-title');
        var submit = $('battle-setup-submit');
        var lockedNote = $('battle-setup-locked-note');
        var editable = mode === 'create' || isSetupEditable();
        popout.classList.toggle('is-locked', !editable);
        if (lockedNote) lockedNote.hidden = editable;
        if (title) {
            title.textContent = mode === 'create' ? 'New encounter' : 'Encounter setup';
        }
        if (submit) {
            submit.textContent = mode === 'create' ? 'Create encounter' : 'Apply changes';
            submit.disabled = mode !== 'create' && !editable;
        }
        var nameEl = $('battle-setup-name');
        if (nameEl) {
            nameEl.value = mode === 'create' ? 'Encounter' : (state.data ? state.data.name : 'Encounter');
        }
        var wEl = $('battle-setup-width');
        var hEl = $('battle-setup-height');
        if (wEl) wEl.value = state.data ? state.data.grid_width : 20;
        if (hEl) hEl.value = state.data ? state.data.grid_height : 20;
        var presetEl = $('battle-setup-preset');
        if (presetEl && state.data && state.data.map && state.data.map.terrain_preset) {
            presetEl.value = state.data.map.terrain_preset;
        }
        var sourceEl = $('battle-setup-source');
        if (sourceEl && state.data && state.data.map) {
            sourceEl.value = state.data.map.source_type === 'uploaded' ? 'uploaded' : 'generated';
        }
        updateSetupSourceVisibility();
        popout.hidden = false;
        var anchor = $('battle-create-btn') || $('battle-setup-edit-btn');
        requestAnimationFrame(function () {
            positionBattleRenamePopout(popout, anchor);
        });
    }

    function closeSetupPopout() {
        var popout = $('battle-setup-popout');
        if (popout) popout.hidden = true;
        var uploadInput = $('battle-setup-upload-input');
        if (uploadInput) uploadInput.value = '';
    }

    var TILE = 34;
    var OVERSCAN = 3;
    var CHUNK_THRESHOLD = 150;
    var battleViewport = null;

    function anchorFixedPanel(panel) {
        if (!panel) return;
        var rect = panel.getBoundingClientRect();
        var local = viewportToPanelLocal(panel, rect.left, rect.top);
        panel.style.transform = 'none';
        panel.style.left = local.left + 'px';
        panel.style.top = local.top + 'px';
        if (!panel.style.width) panel.style.width = rect.width + 'px';
        if (!panel.style.height) panel.style.height = rect.height + 'px';
    }

    function bindFixedPanelDrag(panel, dragHandle, options) {
        if (!panel || panel.dataset.moveBound) return;
        panel.dataset.moveBound = '1';
        options = options || {};
        var edgePx = options.edgePx || 10;
        var edgeDrag = !!options.edgeDrag;
        var drag = null;
        var blockSel = 'button, input, select, summary, textarea, a, label, ' +
            '.battle-floating-resize-handle, .battle-floating-popout-close, .battle-encounter-window-close';

        panel.addEventListener('pointerdown', function (ev) {
            if (ev.button !== 0) return;
            var startDrag = false;
            if (dragHandle && dragHandle.contains(ev.target) &&
                !ev.target.closest(blockSel)) {
                startDrag = true;
            } else if (edgeDrag) {
                var rect = panel.getBoundingClientRect();
                var x = ev.clientX - rect.left;
                var y = ev.clientY - rect.top;
                var onEdge = x <= edgePx || y <= edgePx ||
                    x >= rect.width - edgePx || y >= rect.height - edgePx;
                if (onEdge && !ev.target.closest(blockSel) &&
                    !ev.target.closest('.battle-encounter-window-body')) {
                    startDrag = true;
                }
            }
            if (!startDrag) return;
            anchorFixedPanel(panel);
            var anchored = panel.getBoundingClientRect();
            var local = viewportToPanelLocal(panel, anchored.left, anchored.top);
            drag = {
                pointerId: ev.pointerId,
                startX: ev.clientX,
                startY: ev.clientY,
                left: local.left,
                top: local.top
            };
            try { panel.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
            ev.preventDefault();
        });
        panel.addEventListener('pointermove', function (ev) {
            if (!drag || drag.pointerId !== ev.pointerId) return;
            panel.style.left = (drag.left + ev.clientX - drag.startX) + 'px';
            panel.style.top = (drag.top + ev.clientY - drag.startY) + 'px';
        });
        function endDrag(ev) {
            if (!drag || (ev && drag.pointerId !== ev.pointerId)) return;
            drag = null;
            try { panel.releasePointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
        }
        panel.addEventListener('pointerup', endDrag);
        panel.addEventListener('pointercancel', endDrag);
    }

    function bindFixedPanelResize(panel, resizeHandle, minWidth, minHeight, onResize) {
        if (!panel || !resizeHandle || resizeHandle.dataset.resizeBound) return;
        resizeHandle.dataset.resizeBound = '1';
        var resize = null;
        resizeHandle.addEventListener('pointerdown', function (ev) {
            if (ev.button !== 0) return;
            ev.stopPropagation();
            anchorFixedPanel(panel);
            var rect = panel.getBoundingClientRect();
            resize = {
                pointerId: ev.pointerId,
                startX: ev.clientX,
                startY: ev.clientY,
                width: rect.width,
                height: rect.height
            };
            try { resizeHandle.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
            ev.preventDefault();
        });
        resizeHandle.addEventListener('pointermove', function (ev) {
            if (!resize || resize.pointerId !== ev.pointerId) return;
            panel.style.width = Math.max(minWidth, resize.width + ev.clientX - resize.startX) + 'px';
            panel.style.height = Math.max(minHeight, resize.height + ev.clientY - resize.startY) + 'px';
            if (typeof onResize === 'function') onResize();
        });
        function endResize(ev) {
            if (!resize || (ev && resize.pointerId !== ev.pointerId)) return;
            resize = null;
            try { resizeHandle.releasePointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
            if (typeof onResize === 'function') onResize();
        }
        resizeHandle.addEventListener('pointerup', endResize);
        resizeHandle.addEventListener('pointercancel', endResize);
    }

    function initBattleViewport() {
        var stage = $('battle-stage');
        var layer = $('battle-viewport-layer');
        if (!window.MapViewport || !stage || !layer || battleViewport) return;
        battleViewport = window.MapViewport.create(stage, layer, {
            paintActive: false,
            autoFitOnResize: false,
            shouldStartPan: function (ev) {
                if (ev.button === 1 || ev.button === 2) return true;
                if (state.placement ||
                    state.mode === 'move' ||
                    state.mode === 'attack' ||
                    state.mode === 'cast_spell') {
                    return false;
                }
                var target = ev.target;
                if (!target || !target.closest) return true;
                return !target.closest(
                    '.battle-token, .battle-radial, .battle-attack-popout,' +
                    '.battle-cast-popout, button, input, select, textarea, a'
                );
            },
            onViewportChange: function () {
                scheduleVirtualRender();
            }
        });
    }

    function syncBattleViewportWorldSize() {
        if (!battleViewport || !state.data) return;
        var gw = state.data.grid_width || 20;
        var gh = state.data.grid_height || 20;
        battleViewport.setWorldSize(gw * TILE, gh * TILE);
    }

    function worldTileCenterStagePx(tileX, tileY) {
        if (!battleViewport) {
            return {
                x: (tileX + 0.5) * TILE,
                y: (tileY + 0.5) * TILE
            };
        }
        var wx = (tileX + 0.5) * TILE;
        var wy = (tileY + 0.5) * TILE;
        var vp = battleViewport.getState();
        return {
            x: wx * vp.scale + vp.panX,
            y: wy * vp.scale + vp.panY
        };
    }

    function visibleCellBounds() {
        if (!state.data) return { x0: 0, y0: 0, x1: 0, y1: 0 };
        var gw = state.data.grid_width;
        var gh = state.data.grid_height;
        if (!battleViewport) {
            return { x0: 0, y0: 0, x1: gw, y1: gh };
        }
        var stage = $('battle-stage');
        if (!stage) return { x0: 0, y0: 0, x1: gw, y1: gh };
        var rect = stage.getBoundingClientRect();
        var tl = battleViewport.screenToWorld(rect.left, rect.top);
        var br = battleViewport.screenToWorld(rect.right, rect.bottom);
        var x0 = Math.max(0, Math.floor(tl.x / TILE) - OVERSCAN);
        var y0 = Math.max(0, Math.floor(tl.y / TILE) - OVERSCAN);
        var x1 = Math.min(gw, Math.ceil(br.x / TILE) + OVERSCAN);
        var y1 = Math.min(gh, Math.ceil(br.y / TILE) + OVERSCAN);
        return { x0: x0, y0: y0, x1: x1, y1: y1 };
    }

    function focusCameraOnCell(x, y) {
        if (!battleViewport || !state.data) return;
        battleViewport.panToWorldPoint((x + 0.5) * TILE, (y + 0.5) * TILE);
        scheduleVirtualRender();
    }

    function scheduleVirtualRender() {
        if (state.renderPending) return;
        state.renderPending = true;
        requestAnimationFrame(function () {
            state.renderPending = false;
            if (!state.data) return;
            renderGrid();
            renderBattleMapBackground();
        });
    }

    function onStageKeyPan(ev) {
        if (!state.data || !battleViewport) return;
        var target = ev.target;
        if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' ||
            target.tagName === 'SELECT' || target.isContentEditable)) return;
        var dx = 0;
        var dy = 0;
        if (ev.key === 'ArrowLeft') dx = 48;
        else if (ev.key === 'ArrowRight') dx = -48;
        else if (ev.key === 'ArrowUp') dy = 48;
        else if (ev.key === 'ArrowDown') dy = -48;
        else return;
        ev.preventDefault();
        battleViewport.panBy(dx, dy);
    }

    function bindEncounterWindowChrome() {
        if (!IS_GM) return;
        var win = $('battle-encounter-window');
        var drag = $('battle-encounter-window-drag');
        var closeBtn = $('battle-encounter-window-close');
        var resizeHandle = $('battle-encounter-window-resize');
        if (closeBtn && !closeBtn.dataset.bound) {
            closeBtn.dataset.bound = '1';
            closeBtn.addEventListener('click', function () {
                closeEncounterWindow();
            });
        }
        bindFixedPanelDrag(win, drag, { edgeDrag: true });
        bindFixedPanelResize(win, resizeHandle, 520, 400, function () {
            scheduleVirtualRender();
        });
    }

    function bindSetupPopoutChrome() {
        if (!IS_GM) return;
        var popout = $('battle-setup-popout');
        var drag = $('battle-setup-popout-drag');
        var closeBtn = $('battle-setup-popout-close');
        var resizeHandle = $('battle-setup-popout-resize');
        if (closeBtn && !closeBtn.dataset.bound) {
            closeBtn.dataset.bound = '1';
            closeBtn.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                closeSetupPopout();
            });
        }
        bindFixedPanelDrag(popout, drag, { edgeDrag: true });
        bindFixedPanelResize(popout, resizeHandle, 320, 280);
    }

    function openEncounterWindow() {
        if (!IS_GM) {
            activateBattleTab();
            return;
        }
        var win = $('battle-encounter-window');
        if (!win) {
            activateBattleTab();
            return;
        }
        win.hidden = false;
        if (!win.style.left) {
            win.style.left = '50%';
            win.style.top = '50%';
            win.style.transform = 'translate(-50%, -50%)';
        }
        var tab = $('battle-tab-btn');
        if (tab) {
            tab.classList.add('active');
            tab.setAttribute('aria-selected', 'true');
        }
        bindEncounterWindowChrome();
        ensureLoaded();
        requestAnimationFrame(function () {
            syncBattleViewportWorldSize();
            if (battleViewport) battleViewport.fitToView();
        });
    }

    function closeEncounterWindow() {
        var win = $('battle-encounter-window');
        if (win) win.hidden = true;
        stopPolling();
        var tab = $('battle-tab-btn');
        if (tab) {
            tab.classList.remove('active');
            tab.setAttribute('aria-selected', 'false');
        }
    }

    function appendFeaturesToSvg(svg, features, palette, gw, gh) {
        var unit = Math.min(gw, gh);
        (features || []).forEach(function (feat) {
            var t = feat.type;
            if (t === 'patch' || t === 'wall') {
                var poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                poly.setAttribute('points', (feat.points || []).map(function (p) {
                    return (p[0] * gw) + ',' + (p[1] * gh);
                }).join(' '));
                poly.setAttribute('fill', palette.accent || '#6b8e4e');
                poly.setAttribute('opacity', '0.75');
                svg.appendChild(poly);
            } else if (t === 'river' || t === 'road') {
                var pl = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
                pl.setAttribute('points', (feat.points || []).map(function (p) {
                    return (p[0] * gw) + ',' + (p[1] * gh);
                }).join(' '));
                pl.setAttribute('fill', 'none');
                pl.setAttribute('stroke', t === 'river'
                    ? (palette.detail || '#4a90a4')
                    : (palette.accent || '#8a7a62'));
                pl.setAttribute('stroke-width', String(
                    t === 'river' ? Math.max(0.15, unit * 0.04) : Math.max(0.08, unit * 0.025)
                ));
                pl.setAttribute('vector-effect', 'non-scaling-stroke');
                pl.setAttribute('stroke-linecap', 'round');
                pl.setAttribute('opacity', '0.85');
                svg.appendChild(pl);
            } else if (t === 'building') {
                var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                rect.setAttribute('x', String((feat.x || 0) * gw));
                rect.setAttribute('y', String((feat.y || 0) * gh));
                rect.setAttribute('width', String((feat.w || 0.08) * gw));
                rect.setAttribute('height', String((feat.h || 0.08) * gh));
                rect.setAttribute('fill', palette.detail || '#6b5344');
                svg.appendChild(rect);
            } else if (t === 'tent') {
                var tri = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                var cx = (feat.x || 0) * gw;
                var cy = (feat.y || 0) * gh;
                var sz = (feat.size || 0.06) * unit;
                tri.setAttribute('points', cx + ',' + (cy - sz) + ' ' +
                    (cx - sz * 0.7) + ',' + (cy + sz * 0.5) + ' ' +
                    (cx + sz * 0.7) + ',' + (cy + sz * 0.5));
                tri.setAttribute('fill', palette.accent || '#6b5d4f');
                svg.appendChild(tri);
            }
        });
    }

    function buildTerrainSvg(meta, gw, gh, clipBounds) {
        var palette = (meta && meta.palette) || {
            base: '#8fbc8f', accent: '#6b8e4e', detail: '#c4a35a'
        };
        var bounds = clipBounds || { x0: 0, y0: 0, x1: gw, y1: gh };
        var vbW = bounds.x1 - bounds.x0;
        var vbH = bounds.y1 - bounds.y0;
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', bounds.x0 + ' ' + bounds.y0 + ' ' + vbW + ' ' + vbH);
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        var base = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        base.setAttribute('x', String(bounds.x0));
        base.setAttribute('y', String(bounds.y0));
        base.setAttribute('width', String(vbW));
        base.setAttribute('height', String(vbH));
        base.setAttribute('fill', palette.base || '#8fbc8f');
        svg.appendChild(base);
        appendFeaturesToSvg(svg, (meta && meta.features) || [], palette, gw, gh);
        return svg;
    }

    async function loadVisibleMapChunks(force) {
        if (!state.mapData || !state.mapData.chunked || !state.encounterId) return;
        var bounds = visibleCellBounds();
        var cs = state.mapData.chunk_size || 64;
        var cx0 = Math.floor(bounds.x0 / cs);
        var cy0 = Math.floor(bounds.y0 / cs);
        var cx1 = Math.floor((bounds.x1 - 1) / cs);
        var cy1 = Math.floor((bounds.y1 - 1) / cs);
        var ver = state.mapData.map_version || 0;
        var pending = [];
        for (var cy = cy0; cy <= cy1; cy++) {
            for (var cx = cx0; cx <= cx1; cx++) {
                var key = ver + ':' + cx + ':' + cy;
                if (!force && state.mapChunks[key]) continue;
                pending.push((function (chunkX, chunkY, cacheKey) {
                    return api('/encounters/' + state.encounterId +
                        '/map/chunk?chunk_x=' + chunkX + '&chunk_y=' + chunkY)
                        .then(function (out) {
                            state.mapChunks[cacheKey] = out.map_chunk || null;
                        })
                        .catch(function () { /* chunk fetch is best-effort */ });
                })(cx, cy, key));
            }
        }
        if (pending.length) await Promise.all(pending);
    }

    function renderChunkedMapBackground(bg, gw, gh, bounds) {
        if (!bg) return;
        bg.innerHTML = '';
        syncMapBackgroundLayout(bg, bounds);
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute(
            'viewBox',
            bounds.x0 + ' ' + bounds.y0 + ' ' +
            (bounds.x1 - bounds.x0) + ' ' + (bounds.y1 - bounds.y0)
        );
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        var base = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        base.setAttribute('x', String(bounds.x0));
        base.setAttribute('y', String(bounds.y0));
        base.setAttribute('width', String(bounds.x1 - bounds.x0));
        base.setAttribute('height', String(bounds.y1 - bounds.y0));
        base.setAttribute('fill', '#8fbc8f');
        svg.appendChild(base);
        Object.keys(state.mapChunks).forEach(function (key) {
            var chunk = state.mapChunks[key];
            if (!chunk || !chunk.terrain_metadata) return;
            appendFeaturesToSvg(
                svg,
                chunk.terrain_metadata.features || [],
                chunk.terrain_metadata.palette || {},
                gw,
                gh
            );
        });
        bg.appendChild(svg);
    }

    function occupiedTiles() {
        if (!state.data) return {};
        var map = {};
        (state.data.combatants || []).forEach(function (c) {
            if (c.status === 'dead' || c.status === 'removed') return;
            map[c.x + ',' + c.y] = true;
        });
        return map;
    }

    function isTileOccupied(x, y) {
        return !!occupiedTiles()[x + ',' + y];
    }

    /** Keep absolutely positioned popouts inside the battle stage viewport. */
    function positionPopoutWithinStage(el, stage, anchorX, anchorY, opts) {
        opts = opts || {};
        var pad = opts.pad == null ? 6 : opts.pad;
        el.hidden = false;
        var w = el.offsetWidth;
        var h = el.offsetHeight;
        var viewW = stage.clientWidth;
        var viewH = stage.clientHeight;
        var left = anchorX - w / 2;
        var top = opts.preferBelow
            ? anchorY + TILE / 2 + 8
            : anchorY - h - 8;
        if (top < pad && !opts.preferBelow) {
            top = anchorY + TILE / 2 + 8;
        }
        el.style.left = Math.max(pad, Math.min(left, viewW - w - pad)) + 'px';
        el.style.top = Math.max(pad, Math.min(top, viewH - h - pad)) + 'px';
    }

    function activateBattleTab() {
        if (IS_GM) {
            openEncounterWindow();
            return;
        }
        var btn = $('battle-tab-btn');
        if (btn && btn.getAttribute('aria-selected') !== 'true') {
            btn.click();
        }
    }

    function updatePlacementHint() {
        var hint = $('battle-placement-hint');
        if (!hint) return;
        if (!state.placement) {
            hint.hidden = true;
            hint.textContent = '';
            return;
        }
        hint.hidden = false;
        hint.textContent = 'Click an empty tile on the battle map to place ' +
            state.placement.label + '. Press Esc to cancel.';
    }

    function cancelPlacement() {
        state.placement = null;
        updatePlacementHint();
        var grid = $('battle-grid');
        if (grid) grid.classList.remove('battle-mode-place');
        renderToolbar();
    }

    function startCharacterPlacement() {
        if (!state.encounterId) {
            feedback('Create an encounter on the Encounters tab first.', true);
            return;
        }
        var sel = $('battle-character-select');
        var pid = sel ? parseInt(sel.value, 10) : NaN;
        if (isNaN(pid)) {
            feedback('Select a character or NPC first.', true);
            return;
        }
        exitMode();
        var label = sel.options[sel.selectedIndex].textContent.trim();
        state.placement = { type: 'character', playerId: pid, label: label };
        activateBattleTab();
        updatePlacementHint();
        var grid = $('battle-grid');
        if (grid) grid.classList.add('battle-mode-place');
    }

    function startOwnCharacterPlacement() {
        if (!state.encounterId || !state.data) {
            feedback('No encounter is loaded yet.', true);
            return;
        }
        if (!OWN_PLAYER_IDS.length) {
            feedback('No player character is available to place.', true);
            return;
        }
        if (ownPlayerCombatant()) {
            feedback('Your character is already placed.');
            renderToolbar();
            return;
        }
        exitMode();
        state.placement = {
            type: 'own_character',
            playerId: OWN_PLAYER_IDS[0],
            label: 'your character'
        };
        updatePlacementHint();
        var grid = $('battle-grid');
        if (grid) grid.classList.add('battle-mode-place');
        feedback('Click an empty tile on the battle map to place your character.');
        renderToolbar();
    }

    function startMonsterPlacement(monster, count) {
        if (!state.encounterId) {
            feedback('Create an encounter on the Encounters tab first.', true);
            return;
        }
        exitMode();
        state.placement = {
            type: 'monster',
            monsterId: monster.id,
            count: count,
            label: monster.name + (count > 1 ? ' (x' + count + ')' : '')
        };
        activateBattleTab();
        updatePlacementHint();
        var grid = $('battle-grid');
        if (grid) grid.classList.add('battle-mode-place');
    }

    async function placeAtTile(x, y) {
        if (!state.placement || !state.encounterId) return;
        if (isTileOccupied(x, y)) {
            feedback('That tile is occupied.', true);
            return;
        }
        var placement = state.placement;
        cancelPlacement();
        if (placement.type === 'character') {
            await mutate('/encounters/' + state.encounterId + '/combatants', {
                player_id: placement.playerId,
                x: x,
                y: y
            });
        } else if (placement.type === 'own_character') {
            await mutate('/encounters/' + state.encounterId + '/own-combatant', {
                player_id: placement.playerId,
                x: x,
                y: y
            });
        } else if (placement.type === 'monster') {
            await mutate('/encounters/' + state.encounterId + '/monsters/' +
                placement.monsterId + '/add', {
                count: placement.count,
                x: x,
                y: y
            });
        }
    }

    function renderGrid() {
        initBattleViewport();
        var grid = $('battle-grid');
        if (!grid) return;
        grid.innerHTML = '';
        closeRadial();
        if (!state.data) {
            grid.innerHTML = '<p class="battle-empty">No encounter loaded.' +
                (IS_GM ? ' Create one to begin.' : '') + '</p>';
            return;
        }
        var bounds = visibleCellBounds();
        var x0 = bounds.x0;
        var y0 = bounds.y0;
        var x1 = bounds.x1;
        var y1 = bounds.y1;
        var visW = (x1 - x0) * TILE;
        var visH = (y1 - y0) * TILE;

        grid.style.position = 'absolute';
        grid.style.left = (x0 * TILE) + 'px';
        grid.style.top = (y0 * TILE) + 'px';
        grid.style.width = visW + 'px';
        grid.style.height = visH + 'px';

        var board = document.createElement('div');
        board.className = 'battle-board battle-board-virtual';
        board.style.width = visW + 'px';
        board.style.height = visH + 'px';

        var layer = document.createElement('div');
        layer.className = 'battle-visible-layer';
        layer.style.transform = 'translate3d(0, 0, 0)';

        for (var y = y0; y < y1; y++) {
            for (var x = x0; x < x1; x++) {
                var tile = document.createElement('div');
                tile.className = 'battle-tile';
                if (isTileOccupied(x, y)) {
                    tile.classList.add('battle-tile-occupied');
                }
                tile.dataset.x = x;
                tile.dataset.y = y;
                tile.style.left = ((x - x0) * TILE) + 'px';
                tile.style.top = ((y - y0) * TILE) + 'px';
                tile.style.width = TILE + 'px';
                tile.style.height = TILE + 'px';
                tile.addEventListener('click', onTileClick);
                layer.appendChild(tile);
            }
        }

        (state.data.combatants || []).forEach(function (c) {
            if (c.status === 'removed') return;
            if (c.x < x0 || c.x >= x1 || c.y < y0 || c.y >= y1) return;
            var tile = layer.querySelector(
                '.battle-tile[data-x="' + c.x + '"][data-y="' + c.y + '"]'
            );
            if (!tile) return;
            var token = document.createElement('button');
            token.type = 'button';
            token.className = 'battle-token battle-token-' + c.side +
                (isOwnPlayerCombatant(c) ? ' battle-token-own-player' : '') +
                (isCurrentTurn(c) ? ' battle-token-current' : '') +
                (c.status !== 'active' ? ' battle-token-down' : '');
            token.dataset.combatantId = c.id;
            token.title = c.name + (c.hp_current !== undefined
                ? (' - ' + c.hp_current + '/' + c.hp_max + ' HP')
                : (' - ' + c.health_state)) +
                (c.concentration && c.concentration.spell_name
                    ? (' — Concentrating: ' + c.concentration.spell_name)
                    : '');
            token.textContent = (c.name || '?').charAt(0).toUpperCase();
            token.addEventListener('click', onTokenClick);
            tile.appendChild(token);
        });

        board.appendChild(layer);
        grid.appendChild(board);
        grid.classList.toggle('battle-mode-move', state.mode === 'move');
        grid.classList.toggle('battle-mode-attack', state.mode === 'attack');
        grid.classList.toggle('battle-mode-place', !!state.placement);
    }

    function renderTracker() {
        var list = $('battle-turn-tracker');
        if (!list) return;
        list.innerHTML = '';
        if (!state.data) return;
        var ordered = (state.data.combatants || [])
            .filter(function (c) { return c.initiative_order !== null && c.status !== 'removed'; })
            .sort(function (a, b) { return a.initiative_order - b.initiative_order; });
        if (!ordered.length) {
            list.innerHTML = '<li class="battle-tracker-empty">Initiative not rolled yet.</li>';
            return;
        }
        ordered.forEach(function (c) {
            var li = document.createElement('li');
            li.className = 'battle-tracker-row' +
                (isCurrentTurn(c) ? ' battle-tracker-current' : '') +
                (c.status !== 'active' ? ' battle-tracker-down' : '');
            var hp = c.hp_current !== undefined
                ? (c.hp_current + '/' + c.hp_max)
                : c.health_state;
            li.innerHTML = '<span class="battle-tracker-init">' + esc(c.initiative) + '</span>' +
                '<span class="battle-tracker-name">' + esc(c.name) + '</span>' +
                '<span class="battle-tracker-hp">' + esc(hp) + '</span>' +
                (c.has_waited ? '<span class="battle-tracker-flag" title="Waited this round">W</span>' : '');
            list.appendChild(li);
        });
    }

    function renderLog() {
        var list = $('battle-log');
        if (!list) return;
        list.innerHTML = '';
        if (!state.data) return;
        (state.data.log || []).forEach(function (entry) {
            var li = document.createElement('li');
            var text = describeLog(entry);
            if (text.indexOf('\n') >= 0) {
                li.style.whiteSpace = 'pre-wrap';
            }
            li.textContent = text;
            list.appendChild(li);
        });
    }

    function formatToHitRoll(toHit) {
        if (!toHit) return '';
        var kept = toHit.natural;
        var parts = [];
        if (toHit.rolls && toHit.rolls.length > 1) {
            parts.push('attack d20 [' + toHit.rolls.join(', ') + '] → kept ' + kept);
        } else {
            parts.push('attack d20 ' + kept);
        }
        if (toHit.lucky_reroll) {
            parts.push('Lucky reroll');
        }
        if (toHit.mode && toHit.mode !== 'normal') {
            parts.push(toHit.mode);
        }
        var line = parts.join(', ') + ' → total ' + toHit.total;
        if (toHit.target_ac != null) {
            line += ' vs AC ' + toHit.target_ac;
        }
        if (toHit.crit || toHit.is_nat20) {
            line += ' — CRIT';
        } else if (toHit.is_nat1) {
            line += ' — natural 1';
        } else if (toHit.hit) {
            line += ' — hit';
        } else {
            line += ' — miss';
        }
        return line;
    }

    function formatDamageRoll(damageRoll) {
        if (!damageRoll) return '';
        var dice = (damageRoll.rolls || []).join(' + ');
        var mod = Number(damageRoll.modifier || 0);
        var line = 'damage';
        if (damageRoll.notation) {
            line += ' ' + damageRoll.notation;
        }
        line += ':';
        if (dice) {
            line += ' [' + dice + ']';
        }
        if (mod) {
            line += (mod > 0 ? ' + ' : ' ') + mod;
        }
        line += ' = ' + damageRoll.total;
        if (damageRoll.crit) {
            line += ' (crit)';
        }
        if (damageRoll.damage_modifiers && damageRoll.damage_modifiers.applied &&
                damageRoll.damage_modifiers.applied.length) {
            line += ' (' + damageRoll.damage_modifiers.applied.join(', ') + ')';
        }
        return line;
    }

    function formatSaveRoll(save) {
        if (!save) return '';
        var line = 'save d20 ' + save.natural + ' → total ' + save.total;
        if (save.dc != null) {
            line += ' vs DC ' + save.dc;
        }
        line += save.success ? ' — saved' : ' — failed';
        return line;
    }

    function formatHealingRoll(healingRoll) {
        if (!healingRoll) return '';
        var dice = (healingRoll.rolls || []).join(' + ');
        var mod = Number(healingRoll.modifier || 0);
        var line = 'healing';
        if (healingRoll.notation) {
            line += ' ' + healingRoll.notation;
        }
        line += ':';
        if (dice) {
            line += ' [' + dice + ']';
        }
        if (mod) {
            line += (mod > 0 ? ' + ' : ' ') + mod;
        }
        return line + ' = ' + healingRoll.total;
    }

    function describeAttackPayload(p, who, targetName) {
        var tn = targetName || 'target';
        var label = who;
        if (p.attack && p.attack.name) {
            label += ' — ' + p.attack.name;
        } else if (p.legendary_action && p.legendary_action.name) {
            label += ' — ' + p.legendary_action.name;
        }
        var parts = [label + ' → ' + tn];
        if (p.to_hit) {
            parts.push(formatToHitRoll(p.to_hit));
        }
        if (p.hit && p.damage_roll) {
            parts.push(formatDamageRoll(p.damage_roll));
        }
        return parts.join(' · ');
    }

    function describeLog(entry) {
        var actor = entry.combatant_id ? combatantById(entry.combatant_id) : null;
        var who = actor ? actor.name : 'GM';
        var p = entry.payload || {};
        switch (entry.type) {
            case 'encounter_created': return 'Encounter created.';
            case 'encounter_ended': return 'Encounter ended.';
            case 'combatant_added': return who + ' joined the battle.';
            case 'combatant_removed': return who + ' was removed.';
            case 'initiative_rolled': return 'Initiative rolled - round 1 begins.';
            case 'move': return who + ' moved ' + (p.cost_ft || '?') + ' ft.';
            case 'attack': {
                var target = p.target_id ? combatantById(p.target_id) : null;
                var tn = target ? target.name : 'target';
                return describeAttackPayload(p, who, tn);
            }
            case 'multiattack': {
                var maTarget = p.target_id ? combatantById(p.target_id) : null;
                var maName = maTarget ? maTarget.name : 'target';
                var maLabel = (p.multiattack && p.multiattack.name) || 'Multiattack';
                var maResults = p.results || [];
                if (!maResults.length) {
                    return who + ' used ' + maLabel + ' on ' + maName + '.';
                }
                return maLabel + ' → ' + maName + ':\n' + maResults.map(function (r) {
                    if (r.skipped) {
                        var atkName = r.attack && r.attack.name ? r.attack.name + ': ' : '';
                        return atkName + r.skipped;
                    }
                    return describeAttackPayload(r, who, maName);
                }).join('\n');
            }
            case 'batch_attack': {
                var results = p.results || [];
                if (!results.length) {
                    return who + ' led a group attack.';
                }
                var batchTarget = p.target_id ? combatantById(p.target_id) : null;
                var batchTargetName = batchTarget ? batchTarget.name : 'target';
                return results.map(function (r) {
                    if (r.skipped) {
                        var skippedWho = combatantById(r.attacker_id);
                        return (skippedWho ? skippedWho.name : who) + ': ' + r.skipped;
                    }
                    var attacker = combatantById(r.attacker_id);
                    return describeAttackPayload(
                        r,
                        attacker ? attacker.name : who,
                        batchTargetName
                    );
                }).join('\n');
            }
            case 'wait': return who + ' waits (drops to bottom of round).';
            case 'disengage': return who + ' disengaged.';
            case 'legendary_action': {
                var laTarget = p.target_id ? combatantById(p.target_id) : null;
                var laName = laTarget ? laTarget.name : 'target';
                return describeAttackPayload(p, who, laName);
            }
            case 'opportunity_attack': {
                var oaTarget = p.target_id ? combatantById(p.target_id) : null;
                var oaName = oaTarget ? oaTarget.name : 'target';
                return describeAttackPayload(p, who + ' (opportunity attack)', oaName);
            }
            case 'turn_ended': return 'R' + (p.round || '?') + ': next turn.';
            case 'death_save': return who + ' rolled a death save.';
            case 'cast_spell': {
                var spell = p.spell || {};
                var target = p.target_id ? combatantById(p.target_id) : null;
                var tn = target ? target.name : 'target';
                var label = spell.name || spell.key || 'a spell';
                if (p.manual_resolution) {
                    return who + ' logged ' + label + ' at ' + tn + ' (manual resolution).';
                }
                var parts = [who + ' cast ' + label + ' → ' + tn];
                if (p.to_hit) {
                    parts.push(formatToHitRoll(p.to_hit));
                }
                if (p.save) {
                    parts.push(formatSaveRoll(p.save));
                }
                if (p.damage_roll) {
                    parts.push(formatDamageRoll(p.damage_roll));
                }
                if (p.healing_roll) {
                    parts.push(formatHealingRoll(p.healing_roll));
                }
                return parts.join(' · ');
            }
            case 'concentration_start': {
                var started = (p.spell && p.spell.name) || 'a spell';
                return who + ' began concentrating on ' + started + '.';
            }
            case 'concentration_end': {
                var ended = (p.ended_spell && p.ended_spell.name) || 'a spell';
                var reason = p.reason || 'ended';
                return who + ' stopped concentrating on ' + ended + ' (' + reason + ').';
            }
            default: return entry.type;
        }
    }

    /* ------------------------------------------------------------------
     * Radial menu + arrows
     * ------------------------------------------------------------------ */
    function hideRadialMenu() {
        var menu = $('battle-radial');
        if (menu) {
            menu.hidden = true;
            menu.style.display = '';
        }
    }

    function closeRadial() {
        hideRadialMenu();
    }

    function clearTargetingModes() {
        state.mode = 'idle';
        state.actorId = null;
        hideArrow();
        var grid = $('battle-grid');
        if (grid) {
            grid.classList.remove('battle-mode-move', 'battle-mode-attack', 'battle-mode-cast');
        }
    }

    function resetBattleUiAfterMutation() {
        var attackPop = $('battle-attack-popout');
        var castPop = $('battle-cast-popout');
        if ((attackPop && !attackPop.hidden) || (castPop && !castPop.hidden)) {
            hideRadialMenu();
            clearTargetingModes();
            return;
        }
        exitMode();
    }

    function exitMode() {
        clearTargetingModes();
        cancelPlacement();
        hideRadialMenu();
        closeAttackPopout();
        closeCastPopout();
        var grid = $('battle-grid');
        if (grid) grid.classList.remove('battle-mode-place');
    }

    function onTokenClick(ev) {
        ev.stopPropagation();
        var id = parseInt(ev.currentTarget.dataset.combatantId, 10);
        var c = combatantById(id);
        if (!c) return;

        if (state.mode === 'attack' && state.actorId && id !== state.actorId) {
            openAttackPopout(combatantById(state.actorId), c, ev.currentTarget);
            return;
        }
        if (state.mode === 'cast_spell' && state.actorId && id !== state.actorId) {
            openCastPopout(combatantById(state.actorId), c, ev.currentTarget);
            return;
        }
        if (!IS_GM && state.mode === 'idle' && c.side === 'foe' && c.compendium_entry_id) {
            openPlayerMonsterInspectPopout(c, ev.currentTarget);
            return;
        }
        if (state.mode !== 'idle') { exitMode(); return; }
        if (!canAct(c)) {
            feedback(isCurrentTurn(c) ? 'You cannot control this combatant.'
                : 'It is not ' + c.name + "'s turn.");
            return;
        }
        openRadial(c, ev.currentTarget);
    }

    function openRadial(c, tokenEl) {
        var menu = $('battle-radial');
        var stage = $('battle-stage');
        if (!menu || !stage) return;
        state.actorId = c.id;
        var sRect = stage.getBoundingClientRect();
        var tRect = tokenEl.getBoundingClientRect();
        var anchorX = tRect.left - sRect.left + TILE / 2;
        var anchorY = tRect.top - sRect.top + TILE / 2;
        positionPopoutWithinStage(menu, stage, anchorX, anchorY);

        var isDown = c.status === 'down';
        $('battle-radial-move').hidden = isDown;
        $('battle-radial-attack').hidden = isDown;
        var castBtn = $('battle-radial-cast');
        if (castBtn) {
            castBtn.hidden = isDown || !castableSpells(c.spells).length;
        }
        $('battle-radial-wait').hidden = isDown;
        $('battle-radial-wait').disabled = !!c.has_waited;
        var disengageBtn = $('battle-radial-disengage');
        if (disengageBtn) disengageBtn.hidden = isDown;
        var deathBtn = $('battle-radial-death-save');
        if (deathBtn) deathBtn.hidden = !isDown;

        var endConcBtn = menu.querySelector('[data-action="end-concentration"]');
        if (!endConcBtn) {
            endConcBtn = document.createElement('button');
            endConcBtn.type = 'button';
            endConcBtn.className = 'battle-radial-btn';
            endConcBtn.dataset.action = 'end-concentration';
            endConcBtn.textContent = 'End concentration';
            endConcBtn.addEventListener('click', async function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                var actorId = state.actorId;
                exitMode();
                await mutate('/encounters/' + state.encounterId + '/action', {
                    type: 'end_concentration',
                    combatant_id: actorId
                });
            });
            menu.insertBefore(endConcBtn, $('battle-radial-close'));
        }
        endConcBtn.hidden = isDown || !canEndConcentration(c);
    }

    function showArrow(color) {
        var svg = $('battle-arrow');
        if (!svg) return;
        svg.hidden = false;
        svg.querySelector('line').setAttribute('stroke', color);
    }

    function hideArrow() {
        var svg = $('battle-arrow');
        if (svg) svg.hidden = true;
    }

    function onStageMouseMove(ev) {
        if (state.mode !== 'move' && state.mode !== 'attack' && state.mode !== 'cast_spell') return;
        var actor = combatantById(state.actorId);
        var svg = $('battle-arrow'), stage = $('battle-stage');
        if (!actor || !svg || !stage) return;
        var rect = stage.getBoundingClientRect();
        var anchor = worldTileCenterStagePx(actor.x, actor.y);
        var line = svg.querySelector('line');
        line.setAttribute('x1', anchor.x);
        line.setAttribute('y1', anchor.y);
        line.setAttribute('x2', ev.clientX - rect.left);
        line.setAttribute('y2', ev.clientY - rect.top);
    }

    function onTileClick(ev) {
        var x = parseInt(ev.currentTarget.dataset.x, 10);
        var y = parseInt(ev.currentTarget.dataset.y, 10);
        if (state.placement) {
            ev.stopPropagation();
            placeAtTile(x, y);
            return;
        }
        if (state.mode !== 'move' || !state.actorId) return;
        var actorId = state.actorId;
        exitMode();
        mutate('/encounters/' + state.encounterId + '/move',
            { combatant_id: actorId, x: x, y: y });
    }

    /* ------------------------------------------------------------------
     * Attack popout (with GM batch-roll checkboxes)
     * ------------------------------------------------------------------ */
    function closeAttackPopout() {
        var pop = $('battle-attack-popout');
        if (pop) pop.hidden = true;
    }

    function closeCastPopout() {
        var pop = $('battle-cast-popout');
        if (pop) pop.hidden = true;
    }

    function closePlayerMonsterInspectPopout() {
        var pop = $('battle-monster-inspect-popout');
        if (pop) pop.hidden = true;
    }

    function playerMonsterApiUrl(configKey, entryId) {
        var tpl = cfg[configKey] || '';
        return String(tpl).replace('999999999', encodeURIComponent(entryId));
    }

    async function discoverMonsterFromEncounter(entryId, pop) {
        var url = cfg.playerMonsterDiscoverUrl || '/player/monsters/discover';
        try {
            var resp = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-CSRFToken': cfg.csrfToken || ''
                },
                body: JSON.stringify({ monster_entry_id: entryId })
            });
            var data = await resp.json();
            if (!resp.ok) {
                throw new Error((data && data.error) || 'Could not add monster.');
            }
            feedback('Added to your bestiary.');
            if (pop) {
                var addBtn = pop.querySelector('#battle-monster-inspect-journal');
                var openBtn = pop.querySelector('#battle-monster-inspect-open');
                if (addBtn) addBtn.hidden = true;
                if (openBtn) openBtn.hidden = false;
            }
            if (typeof window.refreshPlayerMonsterList === 'function') {
                window.refreshPlayerMonsterList();
            }
        } catch (err) {
            feedback(err.message, true);
        }
    }

    function openPlayerMonsterInspectPopout(combatant, tokenEl) {
        var stage = $('battle-stage');
        if (!stage || !combatant || !combatant.compendium_entry_id) return;
        closePlayerMonsterInspectPopout();
        closeAttackPopout();
        closeCastPopout();
        var pop = $('battle-monster-inspect-popout');
        if (!pop) {
            pop = document.createElement('div');
            pop.id = 'battle-monster-inspect-popout';
            pop.className = 'battle-attack-popout battle-monster-inspect-popout';
            stage.appendChild(pop);
        }
        var entryId = combatant.compendium_entry_id;
        var health = combatant.health_state || 'unknown';
        pop.innerHTML =
            '<h4>' + esc(combatant.name) + '</h4>' +
            '<p class="battle-monster-inspect-health">Observed condition: ' + esc(health) + '</p>' +
            '<p class="battle-monster-inspect-hint">Add this creature to your bestiary and record what you learn. GM stat blocks are never shown here.</p>' +
            '<div class="battle-monster-inspect-actions">' +
            '<button type="button" class="button" id="battle-monster-inspect-journal">Add to bestiary</button>' +
            '<button type="button" class="button" id="battle-monster-inspect-open" hidden>Open bestiary</button>' +
            '<button type="button" class="button" id="battle-monster-inspect-close">Close</button>' +
            '</div>';
        pop.hidden = false;
        pop.addEventListener('click', function (e) { e.stopPropagation(); });
        pop.querySelector('#battle-monster-inspect-close').addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            closePlayerMonsterInspectPopout();
        });
        pop.querySelector('#battle-monster-inspect-journal').addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            discoverMonsterFromEncounter(entryId, pop);
        });
        pop.querySelector('#battle-monster-inspect-open').addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            closePlayerMonsterInspectPopout();
            if (typeof window.openPlayerMonsterDetail === 'function') {
                window.openPlayerMonsterDetail(entryId, combatant.name);
            }
        });
        var sRect = stage.getBoundingClientRect();
        var tRect = tokenEl.getBoundingClientRect();
        var anchorX = tRect.left - sRect.left + TILE / 2;
        var anchorY = tRect.top - sRect.top + TILE / 2;
        positionPopoutWithinStage(pop, stage, anchorX, anchorY, { preferBelow: true });

        fetch(playerMonsterApiUrl('playerMonsterProfileUrl', entryId), {
            credentials: 'same-origin',
            headers: { Accept: 'application/json' }
        }).then(function (resp) {
            return resp.json().then(function (data) {
                return { ok: resp.ok, data: data };
            });
        }).then(function (result) {
            if (!result.ok || !result.data || !result.data.monster) return;
            var addBtn = pop.querySelector('#battle-monster-inspect-journal');
            var openBtn = pop.querySelector('#battle-monster-inspect-open');
            if (addBtn) addBtn.hidden = true;
            if (openBtn) openBtn.hidden = false;
        }).catch(function () {});
    }

    function openCastPopout(caster, target, targetEl) {
        var pop = $('battle-cast-popout');
        if (!pop || !caster || !target) return;
        hideRadialMenu();
        clearTargetingModes();

        var spells = castableSpells(caster.spells || []);
        var slots = caster.spell_slots || {};
        var html = '<h4>' + esc(caster.name) + ' &rarr; ' + esc(target.name) + '</h4>';
        if (Object.keys(slots).length) {
            html += '<p class="battle-spell-slots">Slots: ' + Object.keys(slots).map(function (lvl) {
                var bucket = slots[lvl] || {};
                return esc(lvl) + '=' + esc(String(bucket.remaining != null ? bucket.remaining : '?'));
            }).join(', ') + '</p>';
        }
        if (!spells.length) {
            html += '<p>No castable spells with automated resolution for this combatant.</p>';
        }
        spells.forEach(function (spell) {
            var lvl = spell.level == null ? 0 : spell.level;
            var bucket = spell.spell_bucket || (lvl === 0 ? 'cantrip' : 'prepared');
            var bucketLabel = bucket === 'cantrip' ? 'Cantrip' : (bucket === 'known' ? 'Known' : 'Prepared');
            var meta = spellManualMetadataLines(spell);
            html += '<div class="battle-attack-row battle-cast-row">' +
                '<div class="battle-cast-spell-head">' +
                '<span>' + esc(spell.name) + ' (' + esc(bucketLabel) + ', L' + esc(lvl) + ', ' + esc(spell.range_ft || 0) + ' ft)</span>' +
                '<span class="battle-cast-mode">' + esc(spellAutomationHint(spell)) + '</span>' +
                (meta.length ? ('<ul class="battle-cast-meta">' +
                    meta.map(function (line) { return '<li>' + line + '</li>'; }).join('') +
                    '</ul>') : '') +
                '</div>' +
                '<label>Slot <input type="number" class="battle-cast-level-input" min="' + esc(lvl) +
                '" max="9" value="' + esc(lvl) + '" data-spell-key="' + esc(spell.key) + '" style="width:3em"></label>' +
                '<button type="button" class="button battle-cast-roll-btn" data-spell-key="' +
                esc(spell.key) + '">' + esc(spellCastButtonLabel(spell)) + '</button></div>';
        });
        html += '<div class="battle-attack-results" id="battle-cast-results"></div>' +
            '<button type="button" class="button" id="battle-cast-close">Close</button>';
        pop.innerHTML = html;
        var stage = $('battle-stage');
        var sRect = stage.getBoundingClientRect();
        var tRect = targetEl.getBoundingClientRect();
        var anchorX = tRect.left - sRect.left + stage.scrollLeft + TILE / 2;
        var anchorY = tRect.top - sRect.top + stage.scrollTop + TILE / 2;
        positionPopoutWithinStage(pop, stage, anchorX, anchorY, { preferBelow: true });

        pop.querySelector('#battle-cast-close').addEventListener('click', exitMode);
        pop.querySelectorAll('.battle-cast-roll-btn').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                var key = btn.dataset.spellKey;
                var levelInput = pop.querySelector('.battle-cast-level-input[data-spell-key="' + key + '"]');
                var castLevel = levelInput ? parseInt(levelInput.value, 10) : null;
                var out = await mutate('/encounters/' + state.encounterId + '/action', {
                    type: 'cast_spell',
                    combatant_id: caster.id,
                    target_id: target.id,
                    spell_key: key,
                    cast_level: castLevel
                });
                if (out) showCastResults(out.result);
            });
        });
    }

    function showCastResults(result) {
        var box = $('battle-cast-results');
        if (!box) return;
        var html = '';
        if (result.concentration && result.concentration.spell_name) {
            html += '<div>Concentration: ' + esc(result.concentration.spell_name) + '</div>';
        }
        if (result.concentration && result.concentration.gm_manual_remainder) {
            html += '<div>Remaining table effects are GM-resolved.</div>';
        }
        if (result.to_hit) {
            html += '<div>To hit: ' + esc(result.to_hit.total) +
                (result.hit ? ' — HIT' : ' — miss') + '</div>';
        }
        if (result.save) {
            html += '<div>Save: ' + esc(result.save.total) +
                (result.save.success ? ' — saved' : ' — failed') + '</div>';
        }
        if (result.damage_roll) {
            html += '<div>Damage: ' + esc(result.damage_roll.total) + '</div>';
            if (result.damage_roll.damage_modifiers && result.damage_roll.damage_modifiers.applied &&
                result.damage_roll.damage_modifiers.applied.length) {
                html += '<div>Modifiers: ' + esc(result.damage_roll.damage_modifiers.applied.join(', ')) + '</div>';
            }
        }
        if (result.area_targets && result.area_targets.length) {
            html += '<div class="battle-area-results"><strong>Area targets</strong><ul>';
            result.area_targets.forEach(function (row) {
                html += '<li>' + esc(row.target_name || row.target_id) + ': ';
                if (row.save) {
                    html += 'save ' + esc(row.save.total) + (row.save.success ? ' (saved)' : ' (failed)') + '; ';
                }
                if (row.damage_roll) {
                    html += 'damage ' + esc(row.damage_roll.total);
                    if (row.damage_roll.damage_modifiers && row.damage_roll.damage_modifiers.applied &&
                        row.damage_roll.damage_modifiers.applied.length) {
                        html += ' [' + esc(row.damage_roll.damage_modifiers.applied.join(', ')) + ']';
                    }
                }
                html += '</li>';
            });
            html += '</ul></div>';
        }
        if (result.healing_roll) {
            html += '<div>Healing: ' + esc(result.healing_roll.total) + '</div>';
        }
        box.innerHTML = html || '<div>Spell resolved.</div>';
    }

    function openAttackPopout(attacker, target, targetEl) {
        var pop = $('battle-attack-popout');
        if (!pop || !attacker || !target) return;
        hideRadialMenu();
        clearTargetingModes();

        var attacks = attacker.attacks || [];
        var multiattacks = attacker.multiattacks || [];
        var html = '<h4>' + esc(attacker.name) + ' &rarr; ' + esc(target.name) + '</h4>';

        if (multiattacks.length) {
            html += '<div class="battle-multiattack-block">';
            multiattacks.forEach(function (ma) {
                var swingCount = ma.swing_count || (ma.attack_keys || []).length;
                var label = esc(ma.name || 'Multiattack');
                if (swingCount > 1) {
                    label += ' (' + esc(String(swingCount)) + ' attacks)';
                }
                if (ma.uses_primary_attack) {
                    html += '<p class="battle-multiattack-hint">Choose a weapon below, then roll Attack.</p>';
                }
                html += '<div class="battle-attack-row battle-multiattack-row">' +
                    '<span>' + label + '</span>';
                if (ma.uses_primary_attack) {
                    html += '<span class="battle-multiattack-note">Uses selected weapon</span>';
                }
                html += '<button type="button" class="button battle-multiattack-roll-btn" ' +
                    'data-multiattack-key="' + esc(ma.key) + '"' +
                    (ma.uses_primary_attack ? ' data-uses-primary="1"' : '') +
                    '>Roll</button></div>';
            });
            html += '</div>';
        }

        if (attacker.action_surge && attacker.action_surge_additional_actions > 0) {
            html += '<p class="battle-class-ability-hint">Action Surge: take ' +
                esc(String(attacker.action_surge_additional_actions)) +
                ' additional action' + (attacker.action_surge_additional_actions === 1 ? '' : 's') +
                ' this turn (track uses in class resources).</p>';
        }

        if (!attacks.length && !multiattacks.length) {
            html += '<p>No attacks available.</p>';
        }
        attacks.forEach(function (atk, atkIndex) {
            var isPrimaryChoice = multiattacks.some(function (ma) { return ma.uses_primary_attack; });
            html += '<div class="battle-attack-row' +
                (isPrimaryChoice ? ' battle-primary-weapon-row' : '') + '">' +
                '<span>' + esc(atk.name) + ' (+' + esc(atk.attack_mod) + ', ' +
                esc(atk.damage) + ', ' + esc(atk.range_ft) + ' ft)</span>';
            if (!multiattacks.length) {
                html += '<button type="button" class="button battle-attack-roll-btn" data-attack-key="' +
                    esc(atk.key) + '">Roll</button>';
            } else if (isPrimaryChoice) {
                html += '<label class="battle-primary-weapon-choice">' +
                    '<input type="radio" name="battle-primary-weapon" class="battle-primary-weapon-radio" ' +
                    'value="' + esc(atk.key) + '"' +
                    (atkIndex === 0 ? ' checked' : '') + '> Use</label>';
            }
            html += '</div>';
        });

        // GM batch roll: other active GM-controlled foes join the same roll.
        var batchables = [];
        if (IS_GM && attacker.side === 'foe' && !attacker.player_id) {
            batchables = (state.data.combatants || []).filter(function (c) {
                return c.id !== attacker.id && c.side === 'foe' && !c.player_id &&
                    c.status === 'active';
            });
        }
        if (batchables.length) {
            html += '<div class="battle-batch-list"><span class="battle-batch-label">Also roll for:</span>';
            batchables.forEach(function (c) {
                html += '<label class="battle-batch-item"><input type="checkbox" ' +
                    'class="battle-batch-check" value="' + c.id + '"> ' + esc(c.name) + '</label>';
            });
            html += '</div>';
        }

        var legendary = attacker.legendary_actions || [];
        var currentId = state.data && state.data.current_combatant_id;
        var legendaryMode = IS_GM && legendary.length && currentId !== attacker.id;
        if (legendaryMode) {
            var pts = attacker.legendary_points_remaining;
            html += '<div class="battle-legendary-block"><span class="battle-batch-label">Legendary actions' +
                (pts != null ? ' (' + pts + ' left)' : '') + ':</span>';
            legendary.forEach(function (la) {
                html += '<div class="battle-attack-row battle-legendary-row">' +
                    '<span>' + esc(la.name) + ' (cost ' + esc(la.cost || 1) + ')</span>' +
                    '<button type="button" class="button battle-legendary-roll-btn" data-action-key="' +
                    esc(la.key) + '">Use</button></div>';
            });
            html += '</div>';
        }

        html += '<div class="battle-attack-results" id="battle-attack-results"></div>' +
            '<button type="button" class="button" id="battle-attack-close">Close</button>';
        pop.innerHTML = html;
        var stage = $('battle-stage');
        var sRect = stage.getBoundingClientRect();
        var tRect = targetEl.getBoundingClientRect();
        var anchorX = tRect.left - sRect.left + stage.scrollLeft + TILE / 2;
        var anchorY = tRect.top - sRect.top + stage.scrollTop + TILE / 2;
        positionPopoutWithinStage(pop, stage, anchorX, anchorY, { preferBelow: true });

        pop.querySelector('#battle-attack-close').addEventListener('click', exitMode);
        pop.querySelectorAll('.battle-attack-roll-btn').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                var key = btn.dataset.attackKey;
                var checked = Array.prototype.slice
                    .call(pop.querySelectorAll('.battle-batch-check:checked'))
                    .map(function (cb) { return parseInt(cb.value, 10); });
                var out;
                if (checked.length) {
                    out = await mutate('/encounters/' + state.encounterId + '/action', {
                        type: 'batch_attack',
                        attacker_ids: [attacker.id].concat(checked),
                        target_id: target.id,
                        attack_key: key
                    });
                } else {
                    out = await mutate('/encounters/' + state.encounterId + '/action', {
                        type: 'attack',
                        combatant_id: attacker.id,
                        target_id: target.id,
                        attack_key: key
                    });
                }
                if (out) showAttackResults(out.result);
            });
        });
        pop.querySelectorAll('.battle-multiattack-roll-btn').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                var payload = {
                    type: 'multiattack',
                    combatant_id: attacker.id,
                    target_id: target.id,
                    multiattack_key: btn.dataset.multiattackKey
                };
                if (btn.dataset.usesPrimary === '1') {
                    var selected = pop.querySelector('.battle-primary-weapon-radio:checked');
                    if (!selected) {
                        alert('Choose a weapon for Attack.');
                        return;
                    }
                    payload.primary_attack_key = selected.value;
                }
                var out = await mutate('/encounters/' + state.encounterId + '/action', payload);
                if (out) showAttackResults(out.result);
            });
        });
        pop.querySelectorAll('.battle-legendary-roll-btn').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                var out = await mutate('/encounters/' + state.encounterId + '/action', {
                    type: 'legendary_action',
                    actor_id: attacker.id,
                    target_id: target.id,
                    action_key: btn.dataset.actionKey
                });
                if (out) showAttackResults(out.result);
            });
        });
    }

    function showAttackResults(result) {
        var box = $('battle-attack-results');
        if (!box) return;
        var rows = [];
        if (result && result.results && result.multiattack) {
            rows = result.results;
        } else {
            rows = Array.isArray(result) ? result : [result];
        }
        box.innerHTML = rows.map(function (r) {
            if (r.skipped) return '<div>' + esc(r.skipped) + '</div>';
            var who = combatantById(r.attacker_id || r.reactor_id);
            if (!r.to_hit) return '<div>' + esc(JSON.stringify(r)) + '</div>';
            var attackLabel = r.attack && r.attack.name ? r.attack.name + ': ' : '';
            var line = attackLabel + (who ? who.name : 'Attacker') + ': d20 &rarr; ' +
                r.to_hit.natural + ' (total ' + r.to_hit.total + ') - ' +
                (r.crit ? 'CRIT!' : (r.hit ? 'HIT' : 'MISS'));
            if (r.hit && r.damage_roll) {
                line += ', ' + r.damage_roll.total + ' damage';
                if (r.damage_roll.damage_modifiers && r.damage_roll.damage_modifiers.applied &&
                        r.damage_roll.damage_modifiers.applied.length) {
                    line += ' (' + r.damage_roll.damage_modifiers.applied.join(', ') + ')';
                }
            }
            if (r.ac_detail && r.ac_detail.cover_bonus) {
                line += ' [cover +' + r.ac_detail.cover_bonus + ']';
            }
            return '<div>' + esc(line) + '</div>';
        }).join('');
    }

    /* ------------------------------------------------------------------
     * Settings popout
     * ------------------------------------------------------------------ */
    var SETTING_LABELS = {
        diagonal_mode: 'Diagonal movement',
        initiative_tie_mode: 'Initiative ties',
        opportunity_attacks: 'Opportunity attacks',
        flanking: 'Flanking',
        cover: 'Cover',
        death_saves: 'Death saves',
        concentration_checks: 'Concentration damage checks',
        conditions_enabled: 'Track conditions',
        auto_apply_damage: 'Auto-apply damage',
        track_action_economy: 'Track action economy',
        track_spell_slots: 'Track spell slots',
        direct_numeric_auto_resolution: 'Auto-resolve direct numeric spells',
        manual_spell_slot_consumption: 'Consume slots on manual leveled casts',
        concentration_tracking: 'Track concentration',
        concentration_auto_replace: 'Auto-replace concentration on new cast',
        concentration_cleanup_tracked_effects: 'Clean up tracked concentration effects',
        player_concentration_end: 'Allow players to end concentration',
        concentration_check_mode: 'Concentration check handling',
        crit_mode: 'Critical hits'
    };
    var SETTING_ENUMS = {
        diagonal_mode: ['five_ten_five', 'always_five', 'euclidean'],
        initiative_tie_mode: ['dex_then_random', 'stable'],
        crit_mode: ['double_dice'],
        concentration_check_mode: ['server_roll', 'gm_entered', 'server_and_gm']
    };

    function renderSettings() {
        var body = $('battle-settings-body');
        if (!body || !state.settings) return;
        body.innerHTML = '';
        Object.keys(SETTING_LABELS).forEach(function (key) {
            var row = document.createElement('label');
            row.className = 'battle-setting-row';
            var label = document.createElement('span');
            label.textContent = SETTING_LABELS[key];
            if (SETTING_ENUMS[key]) {
                var sel = document.createElement('select');
                sel.dataset.settingKey = key;
                SETTING_ENUMS[key].forEach(function (v) {
                    var opt = document.createElement('option');
                    opt.value = v;
                    opt.textContent = v.replace(/_/g, ' ');
                    sel.appendChild(opt);
                });
                sel.value = state.settings[key];
                row.appendChild(label);
                row.appendChild(sel);
            } else {
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.dataset.settingKey = key;
                cb.checked = !!state.settings[key];
                row.appendChild(cb);
                row.appendChild(label);
            }
            body.appendChild(row);
        });
        if (IS_GM && state.data) {
            var visibilityRow = document.createElement('label');
            visibilityRow.className = 'battle-setting-row battle-player-visible-setting';
            var visibilityInput = document.createElement('input');
            visibilityInput.type = 'checkbox';
            visibilityInput.dataset.playerVisibility = 'true';
            visibilityInput.checked = !!state.data.visible_to_players;
            var visibilityLabel = document.createElement('span');
            visibilityLabel.textContent = 'Show to players';
            visibilityRow.appendChild(visibilityInput);
            visibilityRow.appendChild(visibilityLabel);
            body.appendChild(visibilityRow);
        }
    }

    async function saveSettings() {
        var body = $('battle-settings-body');
        if (!body) return;
        var settings = {};
        body.querySelectorAll('[data-setting-key]').forEach(function (el) {
            settings[el.dataset.settingKey] =
                el.type === 'checkbox' ? el.checked : el.value;
        });
        var visibilityInput = body.querySelector('[data-player-visibility]');
        var shouldUpdateVisibility = !!(visibilityInput && state.data);
        var nextVisibility = visibilityInput ? visibilityInput.checked : false;
        try {
            var out = await api('/settings', 'POST', { settings: settings });
            state.settings = out.settings;
            if (shouldUpdateVisibility && nextVisibility !== !!state.data.visible_to_players) {
                await setEncounterPlayerVisibility(state.data.id, nextVisibility);
            }
            feedback('Battle settings saved.');
            $('battle-settings-popout').hidden = true;
        } catch (err) {
            feedback(err.message, true);
        }
    }

    /* ------------------------------------------------------------------
     * Monsters compendium
     * ------------------------------------------------------------------ */
    /* ------------------------------------------------------------------
     * Monsters compendium
     * ------------------------------------------------------------------ */
    var DAMAGE_TYPES = [
        'bludgeoning', 'piercing', 'slashing', 'fire', 'cold',
        'lightning', 'acid', 'poison', 'psychic', 'necrotic', 'radiant', 'force'
    ];

    function buildAttackEditRow(attack, index) {
        attack = attack || {};
        var row = document.createElement('div');
        row.className = 'battle-monster-edit-attack-row';
        row.dataset.attackIndex = String(index);
        var kindOpts = ['melee', 'ranged'].map(function (k) {
            return '<option value="' + k + '"' +
                (attack.kind === k ? ' selected' : '') + '>' + k + '</option>';
        }).join('');
        var dmgOpts = DAMAGE_TYPES.map(function (dt) {
            return '<option value="' + dt + '"' +
                ((attack.damage_type || 'bludgeoning') === dt ? ' selected' : '') +
                '>' + dt + '</option>';
        }).join('');
        row.innerHTML =
            '<label>Name<input type="text" class="battle-edit-attack-name" value="' +
                esc(attack.name || ('Attack ' + (index + 1))) + '"></label>' +
            '<label>Mod<input type="number" class="battle-edit-attack-mod" min="-10" max="30" value="' +
                esc(attack.attack_mod == null ? 0 : attack.attack_mod) + '"></label>' +
            '<label>Damage<input type="text" class="battle-edit-attack-damage" value="' +
                esc(attack.damage || '1d6') + '"></label>' +
            '<label>Range (ft)<input type="number" class="battle-edit-attack-range" min="5" max="600" value="' +
                esc(attack.range_ft == null ? 5 : attack.range_ft) + '"></label>' +
            '<label>Kind<select class="battle-edit-attack-kind">' + kindOpts + '</select></label>' +
            '<label>Type<select class="battle-edit-attack-dtype">' + dmgOpts + '</select></label>' +
            '<button type="button" class="button battle-edit-attack-remove">Remove</button>';
        row.querySelector('.battle-edit-attack-remove').addEventListener('click', function () {
            row.remove();
        });
        return row;
    }

    function renderAttackEditRows(attacks) {
        var host = $('battle-monster-edit-attacks');
        if (!host) return;
        host.innerHTML = '';
        (attacks && attacks.length ? attacks : [{}]).forEach(function (atk, i) {
            host.appendChild(buildAttackEditRow(atk, i));
        });
    }

    function collectAttackEditRows() {
        var host = $('battle-monster-edit-attacks');
        if (!host) return [];
        return Array.prototype.map.call(
            host.querySelectorAll('.battle-monster-edit-attack-row'),
            function (row, index) {
                return {
                    key: 'attack_' + index,
                    name: row.querySelector('.battle-edit-attack-name').value.trim(),
                    attack_mod: parseInt(row.querySelector('.battle-edit-attack-mod').value, 10) || 0,
                    damage: row.querySelector('.battle-edit-attack-damage').value.trim() || '1d6',
                    range_ft: parseInt(row.querySelector('.battle-edit-attack-range').value, 10) || 5,
                    kind: row.querySelector('.battle-edit-attack-kind').value,
                    damage_type: row.querySelector('.battle-edit-attack-dtype').value
                };
            }
        );
    }

    function buildLegendaryEditRow(action, index) {
        action = action || {};
        var row = document.createElement('div');
        row.className = 'battle-monster-edit-legendary-row';
        row.dataset.legendaryIndex = String(index);
        var dmgOpts = DAMAGE_TYPES.map(function (dt) {
            return '<option value="' + dt + '"' +
                ((action.damage_type || '') === dt ? ' selected' : '') +
                '>' + dt + '</option>';
        }).join('');
        row.innerHTML =
            '<label>Name<input type="text" class="battle-edit-legendary-name" value="' +
                esc(action.name || ('Legendary action ' + (index + 1))) + '"></label>' +
            '<label>Cost<input type="number" class="battle-edit-legendary-cost" min="1" max="3" value="' +
                esc(action.cost == null ? 1 : action.cost) + '"></label>' +
            '<label>Mod<input type="number" class="battle-edit-legendary-mod" min="-10" max="30" value="' +
                esc(action.attack_mod == null ? '' : action.attack_mod) + '"></label>' +
            '<label>Description<input type="text" class="battle-edit-legendary-desc" maxlength="500" value="' +
                esc(action.description || '') + '"></label>' +
            '<label>Damage<input type="text" class="battle-edit-legendary-damage" value="' +
                esc(action.damage || '') + '"></label>' +
            '<label>Range (ft)<input type="number" class="battle-edit-legendary-range" min="5" max="600" value="' +
                esc(action.range_ft == null ? '' : action.range_ft) + '"></label>' +
            '<label>Type<select class="battle-edit-legendary-dtype"><option value=""></option>' +
                dmgOpts + '</select></label>' +
            '<button type="button" class="button battle-edit-legendary-remove">Remove</button>';
        row.querySelector('.battle-edit-legendary-remove').addEventListener('click', function () {
            row.remove();
        });
        return row;
    }

    function renderLegendaryEditRows(actions) {
        var host = $('battle-monster-edit-legendary-actions');
        if (!host) return;
        host.innerHTML = '';
        (actions || []).forEach(function (action, i) {
            host.appendChild(buildLegendaryEditRow(action, i));
        });
    }

    function nullableIntFromInput(value) {
        value = String(value == null ? '' : value).trim();
        return value === '' ? null : parseInt(value, 10);
    }

    function collectLegendaryEditRows() {
        var host = $('battle-monster-edit-legendary-actions');
        if (!host) return [];
        return Array.prototype.map.call(
            host.querySelectorAll('.battle-monster-edit-legendary-row'),
            function (row, index) {
                return {
                    key: 'legendary_' + index,
                    name: row.querySelector('.battle-edit-legendary-name').value.trim(),
                    cost: parseInt(row.querySelector('.battle-edit-legendary-cost').value, 10) || 1,
                    description: row.querySelector('.battle-edit-legendary-desc').value.trim(),
                    attack_mod: nullableIntFromInput(row.querySelector('.battle-edit-legendary-mod').value),
                    damage: row.querySelector('.battle-edit-legendary-damage').value.trim(),
                    range_ft: nullableIntFromInput(row.querySelector('.battle-edit-legendary-range').value),
                    damage_type: row.querySelector('.battle-edit-legendary-dtype').value
                };
            }
        );
    }

    function openMonsterEditor(monster) {
        var pop = $('battle-monster-edit-popout');
        if (!pop || !monster) return;
        var stats = monster.stats || {};
        var abilities = stats.abilities || {};
        $('battle-monster-edit-id').value = monster.id;
        $('battle-monster-edit-name').value = monster.name || '';
        $('battle-monster-edit-cr').value = monster.challenge_rating == null ? '' : monster.challenge_rating;
        var knownEl = $('battle-monster-edit-known');
        if (knownEl) knownEl.checked = !!monster.known_to_players;
        $('battle-monster-edit-hp').value = stats.hp_max == null ? 10 : stats.hp_max;
        $('battle-monster-edit-ac').value = stats.ac == null ? 10 : stats.ac;
        $('battle-monster-edit-speed').value = stats.speed_ft == null ? 30 : stats.speed_ft;
        ['str', 'dex', 'con', 'int', 'wis', 'cha'].forEach(function (ab) {
            var el = $('battle-monster-edit-' + ab);
            if (el) el.value = abilities[ab] == null ? 10 : abilities[ab];
        });
        renderAttackEditRows(stats.attacks || []);
        renderLegendaryEditRows(stats.legendary_actions || []);

        function revealMonsterEditor() {
            if (window.gmCompendiumDetail) {
                window.gmCompendiumDetail.open('monsters-pane-content', 'Edit ' + (monster.name || 'monster'));
            } else {
                pop.hidden = false;
                pop.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        }

        var pickers = window.gmTraitPickers;
        if (pickers) {
            pickers.initMonsterDefensePickers();
            pickers.loadCombatEffectsIntoForm(
                pickers.combatEffectsFormConfig('battle-monster-edit-', { includeFlags: false }),
                pickers.monsterEffectsFromStats(stats)
            );
            pickers.refreshAttachedTraitPicker(
                'battle-monster-edit-trait-keys-picker',
                stats.trait_keys || []
            ).then(revealMonsterEditor);
            return;
        }
        revealMonsterEditor();
    }

    function closeMonsterEditor() {
        if (window.gmCompendiumDetail) {
            window.gmCompendiumDetail.close('monsters-pane-content');
            return;
        }
        var pop = $('battle-monster-edit-popout');
        if (pop) pop.hidden = true;
    }

    async function saveMonsterEditor(ev) {
        if (ev) ev.preventDefault();
        var entryId = parseInt($('battle-monster-edit-id').value, 10);
        if (isNaN(entryId)) return;
        var crRaw = $('battle-monster-edit-cr').value;
        var pickers = window.gmTraitPickers;
        var defenseEffects = pickers
            ? pickers.combatEffectsFromForm(
                pickers.combatEffectsFormConfig('battle-monster-edit-', { includeFlags: false })
            )
            : {};
        var payload = {
            name: $('battle-monster-edit-name').value.trim(),
            challenge_rating: crRaw === '' ? null : parseFloat(crRaw),
            known_to_players: $('battle-monster-edit-known')
                ? $('battle-monster-edit-known').checked
                : false,
            stats: {
                hp_max: parseInt($('battle-monster-edit-hp').value, 10),
                ac: parseInt($('battle-monster-edit-ac').value, 10),
                speed_ft: parseInt($('battle-monster-edit-speed').value, 10),
                abilities: {
                    str: parseInt($('battle-monster-edit-str').value, 10),
                    dex: parseInt($('battle-monster-edit-dex').value, 10),
                    con: parseInt($('battle-monster-edit-con').value, 10),
                    int: parseInt($('battle-monster-edit-int').value, 10),
                    wis: parseInt($('battle-monster-edit-wis').value, 10),
                    cha: parseInt($('battle-monster-edit-cha').value, 10)
                },
                attacks: collectAttackEditRows(),
                legendary_actions: collectLegendaryEditRows(),
                damage_resistances: pickers
                    ? pickers.formatTagList(defenseEffects.damage_resistances)
                    : '',
                damage_immunities: pickers
                    ? pickers.formatTagList(defenseEffects.damage_immunities)
                    : '',
                damage_vulnerabilities: pickers
                    ? pickers.formatTagList(defenseEffects.damage_vulnerabilities)
                    : '',
                condition_immunities: pickers
                    ? pickers.formatTagList(defenseEffects.condition_immunities)
                    : '',
                saving_throws: pickers
                    ? pickers.formatMonsterSaveBonuses(defenseEffects.save_bonuses)
                    : '',
                senses: pickers
                    ? pickers.formatDarkvisionSenses(defenseEffects.darkvision_ft)
                    : '',
                trait_keys: pickers
                    ? pickers.readTraitSearchPicker('battle-monster-edit-trait-keys-picker')
                    : []
            }
        };
        try {
            await api('/monsters/' + entryId, 'POST', payload);
            closeMonsterEditor();
            await loadMonsters();
            feedback('Monster updated.');
        } catch (err) {
            feedback(err.message, true);
        }
    }

    function monsterCr(monster) {
        var cr = parseFloat(monster.challenge_rating);
        return isNaN(cr) ? 0 : cr;
    }

    function currentCrFilter() {
        var minEl = $('battle-monster-cr-min');
        var maxEl = $('battle-monster-cr-max');
        var min = minEl ? parseFloat(minEl.value) : 0;
        var max = maxEl ? parseFloat(maxEl.value) : 30;
        if (isNaN(min)) min = 0;
        if (isNaN(max)) max = 30;
        if (min > max) {
            var tmp = min;
            min = max;
            max = tmp;
        }
        return { min: min, max: max };
    }

    function renderMonsterPicker() {
        var select = $('battle-monster-select');
        if (!select) return;
        var minLabel = $('battle-monster-cr-min-label');
        var maxLabel = $('battle-monster-cr-max-label');
        var filter = currentCrFilter();
        if (minLabel) minLabel.textContent = String(filter.min);
        if (maxLabel) maxLabel.textContent = String(filter.max);
        var current = select.value;
        select.innerHTML = '';
        var filtered = (state.monsters || []).filter(function (monster) {
            var cr = monsterCr(monster);
            return cr >= filter.min && cr <= filter.max;
        });
        if (!filtered.length) {
            var empty = document.createElement('option');
            empty.value = '';
            empty.textContent = 'No monsters in CR range';
            select.appendChild(empty);
            select.disabled = true;
        } else {
            filtered.forEach(function (monster) {
                var opt = document.createElement('option');
                opt.value = monster.id;
                opt.textContent = monster.name + ' (CR ' +
                    (monster.challenge_rating == null ? '-' : monster.challenge_rating) + ')';
                select.appendChild(opt);
            });
            select.disabled = false;
            if (current && filtered.some(function (monster) {
                return String(monster.id) === String(current);
            })) {
                select.value = current;
            }
        }
        var addBtn = $('battle-add-monster-btn');
        if (addBtn) addBtn.disabled = select.disabled;
    }

    function selectedSidebarMonster() {
        var select = $('battle-monster-select');
        if (!select || !select.value) return null;
        return (state.monsters || []).find(function (monster) {
            return String(monster.id) === String(select.value);
        }) || null;
    }

    function isSrdMonster(monster) {
        return String(monster.source || '') === 'srd_5_1';
    }

    function isCustomMonster(monster) {
        return !isSrdMonster(monster);
    }

    function compendiumMonsters() {
        var rows = state.monsters || [];
        var filter = state.monsterSourceFilter || 'all';
        if (filter === 'srd_only') {
            return rows.filter(isSrdMonster);
        }
        if (filter === 'custom_only') {
            return rows.filter(isCustomMonster);
        }
        return rows;
    }

    function monsterSourceFilterLabel(filter) {
        if (filter === 'srd_only') return 'SRD';
        if (filter === 'custom_only') return 'custom';
        return '';
    }

    function updateMonsterSourceFilterButtons() {
        var filter = state.monsterSourceFilter || 'all';
        document.querySelectorAll('[data-monster-source-filter]').forEach(function (btn) {
            var active = btn.getAttribute('data-monster-source-filter') === filter;
            btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
    }

    function renderMonsters() {
        var tbody = $('battle-monsters-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        var monsters = compendiumMonsters();
        var countEl = $('battle-monsters-count');
        if (countEl) {
            var total = (state.monsters || []).length;
            var filter = state.monsterSourceFilter || 'all';
            if (!total) {
                countEl.textContent = '';
            } else if (filter === 'all') {
                countEl.textContent = total + ' monster' + (total === 1 ? '' : 's') + ' shown';
            } else {
                var label = monsterSourceFilterLabel(filter);
                countEl.textContent = monsters.length + ' ' + label + ' monster' +
                    (monsters.length === 1 ? '' : 's') + ' shown (' + total + ' total)';
            }
        }
        if (!monsters.length) {
            var filter = state.monsterSourceFilter || 'all';
            tbody.innerHTML = filter === 'srd_only'
                ? '<tr><td colspan="5">No SRD monsters match this filter.</td></tr>'
                : filter === 'custom_only'
                    ? '<tr><td colspan="5">No custom monsters yet. Generate or create one.</td></tr>'
                    : '<tr><td colspan="5">No monsters yet. Generate or create one.</td></tr>';
            return;
        }
        monsters.forEach(function (m) {
            var s = m.stats || {};
            var tr = document.createElement('tr');
            var legendaryCount = (s.legendary_actions || []).length;
            var legendaryText = legendaryCount
                ? '<br><span class="battle-monster-source">' + legendaryCount + ' legendary</span>'
                : '';
            tr.innerHTML = '<td><strong>' + esc(m.name) + '</strong> ' +
                '<span class="battle-monster-source">' + esc(m.source) + '</span></td>' +
                '<td>' + esc(m.challenge_rating == null ? '-' : m.challenge_rating) + '</td>' +
                '<td>' + esc(s.hp_max || '?') + ' HP / AC ' + esc(s.ac || '?') +
                legendaryText + '</td>' +
                '<td><input type="number" class="battle-monster-count" value="1" min="1" max="10"></td>' +
                '<td class="battle-monster-actions">' +
                '<button type="button" class="button battle-monster-add">Place on map</button> ' +
                '<button type="button" class="button battle-monster-edit">Edit</button> ' +
                '<button type="button" class="button battle-monster-delete">Delete</button></td>';
            tr.querySelector('.battle-monster-add').addEventListener('click', function () {
                var count = parseInt(tr.querySelector('.battle-monster-count').value, 10) || 1;
                startMonsterPlacement(m, count);
            });
            tr.querySelector('.battle-monster-edit').addEventListener('click', function () {
                openMonsterEditor(m);
            });
            tr.querySelector('.battle-monster-delete').addEventListener('click', async function () {
                try {
                    await api('/monsters/' + m.id + '/delete', 'POST');
                    await loadMonsters();
                } catch (err) { feedback(err.message, true); }
            });
            tbody.appendChild(tr);
        });
    }

    /* ------------------------------------------------------------------
     * Polling
     * ------------------------------------------------------------------ */
    function startPolling() {
        stopPolling();
        state.pollTimer = setInterval(async function () {
            if (!state.encounterId || state.busy || state.mode !== 'idle') return;
            try {
                var data = await api('/encounters/' + state.encounterId);
                var mapChanged = !state.data || !state.data.map || !data.map ||
                    Number(data.map.map_version) !== Number(state.data.map.map_version);
                if (!state.data || data.turn_version !== state.data.turn_version || mapChanged) {
                    state.data = data;
                    if (mapChanged) state.mapVersionLoaded = null;
                    renderAll();
                }
            } catch (e) { /* transient poll errors are non-fatal */ }
        }, 4000);
    }

    function stopPolling() {
        if (state.pollTimer) {
            clearInterval(state.pollTimer);
            state.pollTimer = null;
        }
    }

    /* ------------------------------------------------------------------
     * Wiring
     * ------------------------------------------------------------------ */
    function bindControls() {
        if (state.controlsBound) return;
        state.controlsBound = true;
        var stage = $('battle-stage');
        if (stage) {
            initBattleViewport();
            stage.addEventListener('mousemove', onStageMouseMove);
        }
        document.addEventListener('keydown', onStageKeyPan);
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') {
                var setupPopout = $('battle-setup-popout');
                if (setupPopout && !setupPopout.hidden) {
                    closeSetupPopout();
                    ev.preventDefault();
                    return;
                }
                if (IS_GM && $('battle-encounter-window') &&
                    !$('battle-encounter-window').hidden && !state.mode && !state.placement) {
                    closeEncounterWindow();
                    ev.preventDefault();
                    return;
                }
                exitMode();
            }
        });
        window.addEventListener('resize', function () {
            scheduleVirtualRender();
        });
        bindEncounterWindowChrome();
        bindSetupPopoutChrome();
        if (IS_GM) {
            bindFixedPanelDrag($('battle-rename-popout'), null, { edgeDrag: true });
            bindFixedPanelDrag($('battle-delete-popout'), null, { edgeDrag: true });
        }

        var createBtn = $('battle-create-btn');
        if (createBtn) {
            createBtn.addEventListener('click', function () {
                openSetupPopout('create');
            });
        }
        var setupEditBtn = $('battle-setup-edit-btn');
        if (setupEditBtn) {
            setupEditBtn.addEventListener('click', function () {
                if (!state.encounterId) return;
                openSetupPopout('edit');
            });
        }
        var setupCancel = $('battle-setup-cancel');
        if (setupCancel) setupCancel.addEventListener('click', closeSetupPopout);
        var setupSource = $('battle-setup-source');
        if (setupSource) setupSource.addEventListener('change', updateSetupSourceVisibility);
        var setupRegen = $('battle-setup-regenerate-btn');
        if (setupRegen) {
            setupRegen.addEventListener('click', async function () {
                if (!state.encounterId || !isSetupEditable()) return;
                try {
                    var preset = ($('battle-setup-preset') || {}).value;
                    await api('/encounters/' + state.encounterId + '/map/generate', 'POST', {
                        terrain_preset: preset
                    });
                    await loadEncounter(state.encounterId);
                    feedback('Map regenerated.');
                } catch (err) { feedback(err.message, true); }
            });
        }
        var setupUpload = $('battle-setup-upload-input');
        if (setupUpload) {
            setupUpload.addEventListener('change', async function () {
                if (!setupUpload.files || !setupUpload.files.length) return;
                if (setupUpload.files[0].size > 4 * 1024 * 1024) {
                    feedback('File exceeds 4 MB.', true);
                    setupUpload.value = '';
                    return;
                }
                if (state.setupMode === 'create') {
                    feedback('Create the encounter first, then upload a map.');
                    setupUpload.value = '';
                    return;
                }
                if (!state.encounterId || !isSetupEditable()) return;
                var fd = new FormData();
                fd.append('map_image', setupUpload.files[0]);
                try {
                    await apiMultipart('/encounters/' + state.encounterId + '/map/upload', fd);
                    await loadEncounter(state.encounterId);
                    feedback('Map uploaded.');
                } catch (err) { feedback(err.message, true); }
                setupUpload.value = '';
            });
        }
        var setupForm = $('battle-setup-form');
        if (setupForm) {
            setupForm.addEventListener('submit', async function (ev) {
                ev.preventDefault();
                var name = ($('battle-setup-name') || {}).value || 'Encounter';
                var gw = parseInt(($('battle-setup-width') || {}).value, 10) || 20;
                var gh = parseInt(($('battle-setup-height') || {}).value, 10) || 20;
                var preset = ($('battle-setup-preset') || {}).value || 'plains';
                try {
                    if (state.setupMode === 'create') {
                        var out = await api('/encounters', 'POST', {
                            name: name,
                            grid_width: gw,
                            grid_height: gh,
                            terrain_preset: preset
                        });
                        state.encounterId = out.encounter.id;
                        state.data = out.encounter;
                        await loadEncounters();
                        refreshMapEncounters();
                        renderAll();
                    } else if (isSetupEditable()) {
                        await api('/encounters/' + state.encounterId + '/grid', 'POST', {
                            grid_width: gw,
                            grid_height: gh
                        });
                        await api('/encounters/' + state.encounterId + '/map/generate', 'POST', {
                            terrain_preset: preset
                        });
                        await loadEncounter(state.encounterId);
                        feedback('Encounter setup updated.');
                    }
                    closeSetupPopout();
                    var menu = $('battle-encounter-menu');
                    if (menu) menu.open = false;
                } catch (err) { feedback(err.message, true); }
            });
        }
        var renameBtn = $('battle-rename-btn');
        if (renameBtn) {
            renameBtn.addEventListener('click', function () {
                if (!state.encounterId || !state.data) return;
                var popout = $('battle-rename-popout');
                var input = $('battle-rename-input');
                if (!popout || !input) return;
                input.value = state.data.name || '';
                popout.hidden = false;
                positionBattleRenamePopout(popout, renameBtn);
                input.focus();
                input.select();
            });
        }
        var renameCancel = $('battle-rename-cancel');
        if (renameCancel) {
            renameCancel.addEventListener('click', function () {
                var popout = $('battle-rename-popout');
                if (popout) popout.hidden = true;
            });
        }
        var renameForm = $('battle-rename-form');
        if (renameForm) {
            renameForm.addEventListener('submit', async function (ev) {
                ev.preventDefault();
                if (!state.encounterId || !state.data) return;
                var input = $('battle-rename-input');
                var name = input ? input.value : '';
                try {
                    var out = await api(
                        '/encounters/' + state.encounterId + '/rename',
                        'POST',
                        { name: name }
                    );
                    if (state.data) state.data.name = out.encounter.name;
                    await loadEncounters();
                    refreshMapEncounters();
                    renderAll();
                    var menu = $('battle-encounter-menu');
                    if (menu) menu.open = false;
                    var popout = $('battle-rename-popout');
                    if (popout) popout.hidden = true;
                    feedback('Encounter renamed.');
                } catch (err) { feedback(err.message, true); }
            });
        }
        var deleteCancel = $('battle-delete-cancel');
        if (deleteCancel) {
            deleteCancel.addEventListener('click', closeDeleteEncounterPopout);
        }
        var deleteConfirm = $('battle-delete-confirm');
        if (deleteConfirm) {
            deleteConfirm.addEventListener('click', async function () {
                var encounter = state.pendingDeleteEncounter;
                closeDeleteEncounterPopout();
                if (!encounter || !encounter.id) return;
                await deleteEncounter(encounter.id);
                var menu = $('battle-encounter-menu');
                if (menu) menu.open = false;
            });
        }
        var placeMapBtn = $('battle-place-map-btn');
        if (placeMapBtn) {
            placeMapBtn.addEventListener('click', function () {
                if (!state.data) return;
                var menu = $('battle-encounter-menu');
                if (menu) menu.open = false;
                if (window.gmMap && window.gmMap.placeEncounter) {
                    window.gmMap.placeEncounter({
                        id: state.data.id,
                        name: state.data.name,
                        map_canvas_id: state.data.map_canvas_id,
                        map_x: state.data.map_x,
                        map_y: state.data.map_y
                    });
                } else {
                    feedback('Map is not ready yet.', true);
                }
            });
        }
        var initBtn = $('battle-initiative-btn');
        if (initBtn) {
            initBtn.addEventListener('click', function () {
                if (state.encounterId) {
                    mutate('/encounters/' + state.encounterId + '/initiative');
                }
            });
        }
        var endTurnBtn = $('battle-end-turn-btn');
        if (endTurnBtn) {
            endTurnBtn.addEventListener('click', function () {
                if (state.encounterId) {
                    mutate('/encounters/' + state.encounterId + '/end-turn');
                }
            });
        }
        var endEncBtn = $('battle-end-encounter-btn');
        if (endEncBtn) {
            endEncBtn.addEventListener('click', function () {
                if (state.encounterId && window.confirm('End this encounter?')) {
                    mutate('/encounters/' + state.encounterId + '/end');
                }
            });
        }

        // Radial menu actions
        var radialMove = $('battle-radial-move');
        if (radialMove) {
            radialMove.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                state.mode = 'move';
                hideRadialMenu();
                $('battle-grid').classList.add('battle-mode-move');
                showArrow('var(--color-info, #2563eb)');
            });
        }
        var radialAttack = $('battle-radial-attack');
        if (radialAttack) {
            radialAttack.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                state.mode = 'attack';
                hideRadialMenu();
                $('battle-grid').classList.add('battle-mode-attack');
                showArrow('var(--color-danger, #dc2626)');
            });
        }
        var radialCast = $('battle-radial-cast');
        if (radialCast) {
            radialCast.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                state.mode = 'cast_spell';
                hideRadialMenu();
                $('battle-grid').classList.add('battle-mode-cast');
                showArrow('var(--color-accent, #7c3aed)');
            });
        }
        var radialWait = $('battle-radial-wait');
        if (radialWait) {
            radialWait.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                var actorId = state.actorId;
                exitMode();
                mutate('/encounters/' + state.encounterId + '/wait',
                    { combatant_id: actorId });
            });
        }
        var radialDisengage = $('battle-radial-disengage');
        if (radialDisengage) {
            radialDisengage.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                var actorId = state.actorId;
                exitMode();
                mutate('/encounters/' + state.encounterId + '/action',
                    { type: 'disengage', combatant_id: actorId });
            });
        }
        var radialDeath = $('battle-radial-death-save');
        if (radialDeath) {
            radialDeath.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                var actorId = state.actorId;
                exitMode();
                mutate('/encounters/' + state.encounterId + '/action',
                    { type: 'death_save', combatant_id: actorId });
            });
        }
        var radialClose = $('battle-radial-close');
        if (radialClose) {
            radialClose.addEventListener('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                exitMode();
            });
        }

        // Settings gear
        var gearBtn = $('battle-settings-btn');
        if (gearBtn) {
            gearBtn.addEventListener('click', function () {
                var pop = $('battle-settings-popout');
                pop.hidden = !pop.hidden;
                if (!pop.hidden) loadSettings();
            });
        }
        var settingsSave = $('battle-settings-save');
        if (settingsSave) settingsSave.addEventListener('click', saveSettings);
        var settingsClose = $('battle-settings-close');
        if (settingsClose) {
            settingsClose.addEventListener('click', function () {
                $('battle-settings-popout').hidden = true;
            });
        }

        // Add character / NPC to encounter (placement mode)
        var addCharBtn = $('battle-add-character-btn');
        if (addCharBtn) {
            addCharBtn.addEventListener('click', startCharacterPlacement);
        }
        var placeOwnBtn = $('battle-place-own-character-btn');
        if (placeOwnBtn) {
            placeOwnBtn.addEventListener('click', startOwnCharacterPlacement);
        }
        var addMonsterBtn = $('battle-add-monster-btn');
        if (addMonsterBtn) {
            addMonsterBtn.addEventListener('click', function () {
                var monster = selectedSidebarMonster();
                if (!monster) {
                    feedback('Choose a monster first.', true);
                    return;
                }
                var count = parseInt(($('battle-monster-place-count') || {}).value, 10) || 1;
                count = Math.max(1, Math.min(10, count));
                startMonsterPlacement(monster, count);
            });
        }
        ['battle-monster-cr-min', 'battle-monster-cr-max'].forEach(function (id) {
            var el = $(id);
            if (el) el.addEventListener('input', renderMonsterPicker);
        });

        var editForm = $('battle-monster-edit-form');
        if (editForm) {
            editForm.addEventListener('submit', saveMonsterEditor);
        }
        var editCancel = $('battle-monster-edit-cancel');
        if (editCancel) editCancel.addEventListener('click', closeMonsterEditor);
        var editAddAttack = $('battle-monster-edit-add-attack');
        if (editAddAttack) {
            editAddAttack.addEventListener('click', function () {
                var host = $('battle-monster-edit-attacks');
                if (!host) return;
                host.appendChild(buildAttackEditRow({}, host.children.length));
            });
        }
        var editAddLegendary = $('battle-monster-edit-add-legendary');
        if (editAddLegendary) {
            editAddLegendary.addEventListener('click', function () {
                var host = $('battle-monster-edit-legendary-actions');
                if (!host) return;
                host.appendChild(buildLegendaryEditRow({}, host.children.length));
            });
        }

        // Monster generate / create
        var genBtn = $('battle-generate-btn');
        if (genBtn) {
            genBtn.addEventListener('click', async function () {
                var seed = ($('battle-generate-seed') || {}).value || '';
                var cr = parseFloat(($('battle-generate-cr') || {}).value) || 1;
                try {
                    await api('/monsters/generate', 'POST', { seed: seed, challenge: cr });
                    await loadMonsters();
                    feedback('Monster generated.');
                } catch (err) { feedback(err.message, true); }
            });
        }
        var createMonsterBtn = $('battle-monster-create-btn');
        if (createMonsterBtn) {
            createMonsterBtn.addEventListener('click', async function () {
                var name = ($('battle-monster-name') || {}).value || '';
                var hp = parseInt(($('battle-monster-hp') || {}).value, 10) || 10;
                var ac = parseInt(($('battle-monster-ac') || {}).value, 10) || 10;
                var dmg = ($('battle-monster-damage') || {}).value || '1d6';
                var mod = parseInt(($('battle-monster-mod') || {}).value, 10) || 3;
                try {
                    await api('/monsters', 'POST', {
                        name: name,
                        stats: {
                            hp_max: hp, ac: ac, speed_ft: 30,
                            abilities: { str: 12, dex: 12, con: 12, int: 8, wis: 10, cha: 8 },
                            attacks: [{
                                key: 'melee', name: 'Strike', kind: 'melee',
                                attack_mod: mod, damage: dmg,
                                damage_type: 'bludgeoning', range_ft: 5
                            }]
                        }
                    });
                    await loadMonsters();
                    feedback('Monster saved.');
                } catch (err) { feedback(err.message, true); }
            });
        }

        document.querySelectorAll('[data-monster-source-filter]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var next = btn.getAttribute('data-monster-source-filter');
                if (!next || next === state.monsterSourceFilter) return;
                state.monsterSourceFilter = next;
                updateMonsterSourceFilterButtons();
                renderMonsters();
            });
        });
        updateMonsterSourceFilterButtons();
    }

    async function ensureLoaded() {
        if (!state.loadedOnce) {
            state.loadedOnce = true;
            bindControls();
            await loadEncounters();
            await loadMonsters();
            if (state.encounterId) await loadEncounter(state.encounterId);
            else renderAll();
        }
        startPolling();
    }

    async function ensureMonstersLoaded() {
        if (!state.monstersLoadedOnce) {
            state.monstersLoadedOnce = true;
            bindControls();
            await loadEncounters();
        }
        await loadMonsters();
    }

    async function openEncounter(encounterId) {
        if (!encounterId) return;
        bindControls();
        state.encounterId = encounterId;
        await loadEncounters();
        await loadEncounter(encounterId);
        activateBattleTab();
        startPolling();
    }

    async function syncMapEncounterButton(canvasId) {
        var btn = document.getElementById('map-encounter-btn');
        if (!btn || !IS_GM || !canvasId) return;
        try {
            var data = await api('/encounters/for-canvas/' + canvasId);
            btn.textContent = 'Add Encounter';
            btn.dataset.encounterId = data.encounter ? String(data.encounter.id) : '';
        } catch (err) {
            btn.textContent = 'Add Encounter';
            delete btn.dataset.encounterId;
        }
    }

    async function openEncounterForCanvas(canvasId) {
        if (!canvasId) return;
        try {
            var out = await api('/encounters/for-canvas/' + canvasId, 'POST', {});
            state.encounterId = out.encounter.id;
            await loadEncounters();
            await loadEncounter(out.encounter.id);
            activateBattleTab();
            renderToolbar();
            feedback(out.created ? 'Encounter created for this map.' : 'Opened encounter for this map.');
            startPolling();
            await syncMapEncounterButton(canvasId);
        } catch (err) {
            feedback(err.message, true);
        }
    }

    window.gmBattle = {
        ensureLoaded: ensureLoaded,
        ensureMonstersLoaded: ensureMonstersLoaded,
        openEncounter: openEncounter,
        openEncounterWindow: openEncounterWindow,
        closeEncounterWindow: closeEncounterWindow,
        stopPolling: stopPolling,
        syncMapEncounterButton: syncMapEncounterButton,
        openEncounterForCanvas: openEncounterForCanvas
    };

    // Player panel boots immediately (no tab gating).
    if (!IS_GM && cfg.autoStart) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', ensureLoaded);
        } else {
            ensureLoaded();
        }
    }
})();

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

    var state = {
        loadedOnce: false,
        monstersLoadedOnce: false,
        encounterId: cfg.initialEncounterId || null,
        encounters: [],
        data: null,          // last GET /encounters/<id> payload
        monsters: [],
        settings: null,
        mode: 'idle',        // idle | move | attack
        actorId: null,       // combatant acting via radial menu
        placement: null,     // { type, playerId|monsterId, count, label }
        pendingDeleteEncounter: null,
        pollTimer: null,
        busy: false,
        controlsBound: false
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
            state.data = await api('/encounters/' + id);
            state.encounterId = id;
            renderAll();
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
    function renderAll() {
        renderGrid();
        renderTracker();
        renderLog();
        renderToolbar();
        renderMonsterPicker();
    }

    function refreshMapEncounters() {
        if (window.gmMap && typeof window.gmMap.refreshEncounters === 'function') {
            window.gmMap.refreshEncounters();
        }
    }

    function positionBattleRenamePopout(popout, anchor) {
        if (!popout) return;
        var margin = 12;
        var rect = anchor && anchor.getBoundingClientRect
            ? anchor.getBoundingClientRect()
            : null;
        var popRect = popout.getBoundingClientRect();
        var width = popRect.width || 320;
        var height = popRect.height || 120;
        var viewportW = window.innerWidth || document.documentElement.clientWidth || 0;
        var viewportH = window.innerHeight || document.documentElement.clientHeight || 0;
        var left = rect
            ? rect.left + (rect.width / 2) - (width / 2)
            : (viewportW - width) / 2;
        var top = rect
            ? rect.bottom + margin
            : (viewportH - height) / 2;

        if (rect && top + height > viewportH - margin) {
            top = rect.top - height - margin;
        }
        if (!rect || top < margin) {
            top = Math.max(margin, (viewportH - height) / 2);
        }
        left = Math.min(Math.max(margin, left), Math.max(margin, viewportW - width - margin));

        popout.style.left = left + 'px';
        popout.style.top = top + 'px';
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

    var TILE = 34;

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

    /** Keep absolutely positioned popouts inside the scrollable battle stage. */
    function positionPopoutWithinStage(el, stage, anchorX, anchorY, opts) {
        opts = opts || {};
        var pad = opts.pad == null ? 6 : opts.pad;
        el.hidden = false;
        var w = el.offsetWidth;
        var h = el.offsetHeight;
        var viewL = stage.scrollLeft + pad;
        var viewT = stage.scrollTop + pad;
        var viewR = stage.scrollLeft + stage.clientWidth - w - pad;
        var viewB = stage.scrollTop + stage.clientHeight - h - pad;
        var left = anchorX - w / 2;
        var top = opts.preferBelow
            ? anchorY + TILE / 2 + 8
            : anchorY - h - 8;
        if (top < viewT && !opts.preferBelow) {
            top = anchorY + TILE / 2 + 8;
        }
        el.style.left = Math.max(viewL, Math.min(left, viewR)) + 'px';
        el.style.top = Math.max(viewT, Math.min(top, viewB)) + 'px';
    }

    function activateBattleTab() {
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
        var grid = $('battle-grid');
        if (!grid) return;
        grid.innerHTML = '';
        closeRadial();
        if (!state.data) {
            grid.innerHTML = '<p class="battle-empty">No encounter loaded.' +
                (IS_GM ? ' Create one to begin.' : '') + '</p>';
            return;
        }
        var w = state.data.grid_width, h = state.data.grid_height;
        var board = document.createElement('div');
        board.className = 'battle-board';
        board.style.gridTemplateColumns = 'repeat(' + w + ', ' + TILE + 'px)';
        board.style.gridTemplateRows = 'repeat(' + h + ', ' + TILE + 'px)';
        for (var y = 0; y < h; y++) {
            for (var x = 0; x < w; x++) {
                var tile = document.createElement('div');
                tile.className = 'battle-tile';
                if (isTileOccupied(x, y)) {
                    tile.classList.add('battle-tile-occupied');
                }
                tile.dataset.x = x;
                tile.dataset.y = y;
                tile.addEventListener('click', onTileClick);
                board.appendChild(tile);
            }
        }
        (state.data.combatants || []).forEach(function (c) {
            if (c.status === 'removed') return;
            var idx = c.y * w + c.x;
            var tile = board.children[idx];
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
                : (' - ' + c.health_state));
            token.textContent = (c.name || '?').charAt(0).toUpperCase();
            token.addEventListener('click', onTokenClick);
            tile.appendChild(token);
        });
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
            li.textContent = describeLog(entry);
            list.appendChild(li);
        });
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
                if (!p.hit) return who + ' missed ' + tn + '.';
                var dmg = p.damage_roll ? (' for ' + p.damage_roll.total + ' damage') : '';
                return who + (p.crit ? ' CRIT ' : ' hit ') + tn + dmg + '.';
            }
            case 'batch_attack': return who + ' led a group attack.';
            case 'wait': return who + ' waits (drops to bottom of round).';
            case 'turn_ended': return 'R' + (p.round || '?') + ': next turn.';
            case 'death_save': return who + ' rolled a death save.';
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
            grid.classList.remove('battle-mode-move', 'battle-mode-attack');
        }
    }

    function resetBattleUiAfterMutation() {
        var attackPop = $('battle-attack-popout');
        if (attackPop && !attackPop.hidden) {
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
        var anchorX = tRect.left - sRect.left + stage.scrollLeft + TILE / 2;
        var anchorY = tRect.top - sRect.top + stage.scrollTop + TILE / 2;
        positionPopoutWithinStage(menu, stage, anchorX, anchorY);

        var isDown = c.status === 'down';
        $('battle-radial-move').hidden = isDown;
        $('battle-radial-attack').hidden = isDown;
        $('battle-radial-wait').hidden = isDown;
        $('battle-radial-wait').disabled = !!c.has_waited;
        var deathBtn = $('battle-radial-death-save');
        if (deathBtn) deathBtn.hidden = !isDown;
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
        if (state.mode !== 'move' && state.mode !== 'attack') return;
        var actor = combatantById(state.actorId);
        var svg = $('battle-arrow'), stage = $('battle-stage');
        if (!actor || !svg || !stage) return;
        var rect = stage.getBoundingClientRect();
        var line = svg.querySelector('line');
        line.setAttribute('x1', actor.x * TILE + TILE / 2);
        line.setAttribute('y1', actor.y * TILE + TILE / 2);
        line.setAttribute('x2', ev.clientX - rect.left + stage.scrollLeft);
        line.setAttribute('y2', ev.clientY - rect.top + stage.scrollTop);
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

    function openAttackPopout(attacker, target, targetEl) {
        var pop = $('battle-attack-popout');
        if (!pop || !attacker || !target) return;
        hideRadialMenu();
        clearTargetingModes();

        var attacks = attacker.attacks || [];
        var html = '<h4>' + esc(attacker.name) + ' &rarr; ' + esc(target.name) + '</h4>';
        if (!attacks.length) {
            html += '<p>No attacks available.</p>';
        }
        attacks.forEach(function (atk, i) {
            html += '<div class="battle-attack-row">' +
                '<span>' + esc(atk.name) + ' (+' + esc(atk.attack_mod) + ', ' +
                esc(atk.damage) + ', ' + esc(atk.range_ft) + ' ft)</span>' +
                '<button type="button" class="button battle-attack-roll-btn" data-attack-key="' +
                esc(atk.key) + '">Roll</button></div>';
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
    }

    function showAttackResults(result) {
        var box = $('battle-attack-results');
        if (!box) return;
        var rows = Array.isArray(result) ? result : [result];
        box.innerHTML = rows.map(function (r) {
            if (r.skipped) return '<div>' + esc(r.skipped) + '</div>';
            var who = combatantById(r.attacker_id);
            var line = (who ? who.name : 'Attacker') + ': d20 &rarr; ' +
                r.to_hit.natural + ' (total ' + r.to_hit.total + ') - ' +
                (r.crit ? 'CRIT!' : (r.hit ? 'HIT' : 'MISS'));
            if (r.hit && r.damage_roll) {
                line += ', ' + r.damage_roll.total + ' damage';
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
        concentration_checks: 'Concentration checks',
        conditions_enabled: 'Track conditions',
        auto_apply_damage: 'Auto-apply damage',
        track_action_economy: 'Track action economy',
        track_spell_slots: 'Track spell slots',
        crit_mode: 'Critical hits'
    };
    var SETTING_ENUMS = {
        diagonal_mode: ['five_ten_five', 'always_five', 'euclidean'],
        initiative_tie_mode: ['dex_then_random', 'stable'],
        crit_mode: ['double_dice']
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
        $('battle-monster-edit-hp').value = stats.hp_max == null ? 10 : stats.hp_max;
        $('battle-monster-edit-ac').value = stats.ac == null ? 10 : stats.ac;
        $('battle-monster-edit-speed').value = stats.speed_ft == null ? 30 : stats.speed_ft;
        ['str', 'dex', 'con', 'int', 'wis', 'cha'].forEach(function (ab) {
            var el = $('battle-monster-edit-' + ab);
            if (el) el.value = abilities[ab] == null ? 10 : abilities[ab];
        });
        renderAttackEditRows(stats.attacks || []);
        renderLegendaryEditRows(stats.legendary_actions || []);
        pop.hidden = false;
        pop.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    function closeMonsterEditor() {
        var pop = $('battle-monster-edit-popout');
        if (pop) pop.hidden = true;
    }

    async function saveMonsterEditor(ev) {
        if (ev) ev.preventDefault();
        var entryId = parseInt($('battle-monster-edit-id').value, 10);
        if (isNaN(entryId)) return;
        var crRaw = $('battle-monster-edit-cr').value;
        var payload = {
            name: $('battle-monster-edit-name').value.trim(),
            challenge_rating: crRaw === '' ? null : parseFloat(crRaw),
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
                legendary_actions: collectLegendaryEditRows()
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

    function renderMonsters() {
        var tbody = $('battle-monsters-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        if (!state.monsters.length) {
            tbody.innerHTML = '<tr><td colspan="5">No monsters yet. Generate or create one.</td></tr>';
            return;
        }
        state.monsters.forEach(function (m) {
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
                if (!state.data || data.turn_version !== state.data.turn_version) {
                    state.data = data;
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
            stage.addEventListener('mousemove', onStageMouseMove);
        }
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') exitMode();
        });

        var createBtn = $('battle-create-btn');
        if (createBtn) {
            createBtn.addEventListener('click', async function () {
                var name = window.prompt('Encounter name?', 'Encounter');
                if (name === null) return;
                try {
                    var out = await api('/encounters', 'POST', { name: name });
                    state.encounterId = out.encounter.id;
                    state.data = out.encounter;
                    await loadEncounters();
                    refreshMapEncounters();
                    renderAll();
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
                    var mapBtn = $('map-tab-btn');
                    if (mapBtn) mapBtn.click();
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

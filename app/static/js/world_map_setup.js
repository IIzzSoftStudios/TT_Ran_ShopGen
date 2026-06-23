/**
 * World setup step 2 — world map builder (no city/shop/POI placement).
 */
(function () {
    'use strict';

    var MAP_UPLOAD_MAX_BYTES = 4 * 1024 * 1024;

    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    var csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
    var urlsEl = document.getElementById('world-map-urls');
    var urls = {};
    if (urlsEl) {
        try {
            urls = JSON.parse(urlsEl.textContent || '{}');
        } catch (err) {
            console.error('world_map_setup: invalid urls JSON', err);
        }
    }

    var state = {
        canvas: null,
        previewGeneration: null
    };

    var stage = document.getElementById('map-stage');
    var markerLayer = document.getElementById('map-marker-layer');
    var genBg = document.getElementById('map-gen-bg');
    var bgImage = document.getElementById('map-bg-image');
    var underlayImage = document.getElementById('map-underlay-image');
    var uploadInput = document.getElementById('map-upload-input');
    var appearancePanel = document.getElementById('map-appearance-panel');
    var stylePresetSelect = document.getElementById('map-style-preset');
    var ctrlHexWidth = document.getElementById('map-ctrl-hex-width');
    var ctrlHexHeight = document.getElementById('map-ctrl-hex-height');
    var ctrlHexSize = document.getElementById('map-ctrl-hex-size');
    var ctrlLandFreq = document.getElementById('map-ctrl-land-freq');
    var ctrlVegetation = document.getElementById('map-ctrl-vegetation');
    var ctrlGrassland = document.getElementById('map-ctrl-grassland');
    var ctrlHills = document.getElementById('map-ctrl-hills');
    var ctrlDesert = document.getElementById('map-ctrl-desert');
    var ctrlCluster = document.getElementById('map-ctrl-cluster');
    var ctrlLandForm = document.getElementById('map-ctrl-land-form');
    var ctrlLandmass = document.getElementById('map-ctrl-landmass');
    var ctrlWaterways = document.getElementById('map-ctrl-waterways');
    var ctrlRoughness = document.getElementById('map-ctrl-roughness');
    var ctrlCoast = document.getElementById('map-ctrl-coast');
    var ctrlIslands = document.getElementById('map-ctrl-islands');
    var ctrlWarmth = document.getElementById('map-ctrl-warmth');
    var seedDisplay = document.getElementById('map-seed-display');
    var seedLockInput = document.getElementById('map-seed-lock');
    var regenLayoutBtn = document.getElementById('map-regen-layout-btn');
    var regenDetailsBtn = document.getElementById('map-regen-details-btn');
    var applyAppearanceBtn = document.getElementById('map-apply-appearance-btn');
    var feedbackEl = document.getElementById('map-feedback');
    var studioPanel = document.getElementById('map-studio-panel');
    var studioBlocked = document.getElementById('map-studio-blocked');
    var studioToggleBtn = document.getElementById('map-studio-toggle-btn');
    var studioMapToggleBtn = document.getElementById('map-studio-map-toggle-btn');
    var studioMapSaveBtn = document.getElementById('map-studio-map-save-btn');
    var studioPaintTools = document.getElementById('map-studio-paint-tools');
    var studioEditModesEl = document.getElementById('map-studio-edit-modes');
    var studioBrushesEl = document.getElementById('map-studio-brushes');
    var studioStampsEl = document.getElementById('map-studio-stamps');
    var studioUndoBtn = document.getElementById('map-studio-undo-btn');
    var studioRedoBtn = document.getElementById('map-studio-redo-btn');
    var studioSaveBtn = document.getElementById('map-studio-save-btn');
    var studioDirtyEl = document.getElementById('map-studio-dirty');
    var studioBrushSize = document.getElementById('map-studio-brush-size');
    var studioGridShow = document.getElementById('map-studio-grid-show');
    var viewportLayer = document.getElementById('map-viewport-layer');
    var underlayInput = document.getElementById('map-underlay-input');
    var underlayClearBtn = document.getElementById('map-underlay-clear-btn');
    var convertEditableBtn = document.getElementById('map-convert-editable-btn');
    var studioOverlay = document.getElementById('map-studio-canvas');
    var continueForm = document.getElementById('world-map-continue-form');
    var previewTimer = null;
    var mapStudio = null;
    var mapViewport = null;
    var continueAfterSave = false;

    function canvasUrl(template, canvasId) {
        return String(template).replace('999999999', encodeURIComponent(canvasId));
    }

    function mapFeedback(msg, isError) {
        if (!feedbackEl) return;
        feedbackEl.textContent = msg || '';
        feedbackEl.classList.toggle('error', !!isError);
    }

    async function fetchJson(url) {
        var resp = await fetch(url, {
            credentials: 'same-origin',
            headers: { Accept: 'application/json' }
        });
        var j = await resp.json().catch(function () { return {}; });
        if (!resp.ok) throw new Error(j.error || 'Could not load map.');
        return j;
    }

    function syncAppearanceControlsFromCanvas() {
        var gen = (state.canvas && state.canvas.generation) || {};
        var profile = gen.profile || {};
        if (stylePresetSelect) {
            stylePresetSelect.value = gen.style_preset || gen.palette || 'parchment_atlas';
        }
        if (ctrlHexWidth) ctrlHexWidth.value = profile.hex_width != null ? profile.hex_width : 200;
        if (ctrlHexHeight) ctrlHexHeight.value = profile.hex_height != null ? profile.hex_height : 125;
        if (ctrlHexSize) ctrlHexSize.value = profile.hex_size != null ? profile.hex_size : 12;
        if (ctrlLandFreq) ctrlLandFreq.value = profile.land_frequency != null ? profile.land_frequency : 55;
        if (ctrlVegetation) ctrlVegetation.value = profile.vegetation_frequency != null ? profile.vegetation_frequency : 18;
        if (ctrlGrassland) ctrlGrassland.value = profile.grassland_frequency != null ? profile.grassland_frequency : 22;
        if (ctrlHills) ctrlHills.value = profile.hills_frequency != null ? profile.hills_frequency : 12;
        if (ctrlDesert) ctrlDesert.value = profile.desert_frequency != null ? profile.desert_frequency : 15;
        if (ctrlCluster) ctrlCluster.value = profile.cluster_percent != null ? profile.cluster_percent : 70;
        if (ctrlLandForm) ctrlLandForm.value = profile.land_form || 'large_continents';
        if (ctrlLandmass) ctrlLandmass.value = profile.landmass_scale != null ? profile.landmass_scale : 6;
        if (ctrlWaterways) ctrlWaterways.value = profile.waterways != null ? profile.waterways : 4;
        if (ctrlRoughness) ctrlRoughness.value = profile.terrain_roughness != null ? profile.terrain_roughness : 5;
        if (ctrlCoast) ctrlCoast.value = profile.coast_detail != null ? profile.coast_detail : 5;
        if (ctrlIslands) ctrlIslands.value = profile.island_count != null ? profile.island_count : 0;
        if (ctrlWarmth) ctrlWarmth.value = profile.biome_warmth != null ? profile.biome_warmth : 5;
        var layoutSeed = gen.layout_seed != null ? gen.layout_seed : gen.seed;
        if (seedDisplay) {
            seedDisplay.textContent = 'Layout seed: ' + (layoutSeed != null ? layoutSeed : '—');
        }
    }

    function buildAppearanceProfile() {
        return {
            hex_width: ctrlHexWidth ? Number(ctrlHexWidth.value) : 200,
            hex_height: ctrlHexHeight ? Number(ctrlHexHeight.value) : 125,
            hex_size: ctrlHexSize ? Number(ctrlHexSize.value) : 12,
            land_frequency: ctrlLandFreq ? Number(ctrlLandFreq.value) : 55,
            vegetation_frequency: ctrlVegetation ? Number(ctrlVegetation.value) : 18,
            grassland_frequency: ctrlGrassland ? Number(ctrlGrassland.value) : 22,
            hills_frequency: ctrlHills ? Number(ctrlHills.value) : 12,
            desert_frequency: ctrlDesert ? Number(ctrlDesert.value) : 15,
            cluster_percent: ctrlCluster ? Number(ctrlCluster.value) : 70,
            land_form: ctrlLandForm ? ctrlLandForm.value : 'large_continents',
            landmass_scale: ctrlLandmass ? Number(ctrlLandmass.value) : 6,
            waterways: ctrlWaterways ? Number(ctrlWaterways.value) : 4,
            terrain_roughness: ctrlRoughness ? Number(ctrlRoughness.value) : 5,
            coast_detail: ctrlCoast ? Number(ctrlCoast.value) : 5,
            island_count: ctrlIslands ? Number(ctrlIslands.value) : 0,
            biome_warmth: ctrlWarmth ? Number(ctrlWarmth.value) : 5
        };
    }

    function buildAppearancePayload(mode, options) {
        options = options || {};
        var gen = (state.canvas && state.canvas.generation) || {};
        var payload = {
            mode: mode || 'details',
            style_preset: stylePresetSelect ? stylePresetSelect.value : 'parchment_atlas',
            profile: buildAppearanceProfile(),
            seed_locked: !!(seedLockInput && seedLockInput.checked)
        };
        if (mode === 'layout') {
            if (options.preserveDetailSeed && gen.detail_seed != null) {
                payload.detail_seed = gen.detail_seed;
            }
        } else if (mode === 'details') {
            if (gen.layout_seed != null) payload.layout_seed = gen.layout_seed;
            else if (gen.seed != null) payload.layout_seed = gen.seed;
            if (options.preserveDetailSeed && gen.detail_seed != null) {
                payload.detail_seed = gen.detail_seed;
            }
        } else {
            if (gen.layout_seed != null) payload.layout_seed = gen.layout_seed;
            else if (gen.seed != null) payload.layout_seed = gen.seed;
            if (options.preserveDetailSeed && gen.detail_seed != null) {
                payload.detail_seed = gen.detail_seed;
            }
        }
        return payload;
    }

    function updateMapViewportHint() {
        var hint = document.getElementById('map-viewport-hint');
        var painting = mapStudio && mapStudio.isActive();
        if (!hint) return;
        if (painting) {
            hint.textContent = 'Painting active — Stop painting or Save map (top-left), or press Escape to exit';
        } else {
            hint.textContent = 'Drag to pan · Wheel to zoom · Right-click ends paint stroke · Right-drag pans';
        }
    }

    function syncStudioToggleUi(active) {
        var label = active ? 'Stop painting' : 'Paint hexes';
        var pressed = active ? 'true' : 'false';
        if (stage) {
            stage.classList.toggle('map-studio-painting', !!active);
        }
        if (studioToggleBtn) {
            studioToggleBtn.setAttribute('aria-pressed', pressed);
            studioToggleBtn.textContent = label;
        }
        if (studioMapToggleBtn) {
            studioMapToggleBtn.setAttribute('aria-pressed', pressed);
            studioMapToggleBtn.textContent = label;
        }
        if (studioPaintTools) {
            studioPaintTools.hidden = !active;
        }
        updateMapStudioMapNav();
        updateMapViewportHint();
    }

    function syncStudioMapNav() {
        var editable = !!(state.canvas && !state.canvas.has_image);
        var painting = mapStudio && mapStudio.isActive();
        var showStudio = editable || painting;
        if (studioMapToggleBtn) studioMapToggleBtn.hidden = !showStudio;
        if (studioMapSaveBtn) {
            studioMapSaveBtn.hidden = !showStudio;
            studioMapSaveBtn.disabled = !(mapStudio && mapStudio.isDirty());
        }
        if (studioSaveBtn) {
            studioSaveBtn.disabled = !(mapStudio && mapStudio.isDirty());
        }
    }

    function updateMapStudioMapNav() {
        syncStudioMapNav();
    }

    function toggleMapStudio() {
        if (!mapStudio) return;
        if (!state.canvas || state.canvas.has_image) {
            mapFeedback('Convert or remove the uploaded background to use map studio.', true);
            return;
        }
        if (mapStudio.isActive()) {
            mapStudio.exit();
            syncStudioToggleUi(false);
            requestAnimationFrame(function () {
                renderBackground();
            });
            mapFeedback('', false);
            return;
        }
        var gen = state.previewGeneration || (state.canvas && state.canvas.generation) || {};
        mapStudio.enter(gen, 'world');
        mapStudio.setEditMode('paint');
        if (studioEditModesEl) {
            studioEditModesEl.querySelectorAll('[data-edit-mode]').forEach(function (el) {
                el.setAttribute('aria-pressed', el.getAttribute('data-edit-mode') === 'paint' ? 'true' : 'false');
            });
        }
        syncStudioToggleUi(true);
        mapFeedback('Map studio active. Paint hexes on the map — click again to stop. Save when done.', false);
    }

    function updateStudioAvailability() {
        var hasImage = !!(state.canvas && state.canvas.has_image);
        if (studioBlocked) studioBlocked.hidden = !hasImage;
        if (studioPanel) studioPanel.hidden = hasImage;
        updateMapStudioMapNav();
        if (hasImage && mapStudio && mapStudio.isActive()) {
            mapStudio.exit();
            syncStudioToggleUi(false);
        }
    }

    function renderUnderlay() {
        if (!underlayImage || !state.canvas) return;
        if (state.canvas.has_underlay) {
            underlayImage.src = canvasUrl(urls.mapUnderlayImage, state.canvas.id) + '?v=' + Date.now();
            underlayImage.hidden = false;
        } else {
            underlayImage.hidden = true;
            underlayImage.removeAttribute('src');
        }
    }

    function buildRenderOptions(gen) {
        var renderOpts = (mapStudio && mapStudio.isActive() && mapStudio.getRenderOptions)
            ? mapStudio.getRenderOptions()
            : {};
        if (mapViewport && window.MapHex && gen && gen.hex_grid) {
            var ms = window.MapHex.mapWorldSize(gen.hex_grid);
            mapViewport.setWorldSize(ms.width, ms.height);
            if (!mapStudio || !mapStudio.isActive()) {
                var st = mapViewport.getState();
                st.stageEl = stage;
                renderOpts.viewportBounds = window.MapHex.viewportBoundsFromState(st);
            }
        }
        return renderOpts;
    }

    function renderBackground() {
        var canvas = state.canvas || {};
        renderUnderlay();
        updateStudioAvailability();
        if (canvas.has_image) {
            if (genBg) genBg.innerHTML = '';
            if (bgImage) {
                bgImage.src = canvasUrl(urls.mapImage, canvas.id) + '?v=' + Date.now();
                bgImage.hidden = false;
            }
            configureUploadedMapViewport(canvas);
            if (appearancePanel) appearancePanel.hidden = true;
            return;
        }
        if (bgImage) {
            bgImage.hidden = true;
            bgImage.removeAttribute('src');
        }
        if (appearancePanel) appearancePanel.hidden = false;
        var gen = (mapStudio && mapStudio.isActive())
            ? mapStudio.getWorkingGeneration()
            : (state.previewGeneration || canvas.generation || {});
        if (window.MapRenderer && genBg) {
            MapRenderer.render(gen, genBg, stage, buildRenderOptions(gen));
        }
    }

    function rebuildStudioToolButtons() {
        if (!mapStudio || !studioBrushesEl) return;
        studioBrushesEl.innerHTML = '';
        mapStudio.getBrushes().forEach(function (brush) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'button map-studio-tool map-world-nav-btn';
            btn.dataset.tool = brush.id;
            btn.textContent = brush.label;
            btn.setAttribute('aria-pressed', brush.id === 'prairie' ? 'true' : 'false');
            studioBrushesEl.appendChild(btn);
        });
    }

    function bindStudioToolClicks(container) {
        if (!container || !mapStudio) return;
        container.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-tool]');
            if (!btn) return;
            var toolId = btn.getAttribute('data-tool');
            mapStudio.setTool(toolId);
            container.querySelectorAll('[data-tool]').forEach(function (el) {
                el.setAttribute('aria-pressed', el === btn ? 'true' : 'false');
            });
            if (studioBrushesEl) {
                studioBrushesEl.querySelectorAll('[data-tool]').forEach(function (el) {
                    el.setAttribute('aria-pressed', 'false');
                });
            }
            if (studioStampsEl) {
                studioStampsEl.querySelectorAll('[data-tool]').forEach(function (el) {
                    el.setAttribute('aria-pressed', 'false');
                });
            }
            btn.setAttribute('aria-pressed', 'true');
        });
    }

    function scheduleFitToView() {
        if (!mapViewport) return;
        requestAnimationFrame(function () {
            var gen = (state.previewGeneration || (state.canvas && state.canvas.generation) || {});
            if (state.canvas && state.canvas.has_image) {
                mapViewport.setWorldSize(
                    Number(state.canvas.width) || 1024,
                    Number(state.canvas.height) || 1024
                );
            } else if (window.MapHex && gen.hex_grid) {
                var ms = window.MapHex.mapWorldSize(gen.hex_grid);
                mapViewport.setWorldSize(ms.width, ms.height);
            }
            mapViewport.fitToView();
        });
    }

    function configureUploadedMapViewport(canvas) {
        if (!mapViewport || !canvas || !canvas.has_image) return;
        mapViewport.setWorldSize(
            Number(canvas.width) || 1024,
            Number(canvas.height) || 1024
        );
        scheduleFitToView();
    }

    function applyPayload(payload) {
        state.canvas = payload.canvas;
        state.previewGeneration = null;
        syncAppearanceControlsFromCanvas();
        renderBackground();
        rebuildStudioToolButtons();
        scheduleFitToView();
    }

    async function postBackground(formData, jsonPayload) {
        var opts = {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrfToken }
        };
        if (jsonPayload) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(jsonPayload);
        } else {
            opts.body = formData;
        }
        var resp = await fetch(urls.mapWorldBackground, opts);
        var j = await resp.json().catch(function () { return {}; });
        if (resp.status === 409) {
            throw new Error(j.error || 'Map studio edits would be discarded.');
        }
        if (!resp.ok) throw new Error(j.error || 'Could not update background.');
        state.previewGeneration = null;
        state.canvas = j.canvas;
        syncAppearanceControlsFromCanvas();
        renderBackground();
        scheduleFitToView();
    }

    async function postBackgroundWithConfirm(formData, jsonPayload) {
        try {
            await postBackground(formData, jsonPayload);
        } catch (err) {
            var msg = err.message || '';
            if (msg.indexOf('confirm_discard_edits') >= 0 || msg.indexOf('discarded') >= 0) {
                if (!window.confirm('Unsaved map studio edits will be lost. Continue?')) {
                    mapFeedback('Cancelled.', false);
                    return;
                }
                var payload = jsonPayload ? Object.assign({}, jsonPayload) : {};
                payload.confirm_discard_edits = true;
                await postBackground(formData, payload);
                if (mapStudio) mapStudio.clearDirty();
                return;
            }
            throw err;
        }
    }

    async function applyAppearance(mode, options) {
        mapFeedback('Updating map appearance\u2026', false);
        try {
            await postBackgroundWithConfirm(null, buildAppearancePayload(mode, options || {}));
            mapFeedback('Map appearance saved.', false);
        } catch (err) {
            mapFeedback(err.message || 'Could not update appearance.', true);
        }
    }

    function scheduleAppearancePreview() {
        if (!state.canvas || state.canvas.has_image) return;
        if (previewTimer) clearTimeout(previewTimer);
        previewTimer = setTimeout(function () {
            previewTimer = null;
            requestAppearancePreview();
        }, 300);
    }

    async function requestAppearancePreview() {
        if (!state.canvas || state.canvas.has_image) return;
        try {
            var resp = await fetch(urls.mapWorldBackgroundPreview, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify(buildAppearancePayload('details', { preserveDetailSeed: true }))
            });
            var j = await resp.json().catch(function () { return {}; });
            if (!resp.ok) throw new Error(j.error || 'Preview failed.');
            state.previewGeneration = j.generation;
            renderBackground();
            scheduleFitToView();
        } catch (err) {
            console.warn('world map preview', err);
        }
    }

    async function saveStudioGeneration() {
        if (!mapStudio || !state.canvas) return;
        var generation = mapStudio.getWorkingGeneration();
        if (!generation) return;
        mapFeedback('Saving map\u2026', false);
        if (studioSaveBtn) studioSaveBtn.disabled = true;
        if (studioMapSaveBtn) studioMapSaveBtn.disabled = true;
        try {
            var resp = await fetch(urls.mapWorldGeneration, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ generation: generation })
            });
            var j = await resp.json().catch(function () { return {}; });
            if (!resp.ok) throw new Error(j.error || 'Could not save map.');
            state.canvas = j.canvas;
            state.previewGeneration = null;
            mapStudio.markSaved(state.canvas.generation || generation);
            syncAppearanceControlsFromCanvas();
            renderBackground();
            mapFeedback('Map saved.', false);
            if (continueAfterSave && continueForm) {
                continueAfterSave = false;
                continueForm.submit();
            }
        } catch (err) {
            continueAfterSave = false;
            mapFeedback(err.message || 'Could not save map.', true);
            throw err;
        } finally {
            syncStudioMapNav();
        }
    }

    async function loadWorldMap() {
        mapFeedback('Loading world map\u2026', false);
        try {
            applyPayload(await fetchJson(urls.mapWorld));
            mapFeedback('', false);
        } catch (err) {
            console.error(err);
            mapFeedback(err.message || 'Could not load map.', true);
        }
    }

    function initViewport() {
        if (!window.MapViewport || !stage || !viewportLayer) return;
        mapViewport = window.MapViewport.create(stage, viewportLayer, {
            paintActive: false,
            onViewportChange: function () {
                if (mapStudio && mapStudio.isActive() && mapStudio.scheduleViewportRender) {
                    mapStudio.scheduleViewportRender();
                }
            }
        });
    }

    function initMapStudio() {
        if (!window.MapStudio || !stage || !studioOverlay) return;
        mapStudio = window.MapStudio.create({
            stage: stage,
            overlay: studioOverlay,
            viewportLayer: viewportLayer,
            genBg: genBg,
            markerLayer: markerLayer,
            mapViewport: mapViewport,
            onDirtyChange: function (dirty) {
                if (studioDirtyEl) studioDirtyEl.hidden = !dirty;
                syncStudioMapNav();
            },
            onFeedback: mapFeedback,
            onExitBaked: function (gen) {
                state.previewGeneration = JSON.parse(JSON.stringify(gen));
                renderBackground();
            }
        });
        rebuildStudioToolButtons();
        bindStudioToolClicks(document.getElementById('map-world-nav'));
        if (studioEditModesEl && mapStudio) {
            studioEditModesEl.addEventListener('click', function (e) {
                var btn = e.target.closest('[data-edit-mode]');
                if (!btn || !mapStudio) return;
                var mode = btn.getAttribute('data-edit-mode');
                if (mode === 'paint' && mapStudio.isActive() && mapStudio.getEditMode() === 'paint') {
                    toggleMapStudio();
                    return;
                }
                if (mode === 'paint' && !mapStudio.isActive()) {
                    toggleMapStudio();
                    return;
                }
                mapStudio.setEditMode(mode);
                studioEditModesEl.querySelectorAll('[data-edit-mode]').forEach(function (el) {
                    el.setAttribute('aria-pressed', el === btn ? 'true' : 'false');
                });
            });
        }
    }

    function bindEvents() {
        if (regenLayoutBtn) {
            regenLayoutBtn.addEventListener('click', function () {
                if (seedLockInput && seedLockInput.checked) {
                    mapFeedback('Layout seed is locked. Unlock it to regenerate layout.', true);
                    return;
                }
                applyAppearance('layout', { preserveDetailSeed: true });
            });
        }
        if (regenDetailsBtn) {
            regenDetailsBtn.addEventListener('click', function () {
                applyAppearance('details');
            });
        }
        if (applyAppearanceBtn) {
            applyAppearanceBtn.addEventListener('click', function () {
                applyAppearance('details', { preserveDetailSeed: true });
            });
        }

        [stylePresetSelect, ctrlHexWidth, ctrlHexHeight, ctrlHexSize, ctrlLandFreq, ctrlVegetation, ctrlDesert, ctrlCluster, ctrlLandForm,
            ctrlLandmass, ctrlWaterways, ctrlRoughness, ctrlCoast, ctrlIslands, ctrlWarmth]
            .forEach(function (el) {
                if (!el) return;
                el.addEventListener('input', scheduleAppearancePreview);
                el.addEventListener('change', scheduleAppearancePreview);
            });

        if (uploadInput) {
            uploadInput.addEventListener('change', async function () {
                if (!uploadInput.files || !uploadInput.files.length) return;
                if (uploadInput.files[0].size > MAP_UPLOAD_MAX_BYTES) {
                    mapFeedback('Map image must be 4 MB or smaller.', true);
                    uploadInput.value = '';
                    return;
                }
                var fd = new FormData();
                fd.append('map_image', uploadInput.files[0]);
                mapFeedback('Uploading map\u2026', false);
                try {
                    await postBackgroundWithConfirm(fd);
                    mapFeedback('Map image uploaded.', false);
                } catch (err) {
                    mapFeedback(err.message || 'Upload failed.', true);
                } finally {
                    uploadInput.value = '';
                }
            });
        }

        if (studioBrushSize && mapStudio) {
            studioBrushSize.addEventListener('input', function () {
                mapStudio.setBrushSize(studioBrushSize.value);
            });
        }
        if (studioGridShow && mapStudio) {
            studioGridShow.addEventListener('change', function () {
                mapStudio.setShowGridLines(studioGridShow.checked);
            });
        }
        if (studioToggleBtn && mapStudio) {
            studioToggleBtn.addEventListener('click', toggleMapStudio);
        }
        if (studioMapToggleBtn && mapStudio) {
            studioMapToggleBtn.addEventListener('click', toggleMapStudio);
        }
        if (studioSaveBtn) {
            studioSaveBtn.addEventListener('click', function () {
                saveStudioGeneration();
            });
        }
        if (studioMapSaveBtn) {
            studioMapSaveBtn.addEventListener('click', function () {
                saveStudioGeneration();
            });
        }
        if (studioUndoBtn && mapStudio) {
            studioUndoBtn.addEventListener('click', function () { mapStudio.undo(); });
        }
        if (studioRedoBtn && mapStudio) {
            studioRedoBtn.addEventListener('click', function () { mapStudio.redo(); });
        }
        if (convertEditableBtn) {
            convertEditableBtn.addEventListener('click', async function () {
                mapFeedback('Converting map\u2026', false);
                try {
                    var resp = await fetch(urls.mapWorldConvertEditable, {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: { 'X-CSRFToken': csrfToken }
                    });
                    var j = await resp.json().catch(function () { return {}; });
                    if (!resp.ok) throw new Error(j.error || 'Could not convert map.');
                    state.canvas = j.canvas;
                    state.previewGeneration = null;
                    syncAppearanceControlsFromCanvas();
                    renderBackground();
                    rebuildStudioToolButtons();
                    mapFeedback('Map is now editable in Map studio.', false);
                } catch (err) {
                    mapFeedback(err.message || 'Could not convert map.', true);
                }
            });
        }
        if (underlayInput) {
            underlayInput.addEventListener('change', async function () {
                if (!underlayInput.files || !underlayInput.files.length) return;
                if (underlayInput.files[0].size > MAP_UPLOAD_MAX_BYTES) {
                    mapFeedback('Trace image must be 4 MB or smaller.', true);
                    underlayInput.value = '';
                    return;
                }
                var fd = new FormData();
                fd.append('map_image', underlayInput.files[0]);
                mapFeedback('Uploading trace underlay\u2026', false);
                try {
                    var resp = await fetch(urls.mapWorldUnderlay, {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: { 'X-CSRFToken': csrfToken },
                        body: fd
                    });
                    var j = await resp.json().catch(function () { return {}; });
                    if (!resp.ok) throw new Error(j.error || 'Could not upload underlay.');
                    state.canvas = j.canvas;
                    renderUnderlay();
                    mapFeedback('Trace underlay added.', false);
                } catch (err) {
                    mapFeedback(err.message || 'Could not upload underlay.', true);
                } finally {
                    underlayInput.value = '';
                }
            });
        }
        if (underlayClearBtn) {
            underlayClearBtn.addEventListener('click', async function () {
                try {
                    var resp = await fetch(urls.mapWorldUnderlay, {
                        method: 'DELETE',
                        credentials: 'same-origin',
                        headers: { 'X-CSRFToken': csrfToken }
                    });
                    var j = await resp.json().catch(function () { return {}; });
                    if (!resp.ok) throw new Error(j.error || 'Could not clear underlay.');
                    state.canvas = j.canvas;
                    renderUnderlay();
                    mapFeedback('Trace underlay removed.', false);
                } catch (err) {
                    mapFeedback(err.message || 'Could not clear underlay.', true);
                }
            });
        }

        document.addEventListener('keydown', function (e) {
            if (!mapStudio || !mapStudio.isActive()) return;
            if (e.ctrlKey && e.key === 'z') {
                e.preventDefault();
                mapStudio.undo();
            } else if (e.ctrlKey && (e.key === 'y' || (e.shiftKey && e.key === 'z'))) {
                e.preventDefault();
                mapStudio.redo();
            } else if (e.key === 'Escape') {
                mapStudio.exit();
                syncStudioToggleUi(false);
                renderBackground();
            }
        });

        if (continueForm) {
            continueForm.addEventListener('submit', function (e) {
                if (mapStudio && mapStudio.isDirty()) {
                    e.preventDefault();
                    continueAfterSave = true;
                    saveStudioGeneration().catch(function () {
                        continueAfterSave = false;
                    });
                }
            });
        }
    }

    initViewport();
    initMapStudio();
    bindEvents();
    loadWorldMap();
})();

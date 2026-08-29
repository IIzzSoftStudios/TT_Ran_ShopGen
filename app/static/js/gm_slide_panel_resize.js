/**
 * Drag handle on slide-out panels (GM + player dashboards).
 * Persists width per dashboard surface in localStorage.
 */
(function () {
    'use strict';

    var STORAGE_KEY_GM = 'ef_gm_slide_panel_width';
    var STORAGE_KEY_PLAYER = 'ef_player_slide_panel_width';
    var MIN_WIDTH = 320;

    function getRailWidth() {
        var raw = getComputedStyle(document.documentElement).getPropertyValue('--gm-rail-width');
        var parsed = parseInt(raw, 10);
        return isNaN(parsed) ? 0 : parsed;
    }

    function maxWidth() {
        return Math.max(MIN_WIDTH, window.innerWidth - getRailWidth() - 16);
    }

    function storageKey(panel) {
        return panel.classList.contains('player-tab-panel') ? STORAGE_KEY_PLAYER : STORAGE_KEY_GM;
    }

    function clampWidth(widthPx) {
        return Math.max(MIN_WIDTH, Math.min(maxWidth(), widthPx));
    }

    function applyWidth(panel, widthPx) {
        var width = clampWidth(widthPx);
        panel.style.width = width + 'px';
        panel.style.maxWidth = maxWidth() + 'px';
        panel.classList.add('gm-slide-panel--user-sized');
        return width;
    }

    function loadSavedWidth(panel) {
        try {
            var saved = localStorage.getItem(storageKey(panel));
            if (!saved) return;
            var width = parseInt(saved, 10);
            if (width > 0) applyWidth(panel, width);
        } catch (err) { /* ignore */ }
    }

    function saveWidth(panel, widthPx) {
        var width = Math.round(clampWidth(widthPx));
        var key = storageKey(panel);
        try {
            localStorage.setItem(key, String(width));
        } catch (err) { /* ignore */ }

        var selector = panel.classList.contains('player-tab-panel')
            ? '#player-slide-panels .gm-slide-panel'
            : '#gm-slide-panels .gm-slide-panel';
        document.querySelectorAll(selector).forEach(function (target) {
            applyWidth(target, width);
        });
    }

    function bindResize(panel, handle) {
        if (handle.dataset.resizeBound === '1') return;
        handle.dataset.resizeBound = '1';

        var drag = null;

        handle.addEventListener('pointerdown', function (ev) {
            if (ev.button !== 0) return;
            ev.preventDefault();
            ev.stopPropagation();
            drag = {
                pointerId: ev.pointerId,
                startX: ev.clientX,
                width: panel.getBoundingClientRect().width
            };
            handle.classList.add('is-dragging');
            document.body.classList.add('gm-slide-panel-resizing');
            try {
                handle.setPointerCapture(ev.pointerId);
            } catch (err) { /* ignore */ }
        });

        handle.addEventListener('pointermove', function (ev) {
            if (!drag || drag.pointerId !== ev.pointerId) return;
            applyWidth(panel, drag.width + ev.clientX - drag.startX);
        });

        function endDrag(ev) {
            if (!drag || (ev && drag.pointerId !== ev.pointerId)) return;
            saveWidth(panel, panel.getBoundingClientRect().width);
            drag = null;
            handle.classList.remove('is-dragging');
            document.body.classList.remove('gm-slide-panel-resizing');
            if (ev) {
                try {
                    handle.releasePointerCapture(ev.pointerId);
                } catch (err) { /* ignore */ }
            }
        }

        handle.addEventListener('pointerup', endDrag);
        handle.addEventListener('pointercancel', endDrag);
    }

    function ensureHandle(panel) {
        if (panel.querySelector('.gm-slide-panel-resize-handle')) return;
        var handle = document.createElement('div');
        handle.className = 'gm-slide-panel-resize-handle';
        handle.setAttribute('role', 'separator');
        handle.setAttribute('aria-orientation', 'vertical');
        handle.setAttribute('aria-label', 'Drag to resize panel');
        panel.appendChild(handle);
        bindResize(panel, handle);
    }

    function setupSlidePanelResize(root) {
        var scope = root || document;
        var panels = scope.querySelectorAll('.gm-slide-panel');
        panels.forEach(function (panel) {
            ensureHandle(panel);
            loadSavedWidth(panel);
        });
    }

    function onWindowResize() {
        document.querySelectorAll('.gm-slide-panel.gm-slide-panel--user-sized').forEach(function (panel) {
            applyWidth(panel, panel.getBoundingClientRect().width);
        });
    }

    window.setupSlidePanelResize = setupSlidePanelResize;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            setupSlidePanelResize();
        });
    } else {
        setupSlidePanelResize();
    }

    window.addEventListener('resize', onWindowResize, { passive: true });
})();

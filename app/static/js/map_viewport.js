/**
 * Pan/zoom viewport for large world maps (hex grids up to 500×500).
 */
(function (global) {
    'use strict';

    var MIN_SCALE = 0.08;
    var MAX_SCALE = 6;

    function create(stageEl, layerEl, options) {
        options = options || {};
        var panX = 0;
        var panY = 0;
        var scale = 1;
        var worldW = options.worldWidth || 1000;
        var worldH = options.worldHeight || 750;
        var dragging = false;
        var panPointer = false;
        var lastX = 0;
        var lastY = 0;
        var paintCapture = false;
        var capturedPointerId = null;

        function releasePointerCaptureSafe(pointerId) {
            var captureTarget = layerEl || stageEl;
            if (!captureTarget || pointerId == null) return;
            try {
                if (captureTarget.hasPointerCapture(pointerId)) {
                    captureTarget.releasePointerCapture(pointerId);
                }
            } catch (e) { /* ignore */ }
            if (capturedPointerId === pointerId) capturedPointerId = null;
        }

        function endDocumentPanTracking() {
            document.removeEventListener('pointerup', onDocumentPanEnd);
            document.removeEventListener('pointercancel', onDocumentPanEnd);
        }

        function onDocumentPanEnd(ev) {
            if (!panPointer) {
                endDocumentPanTracking();
                return;
            }
            endPan();
            releasePointerCaptureSafe(ev.pointerId);
            endDocumentPanTracking();
        }

        function applyTransform() {
            if (!layerEl) return;
            layerEl.style.transform = 'translate(' + panX + 'px,' + panY + 'px) scale(' + scale + ')';
            if (options.onViewportChange) options.onViewportChange(getState());
        }

        function getState() {
            return {
                panX: panX,
                panY: panY,
                scale: scale,
                worldWidth: worldW,
                worldHeight: worldH
            };
        }

        function setWorldSize(w, h) {
            worldW = Math.max(1, Number(w) || 1000);
            worldH = Math.max(1, Number(h) || 750);
            if (layerEl) {
                layerEl.style.width = worldW + 'px';
                layerEl.style.height = worldH + 'px';
            }
        }

        /**
         * Map a screen point into stage layout (CSS) pixels.
         * Uses clientWidth/Height — not getBoundingClientRect size — so a CSS
         * transform on the stage (e.g. decorative scale) cannot desync pan/zoom
         * math from marker placement.
         */
        function clientToStageLocal(clientX, clientY) {
            if (!stageEl) return { x: 0, y: 0 };
            var rect = stageEl.getBoundingClientRect();
            var lw = stageEl.clientWidth || 0;
            var lh = stageEl.clientHeight || 0;
            if (!rect.width || !rect.height || !lw || !lh) return { x: 0, y: 0 };
            return {
                x: (clientX - rect.left) * (lw / rect.width),
                y: (clientY - rect.top) * (lh / rect.height)
            };
        }

        function stageLayoutSize() {
            if (!stageEl) return { width: 0, height: 0 };
            return {
                width: stageEl.clientWidth || 0,
                height: stageEl.clientHeight || 0
            };
        }

        function fitToView(padding) {
            if (!stageEl) return;
            padding = padding == null ? 24 : padding;
            var size = stageLayoutSize();
            var sx = (size.width - padding * 2) / worldW;
            var sy = (size.height - padding * 2) / worldH;
            scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, Math.min(sx, sy)));
            panX = (size.width - worldW * scale) / 2;
            panY = (size.height - worldH * scale) / 2;
            applyTransform();
        }

        function screenToWorld(clientX, clientY) {
            if (!stageEl) return { x: 0, y: 0 };
            var local = clientToStageLocal(clientX, clientY);
            var x = (local.x - panX) / scale;
            var y = (local.y - panY) / scale;
            return {
                x: Math.max(0, Math.min(worldW, x)),
                y: Math.max(0, Math.min(worldH, y)),
                normX: Math.max(0, Math.min(1, x / worldW)),
                normY: Math.max(0, Math.min(1, y / worldH))
            };
        }

        function setPaintCapture(active) {
            paintCapture = !!active;
        }

        function releaseInteraction() {
            paintCapture = false;
            if (panPointer) {
                endPan();
            }
            endDocumentPanTracking();
            if (capturedPointerId != null) {
                releasePointerCaptureSafe(capturedPointerId);
            }
        }

        function onWheel(ev) {
            if (!stageEl) return;
            ev.preventDefault();
            var local = clientToStageLocal(ev.clientX, ev.clientY);
            var mx = local.x;
            var my = local.y;
            var beforeX = (mx - panX) / scale;
            var beforeY = (my - panY) / scale;
            var factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
            var next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * factor));
            if (next === scale) return;
            scale = next;
            panX = mx - beforeX * scale;
            panY = my - beforeY * scale;
            applyTransform();
        }

        function startPan(clientX, clientY) {
            dragging = true;
            panPointer = true;
            lastX = clientX;
            lastY = clientY;
            if (stageEl) stageEl.classList.add('map-viewport-panning');
        }

        function movePan(clientX, clientY) {
            if (!dragging) return;
            var rect = stageEl ? stageEl.getBoundingClientRect() : null;
            var sx = (stageEl && rect && rect.width)
                ? (stageEl.clientWidth / rect.width)
                : 1;
            var sy = (stageEl && rect && rect.height)
                ? (stageEl.clientHeight / rect.height)
                : 1;
            panX += (clientX - lastX) * sx;
            panY += (clientY - lastY) * sy;
            lastX = clientX;
            lastY = clientY;
            applyTransform();
        }

        function endPan() {
            dragging = false;
            panPointer = false;
            if (stageEl) stageEl.classList.remove('map-viewport-panning');
        }

        function isInteractiveTarget(ev) {
            var target = ev.target;
            if (!target || !target.closest) return false;
            return !!target.closest(
                '.map-marker, .map-entity-wrap, .map-poi-wrap, .map-encounter-wrap, ' +
                '.map-entity-popout, .map-poi-popout, .map-encounter-popout'
            );
        }

        function onPointerDown(ev) {
            if (!stageEl || paintCapture) return;
            if (options.shouldStartPan && !options.shouldStartPan(ev)) return;
            if (isInteractiveTarget(ev)) return;
            var isPanButton = ev.button === 1 || ev.button === 2;
            var isLeftPan = ev.button === 0 && !options.paintActive;
            if (!isPanButton && !isLeftPan) return;
            if (isPanButton) ev.preventDefault();
            startPan(ev.clientX, ev.clientY);
            capturedPointerId = ev.pointerId;
            var captureTarget = ev.currentTarget || layerEl || stageEl;
            try { captureTarget.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
            document.addEventListener('pointerup', onDocumentPanEnd);
            document.addEventListener('pointercancel', onDocumentPanEnd);
        }

        function onPointerMove(ev) {
            if (!panPointer) return;
            movePan(ev.clientX, ev.clientY);
        }

        function onPointerUp(ev) {
            if (!panPointer) return;
            endPan();
            releasePointerCaptureSafe(ev.pointerId);
            endDocumentPanTracking();
        }

        function bindPanTarget(el) {
            if (!el) return;
            el.addEventListener('wheel', onWheel, { passive: false });
            el.addEventListener('pointerdown', onPointerDown);
            el.addEventListener('pointermove', onPointerMove);
            el.addEventListener('pointerup', onPointerUp);
            el.addEventListener('pointercancel', onPointerUp);
        }

        bindPanTarget(layerEl || stageEl);

        if (stageEl) {
            stageEl.addEventListener('contextmenu', function (e) {
                if (options.paintActive) e.preventDefault();
            });
        }

        if (typeof ResizeObserver !== 'undefined' && stageEl) {
            var resizeTimer = null;
            var ro = new ResizeObserver(function () {
                if (resizeTimer) clearTimeout(resizeTimer);
                resizeTimer = setTimeout(function () {
                    if (options.autoFitOnResize) fitToView();
                }, 120);
            });
            ro.observe(stageEl);
        }

        function setPan(newPanX, newPanY) {
            panX = newPanX;
            panY = newPanY;
            applyTransform();
        }

        function panBy(deltaX, deltaY) {
            panX += deltaX;
            panY += deltaY;
            applyTransform();
        }

        function panToWorldPoint(wx, wy) {
            if (!stageEl) return;
            var size = stageLayoutSize();
            panX = size.width / 2 - wx * scale;
            panY = size.height / 2 - wy * scale;
            applyTransform();
        }

        return {
            getState: getState,
            setWorldSize: setWorldSize,
            fitToView: fitToView,
            screenToWorld: screenToWorld,
            setPan: setPan,
            panBy: panBy,
            panToWorldPoint: panToWorldPoint,
            setPaintCapture: setPaintCapture,
            setPaintActive: function (active) {
                options.paintActive = !!active;
            },
            releaseInteraction: releaseInteraction,
            applyTransform: applyTransform
        };
    }

    global.MapViewport = {
        create: create,
        MIN_SCALE: MIN_SCALE,
        MAX_SCALE: MAX_SCALE
    };
})(typeof window !== 'undefined' ? window : this);

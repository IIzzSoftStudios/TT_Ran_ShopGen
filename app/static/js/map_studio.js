/**
 * GM Map Studio — brush painting, stamps, undo/redo on terrain_grid + features.
 * Requires MapRenderer (map_renderer.js).
 */
(function (global) {
    'use strict';

    var GRID_W = 256;
    var GRID_H = 192;
    var MAX_UNDO = 50;

    var WORLD_BRUSHES = [
        { id: 'prairie', code: 1, label: 'Prairie' },
        { id: 'water', code: 0, label: 'Water' },
        { id: 'mountain', code: 2, label: 'Mountain' },
        { id: 'forest', code: 3, label: 'Forest' },
        { id: 'desert', code: 4, label: 'Desert' },
        { id: 'grassland', code: 5, label: 'Grassland' },
        { id: 'hills', code: 6, label: 'Hills' }
    ];

    var CITY_BRUSHES = [
        { id: 'district', code: 1, label: 'Courtyard' },
        { id: 'water', code: 2, label: 'Water' },
        { id: 'park', code: 3, label: 'Park' },
        { id: 'road', code: 4, label: 'Road' },
        { id: 'building', code: 5, label: 'Building' },
        { id: 'wall', code: 6, label: 'Wall' }
    ];

    var SHOP_BRUSHES = [
        { id: 'floor', code: 1, label: 'Floor' },
        { id: 'counter', code: 2, label: 'Counter' },
        { id: 'display', code: 3, label: 'Display' },
        { id: 'aisle', code: 4, label: 'Aisle' },
        { id: 'shelf', code: 5, label: 'Shelf' },
        { id: 'wall', code: 6, label: 'Wall' }
    ];

    function brushesForScope(scopeName) {
        if (scopeName === 'world') return WORLD_BRUSHES;
        if (scopeName === 'shop') return SHOP_BRUSHES;
        return CITY_BRUSHES;
    }

    var WORLD_LINE_TOOLS = [
        { id: 'river', label: 'River', featureType: 'river' },
        { id: 'road', label: 'Road', featureType: 'road' },
        { id: 'trade_route', label: 'Trade route', featureType: 'trade_route' },
        { id: 'railroad', label: 'Railroad', featureType: 'railroad' }
    ];

    var CITY_LINE_TOOLS = [
        { id: 'canal', label: 'Waterway', featureType: 'canal' },
        { id: 'road', label: 'Road', featureType: 'road' },
        { id: 'railroad', label: 'Railroad', featureType: 'railroad' }
    ];

    var LINE_OVERLAY_STYLE = {
        river: { stroke: '#317aa3', dot: '#2563eb' },
        road: { stroke: '#9a8a78', dot: '#6a5a48' },
        trade_route: { stroke: '#7c4a23', dot: '#5a3818', dash: '8 8' },
        railroad: { stroke: '#4a4a4a', dot: '#2a2a2a', dash: '4 6' },
        canal: { stroke: '#4f9ab8', dot: '#317aa3' }
    };

    function lineToolsForScope(scopeName) {
        if (scopeName === 'world') return WORLD_LINE_TOOLS;
        if (scopeName === 'city') return CITY_LINE_TOOLS;
        return [];
    }

    function lineToolMeta(toolId, scopeName) {
        var tools = lineToolsForScope(scopeName);
        for (var i = 0; i < tools.length; i++) {
            if (tools[i].id === toolId) return tools[i];
        }
        return null;
    }

    function isLineToolId(toolId, scopeName) {
        return !!lineToolMeta(toolId, scopeName);
    }

    var WORLD_STAMPS = [
        { id: 'mountain_range', label: 'Mountain range' },
        { id: 'river_mouth', label: 'River mouth' },
        { id: 'lake', label: 'Lake' }
    ];

    var CITY_STAMPS = [
        { id: 'plaza', label: 'Plaza' },
        { id: 'canal', label: 'Canal' },
        { id: 'wall', label: 'Wall segment' }
    ];

    function cloneJson(obj) {
        return JSON.parse(JSON.stringify(obj || {}));
    }

    function pointInPolygon(x, y, polygon) {
        if (!polygon || polygon.length < 3) return false;
        var inside = false;
        for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
            var xi = Number(polygon[i][0]);
            var yi = Number(polygon[i][1]);
            var xj = Number(polygon[j][0]);
            var yj = Number(polygon[j][1]);
            var intersect = ((yi > y) !== (yj > y)) &&
                (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-9) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    function featureGridCode(type, scope) {
        if (scope === 'world') {
            if (type === 'landmass' || type === 'island') return 1;
            if (type === 'hill') return 6;
            if (type === 'mountain_range') return 2;
            if (type === 'forest') return 3;
            if (type === 'grassland') return 5;
        } else {
            if (type === 'district' || type === 'city_wall') return 1;
            if (type === 'canal') return 2;
            if (type === 'park') return 3;
            if (type === 'road') return 4;
            if (type === 'building') return 5;
        }
        return null;
    }

    function initGridFromFeatures(generation) {
        var scope = generation.scope || 'world';
        var cells = new Array(GRID_W * GRID_H);
        for (var i = 0; i < cells.length; i++) cells[i] = 0;
        var features = generation.features || [];
        for (var gy = 0; gy < GRID_H; gy++) {
            var ny = (gy + 0.5) / GRID_H;
            for (var gx = 0; gx < GRID_W; gx++) {
                var nx = (gx + 0.5) / GRID_W;
                for (var f = 0; f < features.length; f++) {
                    var feat = features[f];
                    var code = featureGridCode(feat.type, scope);
                    if (code == null || !feat.points) continue;
                    if (pointInPolygon(nx, ny, feat.points)) {
                        cells[gy * GRID_W + gx] = code;
                        break;
                    }
                }
            }
        }
        return {
            width: GRID_W,
            height: GRID_H,
            encoding: 'rle',
            cells: global.MapRenderer.encodeTerrainRle(cells)
        };
    }

    function blobPoints(cx, cy, rx, ry, count) {
        var pts = [];
        for (var i = 0; i < count; i++) {
            var angle = (Math.PI * 2 * i) / count;
            var wobble = 0.85 + (Math.sin(i * 2.7) * 0.12);
            var x = Math.max(0, Math.min(1, cx + Math.cos(angle) * rx * wobble));
            var y = Math.max(0, Math.min(1, cy + Math.sin(angle) * ry * wobble));
            pts.push([Math.round(x * 10000) / 10000, Math.round(y * 10000) / 10000]);
        }
        return pts;
    }

    function createStudio(options) {
        options = options || {};
        var active = false;
        var dirty = false;
        var tool = 'prairie';
        var editMode = 'paint';
        var brushSize = 12;
        var scope = 'world';
        var working = null;
        var cells = null;
        var undoStack = [];
        var redoStack = [];
        var painting = false;
        var rafPending = false;
        var hexCatalog = null;
        var hexMap = {};
        var hexCells = null;
        var hexMeta = null;
        var showGridLines = true;
        var lineDraft = null;
        var lineStroke = { active: false };

        var stage = options.stage;
        var overlay = options.overlay;
        var lineOverlayLayer = options.lineOverlayLayer;
        var viewportLayer = options.viewportLayer || (stage && stage.querySelector('#map-viewport-layer'));
        var genBg = options.genBg;
        var markerLayer = options.markerLayer;
        var mapViewport = options.mapViewport;
        var onDirtyChange = options.onDirtyChange || function () {};
        var onFeedback = options.onFeedback || function () {};
        var onExitBaked = options.onExitBaked || function () {};
        var onLineDraftChange = options.onLineDraftChange || function () {};

        function gridDims() {
            var tg = working && working.terrain_grid;
            return {
                w: (tg && tg.width) || GRID_W,
                h: (tg && tg.height) || GRID_H
            };
        }

        function viewportRenderBounds() {
            if (!mapViewport || !global.MapHex) return null;
            var st = mapViewport.getState();
            st.stageEl = stage;
            return global.MapHex.viewportBoundsFromState(st);
        }

        function notifyDirty() {
            onDirtyChange(dirty);
        }

        function getCells() {
            if (!working || !working.terrain_grid) return [];
            var d = gridDims();
            return global.MapRenderer.decodeTerrainRle(
                working.terrain_grid.cells,
                d.w * d.h
            );
        }

        function setCells(newCells) {
            if (!working) return;
            var d = gridDims();
            working.terrain_grid = {
                width: d.w,
                height: d.h,
                encoding: 'rle',
                cells: global.MapRenderer.encodeTerrainRle(newCells)
            };
        }

        function pushUndo() {
            if (!working) return;
            undoStack.push({
                terrain_grid: cloneJson(working.terrain_grid),
                features: cloneJson(working.features || []),
                hexMap: cloneJson(hexMap),
                hexCells: hexCells ? hexCells.slice() : null,
                hex_grid: cloneJson(working.hex_grid)
            });
            if (undoStack.length > MAX_UNDO) undoStack.shift();
            redoStack = [];
        }

        function usesHexGrid() {
            return (scope === 'world' || scope === 'city' || scope === 'shop') && working && working.hex_grid && global.MapHex;
        }

        function syncHexGridToWorking() {
            if (!usesHexGrid() || !hexCells || !hexMeta) return;
            working.hex_grid = {
                orientation: 'flat',
                coordinate_space: hexMeta.coordinate_space || 'world',
                width: hexMeta.width,
                height: hexMeta.height,
                hex_size: hexMeta.hex_size,
                origin: hexMeta.origin ? hexMeta.origin.slice() : null,
                encoding: 'rle',
                cells: global.MapRenderer.encodeTerrainRle(hexCells)
            };
        }

        function bakeTerrainPreviewIfNeeded() {
            if (!usesHexGrid() || !hexCells) return;
            bakeTerrainPreview();
        }

        function bakeTerrainPreview() {
            if (!usesHexGrid() || !hexCells) return;
            var d = gridDims();
            working.terrain_grid = global.MapHex.bakeTerrainGrid(
                working.hex_grid,
                hexCells,
                d.w,
                d.h,
                global.MapRenderer.encodeTerrainRle
            );
        }

        function rebuildHexState() {
            if (!global.MapHex) return;
            if (usesHexGrid()) {
                hexMeta = working.hex_grid;
                hexCatalog = global.MapHex.buildCatalogFromHexGrid(hexMeta);
                hexCells = global.MapRenderer.decodeTerrainRle(
                    hexMeta.cells,
                    hexCatalog.width * hexCatalog.height
                );
                hexMap = global.MapHex.buildHexMapFromCells(hexCells, hexCatalog);
                return;
            }
            hexMeta = null;
            hexCells = null;
            hexCatalog = global.MapHex.buildCatalog(global.MapHex.DEFAULT_HEX_SIZE);
            hexMap = global.MapHex.buildHexMapFromCells(cells || [], hexCatalog);
        }

        function getRenderOptions() {
            return {
                showHexGrid: active && usesHexGrid(),
                showGridLines: showGridLines,
                hexCatalog: hexCatalog,
                hexMap: hexMap,
                hexCells: hexCells,
                viewportBounds: viewportRenderBounds()
            };
        }

        function scheduleStudioRender() {
            if (active && usesHexGrid() && global.MapHex &&
                    global.MapHex.catalogCellCount(hexCatalog) > global.MapHex.LARGE_GRID_CELLS) {
                scheduleViewportRender();
            } else {
                renderPreview();
            }
        }

        function renderPreview() {
            if (!working || !genBg || !global.MapRenderer) return;
            global.MapRenderer.render(working, genBg, stage, getRenderOptions());
        }

        var viewportRenderPending = false;
        function scheduleViewportRender() {
            if (!active || viewportRenderPending) return;
            viewportRenderPending = true;
            requestAnimationFrame(function () {
                viewportRenderPending = false;
                renderPreview();
            });
        }

        function syncOverlaySize() {
            if (!overlay) return;
            overlay.width = 1;
            overlay.height = 1;
            overlay.style.width = '100%';
            overlay.style.height = '100%';
        }

        function ensureWorking(generation, scopeName) {
            scope = scopeName || generation.scope || 'world';
            working = cloneJson(generation);
            working.scope = scope;
            working.schema_version = working.schema_version || 6;
            if (!working.terrain_grid || !working.terrain_grid.cells) {
                working.terrain_grid = initGridFromFeatures(working);
                if (!working.editor_meta) working.editor_meta = {};
                working.editor_meta.grid_initialized_from = 'procedural_v4';
            }
            cells = getCells();
            rebuildHexState();
            scheduleStudioRender();
        }

        function brushCodeForTool(toolId) {
            var brushes = brushesForScope(scope);
            for (var i = 0; i < brushes.length; i++) {
                if (brushes[i].id === toolId) return brushes[i].code;
            }
            return scope === 'world' ? 1 : 1;
        }

        function hexBrushRadius() {
            return Math.max(0, Math.min(2, Math.round(Number(brushSize) / 18)));
        }

        function paintHexAt(worldX, worldY) {
            if (!working || !global.MapHex || !hexCatalog) return;
            var size = hexCatalog.size;
            var origin = hexCatalog.origin || [20, 20];
            var axial = global.MapHex.worldToAxial(worldX, worldY, size, origin[0], origin[1]);
            var code = brushCodeForTool(tool);
            var disk = global.MapHex.hexDisk(axial.q, axial.r, hexBrushRadius());
            var changed = false;

            if (usesHexGrid() && hexCells) {
                disk.forEach(function (coord) {
                    if (coord.q < 0 || coord.r < 0 || coord.q >= hexCatalog.width || coord.r >= hexCatalog.height) {
                        return;
                    }
                    var idx = coord.r * hexCatalog.width + coord.q;
                    if (hexCells[idx] !== code) {
                        hexCells[idx] = code;
                        hexMap[global.MapHex.hexKey(coord.q, coord.r)] = code;
                        changed = true;
                    }
                });
                if (changed) {
                    syncHexGridToWorking();
                }
            } else if (cells) {
                var ms = global.MapHex.mapWorldSize(working.hex_grid || {});
                var mapW = ms.width || 1000;
                var mapH = ms.height || 750;
                var d = gridDims();
                disk.forEach(function (coord) {
                    if (coord.q < 0 || coord.r < 0 || coord.q >= hexCatalog.width || coord.r >= hexCatalog.height) {
                        return;
                    }
                    var key = global.MapHex.hexKey(coord.q, coord.r);
                    var c = global.MapHex.axialToWorld(
                        coord.q, coord.r, hexCatalog.size, hexCatalog.origin[0], hexCatalog.origin[1]
                    );
                    var hex = { q: coord.q, r: coord.r, key: key, cx: c[0], cy: c[1] };
                    if (hexMap[key] !== code) {
                        hexMap[key] = code;
                        global.MapHex.fillHexOnGrid(hex, code, cells, d.w, d.h, mapW, mapH, hexCatalog.size);
                        changed = true;
                    }
                });
                if (changed) setCells(cells);
            }

            if (changed) {
                dirty = true;
                notifyDirty();
                if (!rafPending) {
                    rafPending = true;
                    requestAnimationFrame(function () {
                        rafPending = false;
                        renderPreview();
                    });
                }
            }
        }

        function paintAt(worldX, worldY) {
            paintHexAt(worldX, worldY);
        }

        function smoothCoastlines() {
            if (!cells) return;
            pushUndo();
            var isWorld = scope === 'world';
            var landClass = function (c) {
                if (isWorld) return c === 1;
                return c === 1;
            };
            var next = cells.slice();
            for (var pass = 0; pass < 2; pass++) {
                for (var gy = 1; gy < GRID_H - 1; gy++) {
                    for (var gx = 1; gx < GRID_W - 1; gx++) {
                        var idx = gy * GRID_W + gx;
                        var neighbors = [
                            cells[idx - 1], cells[idx + 1],
                            cells[idx - GRID_W], cells[idx + GRID_W],
                            cells[idx - GRID_W - 1], cells[idx - GRID_W + 1],
                            cells[idx + GRID_W - 1], cells[idx + GRID_W + 1]
                        ];
                        var landCount = 0;
                        neighbors.forEach(function (n) {
                            if (landClass(n)) landCount += 1;
                        });
                        if (landClass(cells[idx])) {
                            if (landCount <= 2) next[idx] = 0;
                        } else if (landCount >= 5) {
                            next[idx] = isWorld ? 1 : 1;
                        }
                    }
                }
                cells = next.slice();
                next = cells.slice();
            }
            setCells(cells);
            if (usesHexGrid()) {
                syncHexGridToWorking();
                bakeTerrainPreview();
            }
            rebuildHexState();
            dirty = true;
            notifyDirty();
            renderPreview();
        }

        function applyStamp(normX, normY) {
            if (!working) return;
            pushUndo();
            var features = working.features || [];
            var x = Math.max(0.05, Math.min(0.95, normX));
            var y = Math.max(0.05, Math.min(0.95, normY));

            if (scope === 'world') {
                if (tool === 'mountain_range') {
                    var path = [];
                    for (var i = 0; i < 5; i++) {
                        path.push([
                            Math.round((x - 0.12 + i * 0.06) * 10000) / 10000,
                            Math.round((y + Math.sin(i) * 0.04) * 10000) / 10000
                        ]);
                    }
                    features.push({
                        type: 'mountain_range',
                        points: path,
                        peak_scale: path.map(function () {
                            return Math.round((0.8 + Math.random() * 0.5) * 1000) / 1000;
                        })
                    });
                } else if (tool === 'river_mouth') {
                    features.push({
                        type: 'river',
                        points: [
                            [Math.round(x * 10000) / 10000, 0.02],
                            [Math.round(x * 10000) / 10000, Math.round(y * 10000) / 10000],
                            [Math.round((x + 0.08) * 10000) / 10000, Math.min(0.98, Math.round((y + 0.15) * 10000) / 10000)]
                        ]
                    });
                } else if (tool === 'lake') {
                    features.push({
                        type: 'lake',
                        points: blobPoints(x, y, 0.06, 0.05, 10)
                    });
                }
            } else {
                if (tool === 'plaza') {
                    features.push({ type: 'plaza', x: x, y: y, size: 0.04 });
                } else if (tool === 'canal') {
                    features.push({
                        type: 'canal',
                        points: [
                            [0.05, y],
                            [x, y],
                            [0.95, Math.min(0.95, y + 0.06)]
                        ]
                    });
                } else if (tool === 'wall') {
                    features.push({
                        type: 'city_wall',
                        points: blobPoints(x, y, 0.08, 0.04, 8)
                    });
                }
            }
            working.features = features;
            dirty = true;
            notifyDirty();
            renderPreview();
        }

        function pointerNorm(ev) {
            if (mapViewport) {
                var p = mapViewport.screenToWorld(ev.clientX, ev.clientY);
                return { worldX: p.x, worldY: p.y, normX: p.normX, normY: p.normY };
            }
            var rect = stage.getBoundingClientRect();
            var nx = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
            var ny = Math.max(0, Math.min(1, (ev.clientY - rect.top) / rect.height));
            return {
                worldX: nx * 1000,
                worldY: ny * 750,
                normX: nx,
                normY: ny
            };
        }

        function roundNormPoint(normX, normY) {
            return [
                Math.round(normX * 10000) / 10000,
                Math.round(normY * 10000) / 10000
            ];
        }

        function notifyLineDraftChange() {
            onLineDraftChange(lineDraft);
        }

        function lineOverlayWorldSize() {
            if (mapViewport && mapViewport.getWorldSize) {
                var ws = mapViewport.getWorldSize();
                if (ws && ws.w && ws.h) return ws;
            }
            return { w: 1000, h: 750 };
        }

        function renderLineOverlay() {
            if (!lineOverlayLayer) return;
            if (!lineDraft || !lineDraft.points || !lineDraft.points.length) {
                lineOverlayLayer.innerHTML = '';
                lineOverlayLayer.hidden = true;
                return;
            }
            var style = LINE_OVERLAY_STYLE[lineDraft.type] || LINE_OVERLAY_STYLE.road;
            var world = lineOverlayWorldSize();
            var ns = 'http://www.w3.org/2000/svg';
            var svg = document.createElementNS(ns, 'svg');
            svg.setAttribute('class', 'map-line-draw-svg');
            svg.setAttribute('viewBox', '0 0 ' + world.w + ' ' + world.h);
            svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
            var strokeW = Math.max(3, world.w / 400);
            var dotR = Math.max(4, world.w / 320);
            lineDraft.points.forEach(function (pt) {
                var circle = document.createElementNS(ns, 'circle');
                circle.setAttribute('cx', String(Number(pt[0]) * world.w));
                circle.setAttribute('cy', String(Number(pt[1]) * world.h));
                circle.setAttribute('r', String(dotR));
                circle.setAttribute('fill', style.dot || style.stroke);
                circle.setAttribute('stroke', style.stroke);
                circle.setAttribute('stroke-width', String(Math.max(1, strokeW * 0.35)));
                circle.setAttribute('opacity', '0.95');
                svg.appendChild(circle);
            });
            if (lineDraft.points.length >= 2) {
                var pts = lineDraft.points.map(function (pt) {
                    return (Number(pt[0]) * world.w).toFixed(2) + ',' +
                        (Number(pt[1]) * world.h).toFixed(2);
                }).join(' ');
                var polyline = document.createElementNS(ns, 'polyline');
                polyline.setAttribute('points', pts);
                polyline.setAttribute('fill', 'none');
                polyline.setAttribute('stroke', style.stroke);
                polyline.setAttribute('stroke-width', String(strokeW));
                polyline.setAttribute('stroke-linecap', 'round');
                polyline.setAttribute('stroke-linejoin', 'round');
                polyline.setAttribute('opacity', '0.95');
                if (style.dash) polyline.setAttribute('stroke-dasharray', style.dash);
                svg.appendChild(polyline);
            }
            lineOverlayLayer.hidden = false;
            lineOverlayLayer.innerHTML = '';
            lineOverlayLayer.appendChild(svg);
        }

        function teardownLineStroke() {
            lineStroke.active = false;
            document.removeEventListener('pointermove', onLinePointerMove);
            document.removeEventListener('pointerup', onLinePointerUp);
            document.removeEventListener('pointercancel', onLinePointerUp);
            if (mapViewport) mapViewport.setPaintCapture(false);
        }

        function appendLinePoint(normX, normY) {
            if (!lineDraft) return;
            var pt = roundNormPoint(normX, normY);
            var pts = lineDraft.points;
            if (pts.length) {
                var last = pts[pts.length - 1];
                if (Math.abs(last[0] - pt[0]) < 0.0005 && Math.abs(last[1] - pt[1]) < 0.0005) {
                    renderLineOverlay();
                    return;
                }
            }
            lineDraft.points.push(pt);
            renderLineOverlay();
            notifyLineDraftChange();
        }

        function onLinePointerMove(ev) {
            if (!lineStroke.active || !lineDraft || !lineDraft.drawingStroke) return;
            ev.preventDefault();
            var p = pointerNorm(ev);
            appendLinePoint(p.normX, p.normY);
        }

        function onLinePointerUp() {
            if (!lineStroke.active) return;
            teardownLineStroke();
        }

        function onLinePointerDown(ev) {
            if (!active || !lineDraft || ev.button !== 0) return;
            if (!lineDraft.drawingStroke) return;
            if (ev.target.closest('.map-world-nav, .map-region-boundary-tools, .map-studio-line-tools')) return;
            ev.preventDefault();
            ev.stopPropagation();
            lineStroke.active = true;
            if (mapViewport) mapViewport.setPaintCapture(true);
            var p = pointerNorm(ev);
            appendLinePoint(p.normX, p.normY);
            document.addEventListener('pointermove', onLinePointerMove);
            document.addEventListener('pointerup', onLinePointerUp);
            document.addEventListener('pointercancel', onLinePointerUp);
        }

        function beginLineDraft(toolId) {
            var meta = lineToolMeta(toolId, scope);
            if (!meta) return;
            lineDraft = {
                type: meta.featureType,
                label: meta.label,
                points: [],
                drawingStroke: true
            };
            renderLineOverlay();
            notifyLineDraftChange();
            if (mapViewport) {
                mapViewport.setPaintActive(true);
            }
        }

        function cancelLineDraft() {
            teardownLineStroke();
            lineDraft = null;
            renderLineOverlay();
            notifyLineDraftChange();
            if (mapViewport && !painting) {
                mapViewport.setPaintActive(false);
            }
        }

        function undoLinePoint() {
            if (!lineDraft || !lineDraft.points.length) return;
            lineDraft.points.pop();
            renderLineOverlay();
            notifyLineDraftChange();
        }

        function clearLineStroke() {
            if (!lineDraft) return;
            lineDraft.points = [];
            renderLineOverlay();
            notifyLineDraftChange();
        }

        function toggleLineDrawing() {
            if (!lineDraft) return;
            lineDraft.drawingStroke = !lineDraft.drawingStroke;
            if (!lineDraft.drawingStroke) teardownLineStroke();
            notifyLineDraftChange();
            if (mapViewport) {
                mapViewport.setPaintActive(!!lineDraft.drawingStroke);
            }
        }

        function finishLine() {
            if (!lineDraft || lineDraft.points.length < 2) return false;
            pushUndo();
            working.features = working.features || [];
            working.features.push({
                type: lineDraft.type,
                points: lineDraft.points.map(function (pt) { return pt.slice(); }),
                gm_drawn: true
            });
            dirty = true;
            notifyDirty();
            lineDraft = null;
            teardownLineStroke();
            renderLineOverlay();
            notifyLineDraftChange();
            renderPreview();
            if (mapViewport) mapViewport.setPaintActive(false);
            return true;
        }

        function onDocumentPaintMove(ev) {
            if (!active || !painting) return;
            var p = pointerNorm(ev);
            paintHexAt(p.worldX, p.worldY);
        }

        function onDocumentPaintButtonDown(ev) {
            if (!active || !painting || ev.button !== 2) return;
            ev.preventDefault();
            ev.stopPropagation();
            endPaintStroke();
        }

        function onDocumentPaintUp(ev) {
            if (!painting || ev.button !== 0) return;
            teardownPaintSession();
        }

        function teardownPaintSession() {
            painting = false;
            document.removeEventListener('pointermove', onDocumentPaintMove);
            document.removeEventListener('pointerup', onDocumentPaintUp);
            document.removeEventListener('pointercancel', onDocumentPaintUp);
            document.removeEventListener('pointerdown', onDocumentPaintButtonDown, true);
            if (mapViewport) {
                mapViewport.setPaintCapture(false);
                if (mapViewport.releaseInteraction) mapViewport.releaseInteraction();
            }
        }

        function endPaintStroke() {
            teardownPaintSession();
        }

        function onPointerDown(ev) {
            if (!active || !working) return;
            if (isLineToolId(tool, scope)) {
                onLinePointerDown(ev);
                return;
            }
            if (editMode === 'features') return;
            if (ev.button === 2) {
                if (painting) {
                    ev.preventDefault();
                    endPaintStroke();
                }
                return;
            }
            if (ev.button !== 0) return;
            ev.preventDefault();
            if (mapViewport) mapViewport.setPaintCapture(true);
            var p = pointerNorm(ev);
            if (tool === 'smooth') {
                smoothCoastlines();
                if (mapViewport) mapViewport.setPaintCapture(false);
                return;
            }
            if (isStampTool(tool)) {
                applyStamp(p.normX, p.normY);
                if (mapViewport) mapViewport.setPaintCapture(false);
                return;
            }
            pushUndo();
            painting = true;
            document.addEventListener('pointermove', onDocumentPaintMove);
            document.addEventListener('pointerup', onDocumentPaintUp);
            document.addEventListener('pointercancel', onDocumentPaintUp);
            document.addEventListener('pointerdown', onDocumentPaintButtonDown, true);
            paintHexAt(p.worldX, p.worldY);
        }

        function paintListenerTarget() {
            if (mapViewport && viewportLayer) return viewportLayer;
            return overlay || null;
        }

        function bindPaintListeners() {
            unbindPaintListeners();
            var target = paintListenerTarget();
            if (!target) return;
            target.addEventListener('pointerdown', onPointerDown);
        }

        function unbindPaintListeners() {
            teardownPaintSession();
            var target = paintListenerTarget();
            if (target) {
                target.removeEventListener('pointerdown', onPointerDown);
            }
            if (overlay && overlay !== target) {
                overlay.removeEventListener('pointerdown', onPointerDown);
            }
        }

        function isStampTool(toolId) {
            if (scope === 'world') {
                return toolId === 'mountain_range' || toolId === 'river_mouth' || toolId === 'lake';
            }
            return toolId === 'plaza' || toolId === 'canal' || toolId === 'wall';
        }

        function setEditMode(mode) {
            editMode = mode || 'paint';
            if (overlay) {
                overlay.style.pointerEvents = editMode === 'features' ? 'none' : 'auto';
            }
            if (markerLayer) {
                markerLayer.style.pointerEvents = editMode === 'features' ? 'auto' : 'none';
            }
            if (mapViewport) {
                mapViewport.setPaintActive(active && editMode === 'paint');
            }
        }

        function setTool(toolId) {
            if (isLineToolId(toolId, scope)) {
                if (!isLineToolId(tool, scope) || tool !== toolId) {
                    cancelLineDraft();
                    tool = toolId;
                    beginLineDraft(toolId);
                } else {
                    tool = toolId;
                }
                return;
            }
            if (isLineToolId(tool, scope)) {
                cancelLineDraft();
            }
            tool = toolId;
        }

        function setBrushSize(size) {
            brushSize = Math.max(1, Math.min(48, Number(size) || 12));
        }

        function undo() {
            if (!undoStack.length || !working) return;
            redoStack.push({
                terrain_grid: cloneJson(working.terrain_grid),
                features: cloneJson(working.features || []),
                hexMap: cloneJson(hexMap),
                hexCells: hexCells ? hexCells.slice() : null,
                hex_grid: cloneJson(working.hex_grid)
            });
            var snap = undoStack.pop();
            working.terrain_grid = snap.terrain_grid;
            working.features = snap.features;
            if (snap.hex_grid) working.hex_grid = snap.hex_grid;
            if (snap.hexMap) hexMap = snap.hexMap;
            if (snap.hexCells) hexCells = snap.hexCells.slice();
            cells = getCells();
            dirty = true;
            notifyDirty();
            renderPreview();
        }

        function redo() {
            if (!redoStack.length || !working) return;
            undoStack.push({
                terrain_grid: cloneJson(working.terrain_grid),
                features: cloneJson(working.features || []),
                hexMap: cloneJson(hexMap),
                hexCells: hexCells ? hexCells.slice() : null,
                hex_grid: cloneJson(working.hex_grid)
            });
            var snap = redoStack.pop();
            working.terrain_grid = snap.terrain_grid;
            working.features = snap.features;
            if (snap.hex_grid) working.hex_grid = snap.hex_grid;
            if (snap.hexMap) hexMap = snap.hexMap;
            if (snap.hexCells) hexCells = snap.hexCells.slice();
            cells = getCells();
            dirty = true;
            notifyDirty();
            renderPreview();
        }

        function enter(generation, scopeName) {
            if (!generation) return false;
            if (mapViewport && mapViewport.releaseInteraction) {
                mapViewport.releaseInteraction();
            }
            active = true;
            dirty = false;
            undoStack = [];
            redoStack = [];
            tool = (scopeName === 'city') ? 'district' : (scopeName === 'shop' ? 'floor' : 'prairie');
            ensureWorking(generation, scopeName);
            if (overlay) overlay.hidden = true;
            if (markerLayer) markerLayer.style.pointerEvents = editMode === 'features' ? 'auto' : 'none';
            if (stage) {
                stage.classList.add('map-studio-active');
                if (mapViewport && viewportLayer) stage.classList.add('map-studio-paint');
            }
            setEditMode(editMode);
            bindPaintListeners();
            if (mapViewport) {
                mapViewport.setPaintActive(editMode === 'paint');
            }
            return true;
        }

        function exit() {
            var shouldBake = dirty && usesHexGrid();
            cancelLineDraft();
            active = false;
            painting = false;
            unbindPaintListeners();
            if (mapViewport) {
                mapViewport.setPaintActive(false);
                mapViewport.setPaintCapture(false);
                if (mapViewport.releaseInteraction) mapViewport.releaseInteraction();
            }
            if (overlay) {
                overlay.hidden = true;
                overlay.style.pointerEvents = 'none';
            }
            if (markerLayer) markerLayer.style.pointerEvents = '';
            if (stage) {
                stage.classList.remove('map-studio-active');
                stage.classList.remove('map-studio-paint');
            }
            if (shouldBake) {
                window.setTimeout(function () {
                    try {
                        bakeTerrainPreviewIfNeeded();
                        onExitBaked(working);
                    } catch (err) {
                        console.warn('map studio: terrain bake failed on exit', err);
                    }
                }, 0);
            }
        }

        function getWorkingGeneration() {
            if (usesHexGrid()) {
                syncHexGridToWorking();
                bakeTerrainPreviewIfNeeded();
            }
            return cloneJson(working);
        }

        function markSaved(serverGeneration) {
            working = cloneJson(serverGeneration);
            cells = getCells();
            rebuildHexState();
            dirty = false;
            undoStack = [];
            redoStack = [];
            notifyDirty();
            renderPreview();
        }

        function clearDirty() {
            dirty = false;
            notifyDirty();
        }

        return {
            isActive: function () { return active; },
            isDirty: function () { return dirty; },
            enter: enter,
            exit: exit,
            setTool: setTool,
            setEditMode: setEditMode,
            setShowGridLines: function (show) { showGridLines = !!show; renderPreview(); },
            getShowGridLines: function () { return showGridLines; },
            getEditMode: function () { return editMode; },
            setBrushSize: setBrushSize,
            getTool: function () { return tool; },
            undo: undo,
            redo: redo,
            getWorkingGeneration: getWorkingGeneration,
            markSaved: markSaved,
            clearDirty: clearDirty,
            getRenderOptions: getRenderOptions,
            renderPreview: renderPreview,
            scheduleViewportRender: scheduleViewportRender,
            getBrushes: function () { return brushesForScope(scope); },
            getLineTools: function () { return lineToolsForScope(scope); },
            isLineTool: function (toolId) { return isLineToolId(toolId || tool, scope); },
            getLineDraft: function () { return lineDraft; },
            finishLine: finishLine,
            cancelLineDraft: cancelLineDraft,
            undoLinePoint: undoLinePoint,
            clearLineStroke: clearLineStroke,
            toggleLineDrawing: toggleLineDrawing,
            getStamps: function () { return scope === 'city' ? CITY_STAMPS : []; },
            WORLD_BRUSHES: WORLD_BRUSHES,
            SHOP_BRUSHES: SHOP_BRUSHES,
            CITY_BRUSHES: CITY_BRUSHES
        };
    }

    global.MapStudio = {
        create: createStudio,
        GRID_W: GRID_W,
        GRID_H: GRID_H,
        WORLD_LINE_TOOLS: WORLD_LINE_TOOLS,
        CITY_LINE_TOOLS: CITY_LINE_TOOLS
    };
})(typeof window !== 'undefined' ? window : this);

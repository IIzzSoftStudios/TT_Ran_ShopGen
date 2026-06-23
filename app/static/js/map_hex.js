/**
 * Flat-top hex grid — canonical world authoring surface (schema v7).
 * Large maps use world-pixel coordinates with pan/zoom viewport.
 */
(function (global) {
    'use strict';

    var SQRT3 = Math.sqrt(3);
    var DEFAULT_HEX_SIZE = 12;
    var WORLD_PADDING = 20;
    var LARGE_GRID_CELLS = 8000;

    function hexKey(q, r) {
        return String(q) + ',' + String(r);
    }

    function parseKey(key) {
        var parts = String(key).split(',');
        return { q: parseInt(parts[0], 10), r: parseInt(parts[1], 10) };
    }

    function effectiveHexSize(hexGrid) {
        var size = Number(hexGrid && hexGrid.hex_size) || DEFAULT_HEX_SIZE;
        if (hexGrid && hexGrid.coordinate_space === 'norm') return size;
        if (size < 1) return DEFAULT_HEX_SIZE;
        return size;
    }

    function isWorldSpace(hexGrid) {
        return !!(hexGrid && (hexGrid.coordinate_space === 'world' || Number(hexGrid.width) > 100));
    }

    function gridOrigin(hexGrid) {
        if (hexGrid && hexGrid.origin) {
            return [Number(hexGrid.origin[0]), Number(hexGrid.origin[1])];
        }
        return [WORLD_PADDING, WORLD_PADDING];
    }

    function mapWorldSize(hexGrid) {
        if (!hexGrid) return { width: 1000, height: 750 };
        if (hexGrid.coordinate_space === 'norm') {
            return { width: 1000, height: 750, norm: true };
        }
        var width = Number(hexGrid.width) || 0;
        var height = Number(hexGrid.height) || 0;
        var size = effectiveHexSize(hexGrid);
        var origin = gridOrigin(hexGrid);
        var maxQ = Math.max(0, width - 1);
        var maxR = Math.max(0, height - 1);
        var spanX = size * 1.5 * maxQ + size * 0.75;
        var spanY = size * SQRT3 * (maxR + maxQ / 2);
        return {
            width: Math.ceil(origin[0] + spanX + origin[0]),
            height: Math.ceil(origin[1] + spanY + origin[1])
        };
    }

    function axialToWorld(q, r, size, originX, originY) {
        return [
            originX + size * 1.5 * q,
            originY + size * SQRT3 * (r + q / 2)
        ];
    }

    function worldToAxial(wx, wy, size, originX, originY) {
        var x = wx - originX;
        var y = wy - originY;
        var q = ((2 / 3) * x) / size;
        var r = ((-1 / 3) * x + (SQRT3 / 3) * y) / size;
        return hexRound(q, r);
    }

    function hexRound(q, r) {
        var sq = -q - r;
        var rq = Math.round(q);
        var rr = Math.round(r);
        var rs = Math.round(sq);
        var dq = Math.abs(rq - q);
        var dr = Math.abs(rr - r);
        var ds = Math.abs(rs - sq);
        if (dq > dr && dq > ds) {
            rq = -rr - rs;
        } else if (dr > ds) {
            rr = -rq - rs;
        }
        return { q: rq, r: rr };
    }

    function hexCornersWorld(cx, cy, size) {
        var pts = [];
        for (var i = 0; i < 6; i++) {
            var angle = (Math.PI / 180) * (60 * i - 30);
            pts.push([cx + size * Math.cos(angle), cy + size * Math.sin(angle)]);
        }
        return pts;
    }

    function buildCatalogFromHexGrid(hexGrid) {
        if (!hexGrid) {
            return { size: DEFAULT_HEX_SIZE, origin: [WORLD_PADDING, WORLD_PADDING], width: 0, height: 0, world: true };
        }
        var width = Number(hexGrid.width) || 0;
        var height = Number(hexGrid.height) || 0;
        var size = effectiveHexSize(hexGrid);
        var origin = gridOrigin(hexGrid);
        return {
            size: size,
            origin: [origin[0], origin[1]],
            width: width,
            height: height,
            world: isWorldSpace(hexGrid)
        };
    }

    function catalogCellCount(catalog) {
        if (!catalog) return 0;
        return (Number(catalog.width) || 0) * (Number(catalog.height) || 0);
    }

    function buildCatalog(size) {
        return buildCatalogFromHexGrid({
            coordinate_space: 'world',
            width: 200,
            height: 125,
            hex_size: size || DEFAULT_HEX_SIZE,
            origin: [WORLD_PADDING, WORLD_PADDING]
        });
    }

    function hexDisk(q, r, radius) {
        var out = [];
        for (var dq = -radius; dq <= radius; dq++) {
            for (var dr = Math.max(-radius, -dq - radius); dr <= Math.min(radius, -dq + radius); dr++) {
                out.push({ q: q + dq, r: r + dr });
            }
        }
        return out;
    }

    function hexAt(catalog, q, r) {
        var c = axialToWorld(q, r, catalog.size, catalog.origin[0], catalog.origin[1]);
        return { q: q, r: r, key: hexKey(q, r), cx: c[0], cy: c[1] };
    }

    function hexIntersectsBounds(hex, size, bounds) {
        if (!bounds) return true;
        var pad = size * 1.2;
        return hex.cx + pad >= bounds.x0 && hex.cx - pad <= bounds.x1 &&
            hex.cy + pad >= bounds.y0 && hex.cy - pad <= bounds.y1;
    }

    function axialRangeForBounds(bounds, catalog) {
        if (!bounds || !catalog) return null;
        var size = catalog.size;
        var ox = catalog.origin[0];
        var oy = catalog.origin[1];
        var corners = [
            [bounds.x0, bounds.y0],
            [bounds.x1, bounds.y0],
            [bounds.x0, bounds.y1],
            [bounds.x1, bounds.y1]
        ];
        var minQ = catalog.width;
        var maxQ = 0;
        var minR = catalog.height;
        var maxR = 0;
        corners.forEach(function (pt) {
            var a = worldToAxial(pt[0], pt[1], size, ox, oy);
            if (a.q < minQ) minQ = a.q;
            if (a.q > maxQ) maxQ = a.q;
            if (a.r < minR) minR = a.r;
            if (a.r > maxR) maxR = a.r;
        });
        var pad = 2;
        return {
            q0: Math.max(0, minQ - pad),
            q1: Math.min(catalog.width - 1, maxQ + pad),
            r0: Math.max(0, minR - pad),
            r1: Math.min(catalog.height - 1, maxR + pad)
        };
    }

    function eachVisibleHex(catalog, bounds, fn) {
        if (!catalog || !catalog.width || !catalog.height) return;
        var range;
        if (bounds) {
            range = axialRangeForBounds(bounds, catalog);
        } else if (catalogCellCount(catalog) <= LARGE_GRID_CELLS) {
            range = { q0: 0, q1: catalog.width - 1, r0: 0, r1: catalog.height - 1 };
        } else {
            return;
        }
        var r;
        var q;
        for (r = range.r0; r <= range.r1; r++) {
            for (q = range.q0; q <= range.q1; q++) {
                var hex = hexAt(catalog, q, r);
                if (hexIntersectsBounds(hex, catalog.size, bounds)) {
                    fn(hex);
                }
            }
        }
    }

    function viewportBoundsFromState(vp) {
        if (!vp || !vp.scale) return null;
        var el = vp.stageEl;
        if (!el) return null;
        var rect = el.getBoundingClientRect();
        return {
            x0: (0 - vp.panX) / vp.scale,
            y0: (0 - vp.panY) / vp.scale,
            x1: (rect.width - vp.panX) / vp.scale,
            y1: (rect.height - vp.panY) / vp.scale
        };
    }

    function buildHexMapFromCells(hexCells, catalog) {
        var map = {};
        if (!catalog || !hexCells) return map;
        var w = catalog.width || 0;
        var r;
        var q;
        for (r = 0; r < catalog.height; r++) {
            for (q = 0; q < catalog.width; q++) {
                var code = hexCells[r * w + q] || 0;
                if (code) map[hexKey(q, r)] = code;
            }
        }
        return map;
    }

    function bakeTerrainGrid(hexGrid, hexCells, gridW, gridH, encodeRle) {
        var catalog = buildCatalogFromHexGrid(hexGrid);
        var mapSize = mapWorldSize(hexGrid);
        var out = new Array(gridW * gridH);
        var i;
        for (i = 0; i < out.length; i++) out[i] = 0;
        if (!catalog.width || !catalog.height) {
            return {
                width: gridW,
                height: gridH,
                encoding: 'rle',
                cells: encodeRle(out),
                derived_from: 'hex_grid'
            };
        }
        var mapW = mapSize.width;
        var mapH = mapSize.height;
        var w = catalog.width;
        var r;
        var q;
        for (r = 0; r < catalog.height; r++) {
            for (q = 0; q < catalog.width; q++) {
                var hex = hexAt(catalog, q, r);
                var code = hexCells[r * w + q] || 0;
                fillHexOnGrid(hex, code, out, gridW, gridH, mapW, mapH, catalog.size);
            }
        }
        return {
            width: gridW,
            height: gridH,
            encoding: 'rle',
            cells: encodeRle(out),
            derived_from: 'hex_grid'
        };
    }

    function fillHexOnGrid(hex, code, cells, gridW, gridH, mapW, mapH, size) {
        var corners = hexCornersWorld(hex.cx, hex.cy, size);
        var xs = corners.map(function (p) { return p[0]; });
        var ys = corners.map(function (p) { return p[1]; });
        var minX = Math.min.apply(null, xs);
        var maxX = Math.max.apply(null, xs);
        var minY = Math.min.apply(null, ys);
        var maxY = Math.max.apply(null, ys);
        var gx0 = Math.max(0, Math.floor((minX / mapW) * gridW));
        var gx1 = Math.min(gridW - 1, Math.ceil((maxX / mapW) * gridW));
        var gy0 = Math.max(0, Math.floor((minY / mapH) * gridH));
        var gy1 = Math.min(gridH - 1, Math.ceil((maxY / mapH) * gridH));
        for (var gy = gy0; gy <= gy1; gy++) {
            for (var gx = gx0; gx <= gx1; gx++) {
                var px = ((gx + 0.5) / gridW) * mapW;
                var py = ((gy + 0.5) / gridH) * mapH;
                if (pointInPolygon(px, py, corners)) {
                    cells[gy * gridW + gx] = code;
                }
            }
        }
    }

    function pointInPolygon(px, py, polygon) {
        var inside = false;
        for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
            var xi = polygon[i][0];
            var yi = polygon[i][1];
            var xj = polygon[j][0];
            var yj = polygon[j][1];
            var intersect = ((yi > py) !== (yj > py)) &&
                (px < (xj - xi) * (py - yi) / ((yj - yi) || 1e-9) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    function drawCityStructure(svg, ns, hex, code, catalog, palette, detailSeed) {
        if (!hex || !palette) return;
        var hash = ((hex.q * 73856093) ^ (hex.r * 19349663) ^ (detailSeed || 0)) >>> 0;
        var size = catalog.size;
        var cx = hex.cx;
        var cy = hex.cy;
        var g = document.createElementNS(ns, 'g');
        g.setAttribute('class', 'map-city-structure');

        if (code === 5) {
            var variant = hash % 5;
            var bw = size * (0.42 + (variant % 3) * 0.06);
            var bh = size * (0.5 + (variant % 2) * 0.12);
            var bx = cx - bw / 2;
            var by = cy + size * 0.08 - bh;
            var body = document.createElementNS(ns, 'rect');
            body.setAttribute('x', String(bx));
            body.setAttribute('y', String(by));
            body.setAttribute('width', String(bw));
            body.setAttribute('height', String(bh));
            body.setAttribute('fill', palette.building_fill || '#8a7a68');
            body.setAttribute('stroke', palette.building_stroke || '#3a2e24');
            body.setAttribute('stroke-width', '1');
            g.appendChild(body);
            if (variant !== 3) {
                var roof = document.createElementNS(ns, 'polygon');
                var rw = bw * 1.08;
                var rh = size * 0.22;
                roof.setAttribute('points', [
                    (cx - rw / 2).toFixed(1), (by).toFixed(1),
                    cx.toFixed(1), (by - rh).toFixed(1),
                    (cx + rw / 2).toFixed(1), (by).toFixed(1)
                ].join(' '));
                roof.setAttribute('fill', palette.building_roof || '#5c4a3a');
                roof.setAttribute('stroke', palette.building_stroke || '#3a2e24');
                roof.setAttribute('stroke-width', '0.8');
                g.appendChild(roof);
            } else {
                var chimney = document.createElementNS(ns, 'rect');
                chimney.setAttribute('x', String(cx + bw * 0.2));
                chimney.setAttribute('y', String(by - size * 0.28));
                chimney.setAttribute('width', String(size * 0.1));
                chimney.setAttribute('height', String(size * 0.22));
                chimney.setAttribute('fill', palette.building_stroke || '#3a2e24');
                g.appendChild(chimney);
            }
        } else if (code === 6) {
            var wall = document.createElementNS(ns, 'rect');
            var ww = size * 0.82;
            var wh = size * 0.55;
            wall.setAttribute('x', String(cx - ww / 2));
            wall.setAttribute('y', String(cy - wh / 2));
            wall.setAttribute('width', String(ww));
            wall.setAttribute('height', String(wh));
            wall.setAttribute('fill', palette.wall_fill || '#6a5a48');
            wall.setAttribute('stroke', palette.wall_stroke || '#5b4b3c');
            wall.setAttribute('stroke-width', '1.5');
            g.appendChild(wall);
            for (var i = 0; i < 3; i++) {
                var merlon = document.createElementNS(ns, 'rect');
                var mw = size * 0.14;
                var mh = size * 0.12;
                merlon.setAttribute('x', String(cx - ww / 2 + (i + 0.3) * (ww / 3.5)));
                merlon.setAttribute('y', String(cy - wh / 2 - mh));
                merlon.setAttribute('width', String(mw));
                merlon.setAttribute('height', String(mh));
                merlon.setAttribute('fill', palette.wall_fill || '#6a5a48');
                merlon.setAttribute('stroke', palette.wall_stroke || '#5b4b3c');
                merlon.setAttribute('stroke-width', '0.8');
                g.appendChild(merlon);
            }
        } else if (code === 4) {
            var cobble = document.createElementNS(ns, 'circle');
            cobble.setAttribute('cx', String(cx));
            cobble.setAttribute('cy', String(cy));
            cobble.setAttribute('r', String(size * 0.12));
            cobble.setAttribute('fill', palette.road_stroke || '#6a5a48');
            cobble.setAttribute('opacity', '0.35');
            g.appendChild(cobble);
        }

        if (g.childNodes.length) {
            svg.appendChild(g);
        }
    }

    function drawShopStructure(svg, ns, hex, code, catalog, palette, detailSeed) {
        if (!hex || !palette) return;
        var hash = ((hex.q * 73856093) ^ (hex.r * 19349663) ^ (detailSeed || 0)) >>> 0;
        var size = catalog.size;
        var cx = hex.cx;
        var cy = hex.cy;
        var g = document.createElementNS(ns, 'g');
        g.setAttribute('class', 'map-shop-structure');

        if (code === 2) {
            var counter = document.createElementNS(ns, 'rect');
            var cw = size * 0.78;
            var ch = size * 0.28;
            counter.setAttribute('x', String(cx - cw / 2));
            counter.setAttribute('y', String(cy - ch / 2));
            counter.setAttribute('width', String(cw));
            counter.setAttribute('height', String(ch));
            counter.setAttribute('rx', String(size * 0.04));
            counter.setAttribute('fill', palette.counter_fill || '#c4a574');
            counter.setAttribute('stroke', palette.building_stroke || '#3a2e24');
            counter.setAttribute('stroke-width', '1');
            g.appendChild(counter);
        } else if (code === 3) {
            var table = document.createElementNS(ns, 'rect');
            var tw = size * 0.5;
            var th = size * 0.34;
            table.setAttribute('x', String(cx - tw / 2));
            table.setAttribute('y', String(cy - th / 2));
            table.setAttribute('width', String(tw));
            table.setAttribute('height', String(th));
            table.setAttribute('fill', palette.park || '#5f8c52');
            table.setAttribute('stroke', palette.park_stroke || '#3f6838');
            table.setAttribute('stroke-width', '0.8');
            table.setAttribute('opacity', '0.85');
            g.appendChild(table);
        } else if (code === 5) {
            var variant = hash % 4;
            var sw = size * (0.22 + (variant % 2) * 0.08);
            var sh = size * 0.62;
            var shelf = document.createElementNS(ns, 'rect');
            shelf.setAttribute('x', String(cx - sw / 2));
            shelf.setAttribute('y', String(cy - sh / 2));
            shelf.setAttribute('width', String(sw));
            shelf.setAttribute('height', String(sh));
            shelf.setAttribute('fill', palette.shelf_fill || palette.building_fill || '#9a8a72');
            shelf.setAttribute('stroke', palette.building_stroke || '#3a2e24');
            shelf.setAttribute('stroke-width', '0.8');
            g.appendChild(shelf);
            for (var si = 0; si < 3; si++) {
                var slat = document.createElementNS(ns, 'line');
                var sy = cy - sh / 2 + (si + 1) * (sh / 4);
                slat.setAttribute('x1', String(cx - sw / 2 + 1));
                slat.setAttribute('x2', String(cx + sw / 2 - 1));
                slat.setAttribute('y1', String(sy));
                slat.setAttribute('y2', String(sy));
                slat.setAttribute('stroke', palette.building_stroke || '#3a2e24');
                slat.setAttribute('stroke-width', '0.6');
                g.appendChild(slat);
            }
        } else if (code === 6 || code === 4) {
            drawCityStructure(structureLayer, ns, hex, code, catalog, palette, detailSeed);
            return;
        }

        if (g.childNodes.length) {
            svg.appendChild(g);
        }
    }

    function renderOverlay(svg, ns, catalog, hexMap, palette, isWorld, viewW, viewH, gridCellColorFn, renderOpts) {
        if (!catalog || !catalog.width || !catalog.height) return;
        renderOpts = renderOpts || {};
        var showGridLines = renderOpts.showGridLines !== false;
        var bounds = renderOpts.viewportBounds || null;
        var hexCells = renderOpts.hexCells || null;
        var detailSeed = renderOpts.detailSeed || 0;
        var interiorScope = renderOpts.scope || (isWorld ? 'world' : 'city');
        var w = catalog.width;
        var group = document.createElementNS(ns, 'g');
        group.setAttribute('class', 'map-hex-overlay');
        group.setAttribute('pointer-events', 'none');
        var structureLayer = document.createElementNS(ns, 'g');
        structureLayer.setAttribute('class', interiorScope === 'shop' ? 'map-shop-structures' : 'map-city-structures');

        eachVisibleHex(catalog, bounds, function (hex) {
            var code;
            if (hexCells) {
                code = hexCells[hex.r * w + hex.q];
            } else {
                code = hexMap[hex.key];
            }
            if (code === undefined) code = 0;
            var corners = hexCornersWorld(hex.cx, hex.cy, catalog.size);
            var points = corners.map(function (p) {
                return p[0].toFixed(1) + ',' + p[1].toFixed(1);
            }).join(' ');

            var fill = gridCellColorFn(code, palette, interiorScope);
            var poly = document.createElementNS(ns, 'polygon');
            poly.setAttribute('points', points);
            if (!isWorld && code === 0) {
                poly.setAttribute('fill', 'rgba(90,110,80,0.25)');
                poly.setAttribute('fill-opacity', '0.4');
            } else {
                poly.setAttribute('fill', fill || 'transparent');
                poly.setAttribute('fill-opacity', code === 0 ? '0.5' : '0.88');
            }
            if (showGridLines && (isWorld || code !== 5)) {
                poly.setAttribute('stroke', isWorld ? 'rgba(20,20,20,0.55)' : 'rgba(40,30,20,0.35)');
                poly.setAttribute('stroke-width', isWorld ? '1' : '0.6');
            } else {
                poly.setAttribute('stroke', 'none');
            }
            poly.setAttribute('data-hex-key', hex.key);
            group.appendChild(poly);

            if (!isWorld && (code === 5 || code === 6 || code === 4 || (interiorScope === 'shop' && (code === 2 || code === 3)))) {
                if (interiorScope === 'shop' && (code === 2 || code === 3 || code === 5)) {
                    drawShopStructure(structureLayer, ns, hex, code, catalog, palette, detailSeed + code * 17);
                } else {
                    drawCityStructure(structureLayer, ns, hex, code, catalog, palette, detailSeed + code * 17);
                }
            }
        });
        svg.appendChild(group);
        if (structureLayer.childNodes.length) {
            svg.appendChild(structureLayer);
        }
    }

    global.MapHex = {
        DEFAULT_HEX_SIZE: DEFAULT_HEX_SIZE,
        LARGE_GRID_CELLS: LARGE_GRID_CELLS,
        mapWorldSize: mapWorldSize,
        gridOrigin: gridOrigin,
        buildCatalog: buildCatalog,
        buildCatalogFromHexGrid: buildCatalogFromHexGrid,
        catalogCellCount: catalogCellCount,
        worldToAxial: worldToAxial,
        axialToWorld: axialToWorld,
        hexKey: hexKey,
        parseKey: parseKey,
        hexDisk: hexDisk,
        buildHexMapFromCells: buildHexMapFromCells,
        bakeTerrainGrid: bakeTerrainGrid,
        fillHexOnGrid: fillHexOnGrid,
        renderOverlay: renderOverlay,
        viewportBoundsFromState: viewportBoundsFromState,
        isWorldSpace: isWorldSpace
    };
})(typeof window !== 'undefined' ? window : this);

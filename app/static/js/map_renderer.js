/**
 * Shared procedural campaign map SVG renderer (world + city scopes).
 * Used by GM_Home and Player_Home — keep in sync with gm_maps style presets.
 */
(function (global) {
    'use strict';

    var STYLE_PALETTES = {
        parchment_atlas: {
            water_shallow: '#9fc9c5',
            water_deep: '#5a9aa8',
            land: '#d8c690',
            land_coast: '#e8d8a8',
            coast_stroke: '#8e7a4e',
            forest: '#2f5c2d',
            forest_stipple: '#1e3d1c',
            grassland: '#477c45',
            hill_light: '#c4b878',
            hill_shadow: '#9a8a58',
            mountain_light: '#8a8070',
            mountain_shadow: '#4a4038',
            river: '#317aa3',
            route: '#7c4a23',
            city_base: '#d8d1c3',
            district: '#b68a5f',
            district_stroke: '#7a5a3c',
            wall_stroke: '#5b4b3c',
            wall_fill: '#6a5a48',
            building_fill: '#8a7a68',
            counter_fill: '#c4a574',
            shelf_fill: '#9a8a72',
            building_roof: '#5c4a3a',
            building_stroke: '#3a2e24',
            road: '#9a8a78',
            road_stroke: '#6a5a48',
            railroad: '#4a4a4a',
            canal: '#4f9ab8',
            plaza: '#c7b38a',
            plaza_stroke: '#80643c',
            park: '#5f8c52',
            park_stroke: '#3f6838',
            region_tint: '#c084fc',
            region_stroke: '#7c3aed',
            desert: '#c9a86c',
            desert_stipple: '#a08050',
            stage_bg: '#ece3cd'
        },
        satellite: {
            water_shallow: '#4a90a4',
            water_deep: '#1a3a52',
            land: '#6b8e4e',
            land_coast: '#8fbc6f',
            coast_stroke: '#3d5c3a',
            forest: '#152e14',
            forest_stipple: '#0d2010',
            grassland: '#2a5028',
            hill_light: '#8aa870',
            hill_shadow: '#4a6840',
            mountain_light: '#a0a8b0',
            mountain_shadow: '#505860',
            river: '#2a6080',
            route: '#c4a35a',
            city_base: '#b8c4b0',
            district: '#7a9468',
            district_stroke: '#4a6840',
            wall_stroke: '#3a5038',
            wall_fill: '#4a5848',
            building_fill: '#6a7068',
            counter_fill: '#a89878',
            shelf_fill: '#7a8078',
            building_roof: '#4a5048',
            building_stroke: '#2a3028',
            road: '#8a8070',
            road_stroke: '#5a5848',
            railroad: '#5a5a58',
            canal: '#2a6080',
            plaza: '#a0b090',
            plaza_stroke: '#5a6848',
            park: '#4a7848',
            park_stroke: '#2a5028',
            region_tint: '#6090c0',
            region_stroke: '#2563eb',
            desert: '#b8a060',
            desert_stipple: '#8a7840',
            stage_bg: '#ccd4dd'
        },
        dark_fantasy: {
            water_shallow: '#2a4858',
            water_deep: '#0a1828',
            land: '#4a4038',
            land_coast: '#5a5048',
            coast_stroke: '#2a2018',
            forest: '#0a2818',
            forest_stipple: '#051810',
            grassland: '#1a3828',
            hill_light: '#5a5048',
            hill_shadow: '#2a2018',
            mountain_light: '#6a6068',
            mountain_shadow: '#2a2830',
            river: '#1a4868',
            route: '#6a4030',
            city_base: '#3a3430',
            district: '#5a4840',
            district_stroke: '#3a2820',
            wall_stroke: '#2a2018',
            wall_fill: '#3a3028',
            building_fill: '#4a4038',
            counter_fill: '#6a5848',
            shelf_fill: '#5a5048',
            building_roof: '#2a2018',
            building_stroke: '#1a1410',
            road: '#5a4840',
            road_stroke: '#3a2820',
            railroad: '#3a3430',
            canal: '#1a4868',
            plaza: '#6a5850',
            plaza_stroke: '#4a3830',
            park: '#2a4838',
            park_stroke: '#1a3028',
            region_tint: '#604080',
            region_stroke: '#c084fc',
            desert: '#5a4838',
            desert_stipple: '#3a2818',
            stage_bg: '#1a1818'
        },
        ink_sketch: {
            water_shallow: '#e8e4dc',
            water_deep: '#c8c4bc',
            land: '#f0ece4',
            land_coast: '#faf8f4',
            coast_stroke: '#2a2820',
            forest: '#484840',
            forest_stipple: '#303028',
            grassland: '#686860',
            hill_light: '#dcd8d0',
            hill_shadow: '#a8a4a0',
            mountain_light: '#888480',
            mountain_shadow: '#484440',
            river: '#686860',
            route: '#404040',
            city_base: '#ece8e0',
            district: '#d0ccc4',
            district_stroke: '#686860',
            wall_stroke: '#404040',
            wall_fill: '#a8a4a0',
            building_fill: '#c8c4bc',
            counter_fill: '#d8ccb0',
            shelf_fill: '#b8b4ac',
            building_roof: '#888480',
            building_stroke: '#484440',
            road: '#b8b4ac',
            road_stroke: '#787470',
            railroad: '#686460',
            canal: '#989490',
            plaza: '#e0dcd4',
            plaza_stroke: '#585450',
            park: '#989890',
            park_stroke: '#686860',
            region_tint: '#a0a0a8',
            region_stroke: '#52525b',
            desert: '#c8c0b0',
            desert_stipple: '#a8a098',
            stage_bg: '#f4f0e8'
        }
    };

    var STAGE_PALETTES = Object.keys(STYLE_PALETTES);

    function decodeTerrainRle(cellsSpec, expectedLen) {
        var out = [];
        if (!cellsSpec) return out;
        cellsSpec.split(',').forEach(function (segment) {
            segment = segment.trim();
            if (!segment) return;
            var parts = segment.split(':');
            if (parts.length !== 2) return;
            var code = parseInt(parts[0], 10);
            var count = parseInt(parts[1], 10);
            for (var i = 0; i < count; i++) out.push(code);
        });
        if (expectedLen && out.length !== expectedLen) return [];
        return out;
    }

    function encodeTerrainRle(cells) {
        if (!cells || !cells.length) return '0:0';
        var parts = [];
        var current = cells[0];
        var count = 1;
        for (var i = 1; i < cells.length; i++) {
            if (cells[i] === current) {
                count += 1;
            } else {
                parts.push(current + ':' + count);
                current = cells[i];
                count = 1;
            }
        }
        parts.push(current + ':' + count);
        return parts.join(',');
    }

    function gridCellColor(code, palette, scope) {
        var mapScope = scope === true ? 'world' : (scope === false ? 'city' : (scope || 'city'));
        if (mapScope === 'world') {
            if (code === 0) return null;
            if (code === 1) return palette.land;
            if (code === 2) return palette.mountain_light;
            if (code === 3) return palette.forest;
            if (code === 4) return palette.desert || palette.land_coast;
            if (code === 5) return palette.grassland || palette.forest;
            if (code === 6) return palette.hill_light;
            return null;
        }
        if (code === 0) return null;
        if (mapScope === 'shop') {
            if (code === 1) return palette.plaza || palette.district;
            if (code === 2) return palette.counter_fill || palette.district;
            if (code === 3) return palette.park;
            if (code === 4) return palette.road;
            if (code === 5) return palette.shelf_fill || palette.building_fill || palette.district;
            if (code === 6) return palette.wall_fill || palette.district_stroke;
            return null;
        }
        if (code === 1) return palette.plaza || palette.district;
        if (code === 2) return palette.canal;
        if (code === 3) return palette.park;
        if (code === 4) return palette.road;
        if (code === 5) return palette.building_fill || palette.district;
        if (code === 6) return palette.wall_fill || palette.district_stroke;
        return null;
    }

    function renderTerrainGrid(svg, ns, grid, palette, scope, viewW, viewH) {
        if (!grid || grid.encoding !== 'rle') return;
        var width = Number(grid.width) || 256;
        var height = Number(grid.height) || 192;
        var cells = decodeTerrainRle(grid.cells, width * height);
        if (cells.length !== width * height) return;

        var cellW = viewW / width;
        var cellH = viewH / height;
        var group = document.createElementNS(ns, 'g');
        group.setAttribute('class', 'map-terrain-grid');

        for (var gy = 0; gy < height; gy++) {
            var gx = 0;
            while (gx < width) {
                var code = cells[gy * width + gx];
                var fill = gridCellColor(code, palette, scope);
                if (!fill) {
                    gx += 1;
                    continue;
                }
                var runStart = gx;
                gx += 1;
                while (gx < width && cells[gy * width + gx] === code) {
                    gx += 1;
                }
                var rect = document.createElementNS(ns, 'rect');
                rect.setAttribute('x', String(runStart * cellW));
                rect.setAttribute('y', String(gy * cellH));
                rect.setAttribute('width', String((gx - runStart) * cellW));
                rect.setAttribute('height', String(cellH + 0.5));
                rect.setAttribute('fill', fill);
                rect.setAttribute('opacity', '0.92');
                group.appendChild(rect);
            }
        }
        svg.appendChild(group);
    }

    function resolvePalette(gen) {
        var preset = gen.style_preset || gen.palette || 'parchment_atlas';
        if (!STYLE_PALETTES[preset]) {
            preset = 'parchment_atlas';
        }
        var base = Object.assign({}, STYLE_PALETTES[preset]);
        if (gen.render_palette) {
            return Object.assign(base, gen.render_palette);
        }
        return base;
    }

    function scaledPoint(p, viewW, viewH) {
        return [Number(p[0]) * viewW, Number(p[1]) * viewH];
    }

    function pointsAttr(points, viewW, viewH) {
        return (points || []).map(function (pt) {
            var sp = scaledPoint(pt, viewW, viewH);
            return sp[0].toFixed(1) + ',' + sp[1].toFixed(1);
        }).join(' ');
    }

    function appendDefs(svg, ns, palette, detailSeed) {
        var defs = document.createElementNS(ns, 'defs');
        var uid = String(detailSeed || 0);

        var waterGrad = document.createElementNS(ns, 'radialGradient');
        waterGrad.setAttribute('id', 'map-water-' + uid);
        waterGrad.setAttribute('cx', '50%');
        waterGrad.setAttribute('cy', '45%');
        waterGrad.setAttribute('r', '75%');
        var ws = document.createElementNS(ns, 'stop');
        ws.setAttribute('offset', '0%');
        ws.setAttribute('stop-color', palette.water_shallow);
        waterGrad.appendChild(ws);
        var wd = document.createElementNS(ns, 'stop');
        wd.setAttribute('offset', '100%');
        wd.setAttribute('stop-color', palette.water_deep);
        waterGrad.appendChild(wd);
        defs.appendChild(waterGrad);

        var coastGrad = document.createElementNS(ns, 'linearGradient');
        coastGrad.setAttribute('id', 'map-coast-' + uid);
        coastGrad.setAttribute('x1', '0%');
        coastGrad.setAttribute('y1', '0%');
        coastGrad.setAttribute('x2', '100%');
        coastGrad.setAttribute('y2', '100%');
        var cl = document.createElementNS(ns, 'stop');
        cl.setAttribute('offset', '0%');
        cl.setAttribute('stop-color', palette.land_coast || palette.land);
        coastGrad.appendChild(cl);
        var cd = document.createElementNS(ns, 'stop');
        cd.setAttribute('offset', '100%');
        cd.setAttribute('stop-color', palette.land);
        coastGrad.appendChild(cd);
        defs.appendChild(coastGrad);

        var hillGrad = document.createElementNS(ns, 'linearGradient');
        hillGrad.setAttribute('id', 'map-hill-' + uid);
        hillGrad.setAttribute('x1', '0%');
        hillGrad.setAttribute('y1', '0%');
        hillGrad.setAttribute('x2', '100%');
        hillGrad.setAttribute('y2', '100%');
        var hl = document.createElementNS(ns, 'stop');
        hl.setAttribute('offset', '0%');
        hl.setAttribute('stop-color', palette.hill_light);
        hillGrad.appendChild(hl);
        var hs = document.createElementNS(ns, 'stop');
        hs.setAttribute('offset', '100%');
        hs.setAttribute('stop-color', palette.hill_shadow);
        hillGrad.appendChild(hs);
        defs.appendChild(hillGrad);

        var stipple = document.createElementNS(ns, 'pattern');
        stipple.setAttribute('id', 'map-forest-stipple-' + uid);
        stipple.setAttribute('width', '8');
        stipple.setAttribute('height', '8');
        stipple.setAttribute('patternUnits', 'userSpaceOnUse');
        var phase = (detailSeed || 0) % 8;
        stipple.setAttribute('patternTransform', 'translate(' + phase + ' ' + phase + ')');
        var dot = document.createElementNS(ns, 'circle');
        dot.setAttribute('cx', '2');
        dot.setAttribute('cy', '2');
        dot.setAttribute('r', '1.2');
        dot.setAttribute('fill', palette.forest_stipple || palette.forest);
        dot.setAttribute('opacity', '0.55');
        stipple.appendChild(dot);
        defs.appendChild(stipple);

        svg.appendChild(defs);
        return uid;
    }

    function cellBiomeFill(cell, palette, isWorld) {
        var code = Number(cell.terrain_code);
        if (isWorld) {
            if (code === 0) return null;
            if (code === 2) return palette.mountain_light;
            if (code === 3) return palette.forest;
            if (code === 4) return palette.desert || palette.land_coast;
            if (code === 5) return palette.grassland || palette.forest;
            if (code === 6) return palette.hill_light;
            return palette.land;
        }
        if (code === 0) return null;
        if (code === 2) return palette.canal;
        if (code === 3) return palette.park;
        if (code === 4) return palette.road;
        return palette.district;
    }

    function renderCellBorders(svg, ns, cellGraph, palette, viewW, viewH) {
        if (!cellGraph || !cellGraph.cells || !cellGraph.cells.length) return;
        var group = document.createElementNS(ns, 'g');
        group.setAttribute('class', 'map-cell-borders');
        group.setAttribute('pointer-events', 'none');
        cellGraph.cells.forEach(function (cell) {
            var poly = cell.polygon;
            if (!poly || poly.length < 3) return;
            if (Number(cell.terrain_code) === 0) return;
            var el = document.createElementNS(ns, 'polygon');
            el.setAttribute('points', pointsAttr(poly, viewW, viewH));
            el.setAttribute('fill', 'none');
            el.setAttribute('stroke', palette.coast_stroke || '#666');
            el.setAttribute('stroke-width', '0.35');
            el.setAttribute('opacity', '0.35');
            group.appendChild(el);
        });
        svg.appendChild(group);
    }

    function renderCellGraph(svg, ns, cellGraph, palette, isWorld, viewW, viewH) {
        if (!cellGraph || !cellGraph.cells || !cellGraph.cells.length) return;
        var group = document.createElementNS(ns, 'g');
        group.setAttribute('class', 'map-cell-graph');
        cellGraph.cells.forEach(function (cell) {
            var poly = cell.polygon;
            if (!poly || poly.length < 3) return;
            var fill = cellBiomeFill(cell, palette, isWorld);
            if (!fill) return;
            var el = document.createElementNS(ns, 'polygon');
            el.setAttribute('points', pointsAttr(poly, viewW, viewH));
            el.setAttribute('fill', fill);
            el.setAttribute('stroke', palette.coast_stroke || '#666');
            el.setAttribute('stroke-width', '0.5');
            el.setAttribute('opacity', '0.88');
            el.setAttribute('data-cell-id', String(cell.id));
            group.appendChild(el);
        });
        svg.appendChild(group);
    }

    function riverBezierFromPath(cells, path, viewW, viewH) {
        var pts = [];
        (path || []).forEach(function (cid) {
            var cell = (cells || []).find(function (c) { return Number(c.id) === Number(cid); });
            if (cell && cell.centroid) {
                pts.push(scaledPoint(cell.centroid, viewW, viewH));
            }
        });
        return pts;
    }

    function render(generation, containerEl, stageEl, options) {
        options = options || {};
        var gen = generation || {};
        var mapSize = (global.MapHex && gen.hex_grid)
            ? global.MapHex.mapWorldSize(gen.hex_grid)
            : null;
        var viewW = options.viewWidth || (mapSize && !mapSize.norm ? mapSize.width : 1000);
        var viewH = options.viewHeight || (mapSize && !mapSize.norm ? mapSize.height : 750);

        if (stageEl) {
            STAGE_PALETTES.forEach(function (p) {
                stageEl.classList.remove('map-palette-' + p);
            });
            var preset = gen.style_preset || gen.palette || 'parchment_atlas';
            if (STYLE_PALETTES[preset]) {
                stageEl.classList.add('map-palette-' + preset);
                stageEl.style.background = STYLE_PALETTES[preset].stage_bg || '';
            }
        }

        if (!containerEl) return;

        containerEl.innerHTML = '';
        var palette = resolvePalette(gen);
        var ns = 'http://www.w3.org/2000/svg';
        var svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('class', 'map-gen-svg');
        svg.setAttribute('viewBox', '0 0 ' + viewW + ' ' + viewH);
        svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
        svg.style.pointerEvents = 'none';

        var detailSeed = gen.detail_seed || gen.seed || 0;
        var uid = appendDefs(svg, ns, palette, detailSeed);
        var isWorld = gen.scope === 'world';
        var mapScope = gen.scope || 'world';

        function poly(points, fill, stroke, opacity, width, fillUrl) {
            var el = document.createElementNS(ns, 'polygon');
            el.setAttribute('points', pointsAttr(points, viewW, viewH));
            if (fillUrl) {
                el.setAttribute('fill', fillUrl);
            } else {
                el.setAttribute('fill', fill);
            }
            el.setAttribute('stroke', stroke || 'none');
            el.setAttribute('stroke-width', width == null ? '2' : String(width));
            el.setAttribute('opacity', opacity == null ? '1' : String(opacity));
            svg.appendChild(el);
            return el;
        }

        function line(points, stroke, width, dash, opacity) {
            var el = document.createElementNS(ns, 'polyline');
            el.setAttribute('points', pointsAttr(points, viewW, viewH));
            el.setAttribute('fill', 'none');
            el.setAttribute('stroke', stroke);
            el.setAttribute('stroke-width', String(width || 4));
            el.setAttribute('stroke-linecap', 'round');
            el.setAttribute('stroke-linejoin', 'round');
            if (dash) el.setAttribute('stroke-dasharray', dash);
            el.setAttribute('opacity', opacity == null ? '1' : String(opacity));
            svg.appendChild(el);
            return el;
        }

        function circle(x, y, size, fill, stroke, opacity) {
            var el = document.createElementNS(ns, 'circle');
            el.setAttribute('cx', String(Number(x) * viewW));
            el.setAttribute('cy', String(Number(y) * viewH));
            el.setAttribute('r', String(Number(size || 0.05) * (viewW / 2)));
            el.setAttribute('fill', fill);
            el.setAttribute('stroke', stroke || 'none');
            el.setAttribute('stroke-width', '3');
            el.setAttribute('opacity', opacity == null ? '1' : String(opacity));
            svg.appendChild(el);
            return el;
        }

        function mountains(points, peakScales) {
            (points || []).forEach(function (p, idx) {
                var sp = scaledPoint(p, viewW, viewH);
                var scale = (peakScales && peakScales[idx]) ? Number(peakScales[idx]) : 1;
                var h = 18 * scale;
                var w = 16 * scale;
                var layers = [
                    { dy: 4, h: h * 0.7, fill: palette.mountain_shadow, opacity: 0.5 },
                    { dy: 0, h: h, fill: palette.mountain_light, opacity: 0.85 },
                    { dy: -2, h: h * 0.55, fill: palette.mountain_shadow, opacity: 0.65 }
                ];
                layers.forEach(function (layer) {
                    var tri = [
                        [sp[0] - w, sp[1] + 18 + layer.dy],
                        [sp[0], sp[1] - layer.h + layer.dy],
                        [sp[0] + w, sp[1] + 18 + layer.dy]
                    ].map(function (v) {
                        return v[0].toFixed(1) + ',' + v[1].toFixed(1);
                    }).join(' ');
                    var el = document.createElementNS(ns, 'polygon');
                    el.setAttribute('points', tri);
                    el.setAttribute('fill', layer.fill);
                    el.setAttribute('stroke', palette.mountain_shadow);
                    el.setAttribute('stroke-width', '1.5');
                    el.setAttribute('opacity', String(layer.opacity));
                    svg.appendChild(el);
                });
            });
        }

        if (isWorld) {
            var waterBase = document.createElementNS(ns, 'rect');
            waterBase.setAttribute('width', String(viewW));
            waterBase.setAttribute('height', String(viewH));
            waterBase.setAttribute('fill', 'url(#map-water-' + uid + ')');
            waterBase.setAttribute('opacity', '0.92');
            svg.appendChild(waterBase);

            var shelf = document.createElementNS(ns, 'rect');
            shelf.setAttribute('x', String(viewW * 0.08));
            shelf.setAttribute('y', String(viewH * 0.12));
            shelf.setAttribute('width', String(viewW * 0.84));
            shelf.setAttribute('height', String(viewH * 0.76));
            shelf.setAttribute('fill', palette.water_shallow);
            shelf.setAttribute('opacity', '0.35');
            shelf.setAttribute('rx', '40');
            svg.appendChild(shelf);
        } else {
            var cityBase = document.createElementNS(ns, 'rect');
            cityBase.setAttribute('width', String(viewW));
            cityBase.setAttribute('height', String(viewH));
            cityBase.setAttribute('fill', palette.city_base || '#d8d1c3');
            cityBase.setAttribute('opacity', '0.35');
            svg.appendChild(cityBase);
        }

        var coastFill = 'url(#map-coast-' + uid + ')';
        var hillFill = 'url(#map-hill-' + uid + ')';
        var forestPattern = 'url(#map-forest-stipple-' + uid + ')';
        var hasGrid = !!(gen.terrain_grid && gen.terrain_grid.cells);
        var showHexGrid = !!(options.showHexGrid && global.MapHex);

        if (showHexGrid && options.hexCatalog && (options.hexMap || options.hexCells)) {
            var vpBounds = options.viewportBounds || null;
            global.MapHex.renderOverlay(
                svg, ns, options.hexCatalog, options.hexMap || {},
                palette, isWorld, viewW, viewH, gridCellColor,
                {
                    showGridLines: options.showGridLines !== false,
                    viewportBounds: vpBounds,
                    hexCells: options.hexCells || null,
                    detailSeed: detailSeed,
                    scope: mapScope
                }
            );
        } else if (hasGrid) {
            renderTerrainGrid(svg, ns, gen.terrain_grid, palette, mapScope, viewW, viewH);
        }

        var skipBasePoly = hasGrid ? {
            landmass: true,
            island: true,
            district: true,
            park: true,
            city_wall: true,
            forest: true,
            grassland: true,
            hill: true,
            mountain_range: true,
            lake: true
        } : {};

        function renderLineFeature(f) {
            if (f.type === 'river') {
                line(f.points, palette.river, 7, null, 0.75);
            } else if (f.type === 'trade_route') {
                line(f.points, palette.route, 4, '10 10', 0.7);
            } else if (f.type === 'road') {
                line(f.points, palette.road, 8, null, 0.82);
            } else if (f.type === 'railroad') {
                line(f.points, palette.railroad || '#4a4a4a', 5, '6 5', 0.88);
            } else if (f.type === 'canal') {
                line(f.points, palette.canal, 10, null, 0.68);
            } else {
                return false;
            }
            return true;
        }

        (gen.features || []).forEach(function (f) {
            if (renderLineFeature(f)) return;
            if (skipBasePoly[f.type]) return;
            if (f.type === 'landmass') {
                poly(f.points, palette.land, palette.coast_stroke, 0.96, 5, coastFill);
            } else if (f.type === 'island') {
                poly(f.points, palette.land, palette.coast_stroke, 0.9, 3, coastFill);
            } else if (f.type === 'region_tint') {
                var fillColor = f.main_color || palette.region_tint || '#c084fc';
                var borderColor = f.secondary_color || palette.region_stroke || '#7c3aed';
                var regionStroke = f.region_id != null ? borderColor : 'none';
                var regionStrokeW = f.region_id != null ? 3 : 0;
                var fillOpacity = f.region_id != null ? 0.22 : 0.12;
                poly(
                    f.points,
                    fillColor,
                    regionStroke,
                    fillOpacity,
                    regionStrokeW
                );
            } else if (f.type === 'hill') {
                poly(f.points, hillFill, palette.hill_shadow, 0.55, 1);
            } else if (f.type === 'forest') {
                poly(f.points, palette.forest, palette.forest_stipple, 0.42, 2);
                poly(f.points, forestPattern, 'none', 0.35, 0);
            } else if (f.type === 'grassland') {
                poly(f.points, palette.grassland || palette.forest, palette.forest_stipple, 0.38, 1);
            } else if (f.type === 'lake') {
                poly(f.points, palette.water_deep, palette.river, 0.82, 2);
            } else if (f.type === 'mountain_range') {
                mountains(f.points, f.peak_scale);
            } else if (f.type === 'city_wall') {
                poly(f.points, 'none', palette.wall_stroke, 1, 8);
            } else if (f.type === 'district') {
                poly(f.points, palette.district, palette.district_stroke, 0.42, 2);
            } else if (f.type === 'plaza') {
                if (gen.scope === 'city' && hasGrid) {
                    return;
                }
                circle(f.x, f.y, f.size, palette.plaza, palette.plaza_stroke, 0.8);
            } else if (f.type === 'park') {
                poly(f.points, palette.park, palette.park_stroke, 0.45, 2);
            }
        });

        containerEl.appendChild(svg);
    }

    global.MapRenderer = {
        render: render,
        STYLE_PALETTES: STYLE_PALETTES,
        decodeTerrainRle: decodeTerrainRle,
        encodeTerrainRle: encodeTerrainRle,
        emptyTerrainGrid: function (width, height) {
            width = width || 256;
            height = height || 192;
            return {
                width: width,
                height: height,
                encoding: 'rle',
                cells: encodeTerrainRle(new Array(width * height).fill(0))
            };
        }
    };
})(typeof window !== 'undefined' ? window : this);

/**
 * Keeps --gm-hud-height aligned with the rendered top HUD so map tools and
 * world-stage chrome sit below the bar on wrapped/mobile layouts.
 */
(function () {
    'use strict';

    var HUD_IDS = ['gm-top-hud', 'player-top-hud'];
    var ro = null;

    function findHud() {
        for (var i = 0; i < HUD_IDS.length; i += 1) {
            var el = document.getElementById(HUD_IDS[i]);
            if (el) return el;
        }
        return null;
    }

    function syncHudHeight() {
        var hud = findHud();
        if (!hud) return;
        var height = Math.ceil(hud.getBoundingClientRect().height);
        if (height > 0) {
            document.documentElement.style.setProperty('--gm-hud-height', height + 'px');
        }
    }

    function install() {
        var hud = findHud();
        if (!hud) return;

        syncHudHeight();

        if (typeof ResizeObserver !== 'undefined') {
            if (ro) ro.disconnect();
            ro = new ResizeObserver(syncHudHeight);
            ro.observe(hud);
        }

        window.addEventListener('resize', syncHudHeight, { passive: true });

        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(syncHudHeight).catch(function () {});
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', install);
    } else {
        install();
    }
})();

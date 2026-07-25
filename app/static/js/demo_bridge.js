/**
 * Shared Try-Demo continuation state (sessionStorage).
 * Used when the walkthrough leaves the GM dashboard for campaigns / player UI.
 */
(function (global) {
    'use strict';
    var KEY = 'ef_demo_bridge';

    function read() {
        try {
            return JSON.parse(sessionStorage.getItem(KEY) || '{}') || {};
        } catch (err) {
            return {};
        }
    }

    function write( partial ) {
        var cur = read();
        Object.keys(partial || {}).forEach(function (k) {
            cur[k] = partial[k];
        });
        try {
            sessionStorage.setItem(KEY, JSON.stringify(cur));
        } catch (err2) { /* ignore */ }
        return cur;
    }

    function clear() {
        try {
            sessionStorage.removeItem(KEY);
        } catch (err) { /* ignore */ }
    }

    global.EFDemoBridge = {
        KEY: KEY,
        read: read,
        write: write,
        clear: clear,
        isActive: function () {
            var d = read();
            return !!d.active;
        }
    };
})(window);

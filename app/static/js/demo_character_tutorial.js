/**
 * Demo continuation on character create — restore NPC draft, lock nav, highlight Create.
 */
(function () {
    'use strict';
    if (!window.EFDemoBridge || !window.EFDemoBridge.isActive()) return;

    function injectStyles() {
        if (document.getElementById('demo-character-tutorial-style')) return;
        var style = document.createElement('style');
        style.id = 'demo-character-tutorial-style';
        style.textContent =
            '.demo-city-view-popout{position:fixed;z-index:2147483001;width:min(320px,calc(100vw - 24px));' +
            'padding:.85rem 1rem;border-radius:10px;background:rgba(22,27,34,.97);color:#f3f5f7;box-shadow:0 8px 28px rgba(0,0,0,.45);}' +
            '.demo-city-view-popout--center{left:50%;top:50%;transform:translate(-50%,-50%);}' +
            '.demo-draw-highlight{outline:2px solid #9ecbff!important;outline-offset:2px;}' +
            'body.demo-character-create #wizard-next,' +
            'body.demo-character-create #wizard-back,' +
            'body.demo-character-create #wizard-next.demo-wizard-nav-locked,' +
            'body.demo-character-create #wizard-back.demo-wizard-nav-locked{' +
            'opacity:.4!important;pointer-events:none!important;filter:grayscale(.45)!important;' +
            'cursor:not-allowed!important;box-shadow:none!important;}' +
            'body.demo-character-create #wizard-create.demo-allowed-create{' +
            'opacity:1!important;pointer-events:auto!important;filter:none!important;cursor:pointer!important;}';
        document.head.appendChild(style);
    }

    function ensureCoach() {
        if (document.getElementById('demo-tutorial-root')) return;
        var root = document.createElement('div');
        root.id = 'demo-tutorial-root';
        root.innerHTML =
            '<aside id="demo-tutorial-coach" class="demo-tutorial-coach" role="status">' +
            '<div class="demo-coach-nav">' +
            '<button type="button" class="button" id="demo-coach-forward">Forward</button>' +
            '</div>' +
            '<h2 id="demo-coach-heading">Demo</h2>' +
            '<p id="demo-coach-body"></p></aside>';
        document.body.appendChild(root);
    }

    injectStyles();
    ensureCoach();

    var bridge = window.EFDemoBridge.read() || {};
    document.body.classList.add('demo-character-create');
    document.body.setAttribute('data-demo-phase', 'character_create');
    window.EFDemoBridge.write({ phase: 'character_create', active: true });

    var coachHeading = document.getElementById('demo-coach-heading');
    var coachBody = document.getElementById('demo-coach-body');
    var forwardBtn = document.getElementById('demo-coach-forward');

    function lockWizardNav() {
        ['wizard-next', 'wizard-back'].forEach(function (id) {
            var btn = document.getElementById(id);
            if (!btn) return;
            btn.classList.add('demo-wizard-nav-locked');
            btn.setAttribute('aria-disabled', 'true');
            btn.tabIndex = -1;
            btn.style.setProperty('opacity', '0.4', 'important');
            btn.style.setProperty('pointer-events', 'none', 'important');
            btn.style.setProperty('filter', 'grayscale(0.45)', 'important');
            btn.style.setProperty('cursor', 'not-allowed', 'important');
        });
    }

    function hidePopout() {
        var el = document.getElementById('demo-city-view-popout');
        if (el) el.remove();
    }

    function showPopout() {
        hidePopout();
        var el = document.createElement('aside');
        el.id = 'demo-city-view-popout';
        el.className = 'demo-city-view-popout demo-city-view-popout--center';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<strong>Player character ready</strong>' +
            '<p>Because you already built a nation ruler in the NPC wizard, this character starts with the same identity details.</p>' +
            '<ul>' +
            '<li><strong>Same flow</strong> — species, class, and abilities follow the D&amp;D 5e wizard you used for NPCs.</li>' +
            '<li><strong>Campaign seat</strong> — redeeming the CAMP- code attached this profile to the demo campaign.</li>' +
            '</ul>' +
            '<p>Click <strong>Create character</strong> (or Forward) to finish and return to Campaigns.</p>';
        document.body.appendChild(el);
    }

    function highlightCreate(createBtn) {
        if (!createBtn) return;
        createBtn.hidden = false;
        createBtn.classList.add('demo-draw-highlight', 'demo-allowed-create');
        createBtn.addEventListener('click', function () {
            window.EFDemoBridge.write({ phase: 'player_card', active: true });
        }, true);
    }

    function prepareCreateStep() {
        var hydrated = false;
        if (typeof window.EFDemoHydrateCharacterWizard === 'function') {
            hydrated = !!window.EFDemoHydrateCharacterWizard();
        }
        lockWizardNav();
        var create = document.getElementById('wizard-create');
        var next = document.getElementById('wizard-next');
        if (hydrated && create) {
            create.hidden = false;
            if (next) next.hidden = true;
            highlightCreate(create);
            if (coachBody) {
                coachBody.textContent =
                    'Next and Back are locked. Click Create character (highlighted) to finish setup.';
            }
            return;
        }
        if (coachBody) {
            coachBody.textContent =
                'Could not restore the ruler sheet yet. Wait a moment, or use Forward once Create character highlights.';
        }
        if (create && !create.hidden) highlightCreate(create);
    }

    if (coachHeading) coachHeading.textContent = 'Step 12 — Character setup';
    if (coachBody) {
        coachBody.textContent =
            'Next and Back are locked. Click Create character (highlighted) to finish setup.';
    }
    showPopout();
    prepareCreateStep();
    // Wizard init may race; re-apply after a tick.
    setTimeout(prepareCreateStep, 50);
    setTimeout(prepareCreateStep, 250);

    if (forwardBtn) {
        forwardBtn.hidden = false;
        forwardBtn.disabled = false;
        forwardBtn.classList.add('demo-allowed-forward', 'demo-draw-highlight');
        forwardBtn.addEventListener('click', function () {
            window.EFDemoBridge.write({ phase: 'player_card', active: true });
            var createBtn = document.getElementById('wizard-create');
            if (createBtn) {
                createBtn.hidden = false;
                createBtn.click();
                return;
            }
            window.location.href = '/campaigns';
        });
    }

    document.addEventListener('click', function (ev) {
        var t = ev.target;
        if (!t || !t.closest) return;
        if (t.closest('#demo-tutorial-root') || t.closest('#demo-city-view-popout')) return;
        if (t.closest('#wizard-create.demo-allowed-create') || t.closest('.demo-allowed-create')) return;
        if (t.closest('#accountAvatarBtn')) return;
        if (t.closest('#accountPopoverPanel a.menu-btn-danger-outline')) return;
        var interactive = t.closest('button, a, input, select, textarea, label.button');
        if (!interactive) return;
        if (interactive.id === 'wizard-next' || interactive.id === 'wizard-back' ||
                interactive.classList.contains('demo-wizard-nav-locked')) {
            ev.preventDefault();
            ev.stopPropagation();
            return;
        }
        if (interactive.closest('.wizard-actions, .wizard-action, #dnd5e-wizard')) {
            if (interactive.id === 'wizard-create') return;
            ev.preventDefault();
            ev.stopPropagation();
        }
    }, true);
})();

/**
 * Demo continuation on /campaigns — redeem CAMP code, then highlight player card.
 */
(function () {
    'use strict';
    if (!window.EFDemoBridge || !window.EFDemoBridge.isActive()) return;

    function ensureCoach() {
        if (document.getElementById('demo-tutorial-root')) return;
        var root = document.createElement('div');
        root.id = 'demo-tutorial-root';
        root.innerHTML =
            '<aside id="demo-tutorial-coach" class="demo-tutorial-coach" role="status">' +
            '<div class="demo-coach-nav">' +
            '<button type="button" class="button" id="demo-coach-forward" hidden disabled>Forward</button>' +
            '</div>' +
            '<h2 id="demo-coach-heading">Demo</h2>' +
            '<p id="demo-coach-body"></p></aside>';
        document.body.appendChild(root);
        var style = document.createElement('style');
        style.textContent =
            '.demo-tutorial-coach{position:fixed;z-index:2147483002;right:16px;bottom:16px;width:min(340px,calc(100vw - 24px));' +
            'padding:0.9rem 1rem;border-radius:10px;border:1px solid rgba(255,255,255,.16);background:rgba(22,27,34,.97);color:#f3f5f7;}' +
            '.demo-tutorial-coach h2{margin:0 0 .35rem;font-size:1rem;color:#9ecbff;}' +
            '.demo-draw-highlight{outline:2px solid #9ecbff!important;outline-offset:2px;}' +
            '.campaign-row.demo-allowed-player-card{outline:2px solid #9ecbff!important;outline-offset:3px;' +
            'box-shadow:0 0 0 3px rgba(158,203,255,.25);}';
        document.head.appendChild(style);
    }
    ensureCoach();

    var bridge = window.EFDemoBridge.read() || {};
    var phase = bridge.phase || 'campaigns_redeem';
    if (phase === 'player_tour' || phase === 'complete' || phase === 'character_create') {
        return;
    }
    document.body.classList.add('demo-campaigns-page');
    document.body.setAttribute('data-demo-phase', phase);

    var coachHeading = document.getElementById('demo-coach-heading');
    var coachBody = document.getElementById('demo-coach-body');
    var forwardBtn = document.getElementById('demo-coach-forward');

    var arrowRoot = document.createElement('div');
    arrowRoot.id = 'demo-tutorial-arrow';
    arrowRoot.setAttribute('aria-hidden', 'true');
    arrowRoot.innerHTML = '<div class="demo-arrow-shaft"></div><div class="demo-arrow-head"></div>';
    document.body.appendChild(arrowRoot);
    var arrowShaft = arrowRoot.querySelector('.demo-arrow-shaft');
    var arrowHead = arrowRoot.querySelector('.demo-arrow-head');
    var arrowTarget = null;
    var mouse = { x: window.innerWidth * 0.55, y: window.innerHeight * 0.55 };
    document.addEventListener('mousemove', function (ev) {
        mouse.x = ev.clientX;
        mouse.y = ev.clientY;
    });

    function pointArrowAt(el) {
        arrowTarget = el || null;
        if (!arrowTarget) {
            arrowRoot.hidden = true;
            return;
        }
        arrowRoot.hidden = false;
        function draw() {
            if (!arrowTarget) return;
            var rect = arrowTarget.getBoundingClientRect();
            if (rect.width < 2 && rect.height < 2) {
                arrowRoot.hidden = true;
                requestAnimationFrame(draw);
                return;
            }
            arrowRoot.hidden = false;
            var tx = rect.left + rect.width / 2;
            var ty = rect.top + Math.min(rect.height / 2, 28);
            var dx = tx - mouse.x;
            var dy = ty - mouse.y;
            var len = Math.sqrt(dx * dx + dy * dy) || 1;
            var x1 = mouse.x + (dx / len) * Math.min(28, len * 0.15);
            var y1 = mouse.y + (dy / len) * Math.min(28, len * 0.15);
            var x2 = tx - (dx / len) * Math.min(10, len * 0.08);
            var y2 = ty - (dy / len) * Math.min(10, len * 0.08);
            var shaftLen = Math.sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1));
            if (shaftLen < 12) {
                arrowRoot.hidden = true;
            } else {
                var angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
                arrowShaft.style.width = shaftLen + 'px';
                arrowShaft.style.left = x1 + 'px';
                arrowShaft.style.top = y1 + 'px';
                arrowShaft.style.transform = 'rotate(' + angle + 'deg)';
                arrowHead.style.left = x2 + 'px';
                arrowHead.style.top = y2 + 'px';
                arrowHead.style.transform = 'translate(-50%, -50%) rotate(' + angle + 'deg)';
            }
            requestAnimationFrame(draw);
        }
        requestAnimationFrame(draw);
    }

    function findPlayerCampaignRow() {
        var section = null;
        document.querySelectorAll('h2.section-header').forEach(function (h) {
            if (/player campaigns/i.test(h.textContent || '')) section = h;
        });
        var root = section && section.closest('.content-container');
        if (!root) {
            var rows = document.querySelectorAll('.campaign-row[data-href*="as=player"], .campaign-row[data-href*="as%3Dplayer"]');
            return rows.length ? rows[rows.length - 1] : document.querySelector('.campaign-row[data-href]');
        }
        var playerRows = root.querySelectorAll('.campaign-row[data-href]');
        if (!playerRows.length) return null;
        if (bridge.playerId) {
            for (var i = 0; i < playerRows.length; i++) {
                var href = playerRows[i].getAttribute('data-href') || '';
                if (href.indexOf(String(bridge.playerId)) !== -1) return playerRows[i];
            }
        }
        return playerRows[0];
    }

    function enterPlayerCardPhase() {
        phase = 'player_card';
        document.body.setAttribute('data-demo-phase', 'player_card');
        window.EFDemoBridge.write({ phase: 'player_card', active: true });
        if (coachHeading) coachHeading.textContent = 'Step 12.1 — Open as player';
        if (coachBody) {
            coachBody.textContent =
                'Your new character is seated. Click the highlighted Player Campaigns row (or Enter) to open the player dashboard.';
        }
        var row = findPlayerCampaignRow();
        if (row) {
            row.classList.add('demo-draw-highlight', 'demo-allowed-player-card');
            try {
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (err) { /* ignore */ }
            var enterBtn = row.querySelector('a.switch-button, a.button');
            pointArrowAt(enterBtn || row);
            row.addEventListener('click', function () {
                window.EFDemoBridge.write({ phase: 'player_tour', active: true });
            }, true);
            if (enterBtn) {
                enterBtn.classList.add('demo-allowed-player-card');
                enterBtn.addEventListener('click', function () {
                    window.EFDemoBridge.write({ phase: 'player_tour', active: true });
                }, true);
            }
        } else {
            if (coachBody) {
                coachBody.textContent =
                    'Player seat ready — open Player Campaigns when the row appears, or use Switch campaigns.';
            }
        }
        if (forwardBtn) {
            forwardBtn.hidden = true;
            forwardBtn.disabled = true;
        }
    }

    function enterRedeemPhase() {
        phase = 'campaigns_redeem';
        document.body.setAttribute('data-demo-phase', 'campaigns_redeem');
        var codeInput = document.getElementById('campaign_code');
        var redeemBox = document.querySelector('.redeem-box');
        var redeemForm = redeemBox && redeemBox.querySelector('form');
        var redeemBtn = redeemForm && redeemForm.querySelector('button[type="submit"]');

        if (coachHeading) coachHeading.textContent = 'Step 12 — Join as player';
        if (coachBody) {
            coachBody.textContent =
                'Paste the CAMP- code you copied into Join a campaign, then click Redeem code.';
        }

        if (codeInput && bridge.campCode) {
            codeInput.value = bridge.campCode;
            codeInput.classList.add('demo-draw-highlight');
        }
        if (redeemBox) {
            redeemBox.classList.add('demo-draw-highlight');
            try {
                redeemBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (err) { /* ignore */ }
        }
        if (redeemBtn) {
            redeemBtn.classList.add('demo-draw-highlight', 'demo-allowed-redeem');
            pointArrowAt(redeemBtn);
        } else if (codeInput) {
            pointArrowAt(codeInput);
        }

        if (redeemForm) {
            redeemForm.addEventListener('submit', function () {
                window.EFDemoBridge.write({ phase: 'character_create', active: true });
            });
        }

        if (forwardBtn) {
            forwardBtn.hidden = true;
            forwardBtn.disabled = true;
        }
    }

    if (phase === 'player_card') {
        enterPlayerCardPhase();
    } else {
        enterRedeemPhase();
    }

    document.addEventListener('click', function (ev) {
        var t = ev.target;
        if (!t || !t.closest) return;
        if (t.closest('#demo-tutorial-root')) return;
        if (t.closest('#accountAvatarBtn')) return;
        if (t.closest('#accountPopoverPanel a.menu-btn-danger-outline')) return;
        if (phase === 'player_card') {
            if (t.closest('.demo-allowed-player-card')) return;
            var interactive = t.closest('button, a, input, select, textarea, label.button, .campaign-row');
            if (!interactive) return;
            ev.preventDefault();
            ev.stopPropagation();
            return;
        }
        if (t.closest('.redeem-box')) return;
        var blocked = t.closest('button, a, input, select, textarea, label.button');
        if (!blocked) return;
        ev.preventDefault();
        ev.stopPropagation();
    }, true);
})();

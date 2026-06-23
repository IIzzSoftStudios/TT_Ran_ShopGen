(function () {
    "use strict";

    const cfg = window.DND5E_WIZARD_CONFIG || {};
    const catalog = cfg.catalog || {};
    const settings = cfg.settings || {};
    const pointBuyCosts = cfg.point_buy_costs || {};
    const canAdd = cfg.can_add !== false;
    const gmNpcMode = !!cfg.gm_npc_mode;
    const draftToken = cfg.draft_token || "";
    const campaignPlayerId = cfg.campaign_player_id || null;
    const backUrl = cfg.back_url || "/campaigns";
    const finalizeUrl = cfg.finalize_url || "/player/character/create/dnd5e/finalize";
    const rollUrl = cfg.roll_url || "/player/character/create/dnd5e/roll";
    const createButtonLabel = cfg.create_button_label || "Create character";
    const abilityMin = cfg.ability_min || (gmNpcMode ? 1 : 1);
    const abilityMax = cfg.ability_max || (gmNpcMode ? 999 : 30);
    const csrfToken =
        document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
        document.querySelector('input[name="csrf_token"]')?.value ||
        "";

    const ABILITIES = ["str", "dex", "con", "int", "wis", "cha"];
    const ABILITY_LABELS = {
        str: "STR",
        dex: "DEX",
        con: "CON",
        int: "INT",
        wis: "WIS",
        cha: "CHA",
    };

    const state = {
        step: 0,
        name: "",
        system: cfg.default_system || "dnd5e",
        species: null,
        speciesFlex: {},
        classKey: null,
        classSkills: [],
        backgroundKey: null,
        baseAbilities: {},
        rolls: {},
        errors: [],
    };

    const steps = [
        "identity",
        "species",
        "class",
        "background",
        "abilities",
        "review",
    ];

    function $(sel) {
        return document.querySelector(sel);
    }

    function showError(msg) {
        const box = $("#wizard-errors");
        if (!box) return;
        box.textContent = msg || "";
        box.hidden = !msg;
    }

    function selectedBadge(isSelected) {
        return isSelected ? "<span class='selection-badge'>Selected</span>" : "";
    }

    function setStep(idx) {
        state.step = Math.max(0, Math.min(steps.length - 1, idx));
        document.querySelectorAll(".wizard-slide").forEach((el, i) => {
            el.hidden = i !== state.step;
        });
        document.querySelectorAll(".wizard-nav-item").forEach((el, i) => {
            el.classList.toggle("active", i === state.step);
            el.setAttribute("aria-current", i === state.step ? "step" : "false");
        });
        const back = $("#wizard-back");
        if (back) {
            back.textContent = state.step === 0
                ? (gmNpcMode ? "Back to People list" : "Back to campaign menu")
                : "Back";
        }
        $("#wizard-next").hidden = state.step === steps.length - 1;
        const createBtn = $("#wizard-create");
        if (createBtn) {
            createBtn.hidden = state.step !== steps.length - 1;
            createBtn.textContent = createButtonLabel;
        }
        if (steps[state.step] === "review") renderReview();
    }

    function openExitModal() {
        const modal = $("#wizard-exit-modal");
        if (!modal) return;
        modal.hidden = false;
        $("#wizard-exit-cancel")?.focus();
    }

    function closeExitModal() {
        const modal = $("#wizard-exit-modal");
        if (modal) modal.hidden = true;
    }

    function speciesCards() {
        const host = $("#species-cards");
        if (!host) return;
        host.innerHTML = "";
        (catalog.species || []).forEach((sp) => {
            const isSelected = state.species?.key === sp.key;
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "option-card" + (isSelected ? " selected" : "");
            btn.setAttribute("aria-pressed", isSelected ? "true" : "false");
            btn.innerHTML =
                "<strong>" +
                sp.name +
                "</strong><span class='muted'>" +
                (sp.summary || "") +
                "</span>" +
                selectedBadge(isSelected);
            btn.addEventListener("click", () => openSpeciesModal(sp));
            host.appendChild(btn);
        });
    }

    function openSpeciesModal(sp) {
        const modal = $("#species-modal");
        if (!modal) return;
        $("#species-modal-title").textContent = sp.name;
        const mods = sp.ability_modifiers || {};
        const modLines = ABILITIES.filter((a) => mods[a])
            .map((a) => ABILITY_LABELS[a] + " " + (mods[a] > 0 ? "+" : "") + mods[a])
            .join(", ");
        $("#species-modal-body").textContent =
            (sp.summary || "No description.") +
            (modLines ? "\n\nAbility modifiers: " + modLines : "");
        modal.dataset.key = sp.key;
        modal.hidden = false;
    }

    function closeSpeciesModal() {
        const modal = $("#species-modal");
        if (modal) modal.hidden = true;
    }

    function acceptSpecies() {
        const modal = $("#species-modal");
        const key = modal?.dataset.key;
        const sp = (catalog.species || []).find((row) => row.key === key);
        if (sp) {
            state.species = sp;
            state.speciesFlex = {};
            speciesCards();
        }
        closeSpeciesModal();
    }

    function openBackgroundModal(bg) {
        const modal = $("#background-modal");
        if (!modal) return;
        $("#background-modal-title").textContent = bg.name;
        const skills = (bg.skill_proficiencies || [])
            .map((sk) => String(sk).replace(/_/g, " "))
            .join(", ");
        $("#background-modal-body").textContent =
            (bg.summary || "No description.") +
            (skills ? "\n\nSkill proficiencies: " + skills : "");
        modal.dataset.key = bg.key;
        modal.hidden = false;
    }

    function closeBackgroundModal() {
        const modal = $("#background-modal");
        if (modal) modal.hidden = true;
    }

    function acceptBackground() {
        const modal = $("#background-modal");
        const key = modal?.dataset.key;
        const bg = (catalog.backgrounds || []).find((row) => row.key === key);
        if (bg) {
            state.backgroundKey = bg.key;
            backgroundCards();
        }
        closeBackgroundModal();
    }

    function classCards() {
        const host = $("#class-cards");
        if (!host) return;
        host.innerHTML = "";
        (catalog.classes || []).forEach((cl) => {
            const isSelected = state.classKey === cl.key;
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "option-card" + (isSelected ? " selected" : "");
            btn.setAttribute("aria-pressed", isSelected ? "true" : "false");
            btn.innerHTML =
                "<strong>" +
                cl.name +
                "</strong><span class='muted'>" +
                (cl.summary || "") +
                "</span>" +
                selectedBadge(isSelected);
            btn.addEventListener("click", () => {
                state.classKey = cl.key;
                state.classSkills = [];
                classCards();
                renderClassSkills(cl);
            });
            host.appendChild(btn);
        });
        const current = (catalog.classes || []).find((c) => c.key === state.classKey);
        renderClassSkills(current);
    }

    function renderClassSkills(classEntry) {
        const host = $("#class-skill-choices");
        if (!host) return;
        host.innerHTML = "";
        if (!classEntry) return;
        const cfgSkills = classEntry.skill_choices || {};
        const count = cfgSkills.count || 0;
        const options = cfgSkills.options || [];
        host.innerHTML =
            "<p class='muted'>Choose " +
            count +
            " skill(s) from your class list.</p>";
        options.forEach((sk) => {
            const id = "skill-" + sk;
            const wrap = document.createElement("label");
            wrap.className = "skill-choice";
            const checked = state.classSkills.includes(sk);
            wrap.innerHTML =
                '<input type="checkbox" id="' +
                id +
                '" data-skill="' +
                sk +
                '" ' +
                (checked ? "checked" : "") +
                "> " +
                sk.replace(/_/g, " ");
            const input = wrap.querySelector("input");
            input.addEventListener("change", () => {
                if (input.checked) {
                    if (!state.classSkills.includes(sk)) state.classSkills.push(sk);
                } else {
                    state.classSkills = state.classSkills.filter((s) => s !== sk);
                }
                if (state.classSkills.length > count) {
                    state.classSkills = state.classSkills.slice(-count);
                    classCards();
                }
            });
            host.appendChild(wrap);
        });
    }

    function backgroundCards() {
        const host = $("#background-cards");
        if (!host) return;
        host.innerHTML = "";
        (catalog.backgrounds || []).forEach((bg) => {
            const isSelected = state.backgroundKey === bg.key;
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "option-card" + (isSelected ? " selected" : "");
            btn.setAttribute("aria-pressed", isSelected ? "true" : "false");
            btn.innerHTML =
                "<strong>" +
                bg.name +
                "</strong><span class='muted'>" +
                (bg.summary || "") +
                "</span>" +
                selectedBadge(isSelected);
            btn.addEventListener("click", () => openBackgroundModal(bg));
            host.appendChild(btn);
        });
    }

    function renderAbilitiesPanel() {
        const host = $("#abilities-panel");
        if (!host) return;
        if (gmNpcMode) {
            host.innerHTML =
                "<p class='muted'>Set base ability scores for this NPC. There is no point-buy or level cap — species modifiers are still applied on finalize.</p>";
            renderGmSet(host);
            return;
        }
        const method = settings.ability_method || "point_buy";
        host.innerHTML =
            "<p class='muted'>Stat method: <strong>" +
            method.replace(/_/g, " ") +
            "</strong></p>";
        if (method === "point_buy") {
            renderPointBuy(host);
        } else if (method === "random_roll") {
            renderRandomRoll(host);
        } else {
            renderPlayerSet(host);
        }
    }

    function renderGmSet(parent) {
        const grid = document.createElement("div");
        grid.className = "ability-grid";
        ABILITIES.forEach((ab) => {
            const val = state.baseAbilities[ab] || 10;
            const row = document.createElement("label");
            row.innerHTML =
                ABILITY_LABELS[ab] +
                ' <input type="number" min="' +
                abilityMin +
                '" max="' +
                abilityMax +
                '" data-ability="' +
                ab +
                '" value="' +
                val +
                '">';
            grid.appendChild(row);
        });
        grid.addEventListener("change", (ev) => {
            const input = ev.target;
            if (!input.matches("input[data-ability]")) return;
            state.baseAbilities[input.dataset.ability] = parseInt(input.value, 10) || 10;
        });
        parent.appendChild(grid);
    }

    function renderPointBuy(parent) {
        const budget = settings.point_buy_budget || 27;
        const grid = document.createElement("div");
        grid.className = "ability-grid";
        ABILITIES.forEach((ab) => {
            const val = state.baseAbilities[ab] || 8;
            const row = document.createElement("label");
            row.innerHTML =
                ABILITY_LABELS[ab] +
                ' <input type="number" min="8" max="15" data-ability="' +
                ab +
                '" value="' +
                val +
                '">';
            grid.appendChild(row);
        });
        grid.addEventListener("change", (ev) => {
            const input = ev.target;
            if (!input.matches("input[data-ability]")) return;
            state.baseAbilities[input.dataset.ability] = parseInt(input.value, 10) || 8;
            updatePointBuySpend();
        });
        parent.appendChild(grid);
        const spend = document.createElement("p");
        spend.id = "point-buy-spend";
        spend.className = "muted";
        parent.appendChild(spend);
        updatePointBuySpend(budget, spend);
    }

    function updatePointBuySpend(budget, el) {
        budget = budget || settings.point_buy_budget || 27;
        el = el || $("#point-buy-spend");
        if (!el) return;
        let total = 0;
        ABILITIES.forEach((ab) => {
            const score = state.baseAbilities[ab] || 8;
            total += pointBuyCosts[String(score)] || 0;
        });
        el.textContent = "Points spent: " + total + " / " + budget;
    }

    function renderPlayerSet(parent) {
        const grid = document.createElement("div");
        grid.className = "ability-grid";
        ABILITIES.forEach((ab) => {
            const val = state.baseAbilities[ab] || 10;
            const row = document.createElement("label");
            row.innerHTML =
                ABILITY_LABELS[ab] +
                ' <input type="number" min="1" max="30" data-ability="' +
                ab +
                '" value="' +
                val +
                '">';
            grid.appendChild(row);
        });
        grid.addEventListener("change", (ev) => {
            const input = ev.target;
            if (!input.matches("input[data-ability]")) return;
            state.baseAbilities[input.dataset.ability] = parseInt(input.value, 10) || 10;
        });
        parent.appendChild(grid);
    }

    function renderRandomRoll(parent) {
        const grid = document.createElement("div");
        grid.className = "ability-grid";
        ABILITIES.forEach((ab) => {
            const row = document.createElement("div");
            row.className = "roll-row";
            row.innerHTML =
                "<span>" +
                ABILITY_LABELS[ab] +
                '</span> <span class="roll-value" data-roll-display="' +
                ab +
                '">—</span> ' +
                '<button type="button" data-roll="' +
                ab +
                '">Roll</button> ' +
                '<button type="button" data-reroll="' +
                ab +
                '">Reroll</button>';
            grid.appendChild(row);
        });
        grid.addEventListener("click", (ev) => {
            const rollBtn = ev.target.closest("[data-roll]");
            const rerollBtn = ev.target.closest("[data-reroll]");
            if (rollBtn) requestRoll(rollBtn.dataset.roll, false);
            if (rerollBtn) requestRoll(rerollBtn.dataset.reroll, true);
        });
        parent.appendChild(grid);
    }

    async function requestRoll(abilityKey, reroll) {
        showError("");
        try {
            const resp = await fetch(rollUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({
                    ability_key: abilityKey,
                    reroll: reroll,
                    campaign_player_id: campaignPlayerId,
                }),
            });
            const data = await resp.json();
            if (!data.ok) {
                showError((data.errors || ["Roll failed."]).join(" "));
                return;
            }
            state.baseAbilities[abilityKey] = data.roll.total;
            state.rolls[abilityKey] = data.roll;
            const display = document.querySelector(
                '[data-roll-display="' + abilityKey + '"]'
            );
            if (display) {
                display.textContent =
                    data.roll.total + " (" + data.roll.dice.join(", ") + ")";
            }
        } catch (_err) {
            showError("Could not reach the server to roll abilities.");
        }
    }

    function renderReview() {
        const host = $("#review-panel");
        if (!host) return;
        const sp = (catalog.species || []).find((s) => s.key === state.species?.key);
        const cl = (catalog.classes || []).find((c) => c.key === state.classKey);
        const bg = (catalog.backgrounds || []).find((b) => b.key === state.backgroundKey);
        host.innerHTML =
            "<ul class='review-list'>" +
            "<li><strong>Name:</strong> " +
            (state.name || "Unnamed") +
            "</li>" +
            "<li><strong>Species:</strong> " +
            (sp?.name || "—") +
            "</li>" +
            "<li><strong>Class:</strong> " +
            (cl?.name || "—") +
            "</li>" +
            "<li><strong>Background:</strong> " +
            (bg?.name || "—") +
            "</li>" +
            "<li><strong>Class skills:</strong> " +
            (state.classSkills.join(", ") || "—") +
            "</li>" +
            "<li><strong>Abilities (base):</strong> " +
            ABILITIES.map(
                (a) => ABILITY_LABELS[a] + " " + (state.baseAbilities[a] ?? "—")
            ).join(", ") +
            "</li></ul>";
    }

    function validateStep() {
        const step = steps[state.step];
        if (step === "identity") {
            state.name = ($("#character_name")?.value || "").trim();
            if (gmNpcMode) return true;
            state.system = $("#system_type")?.value || state.system;
            if (state.system === "dnd5e") return true;
            return "simple";
        }
        if (step === "species" && !state.species) {
            showError("Select a species.");
            return false;
        }
        if (step === "class" && !state.classKey) {
            showError("Select a class.");
            return false;
        }
        if (step === "background" && !state.backgroundKey) {
            showError("Select a background.");
            return false;
        }
        if (step === "abilities") {
            if (settings.ability_method === "random_roll") {
                for (const ab of ABILITIES) {
                    if (state.baseAbilities[ab] == null) {
                        showError("Roll all abilities before continuing.");
                        return false;
                    }
                }
            }
        }
        showError("");
        return true;
    }

    async function finalizeWizard() {
        if (!canAdd && !gmNpcMode) return;
        const btn = $("#wizard-create");
        if (btn) btn.disabled = true;
        showError("");
        const payload = {
            draft_token: draftToken,
            name: state.name,
            species_key: state.species?.key,
            class_key: state.classKey,
            background_key: state.backgroundKey,
            class_skill_choices: state.classSkills,
            base_abilities: state.baseAbilities,
            species_flex_assignments: state.speciesFlex,
            campaign_player_id: campaignPlayerId,
            region_id: cfg.region_id || null,
            assign_ruler: !!cfg.assign_ruler,
            city_id: cfg.city_id || null,
            shop_id: cfg.shop_id || null,
            assign_owner: !!cfg.assign_owner,
        };
        try {
            const resp = await fetch(finalizeUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (!data.ok) {
                showError((data.errors || ["Could not create character."]).join(" "));
                if (btn) btn.disabled = false;
                return;
            }
            if (window.parent && window.parent !== window) {
                try {
                    window.parent.postMessage({ type: "gm-players-changed" }, window.location.origin);
                    window.parent.postMessage({ type: "gm-map-changed" }, window.location.origin);
                } catch (_notifyErr) { /* ignore */ }
            }
            window.location.href = data.redirect_url;
        } catch (_err) {
            showError("Could not reach the server to finalize the character.");
            if (btn) btn.disabled = false;
        }
    }

    function submitSimpleForm() {
        $("#simple-create-form")?.submit();
    }

    function bindEvents() {
        $("#wizard-back")?.addEventListener("click", () => {
            if (state.step === 0) {
                if ($("#wizard-exit-modal")) {
                    openExitModal();
                } else {
                    window.location.href = backUrl;
                }
                return;
            }
            setStep(state.step - 1);
        });
        $("#wizard-next")?.addEventListener("click", () => {
            const ok = validateStep();
            if (ok === "simple") {
                submitSimpleForm();
                return;
            }
            if (ok) setStep(state.step + 1);
        });
        $("#wizard-create")?.addEventListener("click", finalizeWizard);
        $("#species-modal-cancel")?.addEventListener("click", closeSpeciesModal);
        $("#species-modal-accept")?.addEventListener("click", acceptSpecies);
        $("#background-modal-cancel")?.addEventListener("click", closeBackgroundModal);
        $("#background-modal-accept")?.addEventListener("click", acceptBackground);
        $("#wizard-exit-cancel")?.addEventListener("click", closeExitModal);
        $("#wizard-exit-confirm")?.addEventListener("click", () => {
            window.location.href = backUrl;
        });
        $("#system_type")?.addEventListener("change", () => {
            const sys = $("#system_type")?.value;
            const wizard = $("#dnd5e-wizard");
            const simple = $("#simple-create-actions");
            if (wizard) wizard.hidden = sys !== "dnd5e";
            if (simple) simple.hidden = sys === "dnd5e";
        });
    }

    function init() {
        ABILITIES.forEach((ab) => {
            if (gmNpcMode) {
                state.baseAbilities[ab] = 10;
            } else {
                state.baseAbilities[ab] = settings.ability_method === "player_set" ? 10 : 8;
            }
        });
        speciesCards();
        classCards();
        backgroundCards();
        renderAbilitiesPanel();
        bindEvents();
        if (!gmNpcMode) {
            const sys = $("#system_type")?.value;
            if ($("#dnd5e-wizard")) $("#dnd5e-wizard").hidden = sys !== "dnd5e";
            if ($("#simple-create-actions")) $("#simple-create-actions").hidden = sys === "dnd5e";
        }
        setStep(0);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

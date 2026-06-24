(function () {
    "use strict";

    var ABILITIES = ["str", "dex", "con", "int", "wis", "cha"];
    var ABILITY_LABELS = {
        str: "STR",
        dex: "DEX",
        con: "CON",
        int: "INT",
        wis: "WIS",
        cha: "CHA",
    };

    var state = {
        summary: null,
        stepIndex: 0,
        steps: [],
        asiMode: "plus_two",
        asiPlusTwo: "",
        asiPlusOneA: "",
        asiPlusOneB: "",
        traitSelection: [],
        subclassSelection: "",
        busy: false,
    };

    function $(sel, root) {
        return (root || document).querySelector(sel);
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function csrfToken() {
        return (
            document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
            document.querySelector('input[name="csrf_token"]')?.value ||
            ""
        );
    }

    function overlayEl() {
        return document.getElementById("levelUpWizardOverlay");
    }

    function showError(msg) {
        var box = $("#levelUpWizardError");
        if (!box) return;
        box.textContent = msg || "";
        box.hidden = !msg;
    }

    function currentStep() {
        return state.steps[state.stepIndex] || null;
    }

    function formatSpellSlots(slots) {
        slots = slots || {};
        var keys = Object.keys(slots).filter(function (k) {
            return Number(slots[k]) > 0;
        });
        if (!keys.length) return "";
        return keys
            .map(function (k) {
                return "Lv " + k + ": " + slots[k];
            })
            .join(", ");
    }

    function formatProgressionCaps(caps) {
        caps = caps || {};
        var parts = [];
        if (caps.cantrips_known != null) parts.push("Cantrips: " + caps.cantrips_known);
        if (caps.spells_known != null) parts.push("Spells known: " + caps.spells_known);
        if (caps.spells_prepared != null) parts.push("Spells prepared: " + caps.spells_prepared);
        if (caps.invocations_known != null) parts.push("Invocations: " + caps.invocations_known);
        if (caps.proficiency_bonus != null) parts.push("Proficiency: +" + caps.proficiency_bonus);
        return parts.join(" · ");
    }

    function renderNav() {
        var nav = $("#levelUpWizardNav");
        if (!nav) return;
        nav.innerHTML = "";
        state.steps.forEach(function (step, idx) {
            var item = document.createElement("li");
            item.className = "level-up-wizard-nav-item" + (idx === state.stepIndex ? " active" : "");
            item.textContent = stepNavLabel(step);
            nav.appendChild(item);
        });
    }

    function stepNavLabel(step) {
        if (!step) return "Step";
        if (step.type === "summary") return "Summary";
        if (step.type === "ability_scores") return "Abilities";
        if (step.type === "trait_pick") return step.title || "Trait";
        if (step.type === "subclass") return step.title || "Subclass";
        return step.title || "Choice";
    }

    function renderSummaryStep(step, summary) {
        var html = "<h3 id=\"levelUpWizardTitle\">" + escapeHtml(step.title || "Level up") + "</h3>";
        if (step.description) {
            html += "<p class=\"level-up-wizard-lead\">" + escapeHtml(step.description) + "</p>";
        }
        if (summary.hp_gain) {
            html += "<p><strong>Hit points:</strong> +" + escapeHtml(String(summary.hp_gain)) + " max HP.</p>";
        }
        var caps = formatProgressionCaps(summary.class_progression || {});
        if (caps) {
            html += "<p><strong>Class progression:</strong> " + escapeHtml(caps) + "</p>";
        }
        var slotText = formatSpellSlots(summary.spell_slots);
        if (slotText) {
            html += "<p><strong>Spell slots:</strong> " + escapeHtml(slotText) + "</p>";
        }
        if ((summary.features || []).length) {
            html += "<p><strong>Gained</strong></p><ul class=\"level-up-wizard-feature-list\">";
            (summary.features || []).forEach(function (feature) {
                html += "<li><strong>" + escapeHtml(feature.name || "Feature") + "</strong>";
                if (feature.description) {
                    html += ": " + escapeHtml(feature.description);
                }
                html += "</li>";
            });
            html += "</ul>";
        }
        var choiceCount = (summary.player_choices || []).length;
        if (choiceCount) {
            html +=
                "<p class=\"level-up-wizard-lead\">Next: " +
                choiceCount +
                " choice" +
                (choiceCount === 1 ? "" : "s") +
                " to complete.</p>";
        }
        return html;
    }

    function abilityOptions(selected) {
        return (
            '<option value="">Choose ability</option>' +
            ABILITIES.map(function (ab) {
                var sel = selected === ab ? " selected" : "";
                return (
                    '<option value="' +
                    ab +
                    '"' +
                    sel +
                    ">" +
                    ABILITY_LABELS[ab] +
                    "</option>"
                );
            }).join("")
        );
    }

    function renderAbilityStep(step) {
        var abilities = step.abilities || state.summary?.abilities || {};
        var html =
            "<h3 id=\"levelUpWizardTitle\">" +
            escapeHtml(step.title || "Ability Score Improvement") +
            "</h3>";
        if (step.description) {
            html += "<p class=\"level-up-wizard-lead\">" + escapeHtml(step.description) + "</p>";
        }
        html += '<div class="level-up-wizard-asi-mode">';
        html +=
            '<label><input type="radio" name="asiMode" value="plus_two"' +
            (state.asiMode === "plus_two" ? " checked" : "") +
            "> +2 to one ability</label>";
        html +=
            '<label><input type="radio" name="asiMode" value="plus_one"' +
            (state.asiMode === "plus_one" ? " checked" : "") +
            "> +1 to two abilities</label>";
        html += "</div>";
        html += '<div class="level-up-wizard-ability-scores"><p><strong>Current scores</strong></p><ul>';
        ABILITIES.forEach(function (ab) {
            html +=
                "<li>" +
                ABILITY_LABELS[ab] +
                " " +
                escapeHtml(String(abilities[ab] != null ? abilities[ab] : 10)) +
                "</li>";
        });
        html += "</ul></div>";
        html += '<div class="level-up-wizard-asi-pickers">';
        if (state.asiMode === "plus_two") {
            html +=
                '<label class="asi-picker-plus-two">Ability (+2) <select id="asiPlusTwoSelect">' +
                abilityOptions(state.asiPlusTwo) +
                "</select></label>";
        } else {
            html +=
                '<label class="asi-picker-plus-one">First ability (+1) <select id="asiPlusOneASelect">' +
                abilityOptions(state.asiPlusOneA) +
                "</select></label>";
            html +=
                '<label class="asi-picker-plus-one">Second ability (+1) <select id="asiPlusOneBSelect">' +
                abilityOptions(state.asiPlusOneB) +
                "</select></label>";
        }
        html += "</div>";
        return html;
    }

    function renderTraitStep(step) {
        var pickCount = Math.max(1, parseInt(step.pick_count || step.pick || 1, 10));
        var html =
            "<h3 id=\"levelUpWizardTitle\">" +
            escapeHtml(step.title || "Trait choice") +
            "</h3>";
        if (step.description) {
            html += "<p class=\"level-up-wizard-lead\">" + escapeHtml(step.description) + "</p>";
        }
        html +=
            "<p class=\"muted\">Select " +
            pickCount +
            " option" +
            (pickCount === 1 ? "" : "s") +
            ".</p>";
        html += '<div class="level-up-wizard-option-grid">';
        (step.options || []).forEach(function (opt) {
            var selected = state.traitSelection.indexOf(opt.key) !== -1;
            html +=
                '<button type="button" class="level-up-wizard-option-card' +
                (selected ? " selected" : "") +
                '" data-trait-key="' +
                escapeHtml(opt.key || "") +
                '">' +
                "<strong>" +
                escapeHtml(opt.name || opt.key) +
                "</strong>";
            if (opt.summary) {
                html += '<span class="muted">' + escapeHtml(opt.summary) + "</span>";
            }
            if (selected) {
                html += '<span class="level-up-wizard-selected-badge">Selected</span>';
            }
            html += "</button>";
        });
        if (!(step.options || []).length) {
            html += '<p class="muted">No traits are configured for this choice pool.</p>';
        }
        html += "</div>";
        return html;
    }

    function renderSubclassStep(step) {
        var html =
            "<h3 id=\"levelUpWizardTitle\">" +
            escapeHtml(step.title || "Choose Subclass") +
            "</h3>";
        if (step.description) {
            html += "<p class=\"level-up-wizard-lead\">" + escapeHtml(step.description) + "</p>";
        }
        html += '<div class="level-up-wizard-option-grid">';
        (step.options || []).forEach(function (opt) {
            var selected = state.subclassSelection === opt.key;
            html +=
                '<button type="button" class="level-up-wizard-option-card' +
                (selected ? " selected" : "") +
                '" data-subclass-key="' +
                escapeHtml(opt.key || "") +
                '">' +
                "<strong>" +
                escapeHtml(opt.name || opt.key) +
                "</strong>";
            if (opt.tagline) {
                html += '<span class="muted">' + escapeHtml(opt.tagline) + "</span>";
            }
            if (opt.summary) {
                html += '<span class="muted">' + escapeHtml(opt.summary) + "</span>";
            }
            if (selected) {
                html += '<span class="level-up-wizard-selected-badge">Selected</span>';
            }
            html += "</button>";
        });
        if (!(step.options || []).length) {
            html += '<p class="muted">No subclasses are available for this class.</p>';
        }
        html += "</div>";
        return html;
    }

    function renderGenericStep(step) {
        var html =
            "<h3 id=\"levelUpWizardTitle\">" +
            escapeHtml(step.title || "Level-up choice") +
            "</h3>";
        if (step.description) {
            html += "<p class=\"level-up-wizard-lead\">" + escapeHtml(step.description) + "</p>";
        }
        html +=
            "<p class=\"muted\">Complete this on your full character sheet when ready, or skip for now.</p>";
        return html;
    }

    function bindAbilityStep(root, step) {
        root.querySelectorAll('input[name="asiMode"]').forEach(function (input) {
            input.addEventListener("change", function () {
                var nextMode = input.value === "plus_one" ? "plus_one" : "plus_two";
                if (nextMode === state.asiMode) return;
                state.asiMode = nextMode;
                if (state.asiMode === "plus_two") {
                    state.asiPlusOneA = "";
                    state.asiPlusOneB = "";
                } else {
                    state.asiPlusTwo = "";
                }
                renderStep();
            });
        });
        var plusTwo = $("#asiPlusTwoSelect", root);
        var plusOneA = $("#asiPlusOneASelect", root);
        var plusOneB = $("#asiPlusOneBSelect", root);
        if (plusTwo) {
            plusTwo.addEventListener("change", function () {
                state.asiPlusTwo = plusTwo.value || "";
            });
        }
        if (plusOneA) {
            plusOneA.addEventListener("change", function () {
                state.asiPlusOneA = plusOneA.value || "";
            });
        }
        if (plusOneB) {
            plusOneB.addEventListener("change", function () {
                state.asiPlusOneB = plusOneB.value || "";
            });
        }
    }

    function normalizeWizardSteps(steps) {
        return (steps || []).filter(function (step) {
            if (!step || step.type === "summary" || step.type === "ability_scores") return true;
            if (step.type === "trait_pick" || step.type === "subclass") {
                return (step.options || []).length > 0;
            }
            return true;
        });
    }

    function hasChoiceStepsAfterSummary() {
        return state.steps.some(function (step) {
            return step && step.type !== "summary" && stepNeedsPlayerInput(step);
        });
    }

    function isLastActionableStep() {
        var step = currentStep();
        if (!step) return true;
        if (step.type === "summary") {
            return !hasChoiceStepsAfterSummary();
        }
        for (var idx = state.stepIndex + 1; idx < state.steps.length; idx += 1) {
            var next = state.steps[idx];
            if (next && next.type !== "summary" && stepNeedsPlayerInput(next)) {
                return false;
            }
        }
        return true;
    }

    function stepNeedsPlayerInput(step) {
        if (!step || step.type === "summary") return false;
        if (step.type === "ability_scores") return true;
        if (step.type === "trait_pick" || step.type === "subclass") {
            return (step.options || []).length > 0;
        }
        return true;
    }

    function bindTraitStep(root, step) {
        var pickCount = Math.max(1, parseInt(step.pick_count || step.pick || 1, 10));
        root.querySelectorAll(".level-up-wizard-option-card").forEach(function (card) {
            card.addEventListener("click", function () {
                var key = card.getAttribute("data-trait-key");
                if (!key) return;
                var idx = state.traitSelection.indexOf(key);
                if (idx !== -1) {
                    state.traitSelection.splice(idx, 1);
                } else if (state.traitSelection.length < pickCount) {
                    state.traitSelection.push(key);
                } else if (pickCount === 1) {
                    state.traitSelection = [key];
                } else {
                    showError("Select exactly " + pickCount + " option(s).");
                    return;
                }
                showError("");
                renderStep();
            });
        });
    }

    function bindSubclassStep(root) {
        root.querySelectorAll(".level-up-wizard-option-card").forEach(function (card) {
            card.addEventListener("click", function () {
                var key = card.getAttribute("data-subclass-key");
                if (!key) return;
                state.subclassSelection = key;
                showError("");
                renderStep();
            });
        });
    }

    function renderStep() {
        var body = $("#levelUpWizardBody");
        if (!body) return;
        var step = currentStep();
        if (!step) {
            closeLevelUpWizard();
            return;
        }
        showError("");
        var html = "";
        if (step.type === "summary") {
            html = renderSummaryStep(step, state.summary || {});
        } else if (step.type === "ability_scores") {
            html = renderAbilityStep(step);
        } else if (step.type === "trait_pick") {
            html = renderTraitStep(step);
        } else if (step.type === "subclass") {
            html = renderSubclassStep(step);
        } else {
            html = renderGenericStep(step);
        }
        body.innerHTML = html;
        renderNav();
        if (step.type === "ability_scores") bindAbilityStep(body, step);
        if (step.type === "trait_pick") bindTraitStep(body, step);
        if (step.type === "subclass") bindSubclassStep(body, step);

        var backBtn = $("#levelUpWizardBack");
        var continueBtn = $("#levelUpWizardContinue");
        var laterBtn = $("#levelUpWizardLater");
        var isFirst = state.stepIndex === 0;
        var onSummary = step.type === "summary";
        var choicesRemain = hasChoiceStepsAfterSummary();
        var lastStep = isLastActionableStep();

        if (backBtn) backBtn.hidden = isFirst;
        if (continueBtn) {
            if (onSummary && choicesRemain) {
                continueBtn.textContent = "Next";
                continueBtn.hidden = false;
            } else if (lastStep) {
                continueBtn.textContent = "Done";
                continueBtn.hidden = false;
            } else if (stepNeedsPlayerInput(step)) {
                continueBtn.textContent = "Next";
                continueBtn.hidden = false;
            } else {
                continueBtn.textContent = "Next";
                continueBtn.hidden = false;
            }
        }
        if (laterBtn) {
            laterBtn.hidden = onSummary && !choicesRemain;
        }
    }

    function refreshCharacterSheetAfterWizard() {
        var refresh = typeof window.loadCharacterData === "function"
            ? window.loadCharacterData()
            : Promise.resolve();
        Promise.resolve(refresh).finally(function () {
            if (typeof window.ensureCharacterPanelOpen === "function") {
                window.ensureCharacterPanelOpen();
            }
        });
    }

    function decideLevelUpLater() {
        closeLevelUpWizard();
        refreshCharacterSheetAfterWizard();
    }

    function continueWizardStep() {
        saveCurrentStep().then(function (ok) {
            if (!ok) return;
            var step = currentStep();
            if (step && step.type === "summary" && hasChoiceStepsAfterSummary()) {
                advanceStep();
                return;
            }
            if (isLastActionableStep()) {
                decideLevelUpLater();
                return;
            }
            advanceStep();
        });
    }

    function postForm(url, fields) {
        var body = new FormData();
        body.append("csrf_token", csrfToken());
        Object.keys(fields || {}).forEach(function (key) {
            var val = fields[key];
            if (Array.isArray(val)) {
                val.forEach(function (item) {
                    body.append(key, item);
                });
            } else if (val != null) {
                body.append(key, val);
            }
        });
        return fetch(url, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                Accept: "application/json",
            },
            body: body,
        }).then(function (resp) {
            return resp.json().then(function (data) {
                return { ok: resp.ok && data.ok !== false, data: data };
            });
        });
    }

    function asiIncreasesFromState() {
        if (state.asiMode === "plus_two") {
            if (!state.asiPlusTwo) return null;
            var out = {};
            out[state.asiPlusTwo] = 2;
            return out;
        }
        if (!state.asiPlusOneA || !state.asiPlusOneB) return null;
        if (state.asiPlusOneA === state.asiPlusOneB) return null;
        var pair = {};
        pair[state.asiPlusOneA] = 1;
        pair[state.asiPlusOneB] = 1;
        return pair;
    }

    function validateCurrentStep() {
        var step = currentStep();
        if (!step || step.type === "summary") return true;
        if (step.type === "ability_scores") {
            var increases = asiIncreasesFromState();
            if (!increases) {
                showError("Choose a valid +2 or two +1 ability increases.");
                return false;
            }
            return true;
        }
        if (step.type === "trait_pick") {
            var pickCount = Math.max(1, parseInt(step.pick_count || step.pick || 1, 10));
            if (state.traitSelection.length !== pickCount) {
                showError("Select exactly " + pickCount + " option(s).");
                return false;
            }
            return true;
        }
        if (step.type === "subclass") {
            if (!state.subclassSelection) {
                showError("Select a subclass.");
                return false;
            }
            return true;
        }
        return true;
    }

    function saveCurrentStep() {
        var overlay = overlayEl();
        if (!overlay || state.busy) return Promise.resolve(false);
        var step = currentStep();
        if (!step || step.type === "summary") return Promise.resolve(true);

        var applyAsiUrl = overlay.getAttribute("data-apply-asi-url") || "";
        var applyTraitUrl = overlay.getAttribute("data-apply-trait-url") || "";
        var applySubclassUrl = overlay.getAttribute("data-apply-subclass-url") || "";
        var skipUrl = overlay.getAttribute("data-skip-url") || "";
        var level = step.level || state.summary?.level;

        if (step.type === "ability_scores") {
            var plusTwoEl = document.getElementById("asiPlusTwoSelect");
            var plusOneAEl = document.getElementById("asiPlusOneASelect");
            var plusOneBEl = document.getElementById("asiPlusOneBSelect");
            if (plusTwoEl) state.asiPlusTwo = plusTwoEl.value || "";
            if (plusOneAEl) state.asiPlusOneA = plusOneAEl.value || "";
            if (plusOneBEl) state.asiPlusOneB = plusOneBEl.value || "";
            if (!validateCurrentStep()) return Promise.resolve(false);
            var increases = asiIncreasesFromState() || {};
            var fields = { level: level };
            Object.keys(increases).forEach(function (ab) {
                fields["increase_" + ab] = String(increases[ab]);
            });
            state.busy = true;
            return postForm(applyAsiUrl, fields)
                .then(function (result) {
                    state.busy = false;
                    if (!result.ok) {
                        showError(result.data.message || "Could not save ability scores.");
                        return false;
                    }
                    var abilities = state.summary?.abilities || {};
                    Object.keys(increases).forEach(function (ab) {
                        abilities[ab] = Number(abilities[ab] || 10) + Number(increases[ab]);
                    });
                    if (state.summary) state.summary.abilities = abilities;
                    return true;
                })
                .catch(function () {
                    state.busy = false;
                    showError("Could not save ability scores.");
                    return false;
                });
        }

        if (step.type === "trait_pick") {
            if (!validateCurrentStep()) return Promise.resolve(false);
            state.busy = true;
            return postForm(applyTraitUrl, {
                level: level,
                pool_tag: step.pool_tag || "",
                trait_keys: state.traitSelection.slice(),
            })
                .then(function (result) {
                    state.busy = false;
                    if (!result.ok) {
                        showError(result.data.message || "Could not save trait choices.");
                        return false;
                    }
                    state.traitSelection = [];
                    return true;
                })
                .catch(function () {
                    state.busy = false;
                    showError("Could not save trait choices.");
                    return false;
                });
        }

        if (step.type === "subclass") {
            if (!validateCurrentStep()) return Promise.resolve(false);
            state.busy = true;
            return postForm(applySubclassUrl, {
                level: level,
                subclass_key: state.subclassSelection,
            })
                .then(function (result) {
                    state.busy = false;
                    if (!result.ok) {
                        showError(result.data.message || "Could not save subclass choice.");
                        return false;
                    }
                    state.subclassSelection = "";
                    return true;
                })
                .catch(function () {
                    state.busy = false;
                    showError("Could not save subclass choice.");
                    return false;
                });
        }

        return Promise.resolve(true);
    }

    function skipCurrentStep() {
        var overlay = overlayEl();
        if (!overlay || state.busy) return;
        var step = currentStep();
        if (!step || step.type === "summary") {
            advanceStep();
            return;
        }
        var skipUrl = overlay.getAttribute("data-skip-url") || "";
        if (!skipUrl) {
            advanceStep();
            return;
        }
        state.busy = true;
        postForm(skipUrl, {
            level: step.level || state.summary?.level,
            choice_type: step.type || "custom",
            pool_tag: step.pool_tag || "",
        })
            .then(function (result) {
                state.busy = false;
                if (!result.ok) {
                    showError(result.data.message || "Could not skip this choice.");
                    return;
                }
                state.traitSelection = [];
                state.subclassSelection = "";
                advanceStep();
            })
            .catch(function () {
                state.busy = false;
                showError("Could not skip this choice.");
            });
    }

    function advanceStep() {
        if (state.stepIndex < state.steps.length - 1) {
            state.stepIndex += 1;
            state.traitSelection = [];
            state.subclassSelection = "";
            renderStep();
            return;
        }
        closeLevelUpWizard();
        refreshCharacterSheetAfterWizard();
    }

    function goBack() {
        if (state.stepIndex <= 0) return;
        state.stepIndex -= 1;
        state.traitSelection = [];
        renderStep();
    }

    function bindWizardChrome() {
        var overlay = overlayEl();
        if (!overlay || overlay.dataset.bound === "1") return;
        overlay.dataset.bound = "1";
        $("#levelUpWizardBack", overlay)?.addEventListener("click", goBack);
        $("#levelUpWizardLater", overlay)?.addEventListener("click", decideLevelUpLater);
        $("#levelUpWizardContinue", overlay)?.addEventListener("click", continueWizardStep);
        overlay.addEventListener("click", function (event) {
            if (event.target === overlay) decideLevelUpLater();
        });
    }

    function openLevelUpConfirm(preview) {
        var overlay = document.getElementById("levelUpConfirmOverlay");
        var body = $("#levelUpConfirmBody");
        if (!overlay || !body) return;
        preview = preview || {};
        var html = "<h3>Level up to level " + escapeHtml(String(preview.next_level || "")) + "?</h3>";
        if (preview.hp_gain) {
            html +=
                "<p><strong>Hit points:</strong> +" +
                escapeHtml(String(preview.hp_gain)) +
                " max HP.</p>";
        }
        if ((preview.features || []).length) {
            html += "<p><strong>You gain</strong></p><ul>";
            (preview.features || []).forEach(function (feature) {
                html += "<li>" + escapeHtml(feature.name || "Feature") + "</li>";
            });
            html += "</ul>";
        }
        if ((preview.player_choices || []).length) {
            html += "<p>After leveling up, you will choose:</p><ul>";
            (preview.player_choices || []).forEach(function (choice) {
                html += "<li>" + escapeHtml(choice.title || "Choice") + "</li>";
            });
            html += "</ul>";
        }
        body.innerHTML = html;
        overlay.hidden = false;
    }

    function closeLevelUpConfirm() {
        var overlay = document.getElementById("levelUpConfirmOverlay");
        if (overlay) overlay.hidden = true;
    }

    function startLevelUpWizard(summary) {
        var overlay = overlayEl();
        if (!overlay || !summary) return;
        bindWizardChrome();
        state.summary = summary;
        state.steps = normalizeWizardSteps((summary.wizard_steps || []).slice());
        if (!state.steps.length) {
            state.steps = [
                {
                    type: "summary",
                    title: "Level " + (summary.level || ""),
                    description: "Your character advanced.",
                },
            ];
        }
        if (!hasChoiceStepsAfterSummary()) {
            return;
        }
        state.stepIndex = 0;
        state.asiMode = "plus_two";
        state.asiPlusTwo = "";
        state.asiPlusOneA = "";
        state.asiPlusOneB = "";
        state.traitSelection = [];
        state.subclassSelection = "";
        showError("");
        overlay.hidden = false;
        renderStep();
    }

    function closeLevelUpWizard() {
        var overlay = overlayEl();
        if (overlay) overlay.hidden = true;
        state.summary = null;
        state.steps = [];
        state.stepIndex = 0;
    }

    function setupLevelUpTrigger() {
        var trigger = document.getElementById("levelUpTrigger");
        var form = document.getElementById("levelUpForm");
        var confirmBtn = document.getElementById("levelUpConfirmBtn");
        var cancelBtn = document.getElementById("levelUpConfirmCancel");
        if (form && trigger && trigger.type === "submit") {
            trigger.type = "button";
        }
        if (trigger) {
            trigger.addEventListener("click", function () {
                if (trigger.disabled) return;
                openLevelUpConfirm(window.levelUpPreviewState || {});
            });
        }
        if (confirmBtn && form) {
            confirmBtn.addEventListener("click", function () {
                closeLevelUpConfirm();
                if (typeof window.submitLevelChangeForm === "function") {
                    window.submitLevelChangeForm(form);
                } else {
                    form.submit();
                }
            });
        }
        if (cancelBtn) {
            cancelBtn.addEventListener("click", closeLevelUpConfirm);
        }
    }

    window.startLevelUpWizard = startLevelUpWizard;
    window.closeLevelUpWizard = closeLevelUpWizard;
    window.setupLevelUpTrigger = setupLevelUpTrigger;

    document.addEventListener("DOMContentLoaded", function () {
        bindWizardChrome();
        setupLevelUpTrigger();
        if (window.LEVEL_UP_SUMMARY) {
            startLevelUpWizard(window.LEVEL_UP_SUMMARY);
            window.LEVEL_UP_SUMMARY = null;
        }
    });
})();

document.addEventListener("error", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLImageElement) || !target.classList.contains("merchant-logo")) {
        return;
    }
    target.style.display = "none";
    const fallback = target.nextElementSibling;
    if (fallback && fallback.classList.contains("logo-fallback")) {
        fallback.style.display = "inline-grid";
    }
}, true);

document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
        return;
    }
    const message = form.dataset.confirm;
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});

function iconMarkup(icon) {
    const icons = {
        basket: '<svg viewBox="0 0 24 24"><path d="M6 10h12l-1.4 9H7.4L6 10Z"/><path d="M9 10 12 5l3 5"/><path d="M9 14h6"/></svg>',
        utensils: '<svg viewBox="0 0 24 24"><path d="M7 4v7"/><path d="M10 4v7"/><path d="M5.5 4v5.5A3 3 0 0 0 8.5 12v8"/><path d="M17 4v16"/><path d="M17 4c2 1.5 3 3.5 3 6 0 2-1 3.5-3 4"/></svg>',
        repeat: '<svg viewBox="0 0 24 24"><path d="M17 3l3 3-3 3"/><path d="M4 11V9a3 3 0 0 1 3-3h13"/><path d="M7 21l-3-3 3-3"/><path d="M20 13v2a3 3 0 0 1-3 3H4"/></svg>',
        car: '<svg viewBox="0 0 24 24"><path d="M5 13l2-5h10l2 5"/><path d="M4 13h16v5H4z"/><path d="M7 18v2"/><path d="M17 18v2"/><path d="M7 16h.1"/><path d="M17 16h.1"/></svg>',
        heart: '<svg viewBox="0 0 24 24"><path d="M12 20s-7-4.4-9-9a4.5 4.5 0 0 1 8-4 4.5 4.5 0 0 1 8 4c-2 4.6-9 9-9 9Z"/></svg>',
        chart: '<svg viewBox="0 0 24 24"><path d="M4 19h16"/><path d="M6 16l4-4 3 3 5-7"/><path d="M15 8h3v3"/></svg>',
        "$": '<svg viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M16 7.5C15 6.5 13.8 6 12.2 6 9.8 6 8 7.2 8 9s1.4 2.6 4 3.1c2.6.5 4 1.2 4 3.1S14.2 18 11.8 18c-1.7 0-3.2-.6-4.3-1.8"/></svg>',
    };
    return icons[icon] || `<span>${icon || ""}</span>`;
}

function updateSelectVisual(select) {
    const wrapper = select.closest(".select-with-visual");
    const leading = wrapper ? wrapper.querySelector(".select-leading") : null;
    const selected = select.options[select.selectedIndex];
    if (!leading || !selected) {
        return;
    }

    leading.className = "select-leading";
    leading.textContent = "";
    leading.style.backgroundImage = "";
    leading.style.backgroundColor = "";
    leading.style.display = "inline-grid";

    if (selected.dataset.kind === "logo" && selected.dataset.logo) {
        leading.classList.add("select-leading-logo");
        leading.style.backgroundImage = `url("${selected.dataset.logo}")`;
    } else if (selected.dataset.kind === "color" && selected.dataset.color) {
        leading.classList.add("select-leading-dot");
        leading.style.backgroundColor = selected.dataset.color;
        leading.innerHTML = iconMarkup(selected.dataset.icon);
    } else if (selected.dataset.kind === "type") {
        leading.classList.add("select-leading-type", `select-leading-${selected.dataset.tone}`);
        leading.innerHTML = selected.dataset.symbol || "";
    } else {
        leading.style.display = "none";
    }
}

function optionVisual(option) {
    if (option.dataset.kind === "logo" && option.dataset.logo) {
        return `<span class="choice-icon choice-logo" style="background-image: url('${option.dataset.logo}')"></span>`;
    }
    if (option.dataset.kind === "color" && option.dataset.color) {
        return `<span class="choice-icon choice-category" style="background-color: ${option.dataset.color}">${iconMarkup(option.dataset.icon)}</span>`;
    }
    if (option.dataset.kind === "type") {
        return `<span class="choice-icon choice-type choice-${option.dataset.tone}">${option.dataset.symbol || ""}</span>`;
    }
    return '<span class="choice-icon choice-empty"></span>';
}

function optionLabel(option) {
    return option.dataset.label || option.textContent.trim() || "None";
}

function closeEnhancedSelects(except = null) {
    document.querySelectorAll(".enhanced-select.open").forEach((wrapper) => {
        if (wrapper !== except) {
            wrapper.classList.remove("open");
            const trigger = wrapper.querySelector(".enhanced-trigger");
            if (trigger) {
                trigger.setAttribute("aria-expanded", "false");
            }
        }
    });
}

function updateEnhancedTrigger(wrapper, select) {
    const selected = select.options[select.selectedIndex];
    const trigger = wrapper.querySelector(".enhanced-trigger");
    if (!selected || !trigger) {
        return;
    }
    trigger.innerHTML = `${optionVisual(selected)}<span class="choice-label">${optionLabel(selected)}</span><span class="choice-caret"></span>`;
}

function enhanceSelect(select) {
    const wrapper = select.closest(".select-with-visual");
    if (!wrapper || wrapper.classList.contains("enhanced-select")) {
        return;
    }

    wrapper.classList.add("enhanced-select");
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "enhanced-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");

    const menu = document.createElement("div");
    menu.className = "enhanced-menu";
    menu.setAttribute("role", "listbox");

    Array.from(select.options).forEach((option) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "enhanced-option";
        item.dataset.value = option.value;
        item.setAttribute("role", "option");
        item.innerHTML = `${optionVisual(option)}<span class="choice-label">${optionLabel(option)}</span>`;
        item.addEventListener("click", () => {
            select.value = option.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
            wrapper.classList.remove("open");
            trigger.setAttribute("aria-expanded", "false");
        });
        menu.appendChild(item);
    });

    trigger.addEventListener("click", () => {
        const willOpen = !wrapper.classList.contains("open");
        closeEnhancedSelects(wrapper);
        wrapper.classList.toggle("open", willOpen);
        trigger.setAttribute("aria-expanded", String(willOpen));
    });

    select.addEventListener("change", () => {
        updateEnhancedTrigger(wrapper, select);
        menu.querySelectorAll(".enhanced-option").forEach((item) => {
            item.classList.toggle("selected", item.dataset.value === select.value);
        });
    });

    wrapper.appendChild(trigger);
    wrapper.appendChild(menu);
    updateEnhancedTrigger(wrapper, select);
    select.dispatchEvent(new Event("change"));
}

document.querySelectorAll("[data-icon]").forEach((element) => {
    element.innerHTML = iconMarkup(element.dataset.icon);
});

document.querySelectorAll("[data-visual-select]").forEach((select) => {
    updateSelectVisual(select);
    select.addEventListener("change", () => updateSelectVisual(select));
    enhanceSelect(select);
});

document.addEventListener("click", (event) => {
    if (!event.target.closest(".enhanced-select")) {
        closeEnhancedSelects();
    }
});

(function () {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const balanceKey = "money-manager:last-net-balance";

    function easeOutCubic(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    function formatValue(value, element) {
        const decimals = Number(element.dataset.decimals || 0);
        const prefix = element.dataset.prefix || "";
        const suffix = element.dataset.suffix || "";
        return `${prefix}${Number(value).toLocaleString("en-US", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        })}${suffix}`;
    }

    function setValue(element, value) {
        element.textContent = formatValue(value, element);
    }

    function animateValue(element, from, to, duration) {
        if (reduceMotion || duration <= 0) {
            setValue(element, to);
            return;
        }

        const start = performance.now();
        const difference = to - from;

        function frame(now) {
            const progress = Math.min((now - start) / duration, 1);
            setValue(element, from + difference * easeOutCubic(progress));
            if (progress < 1) {
                requestAnimationFrame(frame);
            }
        }

        setValue(element, from);
        requestAnimationFrame(frame);
    }

    function initKpiCountups() {
        const values = document.querySelectorAll("[data-countup]");
        if (!values.length) {
            return;
        }

        values.forEach((element) => {
            const target = Number(element.dataset.value || 0);
            let from = 0;
            let duration = 800;

            if (element.dataset.countupKey === "net-balance") {
                const previous = Number(localStorage.getItem(balanceKey));
                if (Number.isFinite(previous) && Math.abs(previous - target) > 0.004) {
                    from = previous;
                    duration = 400;
                }
                localStorage.setItem(balanceKey, String(target));
            }

            animateValue(element, from, target, duration);
        });
    }

    initKpiCountups();
})();

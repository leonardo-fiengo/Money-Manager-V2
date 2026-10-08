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
    return icons[icon] || `<span>${escapeHtml(icon || "")}</span>`;
}

document.querySelectorAll('[data-category-glyph]').forEach((element) => {
    element.innerHTML = iconMarkup(element.dataset.categoryGlyph);
});

function escapeHtml(value) {
    const span = document.createElement("span");
    span.textContent = value;
    return span.innerHTML;
}

let quickSelect = null;
function openQuickOption(select) {
    const dialog = document.querySelector('[data-quick-dialog]');
    if (!dialog) return;
    quickSelect = select;
    const kind = select.dataset.createKind;
    const form = dialog.querySelector('form');
    form.reset();
    dialog.querySelector('#quick-title').textContent = `Add ${kind}`;
    dialog.querySelector('[data-category-type]').hidden = kind !== 'category';
    dialog.querySelector('[data-merchant-category]').hidden = kind !== 'merchant';
    dialog.querySelector('[data-quick-error]').hidden = true;
    form.elements.type.value = document.querySelector('[data-transaction-form] [name="type"]:checked').value;
    dialog.showModal();
    form.elements.name.focus();
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
    if (option.dataset.kind === "logo") {
        return `<span class="choice-icon choice-logo-fallback">${escapeHtml(optionLabel(option).slice(0, 1).toUpperCase())}</span>`;
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
    trigger.innerHTML = `${optionVisual(selected)}<span class="choice-label">${escapeHtml(optionLabel(selected))}</span><span class="choice-caret"></span>`;
}

function enhanceSelect(select) {
    let wrapper = select.closest(".select-with-visual");
    if (!wrapper) {
        wrapper = document.createElement("span");
        wrapper.className = "select-with-visual soft-select";
        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);
    }
    if (wrapper.classList.contains("enhanced-select")) {
        return;
    }

    wrapper.classList.add("enhanced-select");
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "enhanced-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    const fieldNames = {merchant_id: 'Merchant', category: 'Category', account_id: 'Payment account', destination_account_id: 'Destination account'};
    const linkedLabel = select.id ? document.querySelector(`label[for="${CSS.escape(select.id)}"]`) : null;
    trigger.setAttribute("aria-label", select.getAttribute("aria-label") || linkedLabel?.textContent?.trim() || fieldNames[select.name] || select.closest("label")?.firstChild?.textContent?.trim() || select.name);

    const menu = document.createElement("div");
    menu.className = "enhanced-menu";
    menu.setAttribute("role", "group");

    function renderOptions() {
    menu.replaceChildren();
    Array.from(select.options).filter((option) => !option.hidden).forEach((option) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "enhanced-option";
        item.dataset.value = option.value;
        item.setAttribute("aria-pressed", String(option.selected));
        item.classList.toggle("selected", option.selected);
        item.innerHTML = `${optionVisual(option)}<span class="choice-label">${escapeHtml(optionLabel(option))}</span>`;
        item.addEventListener("click", () => {
            select.value = option.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
            wrapper.classList.remove("open");
            trigger.setAttribute("aria-expanded", "false");
            trigger.focus();
        });
        menu.appendChild(item);
    });
    if (select.dataset.createKind) {
        const add = document.createElement("button");
        add.type = "button";
        add.className = "enhanced-create";
        add.textContent = `+ Add new ${select.dataset.createKind}…`;
        add.addEventListener("click", () => {
            closeEnhancedSelects();
            openQuickOption(select);
        });
        menu.appendChild(add);
    }
    }
    renderOptions();

    trigger.addEventListener("click", () => {
        const willOpen = !wrapper.classList.contains("open");
        closeEnhancedSelects(wrapper);
        wrapper.classList.toggle("open", willOpen);
        trigger.setAttribute("aria-expanded", String(willOpen));
        if (willOpen) (menu.querySelector(".selected") || menu.querySelector("button"))?.focus();
    });

    wrapper.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeEnhancedSelects();
            trigger.focus();
        }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            closeEnhancedSelects(wrapper);
            wrapper.classList.add("open");
            trigger.setAttribute("aria-expanded", "true");
            const items = Array.from(menu.querySelectorAll("button"));
            const current = items.indexOf(document.activeElement);
            let next = event.key === "ArrowUp" ? current - 1 : current + 1;
            if (event.key === "Home") next = 0;
            if (event.key === "End") next = items.length - 1;
            items[(next + items.length) % items.length]?.focus();
        }
    });
    wrapper.addEventListener("focusout", (event) => {
        if (event.relatedTarget && !wrapper.contains(event.relatedTarget)) closeEnhancedSelects();
    });
    select.addEventListener("optionschanged", () => {
        renderOptions();
        updateEnhancedTrigger(wrapper, select);
    });

    select.addEventListener("change", () => {
        updateEnhancedTrigger(wrapper, select);
        menu.querySelectorAll(".enhanced-option").forEach((item) => {
            item.classList.toggle("selected", item.dataset.value === select.value);
            item.setAttribute("aria-pressed", String(item.dataset.value === select.value));
        });
    });

    wrapper.appendChild(trigger);
    wrapper.appendChild(menu);
    updateEnhancedTrigger(wrapper, select);
}

const datePickerState = {
    active: null,
};

const monthPickerState = {
    active: null,
};

function parseIsoDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
    if (!match) {
        return null;
    }
    return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

function dateToIso(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

function formatDateLabel(value) {
    const date = parseIsoDate(value);
    if (!date) {
        return "";
    }
    return date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

function parseMonthValue(value) {
    const match = /^(\d{4})-(\d{2})$/.exec(value || "");
    if (!match) {
        return null;
    }
    return new Date(Number(match[1]), Number(match[2]) - 1, 1);
}

function monthToValue(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function formatMonthLabel(value) {
    const date = parseMonthValue(value);
    if (!date) {
        return "";
    }
    return date.toLocaleDateString("en-US", {
        month: "long",
        year: "numeric",
    });
}

function closeDatePicker(except = null) {
    if (datePickerState.active && datePickerState.active !== except) {
        datePickerState.active.classList.remove("open");
        const input = datePickerState.active.querySelector("input[aria-haspopup='dialog']");
        if (input) {
            input.setAttribute("aria-expanded", "false");
        }
    }
    datePickerState.active = except;
}

function closeMonthPicker(except = null) {
    if (monthPickerState.active && monthPickerState.active !== except) {
        monthPickerState.active.classList.remove("open");
        const input = monthPickerState.active.querySelector("input[aria-haspopup='dialog']");
        if (input) {
            input.setAttribute("aria-expanded", "false");
        }
    }
    monthPickerState.active = except;
}

function renderDatePicker(wrapper, input, hidden, viewDate) {
    const picker = wrapper.querySelector(".modern-date-picker");
    const title = picker.querySelector(".modern-date-title");
    const grid = picker.querySelector(".modern-date-days");
    const selectedDate = parseIsoDate(hidden.value);
    const today = new Date();
    const firstDay = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1);
    const monthStartOffset = firstDay.getDay();
    const daysInMonth = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 0).getDate();

    wrapper.dataset.viewYear = String(viewDate.getFullYear());
    wrapper.dataset.viewMonth = String(viewDate.getMonth());
    title.textContent = viewDate.toLocaleDateString("en-US", { month: "long", year: "numeric" });
    grid.innerHTML = "";

    ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].forEach((day) => {
        const label = document.createElement("span");
        label.className = "modern-date-weekday";
        label.textContent = day;
        grid.appendChild(label);
    });

    for (let index = 0; index < monthStartOffset; index += 1) {
        const spacer = document.createElement("span");
        spacer.className = "modern-date-empty";
        grid.appendChild(spacer);
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
        const optionDate = new Date(viewDate.getFullYear(), viewDate.getMonth(), day);
        const optionIso = dateToIso(optionDate);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "modern-date-day";
        button.textContent = String(day);
        button.classList.toggle("selected", selectedDate && optionIso === dateToIso(selectedDate));
        button.classList.toggle("today", optionIso === dateToIso(today));
        button.addEventListener("click", () => {
            hidden.value = optionIso;
            input.value = formatDateLabel(optionIso);
            input.dataset.isoValue = optionIso;
            input.dispatchEvent(new Event("change", { bubbles: true }));
            closeDatePicker();
        });
        grid.appendChild(button);
    }
}

function renderMonthPicker(wrapper, input, hidden, year) {
    const picker = wrapper.querySelector(".modern-month-picker");
    const title = picker.querySelector(".modern-month-title");
    const grid = picker.querySelector(".modern-month-grid");
    const selectedMonth = hidden.value;
    const currentMonth = monthToValue(new Date());

    wrapper.dataset.viewYear = String(year);
    title.textContent = String(year);
    grid.innerHTML = "";

    Array.from({ length: 12 }, (_, index) => new Date(year, index, 1)).forEach((monthDate) => {
        const value = monthToValue(monthDate);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "modern-month-option";
        button.textContent = monthDate.toLocaleDateString("en-US", { month: "short" });
        button.classList.toggle("selected", value === selectedMonth);
        button.classList.toggle("current", value === currentMonth);
        button.addEventListener("click", () => {
            hidden.value = value;
            input.value = formatMonthLabel(value);
            input.dataset.monthValue = value;
            input.dispatchEvent(new Event("change", { bubbles: true }));
            closeMonthPicker();
        });
        grid.appendChild(button);
    });
}

function enhanceDateInput(input) {
    const wrapper = input.closest(".date-control");
    if (!wrapper || wrapper.classList.contains("modern-date-control")) {
        return;
    }

    const hidden = document.createElement("input");
    const initialValue = input.value;
    hidden.type = "hidden";
    hidden.name = input.name;
    hidden.value = initialValue;

    input.removeAttribute("name");
    input.type = "text";
    input.value = formatDateLabel(initialValue);
    input.dataset.isoValue = initialValue;
    input.autocomplete = "off";
    input.inputMode = "none";
    input.placeholder = "Select date";
    input.readOnly = true;
    input.setAttribute("aria-haspopup", "dialog");
    input.setAttribute("aria-expanded", "false");

    const picker = document.createElement("div");
    picker.className = "modern-date-picker";
    picker.setAttribute("role", "dialog");
    picker.setAttribute("aria-label", "Choose date");
    picker.innerHTML = `
        <div class="modern-date-header">
            <button type="button" class="modern-date-nav" data-date-nav="-1" aria-label="Previous month">&lsaquo;</button>
            <strong class="modern-date-title"></strong>
            <button type="button" class="modern-date-nav" data-date-nav="1" aria-label="Next month">&rsaquo;</button>
        </div>
        <div class="modern-date-days"></div>
        <button type="button" class="modern-date-today">Today</button>
    `;

    wrapper.classList.add("modern-date-control");
    wrapper.appendChild(hidden);
    wrapper.appendChild(picker);

    function currentViewDate() {
        const selected = parseIsoDate(hidden.value);
        return selected || new Date();
    }

    function openPicker() {
        closeDatePicker(wrapper);
        wrapper.classList.add("open");
        input.setAttribute("aria-expanded", "true");
        renderDatePicker(wrapper, input, hidden, currentViewDate());
    }

    picker.querySelectorAll("[data-date-nav]").forEach((button) => {
        button.addEventListener("click", () => {
            const year = Number(wrapper.dataset.viewYear);
            const month = Number(wrapper.dataset.viewMonth);
            const nextView = new Date(year, month + Number(button.dataset.dateNav), 1);
            renderDatePicker(wrapper, input, hidden, nextView);
        });
    });

    picker.querySelector(".modern-date-today").addEventListener("click", () => {
        const todayIso = dateToIso(new Date());
        hidden.value = todayIso;
        input.value = formatDateLabel(todayIso);
        input.dataset.isoValue = todayIso;
        input.dispatchEvent(new Event("change", { bubbles: true }));
        closeDatePicker();
    });

    input.addEventListener("focus", openPicker);
    input.addEventListener("click", openPicker);
    input.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeDatePicker();
            input.blur();
        }
    });
}

function enhanceMonthInput(input) {
    const wrapper = input.closest(".month-control");
    if (!wrapper || wrapper.classList.contains("modern-month-control")) {
        return;
    }

    const hidden = document.createElement("input");
    const initialValue = input.value;
    hidden.type = "hidden";
    hidden.name = input.name;
    hidden.value = initialValue;

    input.removeAttribute("name");
    input.type = "text";
    input.value = formatMonthLabel(initialValue);
    input.dataset.monthValue = initialValue;
    input.autocomplete = "off";
    input.inputMode = "none";
    input.placeholder = "Select month";
    input.readOnly = true;
    input.setAttribute("aria-haspopup", "dialog");
    input.setAttribute("aria-expanded", "false");

    const picker = document.createElement("div");
    picker.className = "modern-month-picker";
    picker.setAttribute("role", "dialog");
    picker.setAttribute("aria-label", "Choose month");
    picker.innerHTML = `
        <div class="modern-month-header">
            <button type="button" class="modern-month-nav" data-month-nav="-1" aria-label="Previous year">&lsaquo;</button>
            <strong class="modern-month-title"></strong>
            <button type="button" class="modern-month-nav" data-month-nav="1" aria-label="Next year">&rsaquo;</button>
        </div>
        <div class="modern-month-grid"></div>
    `;

    wrapper.classList.add("modern-month-control");
    wrapper.appendChild(hidden);
    wrapper.appendChild(picker);

    function currentViewYear() {
        const selected = parseMonthValue(hidden.value);
        return selected ? selected.getFullYear() : new Date().getFullYear();
    }

    function openPicker() {
        closeMonthPicker(wrapper);
        wrapper.classList.add("open");
        input.setAttribute("aria-expanded", "true");
        renderMonthPicker(wrapper, input, hidden, currentViewYear());
    }

    picker.querySelectorAll("[data-month-nav]").forEach((button) => {
        button.addEventListener("click", () => {
            renderMonthPicker(wrapper, input, hidden, Number(wrapper.dataset.viewYear) + Number(button.dataset.monthNav));
        });
    });

    input.addEventListener("focus", openPicker);
    input.addEventListener("click", openPicker);
    input.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeMonthPicker();
            input.blur();
        }
    });
}

document.querySelectorAll("[data-icon]:not(option)").forEach((element) => {
    element.innerHTML = iconMarkup(element.dataset.icon);
});

document.querySelectorAll(".date-control input[type='date']").forEach((input) => {
    enhanceDateInput(input);
});

document.querySelectorAll(".month-control input[type='month']").forEach((input) => {
    enhanceMonthInput(input);
});

document.querySelectorAll("[data-logo-upload]").forEach((input) => {
    input.addEventListener("change", () => {
        const file = input.files && input.files[0];
        const field = input.closest(".logo-upload-field");
        const preview = field ? field.querySelector("[data-logo-preview]") : null;
        const label = field ? field.querySelector("[data-logo-label]") : null;
        const filename = field ? field.querySelector("[data-logo-filename]") : null;
        if (!file) {
            return;
        }

        if (label) {
            label.textContent = "Logo selected";
        }
        if (filename) {
            filename.textContent = file.name;
        }
        if (preview && file.type.startsWith("image/")) {
            const reader = new FileReader();
            reader.addEventListener("load", () => {
                preview.innerHTML = `<img src="${reader.result}" alt="">`;
            });
            reader.readAsDataURL(file);
        }
    });
});

document.querySelectorAll("[data-visual-select]").forEach((select) => {
    updateSelectVisual(select);
    select.addEventListener("change", () => updateSelectVisual(select));
    enhanceSelect(select);
});
document.querySelectorAll("select:not([data-visual-select]):not([data-native-select]):not(:disabled)").forEach((select) => {
    if (!select.closest(".amount-control")) enhanceSelect(select);
});

document.querySelectorAll("[data-paypal-calculator]").forEach((calculator) => {
    const amountInput = calculator.querySelector("[data-paypal-amount]");
    const modeSelect = calculator.querySelector("[data-paypal-mode]");
    const netOutput = calculator.querySelector("[data-paypal-net]");
    const feeOutput = calculator.querySelector("[data-paypal-fee]");
    const rateOutput = calculator.querySelector("[data-paypal-rate]");
    const sentOutput = calculator.querySelector("[data-paypal-sent]");
    const flowFeeOutput = calculator.querySelector("[data-paypal-flow-fee]");
    const flowNetOutput = calculator.querySelector("[data-paypal-flow-net]");
    const transferAmountInput = calculator.querySelector("[data-paypal-transfer-amount]");
    const addTransferButton = calculator.querySelector("[data-paypal-add-transfer]");
    const canAddTransfer = addTransferButton ? !addTransferButton.disabled : false;

    function money(value) {
        return `€${Number(value || 0).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })}`;
    }

    function selectedRate() {
        const option = modeSelect.options[modeSelect.selectedIndex];
        return Number(option ? option.dataset.rate : 0) || 0;
    }

    function updatePayPalCalculator() {
        const amount = Math.max(0, Number(amountInput.value || 0));
        const rate = selectedRate();
        const fee = Math.round(amount * (rate / 100) * 100) / 100;
        const net = Math.max(0, Math.round((amount - fee) * 100) / 100);

        netOutput.textContent = money(net);
        feeOutput.textContent = money(fee);
        rateOutput.textContent = `${rate.toFixed(2)}%`;
        sentOutput.textContent = money(amount);
        flowFeeOutput.textContent = money(fee);
        flowNetOutput.textContent = money(net);
        if (transferAmountInput) {
            transferAmountInput.value = net.toFixed(2);
        }
        if (addTransferButton) {
            addTransferButton.disabled = !canAddTransfer || net <= 0;
        }
    }

    amountInput.addEventListener("input", updatePayPalCalculator);
    modeSelect.addEventListener("change", updatePayPalCalculator);
    calculator.querySelectorAll("[data-paypal-quick]").forEach((button) => {
        button.addEventListener("click", () => {
            amountInput.value = button.dataset.paypalQuick;
            updatePayPalCalculator();
            amountInput.focus();
        });
    });

    updatePayPalCalculator();
});

document.addEventListener("click", (event) => {
    if (!event.target.closest(".enhanced-select")) {
        closeEnhancedSelects();
    }
    if (!event.target.closest(".modern-date-control")) {
        closeDatePicker();
    }
    if (!event.target.closest(".modern-month-control")) {
        closeMonthPicker();
    }
});

// Keep transaction entry focused and preserve user choices while suggesting defaults.
const transactionForm = document.querySelector('[data-transaction-form]');
if (transactionForm) {
    const type = transactionForm.elements.type;
    const destination = transactionForm.elements.destination_account_id;
    function syncDestination() {
        const visible = type.value === 'transfer';
        transactionForm.querySelector('[data-destination]').hidden = !visible;
        destination.disabled = !visible;
        destination.required = visible;
    }
    const merchant = transactionForm.elements.merchant_id;
    const category = transactionForm.elements.category;
    function syncType() {
        syncDestination();
        Array.from(category.options).forEach((option) => {
            option.hidden = Boolean(option.value && option.dataset.categoryType !== 'any' && option.dataset.categoryType !== type.value);
        });
        if (category.selectedOptions[0]?.hidden) {
            category.value = '';
            category.dispatchEvent(new Event('change', {bubbles: true}));
        }
        category.dispatchEvent(new Event('optionschanged'));
    }
    transactionForm.querySelectorAll('input[name="type"]').forEach((input) => input.addEventListener('change', syncType));
    syncType();
    const dateInput = transactionForm.querySelector('input[name="date"]');
    const futureNote = transactionForm.querySelector('[data-future-note]');
    function syncFuture() {
        const today = dateToIso(new Date());
        futureNote.hidden = !(dateInput.value > today);
    }
    transactionForm.querySelector('.date-control').addEventListener('change', syncFuture);
    syncFuture();
    let categoryChosen = Boolean(category.value);
    category.addEventListener('change', () => { categoryChosen = Boolean(category.value); });
    merchant.addEventListener('change', () => {
        if (categoryChosen) return;
        const suggestion = merchant.selectedOptions[0]?.dataset.defaultCategory;
        if (suggestion && Array.from(category.options).some(option => option.value === suggestion)) {
            category.value = suggestion;
            category.dispatchEvent(new Event('change', {bubbles: true}));
            categoryChosen = false;
        }
    });
}

const quickDialog = document.querySelector('[data-quick-dialog]');
if (quickDialog) {
    quickDialog.querySelectorAll('[data-dialog-close]').forEach(button => {
        button.addEventListener('click', () => quickDialog.close());
    });
    quickDialog.addEventListener('close', () => quickSelect?.closest('.enhanced-select').querySelector('.enhanced-trigger').focus());
    quickDialog.querySelector('form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.target;
        const button = form.querySelector('[data-quick-save]');
        const error = form.querySelector('[data-quick-error]');
        const kind = quickSelect.dataset.createKind;
        button.disabled = true;
        error.hidden = true;
        try {
            const response = await fetch(`/transactions/options/${kind}`, {method: 'POST', body: (() => { const body = new FormData(form); body.set('csrf_token', document.querySelector('meta[name=csrf-token]').content); return body; })()});
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not create this item. Please try again.');
            const option = new Option(data.name, kind === 'category' ? data.name : String(data.id), true, true);
            option.dataset.label = data.name;
            option.dataset.kind = kind === 'category' ? 'color' : 'logo';
            if (kind === 'category') {
                option.dataset.color = data.color;
                option.dataset.icon = data.icon || data.name[0];
                option.dataset.categoryType = form.elements.type.value;
                form.elements.default_category.add(new Option(data.name, data.name));
            } else {
                option.dataset.defaultCategory = data.default_category || '';
            }
            quickSelect.add(option);
            quickSelect.dispatchEvent(new Event('optionschanged'));
            quickSelect.dispatchEvent(new Event('change', {bubbles: true}));
            quickDialog.close();
        } catch (failure) {
            error.textContent = failure.message || 'Could not connect. Try again.';
            error.hidden = false;
        } finally {
            button.disabled = false;
        }
    });
}

const preferenceMode = document.querySelector('[data-preference-mode]');
if (preferenceMode) {
    function syncPreference() {
        document.querySelector('[data-manual-account]').hidden = preferenceMode.value !== 'manual';
    }
    preferenceMode.addEventListener('change', syncPreference);
    syncPreference();
}

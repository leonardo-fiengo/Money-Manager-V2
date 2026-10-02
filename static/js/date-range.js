document.querySelectorAll("[data-date-range]").forEach((control) => {
    const startInput = control.querySelector('input[name="start"]');
    const endInput = control.querySelector('input[name="end"]');
    if (!startInput || !endInput) return;

    const parseDate = (value) => {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
        const [year, month, day] = value.split("-").map(Number);
        const date = new Date(year, month - 1, day);
        return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
    };
    const isoDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    const shortDate = (value) => parseDate(value)?.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) || "";
    const today = new Date();
    let viewMonth = parseDate(startInput.value)
        ? new Date(parseDate(startInput.value).getFullYear(), parseDate(startInput.value).getMonth(), 1)
        : new Date(today.getFullYear(), today.getMonth() - 1, 1);
    let choosingEnd = false;

    const trigger = control.querySelector(".date-range-trigger");
    if (!trigger) return;

    const panel = document.createElement("div");
    panel.className = "date-range-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Choose transaction date range");
    panel.innerHTML = `
        <div class="date-range-heading">
            <div><strong>Select a date range</strong><span class="date-range-hint">Choose the first day, then the last day.</span></div>
            <button type="button" class="date-range-clear">Clear</button>
        </div>
        <div class="date-range-calendar-header">
            <button type="button" class="date-range-nav" data-range-nav="-1" aria-label="Previous month">&lsaquo;</button>
            <span>Browse months</span>
            <button type="button" class="date-range-nav" data-range-nav="1" aria-label="Next month">&rsaquo;</button>
        </div>
        <div class="date-range-months"></div>
        <div class="date-range-presets">
            <button type="button" data-range-preset="this-month">This month</button>
            <button type="button" data-range-preset="last-month">Last month</button>
            <button type="button" data-range-preset="last-30">Last 30 days</button>
        </div>`;

    function updateTrigger() {
        const start = shortDate(startInput.value);
        const end = shortDate(endInput.value);
        trigger.querySelector(".date-range-value").textContent = start && end
            ? `${start} – ${end}`
            : start ? `From ${start}` : end ? `Until ${end}` : "Any date";
    }

    function close() {
        control.classList.remove("open");
        trigger.setAttribute("aria-expanded", "false");
    }

    function applyFilter() {
        control.closest("form")?.requestSubmit();
    }

    function renderMonth(monthDate) {
        const month = document.createElement("div");
        month.className = "date-range-month";
        const title = document.createElement("strong");
        title.className = "date-range-month-title";
        title.textContent = monthDate.toLocaleDateString("en-US", { month: "long", year: "numeric" });
        month.appendChild(title);
        const grid = document.createElement("div");
        grid.className = "date-range-days";
        ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].forEach((day) => {
            const heading = document.createElement("span");
            heading.className = "date-range-weekday";
            heading.textContent = day;
            grid.appendChild(heading);
        });
        for (let i = 0; i < monthDate.getDay(); i += 1) {
            const spacer = document.createElement("span");
            grid.appendChild(spacer);
        }
        const days = new Date(monthDate.getFullYear(), monthDate.getMonth() + 1, 0).getDate();
        for (let day = 1; day <= days; day += 1) {
            const date = new Date(monthDate.getFullYear(), monthDate.getMonth(), day);
            const value = isoDate(date);
            const button = document.createElement("button");
            button.type = "button";
            button.className = "date-range-day";
            button.dataset.date = value;
            button.textContent = String(day);
            button.setAttribute("aria-label", date.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" }));
            button.classList.toggle("range-edge", value === startInput.value || value === endInput.value);
            button.classList.toggle("in-range", !!startInput.value && !!endInput.value && value > startInput.value && value < endInput.value);
            button.classList.toggle("today", value === isoDate(today));
            button.addEventListener("click", () => {
                if (!choosingEnd) {
                    startInput.value = value;
                    endInput.value = "";
                    choosingEnd = true;
                    render();
                    panel.querySelector(".date-range-hint").textContent = "Now choose the last day.";
                    panel.querySelector(`[data-date="${value}"]`)?.focus();
                } else {
                    if (value < startInput.value) {
                        endInput.value = startInput.value;
                        startInput.value = value;
                    } else {
                        endInput.value = value;
                    }
                    choosingEnd = false;
                    render();
                    close();
                    applyFilter();
                }
                updateTrigger();
            });
            grid.appendChild(button);
        }
        month.appendChild(grid);
        return month;
    }

    function render() {
        const months = panel.querySelector(".date-range-months");
        months.replaceChildren(renderMonth(viewMonth), renderMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1)));
    }

    panel.querySelectorAll("[data-range-nav]").forEach((button) => button.addEventListener("click", () => {
        viewMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + Number(button.dataset.rangeNav), 1);
        render();
    }));
    panel.querySelector(".date-range-clear").addEventListener("click", () => {
        startInput.value = "";
        endInput.value = "";
        choosingEnd = false;
        updateTrigger();
        close();
        applyFilter();
    });
    panel.querySelectorAll("[data-range-preset]").forEach((button) => button.addEventListener("click", () => {
        const first = new Date(today.getFullYear(), today.getMonth(), 1);
        const last = new Date(today.getFullYear(), today.getMonth() + 1, 0);
        if (button.dataset.rangePreset === "last-month") {
            first.setMonth(first.getMonth() - 1);
            last.setDate(0);
        } else if (button.dataset.rangePreset === "last-30") {
            first.setTime(today.getTime());
            first.setDate(first.getDate() - 29);
            last.setTime(today.getTime());
        }
        startInput.value = isoDate(first);
        endInput.value = isoDate(last);
        viewMonth = new Date(first.getFullYear(), first.getMonth(), 1);
        choosingEnd = false;
        updateTrigger();
        close();
        applyFilter();
    }));

    trigger.addEventListener("click", () => {
        const opening = !control.classList.contains("open");
        document.querySelectorAll(".date-range-control.open").forEach((other) => other !== control && other.classList.remove("open"));
        if (typeof closeEnhancedSelects === "function") closeEnhancedSelects();
        control.classList.toggle("open", opening);
        trigger.setAttribute("aria-expanded", String(opening));
        if (opening) {
            choosingEnd = !!startInput.value && !endInput.value;
            panel.querySelector(".date-range-hint").textContent = choosingEnd ? "Now choose the last day." : "Choose the first day, then the last day.";
            render();
        }
    });
    control.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            close();
            trigger.focus();
        }
    });
    document.addEventListener("click", (event) => {
        if (!control.contains(event.target)) close();
    });

    control.classList.add("enhanced-range");
    control.append(panel);
    updateTrigger();
    render();
});

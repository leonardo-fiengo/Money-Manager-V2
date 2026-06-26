(function () {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const money = new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: 0,
    });

    const palette = {
        income: "#147d64",
        expenses: "#d45f3a",
        investments: "#376fd0",
        balance: "#111827",
        amber: "#d9941f",
        tealSoft: "rgba(20, 125, 100, 0.12)",
        blueSoft: "rgba(55, 111, 208, 0.12)",
        redSoft: "rgba(212, 95, 58, 0.12)",
        grid: "rgba(24, 32, 42, 0.08)",
        muted: "#657080",
    };

    const categoryColors = [
        "#147d64",
        "#d45f3a",
        "#376fd0",
        "#d9941f",
        "#8b5cf6",
        "#0891b2",
        "#be3455",
        "#64748b",
    ];

    function hasCanvas(id) {
        return Boolean(document.getElementById(id));
    }

    function emptyMessage(canvas, text) {
        const frame = canvas.closest(".chart-frame");
        if (!frame || frame.querySelector(".chart-empty")) return;
        const message = document.createElement("div");
        message.className = "chart-empty";
        message.textContent = text;
        frame.appendChild(message);
    }

    function valuesPresent(values) {
        return values.some((value) => Number(value || 0) !== 0);
    }

    function baseOptions(extra) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            resizeDelay: 120,
            animation: reduceMotion ? false : { duration: 800, easing: "easeOutQuart" },
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: {
                    position: "bottom",
                    labels: {
                        usePointStyle: true,
                        boxWidth: 8,
                        boxHeight: 8,
                        color: palette.muted,
                        padding: 18,
                    },
                },
                tooltip: {
                    backgroundColor: "#111827",
                    borderColor: "rgba(255, 255, 255, 0.12)",
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: true,
                    callbacks: {
                        label: (context) => `${context.dataset.label}: ${money.format(context.parsed.y ?? context.parsed)}`,
                    },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: palette.muted, maxRotation: 0 },
                    border: { display: false },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: palette.grid },
                    ticks: {
                        color: palette.muted,
                        callback: (value) => money.format(value),
                    },
                    border: { display: false },
                },
            },
            ...extra,
        };
    }

    function renderMonthlyChart(id, rows) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        const labels = rows.map((row) => row.month);
        const income = rows.map((row) => row.income || 0);
        const expenses = rows.map((row) => row.expenses || 0);
        const investments = rows.map((row) => row.investments || 0);
        if (!labels.length || !valuesPresent([...income, ...expenses, ...investments])) {
            emptyMessage(canvas, "Add transactions to see monthly flow.");
            return;
        }
        new Chart(canvas, {
            type: "line",
            data: {
                labels,
                datasets: [
                    { label: "Income", data: income, borderColor: palette.income, backgroundColor: palette.income, tension: 0.42, borderWidth: 3, pointRadius: 3, pointHoverRadius: 6, pointBorderWidth: 0 },
                    { label: "Expenses", data: expenses, borderColor: palette.expenses, backgroundColor: palette.expenses, tension: 0.42, borderWidth: 3, pointRadius: 3, pointHoverRadius: 6, pointBorderWidth: 0 },
                    { label: "Investments", data: investments, borderColor: palette.investments, backgroundColor: palette.investments, tension: 0.42, borderWidth: 3, pointRadius: 3, pointHoverRadius: 6, pointBorderWidth: 0 },
                ],
            },
            options: baseOptions({
                elements: { line: { capBezierPoints: true } },
                plugins: {
                    ...baseOptions().plugins,
                    legend: {
                        position: "bottom",
                        labels: {
                            usePointStyle: true,
                            pointStyle: "rectRounded",
                            boxWidth: 10,
                            boxHeight: 10,
                            color: palette.balance,
                            padding: 22,
                            font: { weight: "700" },
                        },
                    },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { color: palette.balance, font: { weight: "700" } }, border: { display: false } },
                    y: { ...baseOptions().scales.y, grid: { color: "rgba(24, 32, 42, 0.07)" } },
                },
            }),
        });
    }

    function renderCategoryChart(id, rows) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        const labels = rows.map((row) => row.category);
        const values = rows.map((row) => row.total || 0);
        if (!labels.length || !valuesPresent(values)) {
            emptyMessage(canvas, "Categorized expenses will appear here.");
            return;
        }
        new Chart(canvas, {
            type: "doughnut",
            data: {
                labels,
                datasets: [{
                    label: "Expenses",
                    data: values,
                    backgroundColor: labels.map((_, index) => categoryColors[index % categoryColors.length]),
                    borderColor: "#ffffff",
                    borderWidth: 4,
                    hoverOffset: 8,
                }],
            },
            options: baseOptions({
                cutout: "68%",
                scales: {},
                plugins: {
                    ...baseOptions().plugins,
                    tooltip: {
                        ...baseOptions().plugins.tooltip,
                        callbacks: {
                            label: (context) => `${context.label}: ${money.format(context.parsed)}`,
                        },
                    },
                },
            }),
        });
    }

    function renderBalanceChart(id, rows) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        const labels = rows.map((row) => row.date);
        const values = rows.map((row) => row.balance || 0);
        if (!labels.length) {
            emptyMessage(canvas, "Posted transactions will build your balance trend.");
            return;
        }
        const gradient = canvas.getContext("2d").createLinearGradient(0, 0, 0, 260);
        gradient.addColorStop(0, "rgba(20, 125, 100, 0.28)");
        gradient.addColorStop(1, "rgba(20, 125, 100, 0)");
        new Chart(canvas, {
            type: "line",
            data: {
                labels,
                datasets: [{
                    label: "Balance",
                    data: values,
                    borderColor: palette.income,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.35,
                    borderWidth: 3,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHitRadius: 16,
                }],
            },
            options: baseOptions({ plugins: { ...baseOptions().plugins, legend: { display: false } } }),
        });
    }

    function renderWeekdayChart(id, rows) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        const labels = rows.map((row) => row.weekday);
        const values = rows.map((row) => row.total || 0);
        if (!labels.length || !valuesPresent(values)) {
            emptyMessage(canvas, "Expense timing will appear here.");
            return;
        }
        new Chart(canvas, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    label: "Spending",
                    data: values,
                    backgroundColor: palette.amber,
                    borderRadius: 8,
                    maxBarThickness: 42,
                }],
            },
            options: baseOptions({ plugins: { ...baseOptions().plugins, legend: { display: false } } }),
        });
    }

    async function loadJson(url) {
        const response = await fetch(url, { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error(`Request failed: ${url}`);
        return response.json();
    }

    async function initDashboard() {
        if (!hasCanvas("dashboardMonthlyChart") && !hasCanvas("dashboardCategoryChart")) return;
        const data = await loadJson("/api/dashboard");
        renderMonthlyChart("dashboardMonthlyChart", data.monthly || []);
        renderCategoryChart("dashboardCategoryChart", data.categories || []);
    }

    async function initAnalytics() {
        if (!hasCanvas("analyticsBalanceChart") && !hasCanvas("analyticsWeekdayChart")) return;
        const data = await loadJson("/api/analytics");
        renderBalanceChart("analyticsBalanceChart", data.cumulative || []);
        renderWeekdayChart("analyticsWeekdayChart", data.weekdays || []);
        renderMonthlyChart("analyticsMonthlyChart", data.monthly || []);
        renderCategoryChart("analyticsCategoryChart", data.categories || []);
    }

    if (window.Chart) {
        Chart.defaults.font.family = "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
        Chart.defaults.color = palette.muted;
        initDashboard().catch(console.error);
        initAnalytics().catch(console.error);
    }
})();



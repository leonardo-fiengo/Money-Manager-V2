(function () {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dark = document.documentElement.dataset.theme === "dark";

    const money = new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: 0,
    });

    const palette = {
        income: dark ? "#95b6ff" : "#3568df",
        expenses: dark ? "#eca497" : "#cb8b7d",
        investments: dark ? "#c0b5e4" : "#a89bc8",
        balance: dark ? "#e9eef7" : "#1d2635",
        amber: "#d9941f",
        tealSoft: "rgba(20, 125, 100, 0.12)",
        blueSoft: "rgba(55, 111, 208, 0.12)",
        redSoft: "rgba(212, 95, 58, 0.12)",
        grid: dark ? "rgba(230, 245, 235, 0.1)" : "rgba(24, 32, 42, 0.08)",
        muted: dark ? "#a2b0c5" : "#687588",
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
        const labels = rows.map((row) => new Intl.DateTimeFormat("en-GB", {month:"short", year:"2-digit"}).format(new Date(row.month + "-01T12:00:00")));
        const income = rows.map((row) => row.income || 0);
        const expenses = rows.map((row) => row.expenses || 0);
        const investments = rows.map((row) => row.investments || 0);
        if (!labels.length || !valuesPresent([...income, ...expenses, ...investments])) {
            emptyMessage(canvas, "Add transactions to see monthly flow.");
            return;
        }
        new Chart(canvas, {
            type: rows.length === 1 ? "bar" : "line",
            data: {
                labels,
                datasets: [
                    { label: "Income", data: income, borderColor: palette.income, backgroundColor: palette.income, tension: 0.22, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, pointBorderWidth: 0 },
                    { label: "Expenses", data: expenses, borderColor: palette.expenses, backgroundColor: palette.expenses, tension: 0.22, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, pointBorderWidth: 0 },
                    { label: "Investments", data: investments, borderColor: palette.investments, backgroundColor: palette.investments, tension: 0.22, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, pointBorderWidth: 0 },
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
                            pointStyle: "circle",
                            boxWidth: 6,
                            boxHeight: 6,
                            color: palette.muted,
                            padding: 20,
                            font: { weight: "400", size: 11 },
                        },
                    },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { color: palette.muted, font: { weight: "400", size: 10 } }, border: { display: false } },
                    y: { ...baseOptions().scales.y, grid: { color: palette.grid }, ticks: { ...baseOptions().scales.y.ticks, maxTicksLimit: 5, font: {size: 10} } },
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
                    pointRadius: rows.length === 1 ? 4 : 0,
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
        const trend = document.getElementById("dashboardMonthlyChart");
        if (trend?.dataset.flowTrend) {
            renderMonthlyChart("dashboardMonthlyChart", JSON.parse(trend.dataset.flowTrend));
            return;
        }
        const period = new URLSearchParams(window.location.search).get('period') || 'month';
        const data = await loadJson(`/api/dashboard?period=${encodeURIComponent(period)}`);
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

    function initForecast() {
        const canvas = document.getElementById("forecastBalanceChart");
        if (!canvas) return;
        const points = JSON.parse(canvas.dataset.forecast || "[]");
        const step = Math.max(1, Math.ceil(points.length / 48));
        const shown = points.filter((_, index) => index % step === 0 || index === points.length - 1);
        new Chart(canvas, { type: "line", data: { labels: shown.map(point => point.date), datasets: [{ label: "Projected balance", data: shown.map(point => point.balance), borderColor: palette.income, backgroundColor: palette.tealSoft, fill: true, tension: 0.3, pointRadius: 0 }] }, options: baseOptions({ plugins: { ...baseOptions().plugins, legend: { display: false } } }) });
    }

    if (window.Chart) {
        Chart.defaults.font.family = "'Segoe UI Variable Text', 'Segoe UI', ui-sans-serif, system-ui, sans-serif";
        Chart.defaults.color = palette.muted;
        initDashboard().catch(console.error);
        initAnalytics().catch(console.error);
        initForecast();
        const history = document.getElementById("netWorthChart");
        if (history) renderBalanceChart("netWorthChart", JSON.parse(history.dataset.history || "[]"));
        const accountHistory = document.getElementById('accountBalanceChart');
        if (accountHistory) {
            const rows = JSON.parse(accountHistory.dataset.history || '[]');
            new Chart(accountHistory, {
                type: 'line',
                data: {labels: rows.map(row => new Intl.DateTimeFormat('en-GB', {month:'short',day:'numeric'}).format(new Date(row.date+'T12:00:00'))),
                    datasets: [{label:'Balance',data:rows.map(row=>row.balance),borderColor:palette.income,backgroundColor:palette.blueSoft,fill:true,tension:0.15,borderWidth:2,pointRadius:0,pointHoverRadius:5}]},
                options: baseOptions({plugins:{...baseOptions().plugins,legend:{display:false}}}),
            });
        }
        const accountSpending = document.getElementById('accountSpendingChart');
        if (accountSpending) {
            const rows = JSON.parse(accountSpending.dataset.categories || '[]');
            new Chart(accountSpending, {
                type: 'doughnut',
                data: {labels:rows.map(row=>row.category),datasets:[{data:rows.map(row=>row.total),backgroundColor:rows.map(row=>row.color),borderWidth:0,hoverOffset:4}]},
                options: {responsive:true,maintainAspectRatio:false,cutout:'72%',animation:reduceMotion?false:{duration:600},plugins:{legend:{display:false},tooltip:{callbacks:{label:context=>`${context.label}: ${new Intl.NumberFormat('en-GB',{style:'currency',currency:'EUR'}).format(context.parsed)}`}}}},
            });
        }
    }
})();



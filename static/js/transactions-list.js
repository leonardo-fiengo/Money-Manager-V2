const transactionDialog = document.querySelector("[data-transaction-dialog]");
if (transactionDialog) {
    document.querySelectorAll("[data-transaction-detail]").forEach((row) => {
        row.addEventListener("click", () => {
            for (const key of ["title", "date", "type", "account", "category", "description", "tags"]) {
                const target = transactionDialog.querySelector(`[data-detail-${key}]`);
                if (target) target.textContent = key === "date" && row.dataset.date
                    ? new Intl.DateTimeFormat("en-GB", {day:"numeric", month:"short", year:"numeric"}).format(new Date(row.dataset.date + "T12:00:00"))
                    : row.dataset[key] || "—";
            }
            const amount = new Intl.NumberFormat("en-GB", { style: "currency", currency: row.dataset.currency }).format(Number(row.dataset.amount));
            transactionDialog.querySelector("[data-detail-amount]").textContent = `${row.dataset.type === "income" ? "+" : row.dataset.type === "transfer" ? "" : "−"}${amount}`;
            transactionDialog.querySelector("[data-detail-edit]").href = row.dataset.editUrl;
            transactionDialog.querySelector("[data-detail-details]").href = row.dataset.detailsUrl;
            transactionDialog.querySelector("[data-detail-delete]").action = row.dataset.deleteUrl;
            transactionDialog.querySelector('[data-detail-frame]').src = row.dataset.detailsUrl + '?panel=1';
            transactionDialog.showModal();
        });
    });
    transactionDialog.querySelector("[data-detail-close]").addEventListener("click", () => transactionDialog.close());
    transactionDialog.querySelector('[data-detail-edit]').addEventListener('click', event => {
        event.preventDefault();
        transactionDialog.querySelector('[data-detail-frame]').src = event.currentTarget.href + '?panel=1';
    });
    let changed = false;
    window.addEventListener('message', event => {
        if (event.origin !== location.origin || event.source !== transactionDialog.querySelector('[data-detail-frame]').contentWindow) return;
        if (event.data?.type === 'money-manager-panel-change') changed = true;
        if (event.data?.type === 'money-manager-panel-close') transactionDialog.close();
        if (event.data?.type === 'money-manager-panel-summary') {
            const amount = new Intl.NumberFormat('en-GB',{style:'currency',currency:event.data.currency}).format(Number(event.data.amount));
            transactionDialog.querySelector('[data-detail-title]').textContent = event.data.title;
            transactionDialog.querySelector('[data-detail-amount]').textContent = `${event.data.transactionType === 'income' ? '+' : event.data.transactionType === 'transfer' ? '' : '−'}${amount}`;
        }
    });
    transactionDialog.addEventListener('close', () => {
        transactionDialog.querySelector('[data-detail-frame]').removeAttribute('src');
        if (changed) location.reload();
    });
    transactionDialog.addEventListener("click", (event) => {
        if (event.target === transactionDialog) transactionDialog.close();
    });
}

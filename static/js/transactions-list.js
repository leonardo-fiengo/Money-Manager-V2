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
            transactionDialog.showModal();
        });
    });
    transactionDialog.querySelector("[data-detail-close]").addEventListener("click", () => transactionDialog.close());
    transactionDialog.addEventListener("click", (event) => {
        if (event.target === transactionDialog) transactionDialog.close();
    });
}

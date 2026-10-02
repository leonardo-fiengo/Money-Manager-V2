const quickAddDialog = document.querySelector("[data-quick-add-dialog]");
if (quickAddDialog) {
    document.querySelectorAll("[data-open-quick-add]").forEach((button) => button.addEventListener("click", () => {
        quickAddDialog.showModal();
        quickAddDialog.querySelector('input[name="amount"]').focus();
    }));
    quickAddDialog.querySelector("[data-close-quick-add]").addEventListener("click", () => quickAddDialog.close());
    quickAddDialog.addEventListener("click", (event) => {
        if (event.target === quickAddDialog) quickAddDialog.close();
    });
    const destination = quickAddDialog.querySelector("[data-quick-destination]");
    const category = quickAddDialog.querySelector("[data-quick-category]");
    const merchant = quickAddDialog.querySelector("[data-quick-merchant]");
    const sourceAccount = quickAddDialog.querySelector('select[name="account_id"]');
    const destinationAccount = destination.querySelector("select");
    const categorySelect = category.querySelector("select");
    const dateInput = quickAddDialog.querySelector('input[name="date"]');
    const futureNote = quickAddDialog.querySelector('[data-future-note]');
    function syncFuture() {
        futureNote.hidden = !(dateInput.value > dateToIso(new Date()));
    }
    quickAddDialog.querySelector('.date-control').addEventListener('change', syncFuture);
    syncFuture();
    if (typeof enhanceSelect === "function") enhanceSelect(destinationAccount);
    merchant.querySelector("select").addEventListener("change", (event) => {
        const suggested = event.target.selectedOptions[0]?.dataset.defaultCategory;
        if (suggested && !category.querySelector("select").value) {
            category.querySelector("select").value = suggested;
            category.querySelector("select").dispatchEvent(new Event("change", { bubbles: true }));
        }
    });
    quickAddDialog.querySelectorAll('input[name="type"]').forEach((input) => input.addEventListener("change", () => {
        const kind = quickAddDialog.querySelector('input[name="type"]:checked').value;
        const transfer = kind === "transfer";
        destination.hidden = !transfer;
        destination.querySelector("select").disabled = !transfer;
        if (transfer && destinationAccount.value === sourceAccount.value) {
            const other = Array.from(destinationAccount.options).find((option) => option.value !== sourceAccount.value);
            if (other) {
                destinationAccount.value = other.value;
                destinationAccount.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }
        category.hidden = transfer;
        categorySelect.disabled = transfer;
        Array.from(categorySelect.options).forEach((option) => {
            option.hidden = Boolean(option.value && option.dataset.categoryType !== 'any' && option.dataset.categoryType !== kind);
        });
        if (categorySelect.selectedOptions[0]?.hidden) categorySelect.value = '';
        categorySelect.dispatchEvent(new Event('optionschanged'));
        categorySelect.dispatchEvent(new Event('change', { bubbles: true }));
        merchant.hidden = transfer;
        merchant.querySelector("select").disabled = transfer;
    }));
    quickAddDialog.querySelector('input[name="type"]:checked').dispatchEvent(new Event('change'));
    sourceAccount.addEventListener("change", () => {
        if (destinationAccount.disabled || destinationAccount.value !== sourceAccount.value) return;
        const other = Array.from(destinationAccount.options).find((option) => option.value !== sourceAccount.value);
        if (other) {
            destinationAccount.value = other.value;
            destinationAccount.dispatchEvent(new Event("change", { bubbles: true }));
        }
    });
}

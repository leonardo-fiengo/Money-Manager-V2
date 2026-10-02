(() => {
    document.querySelectorAll('[data-detail-period]').forEach(select => {
        const form = select.closest('form');
        form.querySelector('.detail-filter-apply').hidden = true;
        select.addEventListener('change', () => form.requestSubmit());
    });
    const theme = document.documentElement.dataset.theme || 'light';
    document.querySelectorAll('[data-theme-choice]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.themeChoice === theme));
        button.addEventListener('click', () => {
            if (button.dataset.themeChoice === document.documentElement.dataset.theme) return;
            try { localStorage.setItem('money-manager-theme', button.dataset.themeChoice); } catch (_) {}
            document.documentElement.dataset.theme = button.dataset.themeChoice;
            window.location.reload();
        });
    });

    const filters = document.querySelector('[data-account-filters]');
    if (filters) {
        const search = filters.querySelector('[data-account-search]');
        const type = filters.querySelector('[data-account-type-filter]');
        const rows = [...document.querySelectorAll('[data-active-account-list] [data-account-row]')];
        filters.hidden = rows.length === 0;
        function filterAccounts() {
            let visible = 0;
            rows.forEach(row => {
                row.hidden = !row.dataset.accountName.includes(search.value.trim().toLowerCase()) ||
                    Boolean(type.value && row.dataset.accountType !== type.value);
                if (!row.hidden) visible++;
            });
            document.querySelector('[data-account-search-empty]').hidden = visible > 0 || rows.length === 0;
        }
        search.addEventListener('input', filterAccounts);
        type.addEventListener('change', filterAccounts);
    }

    const form = document.querySelector('[data-account-form]');
    if (form) {
        const settlement = form.querySelector('[data-account-settlement]');
        const target = form.elements.settlement_account_id;
        const day = form.elements.settlement_day;
        function syncSettlement() {
            const isCard = form.elements.type.value === 'credit_card';
            settlement.hidden = !isCard;
            target.disabled = !isCard;
            day.disabled = !isCard || !target.value;
            day.required = isCard && Boolean(target.value);
        }
        form.elements.type.addEventListener('change', syncSettlement);
        target.addEventListener('change', syncSettlement);
        syncSettlement();
        const logos = [...form.querySelectorAll('[data-account-logo]')];
        function syncLogo() {
            logos.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.accountLogo === form.elements.logo.value)));
        }
        logos.forEach(button => button.addEventListener('click', () => {
            form.elements.logo.value = button.dataset.accountLogo;
            syncLogo();
        }));
        form.elements.logo.addEventListener('input', syncLogo);
        syncLogo();
    }
})();

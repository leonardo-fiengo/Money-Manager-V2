(() => {
    if (document.body.classList.contains('is-embedded')) {
        const summary = document.querySelector('[data-panel-summary]');
        if (summary) parent.postMessage({type:'money-manager-panel-summary',title:summary.dataset.title,amount:summary.dataset.amount,currency:summary.dataset.currency,transactionType:summary.dataset.type},location.origin);
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && !document.querySelector('dialog[open]')) parent.postMessage({type:'money-manager-panel-close'},location.origin);
        });
        document.querySelectorAll('form').forEach(form => form.addEventListener('submit', () => {
            if (form.method.toLowerCase() === 'post') parent.postMessage({type:'money-manager-panel-change'}, location.origin);
        }));
        return;
    }
    const review = document.querySelector('[data-review-workspace]');
    if (!review) return;
    const form = review.querySelector('form');
    const focused = form.querySelector('[data-review-focused-id]');
    const choices = [...document.querySelectorAll('[data-review-select]')];
    let index = 0;
    function updateSelection() {
        const count = choices.filter(row => row.checked).length;
        focused.disabled = count > 0;
        review.querySelector('[data-review-selected]').textContent = count ? `${count} selected — same category and merchant applied to all` : 'Reviewing one transaction';
        review.querySelector('[data-review-apply]').textContent = count ? `Apply to ${count} selected` : 'Apply & next';
    }
    function focusRow(next) {
        if (!choices.length) return;
        index = Math.max(0, Math.min(next, choices.length - 1));
        const row = choices[index];
        focused.value = row.value;
        review.querySelector('[data-review-title]').textContent = row.dataset.title;
        review.querySelector('[data-review-info]').textContent = row.dataset.info;
        form.elements.category.value = row.dataset.category;
        form.elements.merchant_id.value = row.dataset.merchant;
        const rule = new URL(review.querySelector('[data-review-rule]').href);
        rule.searchParams.set('contains', row.dataset.description);
        rule.searchParams.set('name', `Categorize ${row.dataset.description || 'import'}`);
        rule.searchParams.set('category', row.dataset.category);
        review.querySelector('[data-review-rule]').href = rule;
    }
    choices.forEach(row => row.addEventListener('change', updateSelection));
    function updateRule() {
        const link = review.querySelector('[data-review-rule]');
        const rule = new URL(link.href);
        rule.searchParams.set('category', form.elements.category.value);
        rule.searchParams.set('merchant_id', form.elements.merchant_id.value);
        link.href = rule;
    }
    form.elements.category.addEventListener('change', updateRule);
    form.elements.merchant_id.addEventListener('change', updateRule);
    review.querySelector('[data-review-reset]').addEventListener('click', () => { choices.forEach(row => { row.checked=false; }); updateSelection(); });
    document.addEventListener('keydown', event => {
        if (event.ctrlKey || event.metaKey || event.altKey || document.querySelector('dialog[open]') || ['INPUT','TEXTAREA','SELECT','BUTTON'].includes(event.target.tagName) || event.target.isContentEditable) return;
        if (event.key.toLowerCase() === 'j' || event.key.toLowerCase() === 'k') {
            event.preventDefault(); focusRow(index + (event.key.toLowerCase() === 'j' ? 1 : -1));
        } else if (event.key === 'Enter') { event.preventDefault(); form.requestSubmit(); }
    });
})();

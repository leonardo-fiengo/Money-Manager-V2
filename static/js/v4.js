(() => {
    const privacyButton = document.querySelector('[data-balance-privacy]');
    let hidden = document.documentElement.dataset.balancesHidden === 'true';
    const currencyPattern = /(?:[+−-]?\s*(?:€|\$|£|EUR\s|USD\s|GBP\s|CHF\s)\s*\d[\d,]*(?:\.\d{1,2})?|[+−-]?\d[\d,]*(?:\.\d{1,2})?\s*€|[−-]?\d+(?:\.\d+)?%)/g;
    function markPrivateText() {
        const main = document.querySelector('main');
        if (!main) return;
        const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (!node.parentElement.closest('[data-private-balance],script,style,input,textarea,select,option') && currencyPattern.test(node.textContent)) nodes.push(node);
            currencyPattern.lastIndex = 0;
        }
        for (const node of nodes) {
            const fragment = document.createDocumentFragment();
            let previous = 0;
            for (const match of node.textContent.matchAll(currencyPattern)) {
                fragment.append(document.createTextNode(node.textContent.slice(previous, match.index)));
                const span = document.createElement('span');
                span.dataset.privateBalance = '';
                span.textContent = match[0];
                fragment.append(span);
                previous = match.index + match[0].length;
            }
            fragment.append(document.createTextNode(node.textContent.slice(previous)));
            node.replaceWith(fragment);
        }
    }
    function updatePrivacy() {
        privacyObserver.disconnect();
        markPrivateText();
        document.querySelectorAll('[data-private-balance]').forEach(element => {
            if (!element.dataset.realBalance) element.dataset.realBalance = element.textContent;
            const next = hidden ? '••••' : element.dataset.realBalance;
            if (element.textContent !== next) element.textContent = next;
            if (hidden) element.setAttribute('aria-label', 'Amount hidden'); else element.removeAttribute('aria-label');
        });
        document.documentElement.dataset.balancesHidden = String(hidden);
        document.querySelectorAll('[data-privacy-setting]').forEach(input => { input.checked = hidden; });
        document.querySelectorAll('canvas').forEach(canvas => { canvas.setAttribute('aria-hidden', String(hidden)); });
        if (privacyButton) {
            privacyButton.setAttribute('aria-label', hidden ? 'Show balances' : 'Hide balances');
            privacyButton.setAttribute('aria-pressed', String(hidden));
            privacyButton.title = hidden ? 'Show balances' : 'Hide balances';
            privacyButton.innerHTML = `<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>${hidden ? '<path d="M3 3l18 18"/>' : ''}</svg>`;
        }
        privacyObserver.observe(document.querySelector('main'), {subtree:true, childList:true, characterData:true});
    }
    const privacyObserver = new MutationObserver(() => updatePrivacy());
    function togglePrivacy() {
        hidden = !hidden;
        try { localStorage.setItem('money-manager-hide-balance', hidden ? '1' : '0'); } catch (_) {}
        updatePrivacy();
    }
    privacyButton?.addEventListener('click', togglePrivacy);
    document.querySelectorAll('[data-privacy-setting]').forEach(input => input.addEventListener('change', togglePrivacy));
    updatePrivacy();
    document.querySelectorAll('[data-budget-suggestion]').forEach(button => button.addEventListener('click', () => {
        const form = document.getElementById('budget-form');
        const category = form.querySelector('select[name=category_id]');
        category.value = button.dataset.budgetSuggestion;
        category.dispatchEvent(new Event('change', {bubbles:true}));
        const amount = form.querySelector('input[name=amount]');
        amount.value = button.dataset.budgetAmount;
        amount.focus();
        form.scrollIntoView({block:'center', behavior:'auto'});
    }));

    const sparkline = document.querySelector('[data-sparkline]');
    if (sparkline) {
        try {
            const values = JSON.parse(sparkline.dataset.sparkline).map(Number).filter(Number.isFinite);
            if (values.length > 1) {
                const low = Math.min(...values), high = Math.max(...values), spread = high - low || 1;
                const points = values.map((value, index) => `${index / (values.length - 1) * 240},${64 - (value - low) / spread * 52}`).join(' ');
                const area = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                area.setAttribute('points', `0,72 ${points} 240,72`);
                sparkline.appendChild(area);
                const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
                line.setAttribute('points', points);
                line.setAttribute('vector-effect', 'non-scaling-stroke');
                sparkline.appendChild(line);
            }
        } catch (_) {}
    }

    const palette = document.querySelector('[data-command-palette]');
    const commandInput = palette?.querySelector('[data-command-input]');
    const items = Array.from(palette?.querySelectorAll('[data-command-item]') || []);
    function filterCommands() {
        const query = commandInput.value.trim().toLowerCase();
        items.forEach((item) => { item.hidden = !item.textContent.toLowerCase().includes(query); });
        let searchLink = palette.querySelector('[data-command-search]');
        if (query && !items.some((item) => !item.hidden)) {
            if (!searchLink) {
                searchLink = document.createElement('a');
                searchLink.dataset.commandSearch = '';
                palette.querySelector('.command-results').appendChild(searchLink);
            }
            searchLink.href = `/transactions/?search=${encodeURIComponent(commandInput.value.trim())}`;
            searchLink.textContent = `Search transactions for “${commandInput.value.trim()}”`;
            searchLink.hidden = false;
        } else if (searchLink) searchLink.hidden = true;
    }
    commandInput?.addEventListener('input', filterCommands);
    document.addEventListener('keydown', (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            if (palette?.open) palette.close(); else { palette?.showModal(); commandInput?.focus(); }
        }
        if (event.key.toLowerCase() === 'b' && !event.ctrlKey && !event.altKey && !event.metaKey && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) && !palette?.open) togglePrivacy();
    });
    commandInput?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            const first = palette.querySelector('[data-command-item]:not([hidden]), [data-command-search]:not([hidden])');
            if (first) { event.preventDefault(); window.location.href = first.href; }
        }
    });
    palette?.addEventListener('click', (event) => { if (event.target === palette) palette.close(); });

    const brand = document.querySelector('.app-sidebar .brand');
    let logoClicks = 0, logoTimer;
    brand?.addEventListener('click', (event) => {
        logoClicks += 1;
        clearTimeout(logoTimer);
        logoTimer = setTimeout(() => { logoClicks = 0; }, 2500);
        if (logoClicks === 5) {
            event.preventDefault();
            const mark = brand.querySelector('.brand-mark');
            mark?.classList.remove('coin-drop');
            void mark?.offsetWidth;
            mark?.classList.add('coin-drop');
            setTimeout(() => mark?.classList.remove('coin-drop'), 600);
        }
        if (logoClicks === 10) { event.preventDefault(); logoClicks = 0; brand.title = 'Please stop depositing imaginary money.'; }
    });
})();

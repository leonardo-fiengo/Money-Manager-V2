(() => {
    const privacyButtons = document.querySelectorAll('[data-balance-privacy]');
    const privateText = new WeakMap();
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
        const visited = new Set();
        document.querySelectorAll('[data-private-balance]').forEach(element => {
            // Mask text nodes, preserving child elements, sizes, and labels.
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const node = walker.currentNode;
                if (visited.has(node)) continue;
                visited.add(node);
                let saved = privateText.get(node);
                if (!saved || node.data !== saved.rendered) saved = {real: node.data};
                currencyPattern.lastIndex = 0;
                const hasAmount = currencyPattern.test(saved.real);
                currencyPattern.lastIndex = 0;
                const explicitLeaf = node.parentElement.matches('[data-private-balance]') && !node.parentElement.childElementCount;
                if (!hasAmount && (!explicitLeaf || !saved.real.trim())) continue;
                const next = hidden ? (hasAmount ? saved.real.replace(currencyPattern, '••••') : '••••') : saved.real;
                if (node.data !== next) node.data = next;
                saved.rendered = next;
                privateText.set(node, saved);
            }
            if (!element.childElementCount) {
                if (hidden) element.setAttribute('aria-label', 'Amount hidden'); else element.removeAttribute('aria-label');
            }
        });
        document.documentElement.dataset.balancesHidden = String(hidden);
        document.querySelectorAll('[data-privacy-setting]').forEach(input => { input.checked = hidden; });
        document.querySelectorAll('canvas').forEach(canvas => { canvas.setAttribute('aria-hidden', String(hidden)); });
        privacyButtons.forEach(privacyButton => {
            privacyButton.setAttribute('aria-label', hidden ? 'Show balances' : 'Hide balances');
            privacyButton.setAttribute('aria-pressed', String(hidden));
            privacyButton.title = hidden ? 'Show balances' : 'Hide balances';
            privacyButton.innerHTML = `<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>${hidden ? '<path d="M3 3l18 18"/>' : ''}</svg>`;
        });
        privacyObserver.observe(document.querySelector('main'), {subtree:true, childList:true, characterData:true});
    }
    const privacyObserver = new MutationObserver(() => updatePrivacy());
    function togglePrivacy() {
        hidden = !hidden;
        try { localStorage.setItem('money-manager-hide-balance', hidden ? '1' : '0'); } catch (_) {}
        updatePrivacy();
    }
    privacyButtons.forEach(button => button.addEventListener('click', togglePrivacy));
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
    const commandSearch = palette?.querySelector('[data-command-search]');
    const visibleCommands = () => items.filter(item => !item.hidden).concat(commandSearch && !commandSearch.hidden ? [commandSearch] : []);
    function filterCommands() {
        const query = commandInput.value.trim().toLowerCase();
        const words = query.split(/\s+/).filter(Boolean);
        items.forEach(item => {
            const text = `${item.textContent} ${item.dataset.commandKeywords || ''}`.toLowerCase();
            item.hidden = !words.every(word => text.includes(word));
        });
        palette.querySelectorAll('[data-command-group]').forEach(group => {
            group.hidden = !group.querySelector('[data-command-item]:not([hidden])');
        });
        const count = items.filter(item => !item.hidden).length;
        const fallback = Boolean(query && !count);
        commandSearch.hidden = !fallback;
        palette.querySelector('[data-command-no-match]').hidden = !fallback;
        if (fallback) {
            commandSearch.href = `/transactions/?search=${encodeURIComponent(commandInput.value.trim())}`;
            commandSearch.querySelector('[data-command-search-label]').textContent = `Search transactions for “${commandInput.value.trim()}”`;
        }
        palette.querySelector('[data-command-count]').textContent = query ? `${count} matching ${count === 1 ? 'page' : 'pages'}` : `${count} destinations`;
    }
    commandInput?.addEventListener('input', filterCommands);
    function openCommands() {
        if (!palette) return;
        commandInput.value = '';
        filterCommands();
        palette.showModal();
        palette.querySelector('.command-results').scrollTop = 0;
        commandInput.focus();
    }
    document.querySelectorAll('[data-open-command]').forEach(button => button.addEventListener('click',openCommands));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && palette?.open) {
            event.preventDefault();
            palette.close();
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            if (palette?.open) palette.close(); else openCommands();
        }
        if (event.key.toLowerCase() === 'b' && !event.ctrlKey && !event.altKey && !event.metaKey && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) && !document.activeElement?.isContentEditable && !palette?.open) togglePrivacy();
    });
    commandInput?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            const first = visibleCommands()[0];
            if (first) { event.preventDefault(); window.location.href = first.href; }
        } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const choices = visibleCommands();
            (event.key === 'ArrowDown' ? choices[0] : choices.at(-1))?.focus();
        }
    });
    palette?.addEventListener('keydown', event => {
        const current = event.target.closest('[data-command-item], [data-command-search]');
        if (!current || !['ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault();
        const choices = visibleCommands(), index = choices.indexOf(current);
        const grid = current.closest('.command-group-grid');
        const columns = grid ? getComputedStyle(grid).gridTemplateColumns.split(' ').length : 1;
        let next = index + ({ArrowDown:columns, ArrowUp:-columns, ArrowLeft:-1, ArrowRight:1}[event.key] || 0);
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = choices.length - 1;
        if (next < 0) commandInput.focus(); else choices[Math.min(next,choices.length - 1)]?.focus();
    });
    palette?.querySelector('[data-command-close]').addEventListener('click', () => palette.close());
    palette?.addEventListener('click', event => {
        const bounds = palette.getBoundingClientRect();
        if (event.target === palette && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) palette.close();
    });

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

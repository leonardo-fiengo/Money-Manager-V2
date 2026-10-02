(() => {
    const back = document.querySelector('[data-page-back]');
    const storageKey = 'money-manager-navigation';
    const current = window.location.pathname + window.location.search;
    const fallback = back?.getAttribute('href');
    let trail = [];

    function safePath(value) {
        if (typeof value !== 'string') return null;
        try {
            const url = new URL(value, window.location.origin);
            return url.origin === window.location.origin ? url.pathname + url.search : null;
        } catch (_) { return null; }
    }

    function updateBack(event) {
        try {
            const stored = JSON.parse(sessionStorage.getItem(storageKey) || '[]');
            trail = Array.isArray(stored) ? stored.map(safePath).filter(Boolean) : [];
        } catch (_) { trail = []; }
        // Browser back/forward should revisit an existing entry instead of
        // creating a loop between the two most recently viewed pages.
        if (event.persisted || performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
            const index = trail.lastIndexOf(current);
            if (index !== -1) trail = trail.slice(0, index + 1);
        }
        if (trail.at(-1) !== current) trail.push(current);
        trail = trail.slice(-100);
        try { sessionStorage.setItem(storageKey, JSON.stringify(trail)); } catch (_) {}

        // Sidebar pages have no Back control, but must remain in the trail
        // so an editor or detail page can return to the page that opened it.
        if (!back) return;

        // Once the trail is exhausted, use the parent page. The referrer may
        // be the page we just returned from and would send the user in a loop.
        const target = trail.at(-2) || fallback;
        back.setAttribute('href', target);
        const disabled = target === current;
        if (disabled) {
            back.setAttribute('aria-disabled', 'true');
            back.title = 'You are already at the first page';
        } else {
            back.removeAttribute('aria-disabled');
            back.title = 'Go back';
        }
    }

    back?.addEventListener('click', event => {
        if (back.getAttribute('aria-disabled') === 'true') { event.preventDefault(); return; }
        if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        // Follow a GET link rather than replaying a previous form submission.
        if (trail.length > 1) {
            trail.pop();
            try { sessionStorage.setItem(storageKey, JSON.stringify(trail)); } catch (_) {}
        }
    });
    window.addEventListener('pageshow', updateBack);
})();

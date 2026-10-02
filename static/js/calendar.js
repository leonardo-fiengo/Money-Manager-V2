(() => {
    const panel = document.querySelector('[data-calendar-panel]');
    if (!panel) return;
    const events = JSON.parse(document.getElementById('calendar-event-data').textContent);
    const content = panel.querySelector('[data-calendar-content]');
    const title = panel.querySelector('h2');
    const subtitle = panel.querySelector('[data-panel-subtitle]');
    const money = value => new Intl.NumberFormat('en-IE', {style: 'currency', currency: 'EUR'}).format(value);
    const dateLabel = value => new Intl.DateTimeFormat('en-GB', {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'}).format(new Date(`${value}T12:00:00`));
    const node = (tag, text, className) => {
        const element = document.createElement(tag);
        element.textContent = text;
        if (className) element.className = className;
        return element;
    };
    function show() {
        if (!panel.open) panel.showModal();
    }
    function payment(day, index) {
        const event = events[day][index];
        title.textContent = event.name;
        subtitle.textContent = 'Payment details';
        content.replaceChildren();
        const back = node('button', '\u2190 All payments for this day', 'calendar-back quiet-button');
        back.type = 'button';
        back.addEventListener('click', () => openDay(day));
        content.append(back, node('p', `${event.amount > 0 ? '+' : event.type === 'transfer' ? '' : '\u2212'}${money(event.price ?? Math.abs(event.amount))}`, `calendar-payment-amount ${event.amount > 0 ? 'positive' : event.type === 'transfer' ? 'neutral' : 'negative'}`));
        const details = node('dl', '', 'calendar-payment-details');
        for (const [label, value] of [['Date', dateLabel(day)], ['Status', {posted: 'Posted', pending: 'Pending', recurring: 'Recurring (projected)'}[event.source] || event.source], ['Type', event.type || (event.amount > 0 ? 'Income' : 'Expense')], ['Account', event.account], ['Category', event.category], ['Note', event.description]]) {
            if (value) details.append(node('dt', label), node('dd', value));
        }
        content.append(details);
        show();
    }
    function openDay(day) {
        title.textContent = dateLabel(day);
        subtitle.textContent = 'Day overview';
        content.replaceChildren();
        const rows = events[day] || [];
        const summary = node('div', '', 'calendar-day-summary');
        for (const [label, value] of [['Income', rows.reduce((n, e) => n + Math.max(0, e.amount), 0)], ['Expenses', rows.reduce((n, e) => n + Math.max(0, -e.amount), 0)]]) {
            const item = node('div', '');
            item.append(node('span', label), node('strong', money(value)));
            summary.append(item);
        }
        content.append(summary, node('p', `${rows.length} ${rows.length === 1 ? 'payment' : 'payments'}`, 'calendar-count'));
        if (!rows.length) content.append(node('p', 'No payments for this day. Enjoy a little breathing room.', 'calendar-empty'));
        rows.forEach((event, index) => {
            const button = node('button', '', 'calendar-payment-row');
            button.type = 'button';
            const copy = node('span', '');
            copy.append(node('strong', event.name), node('small', {posted: 'Posted', pending: 'Pending', recurring: 'Recurring \u00b7 Projected'}[event.source] || event.source));
            button.append(copy, node('strong', `${event.amount > 0 ? '+' : event.type === 'transfer' ? '' : '\u2212'}${money(event.price ?? Math.abs(event.amount))}`, event.amount > 0 ? 'positive' : event.type === 'transfer' ? 'neutral' : 'negative'));
            button.addEventListener('click', () => payment(day, index));
            content.append(button);
        });
        show();
    }
    document.querySelectorAll('[data-open-day]').forEach(button => button.addEventListener('click', () => openDay(button.dataset.openDay)));
    document.querySelectorAll('[data-open-payment]').forEach(button => button.addEventListener('click', () => payment(button.dataset.date, Number(button.dataset.openPayment))));
    document.querySelectorAll('[data-calendar-day]').forEach(cell => cell.addEventListener('click', event => {
        if (!event.target.closest('button')) openDay(cell.dataset.calendarDay);
    }));
    panel.querySelector('[data-calendar-close]').addEventListener('click', () => panel.close());
    panel.addEventListener('click', event => {
        const bounds = panel.getBoundingClientRect();
        if (event.target === panel && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) panel.close();
    });
})();

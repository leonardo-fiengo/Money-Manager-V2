document.querySelectorAll('form').forEach(form => {
    const kind = form.querySelector('[name="payee_kind"]');
    if (!kind) return;
    function syncPayee() {
        const transfer = form.querySelector('[name="type"]:checked')?.value === 'transfer';
        const contact = kind.value === 'contact';
        form.querySelector('[data-payee-kind]').hidden = transfer;
        kind.disabled = transfer;
        [['[data-payee-merchant]', transfer || contact], ['[data-payee-contact]', transfer || !contact]].forEach(([selector, hidden]) => {
            const field = form.querySelector(selector);
            field.hidden = hidden;
            field.querySelector('select').disabled = hidden;
        });
        form.querySelector('[name="contact_id"]').required = !transfer && contact;
    }
    kind.addEventListener('change', syncPayee);
    form.querySelectorAll('[name="type"]').forEach(input => input.addEventListener('change', syncPayee));
    syncPayee();
});
const loanContact = document.querySelector('[data-loan-contact]');
if (loanContact) {
    function syncContact() {
        const field = document.querySelector('[data-counterparty]');
        field.hidden = Boolean(loanContact.value);
        field.querySelector('input').required = !loanContact.value;
    }
    loanContact.addEventListener('change', syncContact);
    syncContact();
}

(() => {
    const info = document.querySelector('[data-position-explainer]');
    document.querySelectorAll('[data-position-info]').forEach(button => button.addEventListener('click', () => info?.showModal()));
    info?.querySelector('[data-position-close]').addEventListener('click', () => info.close());
    info?.addEventListener('click', event => {
        const bounds = info.getBoundingClientRect();
        if (event.target === info && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) info.close();
    });

    const editor = document.querySelector('[data-workspace-editor]');
    if (!editor) return;
    const canvas = editor.querySelector('[data-editor-canvas]');
    const templates = [...document.querySelectorAll('[data-widget-template]')];
    const status = editor.querySelector('[data-editor-status]');
    let dirty = false;
    let submitting = false;
    const blocks = () => [...canvas.querySelectorAll('[data-editor-block]')];
    function update(changed = true) {
        if (changed) dirty = true;
        const active = blocks();
        editor.querySelector('[data-editor-empty]').hidden = active.length > 0;
        editor.querySelectorAll('[data-add-widget]').forEach(button => {
            const included = active.some(block => block.dataset.editorBlock === button.dataset.addWidget);
            button.disabled = included;
            button.textContent = included ? 'Added' : 'Add';
        });
        active.forEach((block, index) => {
            block.querySelector('[data-move="up"]').disabled = index === 0;
            block.querySelector('[data-move="down"]').disabled = index === active.length - 1;
        });
        status.textContent = `${dirty ? 'Unsaved changes' : 'Saved layout'} · ${active.length} widgets`;
        document.dispatchEvent(new Event('workspace-layout-change'));
    }
    function add(key) {
        if (blocks().some(block => block.dataset.editorBlock === key)) return;
        const template = templates.find(item => item.dataset.widgetTemplate === key);
        canvas.append(template.content.cloneNode(true));
    }
    function remove(block) {
        block.querySelectorAll('canvas').forEach(chart => window.Chart?.getChart(chart)?.destroy());
        block.remove();
    }
    editor.addEventListener('click', event => {
        const button = event.target.closest('button');
        if (!button || button.type === 'submit') return;
        const block = button.closest('[data-editor-block]');
        if (button.hasAttribute('data-add-widget')) {
            add(button.dataset.addWidget);
            update();
            const added = blocks().find(item => item.dataset.editorBlock === button.dataset.addWidget);
            added.querySelector('[data-remove-widget]').focus({preventScroll:true});
            added.scrollIntoView({block:'nearest', behavior:'auto'});
        } else if (button.hasAttribute('data-remove-widget')) {
            const key = block.dataset.editorBlock;
            remove(block); update();
            editor.querySelector(`[data-add-widget="${key}"]`).focus({preventScroll:true});
        } else if (button.hasAttribute('data-move')) {
            const active = blocks(), index = active.indexOf(block);
            if (button.dataset.move === 'up' && index > 0) canvas.insertBefore(block, active[index - 1]);
            if (button.dataset.move === 'down' && index < active.length - 1) canvas.insertBefore(active[index + 1], block);
            update(); button.focus({preventScroll:true});
        } else if (button.hasAttribute('data-widget-width')) {
            const width = block.dataset.width === 'half' ? 'full' : 'half';
            block.classList.remove(`widget-width-${block.dataset.width}`);
            block.dataset.width = width;
            block.classList.add(`widget-width-${width}`);
            block.querySelector('input[name="widths"]').value = width;
            button.textContent = width === 'half' ? 'Half width' : 'Full width';
            update();
        } else if (button.hasAttribute('data-reset-workspace')) {
            blocks().forEach(remove);
            templates.forEach(template => add(template.dataset.widgetTemplate));
            update();
        }
    });
    editor.addEventListener('submit', () => { submitting = true; });
    window.addEventListener('beforeunload', event => {
        if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
    });
    update(false);
})();

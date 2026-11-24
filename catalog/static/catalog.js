// Confirm dialogs and auto-submitting selects.
document.addEventListener('click', event => {
  const button = event.target.closest('[data-confirm]');
  if (button && !window.confirm(button.getAttribute('data-confirm'))) event.preventDefault();
});
document.addEventListener('change', event => {
  if (event.target.matches('select[data-autosubmit]')) event.target.form.submit();
});

// Save/Cancel appear only when a form has unsaved changes.
// Controls may sit outside their <form> and attach with a form="id"
// attribute, so everything goes through form.elements, which includes
// both kinds.
document.addEventListener('DOMContentLoaded', () => {
  const show = (el, on) => {
    el.style.display = on ? '' : 'none';
  };
  const pristine = el => {
    if (el.tagName === 'BUTTON' || el.type === 'hidden') return true;
    if (el.type === 'checkbox' || el.type === 'radio') return el.checked === el.defaultChecked;
    if (el.tagName === 'SELECT') return [...el.options].every(o => o.selected === o.defaultSelected);
    return el.value === el.defaultValue;
  };
  const dirty = form => [...form.elements].some(el => !pristine(el));
  const sync = form => {
    const changed = dirty(form);
    for (const el of form.elements) {
      if (el.classList.contains('save')) show(el, changed);
      if (el.classList.contains('cancel') && !el.classList.contains('attr-toggle')) show(el, changed);
    }
    // Collapse the dialog buttons row entirely when it has nothing to show.
    const row = form.querySelector('tr.buttons-row');
    if (row) show(row, [...row.querySelectorAll('button')].some(button => button.style.display !== 'none'));
  };
  for (const form of document.querySelectorAll('form[method="post"]')) {
    for (const el of form.elements) {
      el.addEventListener('input', () => sync(form));
      el.addEventListener('change', () => sync(form));
    }
    form.addEventListener('submit', () => (form.dataset.sent = '1'));
    sync(form);
  }
  document.addEventListener('click', event => {
    const cancel = event.target.closest('button.cancel');
    if (!cancel || !cancel.form) return;
    cancel.form.reset();
    sync(cancel.form);
  });
});

// Flash messages fade out after a few seconds.
document.addEventListener('DOMContentLoaded', () => {
  for (const msg of document.querySelectorAll('.msg')) {
    setTimeout(() => {
      msg.classList.add('msg-hide');
      setTimeout(() => msg.remove(), 400);
    }, 5000);
  }
});

// Find-by-search boxes: type, pick a suggestion, the ID field fills in.
document.addEventListener('DOMContentLoaded', () => {
  const closeMenus = () => document.querySelectorAll('.finder-menu').forEach(m => m.remove());

  const search = async box => {
    const query = box.value.trim();
    if (query.length < 2) return closeMenus();
    try {
      const data = await (await fetch(box.getAttribute('data-search') + encodeURIComponent(query))).json();
      closeMenus();
      if (!data.results.length) return;
      const menu = document.createElement('div');
      menu.className = 'finder-menu';
      for (const r of data.results) {
        const item = document.createElement('button');
        item.type = 'button';
        item.append(r.label + ' ');
        const n = document.createElement('span');
        n.className = 'n';
        n.textContent = '#' + r.pk;
        item.append(n);
        if (r.note) item.append(' ', Object.assign(document.createElement('span'), { className: 'n', textContent: r.note }));
        item.addEventListener('mousedown', e => e.preventDefault());
        item.addEventListener('click', () => {
          const target = document.querySelector(box.getAttribute('data-fill'));
          if (target) { target.value = r.pk; target.focus(); }
          box.value = '';
          closeMenus();
        });
        menu.append(item);
      }
      if (data.more) {
        const more = document.createElement('a');
        more.className = 'finder-more';
        more.href = data.more;
        more.textContent = data.total + ' matches — open the full list';
        menu.append(more);
      }
      box.parentElement.append(menu);
    } catch { closeMenus(); }
  };

  document.addEventListener('input', event => {
    const box = event.target.closest('input[data-search]');
    if (!box) return;
    clearTimeout(box._wait);
    box._wait = setTimeout(() => search(box), 250);
  });

  // Enter searches; it must never submit the surrounding link form.
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') return closeMenus();
    const box = event.target.closest && event.target.closest('input[data-search]');
    if (event.key === 'Enter' && box) {
      event.preventDefault();
      clearTimeout(box._wait);
      search(box);
    }
  });

  document.addEventListener('click', event => {
    if (!event.target.closest('.finder')) closeMenus();
  });
});

// MARC fields: one inline editor row open at a time.
document.addEventListener('click', event => {
  const toggle = event.target.closest('.attr-toggle');
  if (!toggle) return;
  const row = document.getElementById(toggle.getAttribute('data-target'));
  if (!row) return;
  const open = row.hidden;
  for (const editor of document.querySelectorAll('tr.attr-editor')) editor.hidden = true;
  row.hidden = !open;
});

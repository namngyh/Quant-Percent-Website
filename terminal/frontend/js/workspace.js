/* Application chrome and quick navigation. Commands use the existing controls
   so the workspace has a single path for changing panels, markets and layouts. */
const Workspace = (() => {
  let connection = 'connecting';
  let selected = 0;
  let visible = [];
  const dialog = document.getElementById('command-dialog');
  const search = document.getElementById('command-search');
  const results = document.getElementById('command-results');
  const normalize = value => value.toLowerCase().normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd');
  const genericIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M4 10h16M10 10v10"/></svg>';

  function trading() {
    if (document.body.dataset.mode === 'overview') document.getElementById('mode-toggle').click();
  }

  function commands() {
    const panels = [...document.querySelectorAll('.rail-btn[data-panel]')].map(button => ({
      title: button.textContent.trim(), description: t('ws.openPanel'),
      icon: button.querySelector('svg').outerHTML,
      run() {
        trading();
        if (!button.classList.contains('active') || document.getElementById('panel-host').classList.contains('collapsed')) button.click();
      },
    }));
    return [
      { title: t('ws.chooseMarket'), description: t('top.symbol'), icon: genericIcon,
        run: () => document.querySelector('#symbol + .sp-button')?.click() },
      ...panels,
      ...[1, 2, 4].map(count => ({ title: t(`ws.layout${count}`), description: t('ws.chartLayout'), icon: genericIcon,
        run() { trading(); document.querySelector(`button[data-layout="${count}"]`).click(); } })),
    ];
  }

  function select(index) {
    selected = Math.max(0, Math.min(index, visible.length - 1));
    [...results.querySelectorAll('.command-item')].forEach((button, i) => {
      button.classList.toggle('selected', i === selected);
      if (i === selected) button.scrollIntoView({ block: 'nearest' });
    });
  }

  function renderCommands() {
    const query = normalize(search.value.trim());
    visible = commands().filter(command => normalize(command.title + ' ' + command.description).includes(query));
    results.replaceChildren();
    for (const [index, command] of visible.entries()) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'command-item';
      button.innerHTML = command.icon;
      const label = document.createElement('div');
      label.textContent = command.title;
      const description = document.createElement('small');
      description.textContent = command.description;
      label.appendChild(description);
      button.appendChild(label);
      const arrow = document.createElement('span');
      arrow.textContent = '↗';
      arrow.setAttribute('aria-hidden', 'true');
      button.appendChild(arrow);
      button.addEventListener('click', () => run(index));
      results.appendChild(button);
    }
    if (!visible.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = t('ws.noCommands');
      results.appendChild(empty);
    }
    select(0);
  }

  function open() {
    if (dialog.open) return;
    search.value = '';
    dialog.showModal();
    renderCommands();
    search.focus();
  }

  function run(index) {
    const command = visible[index];
    if (!command) return;
    dialog.close();
    command.run();
  }

  function setConnection(state) {
    connection = state;
    const node = document.getElementById('connection-state');
    node.dataset.state = state;
    const key = state === 'live' ? 'live.running' : state === 'connecting' ? 'live.connecting'
      : state === 'error' ? 'live.error' : 'live.offline';
    node.querySelector('span').textContent = t(key);
    // The header shows only the dot; the words are its tooltip.
    node.title = t(key);
  }

  function refresh() {
    const cell = MultiChart.cells[MultiChart.active];
    const context = cell ? `${cell.symbol.replace(/^VN:/, '')} / ${cell.timeframe}` : '';
    const node = document.getElementById('workspace-context');
    // The context label went with the page title; nothing to keep in step.
    if (node && node.textContent !== context) node.textContent = context;
  }

  async function fullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      // Browsers can disallow fullscreen in embedded or managed environments.
      document.getElementById('workspace-fullscreen').disabled = true;
    }
  }

  function init() {
    for (const head of document.querySelectorAll('.panel-head')) {
      const close = document.createElement('button');
      close.type = 'button';
      close.className = 'panel-dismiss';
      close.setAttribute('data-i18n-title', 'ws.closePanel');
      close.setAttribute('data-i18n-aria', 'ws.closePanel');
      close.title = t('ws.closePanel');
      close.setAttribute('aria-label', close.title);
      close.innerHTML = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 6 8 8m0-8-8 8"/></svg>';
      close.addEventListener('click', () => document.querySelector('.rail-btn.active')?.click());
      head.appendChild(close);
    }
    document.getElementById('command-open').addEventListener('click', open);
    document.getElementById('command-close').addEventListener('click', () => dialog.close());
    search.addEventListener('input', renderCommands);
    search.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        select(selected + (event.key === 'ArrowDown' ? 1 : -1));
      } else if (event.key === 'Enter') {
        event.preventDefault();
        run(selected);
      }
    });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (dialog.open) dialog.close(); else open();
      }
    });
    document.getElementById('workspace-fullscreen').addEventListener('click', fullscreen);
    document.addEventListener('fullscreenchange', () => {
      const button = document.getElementById('workspace-fullscreen');
      button.title = t(document.fullscreenElement ? 'ws.exitFullscreen' : 'ws.fullscreen');
      button.setAttribute('aria-label', button.title);
    });
    new MutationObserver(refresh).observe(document.getElementById('chart-grid'), {
      subtree: true, childList: true, attributes: true, attributeFilter: ['class'],
    });
    I18n.onChange(() => {
      setConnection(connection);
      if (dialog.open) renderCommands();
    });
    refresh();
  }
  return { init, refresh, setConnection };
})();

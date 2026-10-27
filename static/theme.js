/* Apply the saved theme before styles load; controls also work after page rerenders. */
(() => {
  const key = 'acetime-theme';
  const root = document.documentElement;
  let theme = 'light';
  try { if (localStorage.getItem(key) === 'dark') theme = 'dark'; } catch {}

  const icon = '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 13.2A8.5 8.5 0 0 1 10.8 3.5a8.5 8.5 0 1 0 9.7 9.7Z"/></svg>';
  function control() {
    return `<button class="btn theme-toggle" type="button" data-theme-toggle aria-label="Dark mode" aria-pressed="${theme === 'dark'}" title="Switch to ${theme === 'dark' ? 'light' : 'dark'} mode">${icon}<span>Dark mode</span><span class="theme-switch" aria-hidden="true"></span></button>`;
  }
  function apply(next, persist = false) {
    theme = next === 'dark' ? 'dark' : 'light';
    root.dataset.theme = theme;
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.setAttribute('aria-pressed', String(theme === 'dark'));
      button.title = `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`;
    });
    if (persist) { try { localStorage.setItem(key, theme); } catch {} }
  }
  apply(theme);
  document.addEventListener('click', event => {
    if (event.target.closest?.('[data-theme-toggle]')) apply(theme === 'dark' ? 'light' : 'dark', true);
  });
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) apply(event.key === null ? 'light' : event.newValue);
  });
  window.ACETheme = { control };
})();

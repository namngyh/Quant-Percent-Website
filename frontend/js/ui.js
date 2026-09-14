/* Segmented controls with a thumb that travels.

   The timeframe strip, the layout switch and the language switch are each
   one-of-several choices. Recolouring the chosen button in place answers
   "which one is on", but not "what just changed" — the eye has to find the
   new highlight. A single black thumb that slides from the old choice to the
   new one shows the change itself, which is the one kind of motion this
   interface allows: motion that answers something the person just did.

   Generic on purpose. It watches any `.tf-group` or `.lang-switch` for an
   `.active` child and follows it, so the modules that own those buttons
   (app.js builds the timeframe strip, i18n sets the language) keep toggling
   a class exactly as before and know nothing about the thumb.

   Two details that are easy to get wrong:

   * app.js rebuilds the timeframe strip with `innerHTML = ''` whenever the
     symbol changes, which deletes the thumb along with the buttons. The
     observer puts it back rather than assuming it survives.
   * The first placement must not animate, or every page load starts with the
     thumb sliding in from the left edge. Transitions are only enabled once a
     group has been placed at least once (`.seg-ready`). */

const Segmented = (() => {
  const SELECTOR = '.tf-group, .lang-switch';
  const thumbs = new WeakMap();

  function place(group) {
    const thumb = thumbs.get(group);
    if (!thumb) return;
    if (!group.contains(thumb)) group.prepend(thumb);

    const active = group.querySelector(':scope > .active');
    // A group inside a hidden mode has no layout to measure; hide the thumb
    // rather than parking it at zero width, and let the resize observer place
    // it when the group becomes visible.
    if (!active || !active.offsetWidth) {
      thumb.style.opacity = '0';
      return;
    }
    thumb.style.opacity = '1';
    thumb.style.width = `${active.offsetWidth}px`;
    thumb.style.transform = `translateX(${active.offsetLeft}px)`;
  }

  function attach(group) {
    if (thumbs.has(group)) return;
    const thumb = document.createElement('span');
    thumb.className = 'seg-thumb';
    thumb.setAttribute('aria-hidden', 'true');
    group.prepend(thumb);
    group.classList.add('has-thumb');
    thumbs.set(group, thumb);

    new MutationObserver(() => place(group)).observe(group, {
      childList: true, subtree: true, attributes: true, attributeFilter: ['class'],
    });
    // Covers the font arriving (labels change width), the window resizing,
    // and a mode switch revealing a group that was `display: none`.
    if ('ResizeObserver' in window) new ResizeObserver(() => place(group)).observe(group);

    place(group);
    requestAnimationFrame(() => group.classList.add('seg-ready'));
  }

  function scan(root = document) {
    for (const group of root.querySelectorAll(SELECTOR)) attach(group);
  }

  scan();
  document.fonts?.ready.then(() => {
    for (const group of document.querySelectorAll('.has-thumb')) place(group);
  });

  return { scan };
})();

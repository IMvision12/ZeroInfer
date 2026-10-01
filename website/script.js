// Shared website interactions: clipboard controls and scroll effects.
// Platform selection and download links live in download.js.

// ── copy-to-clipboard for command + code blocks ──────────────────────────
(function () {
  function flash(btn) {
    btn.classList.add('is-copied');
    const label = btn.querySelector('.cmd-copy-label');
    const prev = label ? label.textContent : '';
    if (label) label.textContent = 'Copied';
    setTimeout(() => {
      btn.classList.remove('is-copied');
      if (label) label.textContent = prev || 'Copy';
    }, 1600);
  }

  function fallbackCopy(text, btn) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      flash(btn);
    } catch { /* clipboard unavailable - nothing we can do */ }
  }

  function copy(text, btn) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => flash(btn)).catch(() => fallbackCopy(text, btn));
    } else {
      fallbackCopy(text, btn);
    }
  }

  // Resolve the text to copy: an explicit [data-copy] wins (e.g. commands with
  // markup), otherwise fall back to the block's rendered command / code text.
  function textFor(btn) {
    const holder = btn.closest('[data-copy]');
    if (holder && holder.getAttribute('data-copy')) return holder.getAttribute('data-copy');
    const scope = btn.closest('.cmd, .api-code');
    const src = scope && (scope.querySelector('.cmd-text') || scope.querySelector('.api-pre'));
    return src ? src.textContent : '';
  }

  document.querySelectorAll('.cmd-copy').forEach((btn) => {
    btn.addEventListener('click', () => {
      const text = textFor(btn);
      if (text) copy(text, btn);
    });
  });
})();

// Toggle nav border on scroll for subtle separation.
(function () {
  const nav = document.querySelector('.nav');
  if (!nav) return;
  const onScroll = () => {
    if (window.scrollY > 8) nav.classList.add('scrolled');
    else nav.classList.remove('scrolled');
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

// Fade-in-on-scroll with staggered delay per card in a grid.
(function () {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.style.opacity = '1';
          e.target.style.transform = 'translateY(0)';
          io.unobserve(e.target);
        }
      }
    },
    { threshold: 0.1 }
  );
  // Parent-level reveals (no stagger)
  document.querySelectorAll('.section-head, .screenshot-frame, .api-code').forEach((el) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(24px)';
    el.style.transition = 'opacity 0.7s cubic-bezier(0.2, 0.8, 0.2, 1), transform 0.7s cubic-bezier(0.2, 0.8, 0.2, 1)';
    io.observe(el);
  });
  // Grid reveals with stagger
  ['.feat-grid', '.model-families', '.api-points', '.mcp-tools'].forEach((gridSel) => {
    const cards = document.querySelectorAll(`${gridSel} > *`);
    cards.forEach((el, i) => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(28px)';
      el.style.transition = `opacity 0.55s cubic-bezier(0.2, 0.8, 0.2, 1) ${i * 60}ms, transform 0.55s cubic-bezier(0.2, 0.8, 0.2, 1) ${i * 60}ms, border-color 0.3s, box-shadow 0.3s`;
      io.observe(el);
    });
  });
})();


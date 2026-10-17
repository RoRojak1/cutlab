// tooltip.js — подсказка при наведении на любой [data-tip], с клавишей из data-key
export function initTooltips() {
  const tip = document.getElementById('tooltip');
  let timer = null, cur = null;
  document.addEventListener('mouseover', (e) => {
    const t = e.target.closest('[data-tip]');
    if (t === cur) return;
    cur = t; clearTimeout(timer); tip.hidden = true;
    if (!t) return;
    timer = setTimeout(() => {
      tip.innerHTML = '';
      tip.append(t.dataset.tip);
      if (t.dataset.key) { const k = document.createElement('kbd'); k.textContent = t.dataset.key; tip.append(k); }
      tip.hidden = false;
      const r = t.getBoundingClientRect(), w = tip.offsetWidth;
      tip.style.left = Math.min(innerWidth - w - 8, Math.max(8, r.left + r.width / 2 - w / 2)) + 'px';
      tip.style.top = (r.bottom + 8 + tip.offsetHeight > innerHeight ? r.top - tip.offsetHeight - 8 : r.bottom + 8) + 'px';
    }, 400);
  });
  document.addEventListener('mousedown', () => { clearTimeout(timer); tip.hidden = true; });
}

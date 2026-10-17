// Нативное окно Cutlab.app (WKWebView): шапка в одной строке с кнопками окна.
// Сообщаем приложению высоту шапки и где в ней кнопки — там клики идут в страницу, в остальных местах шапка тянет окно.
export function mountNative() {
  const h = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.cutlab;
  if (!h) return;
  const bar = document.getElementById('titlebar');
  let raf = 0;
  const send = () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      const holes = [...bar.querySelectorAll('button, a, input, select, [data-tip]')].filter((e) => e.offsetParent)
        .map((e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; });
      h.postMessage({ h: bar.getBoundingClientRect().bottom, holes });
    });
  };
  new ResizeObserver(send).observe(bar);
  new MutationObserver(send).observe(bar, { subtree: true, childList: true, characterData: true, attributes: true });
  addEventListener('resize', send);
  send();
}

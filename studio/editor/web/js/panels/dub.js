// Диалог дубляжа: выбор языков, цена, задача для Claude — задача 16.
import { dialog, toast } from '../ui.js';
import { el } from '../util.js';

const MAIN = [['es-419', 'испанский (Латинская Америка)'], ['pt-BR', 'португальский (Бразилия)'], ['de', 'немецкий'], ['fr', 'французский'],
  ['it', 'итальянский'], ['hi', 'хинди'], ['id', 'индонезийский'], ['ja', 'японский'], ['ko', 'корейский'], ['ru', 'русский']];
const MORE = [['tr', 'турецкий'], ['ar', 'арабский'], ['pl', 'польский']];

function ru(n, one, few, many) {
  const n100 = Math.abs(n) % 100, n10 = n100 % 10;
  if (n100 > 10 && n100 < 20) return many;
  if (n10 > 1 && n10 < 5) return few;
  if (n10 === 1) return one;
  return many;
}

export async function openDub(store) {
  const est = await store.api.get(store.url('/dub-estimate'));
  const chosen = new Set((store.project.settings && store.project.settings.dub_langs) || []);
  let okBtn;
  const box = (code, name) => {
    const cb = el('input', { type: 'checkbox' });
    cb.checked = chosen.has(code);
    cb.onchange = () => { cb.checked ? chosen.add(code) : chosen.delete(code); updatePrice(); };
    return el('label', {}, cb, name);
  };
  const mainGrid = el('div', { class: 'langs' }, ...MAIN.map(([c, n]) => box(c, n)));
  const moreGrid = el('div', { class: 'langs', hidden: true }, ...MORE.map(([c, n]) => box(c, n)));
  const moreBtn = el('button', { class: 'btn', onclick: () => { moreGrid.hidden = !moreGrid.hidden; moreBtn.textContent = moreGrid.hidden ? 'ещё языки ▾' : 'ещё языки ▴'; } }, 'ещё языки ▾');
  const price = el('div', { class: 'dubprice' });
  const approve = el('input', { type: 'checkbox' });
  approve.onchange = updatePrice;

  function updatePrice() {
    const n = chosen.size, per = Math.round(est.per_lang);
    price.textContent = n ? `${n} ${ru(n, 'язык', 'языка', 'языков')} × ${per} кр ≈ ${Math.round(est.per_lang * n)} кр` : 'выберите хотя бы один язык';
    if (okBtn) okBtn.disabled = !approve.checked || n === 0;
  }

  // Что уже готово: слушать в плеере, показать файл для YouTube в Finder, название и описание на языке
  const { dubs } = await store.api.get(store.url('/dubs'));
  const ST = { done: 'готово', tts: 'озвучка', text: 'перевод', none: '—' };
  const ready = dubs.length ? el('div', { class: 'dubs' }, el('div', { class: 'mh' }, 'Дорожки'), ...dubs.map((d) => el('div', { class: 'dubrow' },
    el('b', {}, d.lang.toUpperCase()), el('span', {}, d.name),
    el('span', { class: 'mu' }, d.status === 'done' ? `готово ${(d.at || '').slice(5, 16).replace('T', ' ')}${d.overflow ? ` · длинных кусков: ${d.overflow}` : ''}` : `в работе: ${ST[d.status] || d.status}`),
    d.status === 'done' ? el('button', { class: 'btn', onclick: () => { res.close(); window.NE.transport.setLang(d.lang, d.file); } }, 'Слушать') : null,
    d.status === 'done' ? el('button', { class: 'btn', 'data-tip': 'Этот файл загрузить в YouTube Studio → Языки → Дубляж', onclick: () => store.api.post(store.url('/reveal'), { path: `dubs/${d.lang}/${d.file}` }).catch((e) => toast(e.message, 'error')) }, 'В Finder') : null,
    d.meta ? el('a', { class: 'btn', href: `/projects/${store.pid}/dubs/${d.lang}/meta.txt`, target: '_blank', 'data-tip': 'Название и описание ролика на этом языке' }, 'Описание') : null))) : null;

  const body = el('div', {},
    ready,
    mainGrid, moreBtn, moreGrid,
    el('div', { class: 'approve' }, approve, el('span', {}, 'разрешаю — Claude может запустить дубляж по этой цене')),
    price,
    el('p', { class: 'mu' }, 'Claude переведёт текст по кадрам и озвучит голосом Ника (Mark). Дорожка — голос + музыка + эффекты, ровно по таймингу ролика; готовность придёт уведомлением.'));

  const res = dialog({
    title: 'Дубляж', body, ok: 'Запустить', cancel: 'Закрыть', wide: true,
    onOk: async () => {
      const langs = [...chosen];
      const cost = Math.round(est.per_lang * langs.length * 10) / 10;
      await store.reviewPost('jobs', { type: 'dub', params: { langs }, cost, approved: true });
      await store.api.post(store.url('/settings'), { settings: { dub_langs: langs } });
      toast('Задача дубляжа отправлена Claude', 'ok');
    },
  });
  okBtn = res.okBtn;
  updatePrice();
  return res.close;
}

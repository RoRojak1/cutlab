// Картинки для плеера: декод и уменьшение под кадр вне основного потока. На странице WebKit делает
// createImageBitmap синхронно (70–120 мс на 4K JPEG), а первый drawImage большой картинки — прямо в кадре.
// Готовый ImageBitmap уходит странице без копирования (transfer).
onmessage = async ({ data: { id, url, w, h } }) => {
  try {
    const r = await fetch(url); if (!r.ok) throw new Error('HTTP ' + r.status);
    let bm = await createImageBitmap(await r.blob());
    const sc = Math.max(w / bm.width, h / bm.height);
    if (sc < 1) { const s = await createImageBitmap(bm, { resizeWidth: Math.round(bm.width * sc), resizeHeight: Math.round(bm.height * sc), resizeQuality: 'high' }); bm.close(); bm = s; }
    postMessage({ id, bm }, [bm]);
  } catch (e) { postMessage({ id, err: String(e) }); }
};

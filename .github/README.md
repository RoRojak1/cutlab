# Cutlab

Собственный видеоредактор канала «Nick: What If?»: многодорожечный таймлайн, привязка склеек к словам озвучки, живое сведение звука, правки «для Claude» с кнопкой «✦ Исправить», варианты кадров, дубляж, рендер в MP4.

## Состав
- `studio/editor/` — сервер (Python stdlib, порт 8777, SSE) и логика проекта: операции с отменой (`ops.py`), модель (`model.py`), слова и склейки (`words.py`), правки (`review.py`), версии (`history.py`), рендер (`render_mp4.py`), дубляж (`dub.py`), CLI для Claude (`cli.py`), автопроверка (`qc_scan.py`), субтитры (`subs_ru.py`, `subs_en.py`).
- `studio/editor/web/` — интерфейс на ванильных ES-модулях без сборки (таймлайн, плеер, панели, горячие клавиши).
- `tools/cutlab_app/` — нативное окно macOS (Swift + WKWebView), сборка `build.sh`.
- `Cutlab.command` — запуск сервера и окна двойным кликом.
- `assets/ui/icon/v2/5_play_dark.png` — иконка.

## Запуск
```
python3 studio/editor/server.py      # http://127.0.0.1:8777
```
или двойной клик по `Cutlab.command`. Проекты лежат в `projects/<id>/` (в репозиторий не входят).

## Тесты
```
python3 -m unittest discover -s studio/editor/tests
cd studio/editor/web && node --test tests/*.test.js
```

Работа Claude с редактором — `studio/editor/AGENT.md`.

# freeact Roadmap v0.3.1 → v0.4.0

## Completed ✅

| # | Task | Status |
|---|------|--------|
| — | `headless=False` по умолчанию (headed bypass CloudFront) | ✅ |
| — | Кэширование конфига TTL 5s | ✅ |
| — | `--headed` не мутирует глобальный config | ✅ |
| — | `_copy_profile` ошибки через warnings | ✅ |
| — | `is_browser_alive()` + авто-восстановление | ✅ |
| — | `_page_cache` в демоне | ✅ |
| — | `get_selector_and_scroll()` 1 round-trip | ✅ |
| — | Адаптивные CDP тайминги (headed/headless) | ✅ |
| — | Ruff: 0 ошибок | ✅ |

## In Progress 🚧

| # | Task | Priority | Estimate |
|---|------|----------|----------|
| 1 | Локальный turndown.js | HIGH | 30 min |
| 2 | Кроссплатформенные пути BROWSER_MAP | HIGH | 20 min |
| 3 | Симлинки/хардлинки вместо копирования профиля | HIGH | 40 min |
| 4 | Аутентификация демона через api_key | HIGH | 30 min |

## Backlog 📋

| # | Task | Priority |
|---|------|----------|
| 5 | Тесты — smoke browser/state/interaction | MEDIUM |
| 6 | Конфигурируемый лимит network log | MEDIUM |
| 7 | Авто-рефреш профиля (--refresh-profile) | MEDIUM |
| 8 | CLI direct / daemon дедупликация | MEDIUM |
| 9 | macOS/Linux: taskkill → pkill, PowerShell → bash | MEDIUM |
| 10 | playwright-stealth удалить из зависимостей (не используется) | LOW |
| 11 | BrowserConfig.confirm_before_use реализовать | LOW |
| 12 | Логирование (file-based + уровни) | LOW |

---

## Детали по задачам

### #1 Локальный turndown.js
- Сейчас: `import('https://unpkg.com/turndown@7/dist/turndown.js')`
- Надо: сохранить turndown.js в пакет, грузить через `page.add_script_tag()`
- Файл: `freeact/extraction.py`

### #2 Кроссплатформенные пути
- Добавить macOS пути: `/Applications/Google Chrome.app/...`, `/Applications/Yandex.app/...`
- Добавить Linux пути: `/usr/bin/google-chrome`, `/usr/bin/yandex-browser`
- Файл: `freeact/browser.py`

### #3 Симлинки профиля
- Сейчас: `shutil.copytree()` всего профиля (200-500 МБ)
- Надо: `os.symlink()` или хардлинки для файлов, копировать только изменяемые
- Файл: `freeact/browser.py`

### #4 Аутентификация демона
- Сейчас: `api_key` в конфиге не проверяется
- Надо: проверять `X-API-Key` заголовок в демоне, пробрасывать из CLI
- Файлы: `freeact/daemon.py`, `freeact/cli.py`

### #5 Тесты
- smoke_test_browser.py: запуск → CDP → закрытие
- smoke_test_state.py: открыть страницу → state → элементы
- smoke_test_interaction.py: клик → ввод → проверка

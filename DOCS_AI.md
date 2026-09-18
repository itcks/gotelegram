# goTelegram Pro — техническая документация для ИИ-агентов

**Версия:** 2.5.0
**Репозиторий:** `anten-ka/gotelegram_pro`
**Активная ветка:** `main` — основной код и продакшен. `beta` и `alpha` существуют для следующих сборок.
**Целевая ОС:** Ubuntu 20.04+, Debian 11+

Этот документ описывает устройство проекта с максимальным количеством нюансов — все ловушки, на которые мы уже наступали, все причины «почему именно так», формат всех внешних интерфейсов, и checklist действий для типовых задач. Цель: чтобы новый агент мог продолжить работу без повторения ошибок и без регрессий.

---

## 0. Быстрый старт для нового ИИ

Если ты агент, который впервые открыл репозиторий:

1. Не трогай токены, ключи VPS и BotFather-токены в истории диалога; не печатай их в ответах и не клади в файлы.
2. Основной код устанавливается из `main`; `bootstrap.sh` по умолчанию скачивает `main`, если не задан `GOTELEGRAM_BRANCH`.
3. Рабочая модель веток: `alpha` для ранних экспериментов, `beta` для проверочных сборок, `main` для продакшена.
4. Главный код установки — `install.sh` + `lib/*.sh`. Не исправляй Telegram-бот или web-admin в отрыве от bash-слоя: все три интерфейса должны показывать одно и то же состояние.
5. Главный конфиг пользователя — `/opt/gotelegram/config.json`; главный runtime-конфиг ядра — `/etc/telemt/config.toml`.
6. `telemt` использует TOML v3, не совместимый со старым `mtg`. Не возвращай старые секции `[security]`, `[[users]]`, `bind_to`.
7. Любая bash-функция, которую вызывают через `$()`, обязана писать UI и логи в stderr (`>&2`), а в stdout возвращать только значение.
8. Перед пушем запускай проверки из раздела 20. Для документации минимум: bash syntax, unit tests, py_compile, node check, `git diff --check`.
9. Если меняешь поведение, обновляй `DOCS_HUMAN.md`, `DOCS_AI.md`, changelog и при необходимости `GOTELEGRAM_VERSION`.
10. Если меняешь бэкапы, сохраняй обратную совместимость restore для старых архивов.

---

## 1. Общая картина

goTelegram Pro — это менеджер MTProxy для Telegram, собранный вокруг Rust-ядра **telemt** (порт mtproto-proxy с поддержкой fake-TLS, v3.3.x). Проект даёт три вещи:

1. **CLI-меню на bash** (`install.sh` + `lib/*.sh`) — установка, настройка, обновление, бекап, перезапуск, смена режима, управление сайтом-маскировкой, выбор шаблона. Единая точка входа `gotelegram` (symlink → `/opt/gotelegram/install.sh`).
2. **Сайт-маскировку** — поднимает рядом nginx с настоящим сайтом на настоящем домене (Let's Encrypt) из каталога 1801 HTML-шаблонов (html5up / startbootstrap / ThemeWagon / dawidolko). В stealth-режиме telemt слушает 443, маскировочный трафик проксирует на локальный nginx (127.0.0.1:8443) через `dns_overrides`.
3. **Telegram-бота** (`gotelegram-bot/bot.py`, python-telegram-bot v21+) — управление прокси со смартфона: статус/ссылка/QR/перезапуск/бекап/смена режима/смена домена/смена шаблона/переключение языка per-user (RU/EN).

Архитектура stealth-режима:
```
Клиент Telegram  ──┐
                   ├─► anten-ka.com:443 (telemt, 0.0.0.0:443)
Обычный браузер ───┘                 │
                                     │  dns_overrides:
                                     ▼  "anten-ka.com:8443:127.0.0.1"
                            127.0.0.1:8443 (nginx)
                                     │
                                     ▼
                          /var/www/gotelegram-site/ (HTML шаблон)
```

Lite-режим (без домена):
```
Клиент Telegram ─► IP:443 (telemt) ─► Telegram DC
Fake-TLS эмулируется (tls_emulation=true), mask-трафик падает никуда
tls_domain = google.com (или любой из QUICK_DOMAINS)
```

---

## 2. Репозиторий и ветки

```
anten-ka/gotelegram_pro
├── main          ← продакшен и дефолтная установка
├── beta          ← следующая публичная сборка для проверки пользователями
└── alpha         ← ранние личные сборки владельца
```

**Правило коммитов:** новые рискованные изменения сначала идут в `alpha`, затем после ручной проверки в `beta`. В `main` попадает только код, который можно считать установочным по умолчанию. Перед любым рискованным переносом или force-update создавай rollback tag/release для текущего состояния целевой ветки.

**Инструменты для коммитов:**
- Основной путь — обычный `git commit` + `git push` в нужную ветку после локальной проверки.
- Если окружение не может пушить напрямую, используй GitHub REST API с PAT из переменной окружения `GOTELEGRAM_PAT`.
- Workflow через GitHub API: `POST git/blobs` для каждого файла → `POST git/trees` (с `base_tree` от текущего HEAD) → `POST git/commits` (parents=[текущий HEAD]) → `PATCH git/refs/heads/<main|beta|alpha>` (sha=новый commit) → при необходимости `POST /releases`.
- **Важно про `base_tree`:** при частичном обновлении (1-2 файла) ОБЯЗАТЕЛЬНО передавать `base_tree` — иначе дерево получится только из переданных файлов, и все остальные файлы пропадут из коммита. `base_tree` можно опускать только при коммите с полным набором файлов.

---

## 3. Карта файлов

```
install.sh                     главная точка входа, CLI-меню из 5 разделов
install_gotelegram_bot.sh      legacy-установщик бота (функционал продублирован в install.sh)
bootstrap.sh                   установщик приватного репо через raw.githubusercontent.com с PAT
templates_catalog.json         каталог 1801 шаблонов, 18 категорий, 4 источника (~460KB)
DOCS_HUMAN.md                  документация для пользователя (этот каталог)
DOCS_AI.md                     этот файл
README.md                      короткая входная точка проекта

lib/common.sh                  цвета, log_*, confirm, select_option, _valid_ip, config_get,
                               save_gotelegram_config, get_server_ip, run_with_spinner,
                               version, GOTELEGRAM_VERSION, пути
lib/telemt.sh                  download_telemt, install_telemt_full, start/stop/restart_telemt,
                               update_telemt, remove_telemt, telemt_status, telemt_logs,
                               install_telemt_service (systemd юнит)
lib/telemt_config.sh           generate_telemt_toml (TOML v3), generate_proxy_link,
                               get_config_value, validate_telemt_config, QUICK_DOMAINS[],
                               select_quick_domain, select_port, show_proxy_info[_pro]
lib/templates_catalog.sh       download_template, select_category, select_template,
                               show_template_preview, поддержка 5 источников
lib/website.sh                 nginx + certbot + деплой шаблона
lib/backup.sh                  create_backup, restore_backup, list_backups
lib/i18n.sh                    t(), tf(), switch_language(), загрузка lang/ru.sh и lang/en.sh
lib/lang/ru.sh                 328 i18n ключей на русском
lib/lang/en.sh                 328 i18n ключей на английском
lib/stats.sh                   телеметрия (опциональная)

gotelegram-bot/bot.py          Telegram-бот (python-telegram-bot v21+)
gotelegram-bot/config.example.env
gotelegram-bot/requirements.txt
gotelegram-bot/README.md
gotelegram-bot/lang/*.json     i18n для бота с per-user persistence

admin-web/server.py            backend локальной админки на Python stdlib
admin-web/static/index.html    shell интерфейса админки
admin-web/static/app.js        frontend логика, API calls, графики, таблицы
admin-web/static/styles.css    responsive light/dark UI
```

**Где что лежит на VPS после установки:**
| Что | Путь |
| --- | --- |
| Репо-скрипты | `/opt/gotelegram/` |
| Symlink запуска | `/usr/local/bin/gotelegram` → `/opt/gotelegram/install.sh` |
| Конфиг goTelegram Pro (JSON) | `/opt/gotelegram/config.json` |
| Конфиг telemt | `/etc/telemt/config.toml` |
| Бинарник telemt | `/usr/local/bin/telemt` |
| Systemd юнит telemt | `/etc/systemd/system/telemt.service` |
| Bot | `/opt/gotelegram-bot/` |
| Systemd юнит бота | `/etc/systemd/system/gotelegram-bot.service` |
| Сайт | `/var/www/gotelegram-site/` |
| nginx конфиг | `/etc/nginx/sites-available/gotelegram` |
| nginx enabled | `/etc/nginx/sites-enabled/gotelegram` |
| Бекапы | `/opt/gotelegram/backups/` |
| Лог goTelegram Pro | `/var/log/gotelegram.log` |
| Логи telemt | `journalctl -u telemt` |
| Логи бота | `journalctl -u gotelegram-bot` |

---

## 4. Формат telemt v3 TOML (КРИТИЧЕСКИ ВАЖНО)

telemt v3.3.39 использует собственный TOML-формат, **несовместимый с mtg и mtproto-proxy**. Попытка скормить ему старый формат (`[security]`, `[[users]]`, `[listen] bind_to`) приводит к тому, что telemt молча игнорирует секции и запускается с дефолтами → клиенты отваливаются с ошибкой SNI.

### Минимальный рабочий конфиг для Lite-режима

```toml
[server]
port = 443
listen_addr_ipv4 = "0.0.0.0"

[censorship]
tls_domain = "google.com"
mask = true
mask_port = 443
tls_emulation = true    # true → telemt сам эмулирует TLS handshake от имени tls_domain

[access.users]
main = "HEX_SECRET_32"  # 16 байт = 32 hex символа, БЕЗ префикса ee
```

### Минимальный рабочий конфиг для Pro-режима (stealth)

```toml
[server]
port = 443
listen_addr_ipv4 = "0.0.0.0"

[censorship]
tls_domain = "anten-ka.com"
mask = true
mask_port = 8443
tls_emulation = false   # false → mask-трафик идёт на mask_port, nginx имеет свой Let's Encrypt cert

[access.users]
main = "HEX_SECRET_32"

[network]
dns_overrides = ["anten-ka.com:8443:127.0.0.1"]
# формат host:port:ip — именно три поля через двоеточие
```

### Поля по секциям (полный набор, который telemt принимает в дефолтном gen-config)

- `[general]` — modes, telemetry, links (опционально, можно не трогать).
- `[general.modes]` — включение/отключение режимов прокси.
- `[general.telemetry]` — отправка статистики (по умолчанию выключено).
- `[general.links]` — формат публикуемых ссылок.
- `[server]` — `port`, `listen_addr_ipv4`, `listen_addr_ipv6`.
- `[server.api]` — HTTP-админка (не используем).
- `[server.conntrack_control]` — ограничения на conntrack.
- `[timeouts]` — таймауты handshake, idle и т.д.
- `[network]` — `stun_servers`, `dns_overrides`.
- `[censorship]` — `tls_domain`, `mask`, `mask_port`, `tls_emulation`, `unknown_sni_action` (значения: `Drop`, `Proxy`).
- `[censorship.tls_fetch]` — параметры получения реального cert от tls_domain (используется только если `tls_emulation=false` И нет dns_overrides).
- `[access]` — rate limits, доступ.
- `[access.users]` — таблица `name = "secret"` (секрет — 32 hex).
- `[access.user_max_unique_ips]` — опциональная таблица `name = число`, ограничивает одновременные уникальные IP на ключ; в goTelegram Pro значение `0` в UI удаляет строку и означает безлимит.

### Почему `unknown_sni_action = Drop` нас кусал

В Pro-режиме при старом конфиге с `tls_domain = anten-ka.com` telemt дропает всех клиентов, которые приходят с другим SNI. Если потом перегенерировать конфиг в Lite (`tls_domain = google.com`), но НЕ перезапустить telemt полноценно (`systemctl start` no-op на живом сервисе), то у telemt в памяти остаётся старое `anten-ka.com`, и клиенты с SNI=google.com дропаются. Симптом пользователя: «ключ Lite не работает, telemt живой». Фикс — в `start_telemt()`, см. раздел 10, баг #23.

### Fake-TLS секрет (ee-формат)

Что присылается клиенту в ссылке `tg://proxy?...`:

```
секрет_в_ссылке = "ee" + <hex_secret_32chars> + <hex(tls_domain)>
```

Пример для secret=`2de6920b1e17ccd440933ba0600f578f6` (длинное — 32 hex) и domain=`google.com`:
- hex(google.com) = `676f6f676c652e636f6d`
- итог: `ee2de6920b1e17ccd440933ba0600f578f676f6f676c652e636f6d`

В конфиге telemt (`[access.users] main = ...`) секрет хранится **без** префикса `ee` и **без** hex-домена. telemt сам склеивает при handshake. Функция `generate_proxy_link()` в `lib/telemt_config.sh` делает эту конкатенацию при формировании ссылки.

### Systemd юнит

Генерируется функцией `install_telemt_service()` в `lib/telemt.sh`:
```ini
[Unit]
Description=goTelegram Pro MTProxy (telemt engine)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/telemt run /etc/telemt/config.toml
Restart=always
RestartSec=5
LimitNOFILE=65535
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

- `ProtectSystem=full` (НЕ `strict`!) — telemt пишет cache-файлы, при `strict` он падает.
- `User=root` — telemt нужен для bind на 443. Можно заменить на `telemt` + `AmbientCapabilities=CAP_NET_BIND_SERVICE`, но это усложнение ради эстетики.

---

## 5. Жизненный цикл установки (Lite)

Функция `install_lite_mode` в `install.sh`. Порядок:

1. `select_quick_domain` (lib/telemt_config.sh) — интерактивный выбор `tls_domain` из списка QUICK_DOMAINS[] (20 доменов: google.com, microsoft.com, cloudflare.com, apple.com, amazon.com, github.com …). Функция **ОБЯЗАТЕЛЬНО** выводит UI через `>&2`, потому что она вызывается через `$()` — см. раздел 10, баг #14.
2. `select_port` — порт (443 по умолчанию, проверяется занятость через `check_port`).
3. Генерация секрета: `openssl rand -hex 16` → 32 hex символа.
4. `install_telemt_full` → `download_telemt` (скачивает бинарник из telemt/telemt GitHub Releases с фильтром `telemt-x86_64-linux-gnu.tar.gz`) → `install_telemt_service` → `enable_telemt`.
5. `generate_telemt_toml "$secret" "$port" "lite" "$domain" "$port"` → пишет `/etc/telemt/config.toml`.
6. `save_gotelegram_config` → пишет `/opt/gotelegram/config.json` с полями `mode=lite`, `domain=""`, `mask_host=$domain`, `secret`, `port`.
7. `start_telemt` → **restart** если уже active (см. баг #23), иначе `start`. Проверяет `systemctl is-active` через 2 сек.
8. `show_proxy_info` — выводит IP/port/secret/tls_domain и `tg://proxy?...` ссылку, QR через qrencode если есть.

## 6. Жизненный цикл установки (Pro / stealth)

Функция `install_pro_mode` в `install.sh`. Добавляет к Lite-флоу:

1. Запрос домена (`read_user_input domain`), `validate_domain` — проверка формата.
2. `dig +short $domain` → проверка DNS = IP VPS. Если не совпало — предупреждение, но продолжаем (пользователь может знать лучше).
3. `apt install nginx certbot python3-certbot-nginx` (если ещё нет).
4. `interactive_template_selection` → `select_category` → `select_template` → `show_template_preview` → возвращает `tpl_id`. Все UI через `>&2` — иначе ID замусоривается.
5. `download_template "$tpl_id"` → клонирует репо шаблона в temp, проверяет `index.html`, копирует в `/var/www/gotelegram-site/`. Для StartBootstrap проверяет `dist/index.html` — см. баг #21.
6. Запись временного nginx-конфига на порту 80 (для challenge), reload nginx.
7. `certbot --nginx -d $domain` → получает Let's Encrypt сертификат.
8. Переписывание nginx-конфига: listen `127.0.0.1:8443 ssl`, root `/var/www/gotelegram-site`, используем cert от certbot.
9. Генерация `telemt/config.toml` в режиме `pro` с `tls_emulation=false`, `mask_port=8443`, `dns_overrides = ["$domain:8443:127.0.0.1"]`.
10. `save_gotelegram_config mode=pro domain=$domain ...`.
11. `start_telemt` (restart-safe) → `show_proxy_info_pro` выводит ссылку через доменное имя.

---

## 7. Правила subshell-capture (железно)

Это **самое частое место ошибок** в проекте. Любая функция, которая вызывается через `$(...)` для получения значения, должна писать ВСЕ логи и UI в stderr (`>&2`). Единственный разрешённый вывод в stdout — это финальный `echo "$result"` с возвращаемым значением.

Что обязательно `>&2`:
- **Все** `log_info/success/warning/error/step/dim` в `lib/common.sh` (это уже сделано).
- `confirm`, `select_option` в `lib/common.sh` (сделано).
- `select_quick_domain`, `select_port` в `lib/telemt_config.sh` (сделано).
- `select_category`, `select_template`, `show_template_preview` в `lib/templates_catalog.sh` (сделано, баг #18 был о том, что 4 строки в show_template_preview выводили без >&2).
- Любой `echo`/`printf` внутри `download_template` при ошибочном пути — см. баг #22 (`ls -la` без `>&2` замусоривал вывод).
- Любая новая интерактивная функция, которую добавляешь.

Чек-лист когда пишешь новую функцию:
1. Она вызывается через `$()`? → все echo/printf/log_* через `>&2`, кроме финального.
2. Возвращает строку через echo → именно **одна** финальная строка, без лишних переводов строки.
3. Ошибочный путь (early return) → НЕ писать в stdout, только в stderr, `return 1`.

---

## 8. SCRIPT_DIR и symlink

`install.sh` запускается через symlink `/usr/local/bin/gotelegram → /opt/gotelegram/install.sh`. Если наивно использовать `dirname "${BASH_SOURCE[0]}"`, получим `/usr/local/bin`, а там нет каталога `lib/`. Правильный паттерн:

```bash
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
```

`readlink -f` резолвит symlink до реального файла → `SCRIPT_DIR=/opt/gotelegram`, и `source "$SCRIPT_DIR/lib/common.sh"` работает. Это зафиксировано в баге #19.

---

## 9. Каталог шаблонов

Файл `templates_catalog.json`, ~460KB, ~18000 строк. Формат:

```json
{
  "version": "2.4.1",
  "sources": ["html5up", "startbootstrap", "themewagon", "dawidolko"],
  "categories": ["landing", "portfolio", "agency", "saas", "restaurant", ...],
  "templates": [
    {
      "id": "h5up_massively",
      "name": "Massively",
      "source": "html5up",
      "repo": "https://github.com/html5up-inc/massively.git",
      "category": "personal",
      "preview": "https://html5up.net/massively"
    },
    ...
  ]
}
```

Источники и как они скачиваются (`download_template` в `lib/templates_catalog.sh`):

| Источник | Префикс id | Метод | Где index.html |
| --- | --- | --- | --- |
| html5up | `h5up_*` | `git clone --depth 1 $repo` | в корне |
| startbootstrap | `sb_*` | `git clone --depth 1` → **ищем `dist/index.html`** → копируем `dist/*` | в `dist/` |
| themewagon | `tw_*` | `git clone --depth 1 $repo` (каждый шаблон в отдельном репо) | в корне |
| dawidolko | `dw_*` / `colorlib_*` | sparse checkout одного большого репо | в подпапке |

Fallback: если по известным правилам index.html не найден, `download_template` делает `find -name "index.html"` по всему клону и берёт первый. Это спасает для нестандартных структур.

**ColorlibHQ отброшен** — оказались WordPress-темы (PHP), index.html пустой. Не пытаться включать обратно.

---

## 10. История багов (не наступать на те же грабли)

Все решены в текущем HEAD (`main`). Перечисление для того, чтобы новый агент не «чинил» то, что уже починено, и понимал контекст.

1. `telemt.sh grep` — URL формат `telemt-x86_64-linux-gnu.tar.gz`, arch перед `linux`. Нужен `grep -iE "$arch_pattern"` + цепочка фильтров (`grep -i linux`, `grep -v sha256`, `grep gnu`, `head -1`).
2. `bot.py safe_edit_message` — обёртка для `query.edit_message_text`, ловит `BadRequest: message is not modified`.
3. `bot.py QR cleanup` — `os.remove(qr_file)` в `finally` блоке.
4. `common.sh _valid_ip` — проверка октетов 0-255, раньше пропускал 999.
5. `common.sh os-release injection` — блокирует `;`, backticks, `$(`, `${` при парсинге `/etc/os-release`.
6. `common.sh config_get` — return codes: `0=ok`, `2=файл отсутствует`, `3=невалидный JSON`.
7. `common.sh run_with_spinner` — stderr в temp-файл, показ первых 3 строк при ошибке.
8. `install.sh` — проверка пустого домена **перед** `validate_domain` (валидатор падал на пустой строке).
9. `install.sh mode_choice` — санитизация `${mode_choice:-}` чтобы `set -u` не ронял скрипт.
10. `backup.sh` — инициализация `final_file`/`tar_file`/`backup_file` перед ветвлением (иначе unset var).
11. `bot.py XSS` — `html.escape(preview_url, quote=True)` с двойными кавычками.
12. `common.sh` — версия была устаревшая, обновлена (сейчас 2.4.1).
13. `install.sh` — добавлен пункт 12 меню (Telegram-бот) с подменю установка/статус/логи/настройки/удаление.
14. **КРИТИЧЕСКИЙ subshell capture** — интерактивные функции (`select_quick_domain`, `select_port`, `select_category`, `select_template`, `show_template_preview`) выводили UI в stdout. Вызов через `$()` → меню уходило в переменную. Фикс: весь UI через `>&2`.
15. **КРИТИЧЕСКИЙ download_telemt extract** — `find -newer` не находил извлечённый файл (таймстамп архива старше). Фикс: извлечение в отдельную директорию `$extract_dir` + проверка размера файла + fallback через `file` для определения ELF.
16. `common.sh log_*` — все `log_info/success/warning/error/step/dim` выводят в stderr (`>&2`).
17. `common.sh confirm/select_option` — UI через `>&2`.
18. **КРИТИЧЕСКИЙ show_template_preview stdout leak** — 4 строки (блок «Спасибо авторам» + разделители) выводили без `>&2`. Цепочка `interactive_template_selection → select_template → show_template_preview` → мусор подмешивался к `tpl_id` → `download_template` получал мусорный ID → «шаблон не содержит index.html». Фикс: `>&2` ко всем 4 echo.
19. **symlink SCRIPT_DIR** — `readlink -f "${BASH_SOURCE[0]}"` для резолва symlink `/usr/local/bin/gotelegram`.
20. **bootstrap.sh** — скачивание приватного репо через `raw.githubusercontent.com/.../bootstrap.sh?token=...`, создание symlink, запуск install.sh.
21. **КРИТИЧЕСКИЙ StartBootstrap dist/** — sb_* шаблоны хранят production в `dist/`. Фикс: клонируем в `$sb_tmp`, проверяем `dist/index.html`, копируем `dist/*` в `$clone_dir`, + universal fallback через `find`.
22. **templates_catalog.sh ls stdout leak** — `ls -la` в блоке ошибки `download_template` шёл в stdout. Фикс: `>&2`.
23. **КРИТИЧЕСКИЙ start_telemt stale config (v2.4.1)** — `systemctl start` это no-op для уже активного сервиса. После переустановки Lite поверх Pro конфиг на диске менялся, но telemt держал в памяти старый `tls_domain=anten-ka.com` и дропал клиентов с SNI=google.com. Фикс: `start_telemt` теперь делает `restart` если сервис уже активен. См. `lib/telemt.sh:189-213`.
24. **КРИТИЧЕСКИЙ safe_edit_message TypeError (v2.4.2)** — в iter2 аудите субагент нашёл: `cb_pro_confirm` в success-пути вызывал `safe_edit_message(query, text, ..., disable_web_page_preview=True)`, но сигнатура обёртки этот kwarg не принимала. Runtime TypeError прямо в хэппи-пути смены шаблона из бота. Фикс: добавлен `disable_web_page_preview: Optional[bool] = None` + условный форвард через `**kwargs`.
25. **template_id field name mismatch (v2.4.2)** — `save_gotelegram_config` всегда писал ключ `template_id`, но `bot.py` читал `config.get('template')` и писал `config['template']` в `handle_text_message`. Результат: статус шаблона в боте никогда не отображался, а поле в JSON появлялось фантомно и не использовалось. Фикс: везде только `template_id`. Исторические чтения совместимы через `config.get("template_id") or config.get("template")` для legacy конфигов.
26. **jq 1.5 compat в bot_update_config_field (v2.4.2)** — использовалось `jq '... | .updated_at = (now | todate)'`, но фильтр `now|todate` только с jq 1.6. На Debian 10 jq 1.5 падал с syntax error, config не обновлялся. Фикс: генерим timestamp через `date -Iseconds` в shell и передаём через `jq --arg t`.
27. **Отсутствующая валидация tpl_id/domain (v2.4.2)** — `tpl_id` из `callback_data` и `domain` из текстового ввода передавались напрямую в subprocess как `--template=$x`. Defense-in-depth: в bot.py добавлены `_TPL_ID_RE = ^[A-Za-z0-9_-]{1,64}$` и `_DOMAIN_RE`, в install.sh — `validate_domain` перед `generate_telemt_toml`. Малформный ввод отвергается early.
28. **КРИТИЧЕСКИЙ race в bot_action_dispatch (v2.4.3)** — iter3-тест с 3 параллельными `change-lite-domain` дал `{"status":"error","code":"no_secret"}` на одном из вызовов. Причина: `bot_update_config_field` делает `jq ... > tmp && mv tmp config.json`; когда параллельный процесс заходил в `get_config_value secret` в момент между `>` и `mv`, он видел пустой/частичный файл. `asyncio.Lock` в боте ловил только внутри-процессные гонки, но не CLI-level. Фикс: `flock -w 30 9 < /var/lock/gotelegram-bot-action.lock` вокруг всего диспатчера. Новый error code: `lock_timeout` (`EX_TEMPFAIL`=75).

---

## 11. Telegram-бот

Файл `gotelegram-bot/bot.py`, python-telegram-bot v21+, systemd сервис `gotelegram-bot.service`.

Ключевые моменты:
- **Admin ID** — бот отвечает только пользователю с `ADMIN_TG_ID` из `.env`. Всё остальное игнорируется.
- **safe_edit_message** — обёртка над `query.edit_message_text` + `query.edit_message_caption`, глотает `BadRequest: message is not modified`. Начиная с v2.4.2 принимает опциональный `disable_web_page_preview` — не забудь прокинуть его если показываешь ссылку-превью (раньше вызов с этим kwarg ловил TypeError в runtime). Используй её всегда вместо прямого вызова.
- **Language per-user** — файл `/opt/gotelegram-bot/user_langs.json` хранит `{user_id: "ru"/"en"}`. При каждом сообщении бот читает язык пользователя и подставляет строку через `t(user_id, key)` / `tf(user_id, key, ...)`.
- **QR-коды** — генерятся в `/tmp/gotelegram_qr_*.png`, отправляются как `InputFile`, удаляются в `finally`.
- **Шаблон preview в HTML** — URL экранируется через `html.escape(url, quote=True)` (баг #11).
- **Системные действия (v2.4.2+)** — бот реально умеет менять шаблон и домен маскировки. Хелпер `run_bot_action(action, **kwargs)` вызывает `subprocess.run(["/opt/gotelegram/install.sh", "--action=X", "--json", ...])` и парсит JSON. Два коллбэка: `cb_pro_confirm` (change-template) и `cb_lite_domain` (change-lite-domain). Оба обёрнуты в `async with _BOT_ACTION_LOCK` (глобальный `asyncio.Lock()`) — сериализуют параллельные callback'и внутри процесса бота. Входы валидируются ДО subprocess: `_TPL_ID_RE = r"^[A-Za-z0-9_-]{1,64}$"`, `_DOMAIN_RE` (RFC-like). Малформный ввод отвергается с понятным сообщением, не доходя до shell.
- **Поле `template_id` в config.json** — канонический ключ для текущего шаблона. Раньше (до v2.4.2) бот читал `config['template']` и писал в него же в `handle_text_message`, но `save_gotelegram_config` всегда писал `template_id` → поле статуса никогда не отображалось. Используй только `template_id`.
- **Устанавливается** из меню `install.sh → 4) Telegram-бот → Установить`. Пользователь вводит BotFather token + свой Telegram ID, `.env` пишется в `/opt/gotelegram-bot/.env`.
- **Обновляется автоматически (v2.5.0+)** при повторном bootstrap/update: `auto_update_bot_if_possible` сравнивает новые файлы в `$SCRIPT_DIR/gotelegram-bot/` с установленными `/opt/gotelegram-bot/{bot.py,i18n.py,requirements.txt,lang/*.json}`. Если есть отличия и сервис уже установлен, вызывается `bot_install >/dev/null`, `.env` сохраняется, зависимости обновляются, systemd unit переписывается и `gotelegram-bot` перезапускается. Это закрывает сценарий 2.4.x → 2.5.0, где bootstrap обновлял `/opt/gotelegram/gotelegram-bot/`, но рабочий сервис продолжал запускать старый `/opt/gotelegram-bot/bot.py`.

### 11.1 Non-interactive action bridge (install.sh ↔ bot)

Бот общается с CLI через жёсткий JSON-протокол. Единая точка входа — `bot_action_dispatch` в `install.sh`.

```bash
/opt/gotelegram/install.sh --action=<name> [--template=ID|--domain=HOST] --json
```

**Доступные action'ы:**
- `change-template --template=<tpl_id>` — только в Pro режиме. Скачивает шаблон, деплоит в nginx, обновляет `config.json.template_id`.
- `change-lite-domain --domain=<host>` — только в Lite режиме. Регенерит telemt TOML с новым `tls_domain`, валидирует, рестартит telemt, обновляет `config.json.{domain,mask_host}`.

**Формат ответа (stdout, последняя строка):**
```json
{"status":"success","message":"...","<extra>":"..."}
{"status":"error","message":"...","code":"<machine_code>"}
```

Коды ошибок: `missing_arg`, `invalid_domain`, `wrong_mode`, `unknown_template`, `download_failed`, `deploy_failed`, `no_secret`, `gen_failed`, `validate_failed`, `restart_failed`, `unknown_action`, `lock_timeout`.

**Сериализация (v2.4.3+):** `bot_action_dispatch` оборачивает вызов в `flock -w 30 9 < /var/lock/gotelegram-bot-action.lock`. Это защищает от гонок при:
1. Одновременных callback'ах внутри бота (asyncio.Lock уже ловит это, но flock — defense-in-depth).
2. Параллельных CLI-вызовах (бот + ручной SSH, или два бот-процесса — теоретически).

Если таймаут лока (30 с), диспетчер возвращает `exit 75` (`EX_TEMPFAIL`) и JSON `{"status":"error","code":"lock_timeout"}`. `flock` идёт из `util-linux` — добавлен в `critical` зависимости в `ensure_deps`.

**История:** до v2.4.2 коллбэки были stub'ами («сделай через CLI»). В v2.4.2 подключили реальные action'ы. В iter3-тестировании на VPS обнаружилась гонка: `bot_update_config_field` делает `jq ... > tmp && mv tmp config.json`, и параллельный процесс мог прочитать `config.json` в промежутке, увидев пустоту → ошибка `no_secret`. v2.4.3 починил flock'ом.

---

## 12. i18n (bash CLI)

`lib/i18n.sh` экспортирует функции:

```bash
t "key"              # вернуть строку на текущем языке
tf "key" arg1 arg2   # t + printf-интерполяция
switch_language ru|en
```

Под капотом — ассоциативный массив `I18N`, ключи в `lib/lang/ru.sh` и `lib/lang/en.sh`. ~328 ключей.

Добавление нового ключа:
1. Придумай стабильный key (snake_case, без пробелов): `menu_install`, `error_port_busy`.
2. Добавь строку в `lib/lang/ru.sh`: `I18N[menu_install]="Установить / обновить"`.
3. Добавь строку в `lib/lang/en.sh`: `I18N[menu_install]="Install / update"`.
4. В коде вызови `t menu_install`.
5. Если есть интерполяция — используй `%s`/`%d`: `I18N[info_port]="Порт %s свободен"` + `tf info_port "$port"`.

Выбор языка сохраняется в `$GOTELEGRAM_CONFIG` → `config.json` → ключ `lang`. Первый запуск — интерактивный выбор.

---

## 13. Бекапы

`lib/backup.sh`. Собирает в `.tar.gz`:
- `/etc/telemt/config.toml`
- `/opt/gotelegram/config.json`
- `/opt/gotelegram/disabled_users.json`
- `/var/www/gotelegram-site/` (если есть)
- `/opt/gotelegram/custom_templates/`, `/opt/gotelegram/templates_catalog.json`
- `/opt/gotelegram/stats_history.csv`, `/opt/gotelegram/user_stats_history.csv`, `/opt/gotelegram/shared-443.json`
- `/opt/gotelegram-bot/.env`, bot i18n/lang
- `/opt/gotelegram-admin/server.py`, `/opt/gotelegram-admin/static/`
- `/etc/letsencrypt/live/<domain>/` + `/etc/letsencrypt/archive/<domain>/` + `/etc/letsencrypt/renewal/<domain>.conf` (если Pro)
- `/etc/nginx/sites-available/gotelegram` (если есть)

Складывает в `/opt/gotelegram/backups/gotelegram_backup_YYYYMMDD_HHMMSS.tar.gz`.

`restore_backup <file> [password] [yes]` разворачивает архив обратно, перезапускает telemt, nginx, bot и admin. Третий аргумент `yes` нужен для неинтерактивного restore из web-admin/бота; перед ним они создают свежий safety backup. Restore понимает legacy-архивы раннего бота `backup_*.tar.gz`, где внутри лежали только `opt/gotelegram/config.json` и `etc/telemt/config.toml`.

Расписания бекапов: `set_backup_schedule off|daily|weekly|monthly` пишет `/etc/systemd/system/gotelegram-backup.{service,timer}` и `/opt/gotelegram/backup_schedule.json`. OnCalendar: daily `*-*-* 03:20:00`, weekly `Sun 03:20:00`, monthly `*-*-01 03:20:00`. Автоматическая чистка держит 30 последних `.tar.gz*` архивов.

### 13.1 Local Web Admin (v2.5.0)

Локальная web-админка находится в `admin-web/` и устанавливается в `/opt/gotelegram-admin`:

- backend: `admin-web/server.py`, Python stdlib only, без pip/npm dependencies;
- frontend: `admin-web/static/`, vanilla JS/CSS, SVG-график без CDN;
- systemd service: `gotelegram-admin`;
- bind: `127.0.0.1:1984`, доступ только через SSH tunnel;
- токена нет: после SSH tunnel открывается `http://127.0.0.1:1984/`;
- write-запросы дополнительно требуют `X-GoTelegram-Admin: 1`, фронтенд добавляет его автоматически.
- язык панели читается из `config.json.language`, затем из `/opt/gotelegram/.language`, fallback `en`; `POST /api/settings/language` сохраняет RU/EN в общий конфиг, marker file и bot `.env`; `gotelegram-bot/i18n.py` использует тот же источник как default до per-user override;
- UI построен вкладками (`dashboard`, `traffic`, `keys`, `backups`, `logs`, `settings`), есть иконки меню, полезный overview-блок по реальным TCP/UDP-слушателям 443, light/dark theme в `localStorage` и promo-modal раз в 24 часа через `localStorage`;
- `/api/overview` отдаёт `stats_status`, `admin_bind`, `site_status`, `port_443` и `backup_schedule`; `/api/site/check` проверяет `https://config.domain/` и считает OK только HTTP 200; `/api/stats?range=15m|1h|24h|month` отдаёт выбранное окно и `summary_rows`; `/api/users/<name>/traffic?range=15m|1h|24h|month` отдаёт per-user историю по `telemt total_octets`; `/api/users/<name>/qr` отдаёт PNG QR для Telegram proxy link через `qrencode`; `POST /api/users/<name>/max-ips` пишет `[access.user_max_unique_ips]` (`0` удаляет строку и означает безлимит); `/api/stats/collect` делает разовый сбор, `/api/stats/repair` устанавливает/перезапускает `gotelegram-stats`.

Функции: overview, проверка сайта на HTTP 200, service status/restart, чтение/запись `[access.users]`, enable/disable ключей через `/api/users/<name>/enabled`, per-user лимит одновременных уникальных IP через `[access.user_max_unique_ips]`, генерация proxy links и QR, общий traffic history из `/opt/gotelegram/stats_history.csv`, per-user traffic history из `/opt/gotelegram/user_stats_history.csv` с периодами 15m/1h/24h/month, current stats из `/run/gotelegram/stats_current.json`, список/создание backup, `POST /api/backups/schedule`, `POST /api/backups/restore` (background restore job, только basename из backup dir), структурированные journal logs (`service`, `ok`, `exit_code`, `line_count`, `text`).

Traffic retention: обе CSV-истории хранятся максимум 365 дней. Последние 31 день остаются с поминутным разрешением, более старые точки автоматически уплотняются до одной последней cumulative-точки в час. Чистка/уплотнение запускается не чаще одного раза в час, а per-user сбор пишет данные не чаще одного раза в минуту, даже если systemd-loop вызывает `stats_collect` каждую секунду. Параметры можно переопределить переменными `STATS_RETENTION_DAYS`, `STATS_MINUTE_RETENTION_DAYS`, `STATS_CLEANUP_INTERVAL`.

### 13.1.1 Shared TCP/443 with 3x-ui/Xray

`lib/shared443.sh` добавляет управляемую схему shared-443 через nginx stream `ssl_preread`:

- публичный вход: `0.0.0.0:443` принадлежит nginx stream dispatcher;
- default backend: `127.0.0.1:7443` (`telemt`), а `general.links.public_port` остаётся `443`;
- сайт остаётся за telemt через `dns_overrides` на `127.0.0.1:8443`;
- Xray/3x-ui должен быть перенесён в панели на внутренний target, например `127.0.0.1:9443`, после чего `shared443_enable <domain> <xray-sni> 127.0.0.1:9443` пишет `/opt/gotelegram/shared-443.json` и `/etc/nginx/stream-conf.d/gotelegram-shared443.conf`.

Автоматически переписывать SQLite/JSON 3x-ui нельзя: панель может перегенерировать Xray config и потерять ручные правки. Поэтому goTelegram Pro показывает конфликт прямого bind на `443`, даёт маршрут и включает dispatcher только на уровне собственных конфигов/nginx.

Отключённые ключи хранятся в `/opt/gotelegram/disabled_users.json`: active keys остаются в `/etc/telemt/config.toml` под `[access.users]`, disabled keys удаляются из active block и могут быть возвращены обратно без потери secret. `main` защищён от удаления и отключения. Лимит уникальных IP сохраняется в `[access.user_max_unique_ips]` и не теряется при disable/enable; при удалении ключа строка лимита удаляется. Операции с ключами в web-admin и Telegram-боте берут общий file lock `/run/gotelegram/admin-users.lock`, TOML пишется через temp+replace и quoted keys (`"a.b"`), а telemt restart для add/delete/enable/disable/IP-limit ставится через `systemctl --no-block restart`, чтобы switch в UI не зависал на `wait_tcp_port`.

`install_admin_web` вызывается при установке Telegram-бота. `auto_install_admin_web_if_possible` подхватывает админку после bootstrap/update, если Python уже установлен и файлы отличаются. `auto_update_bot_if_possible` аналогично подхватывает уже установленный Telegram-бот и обновляет рабочий `/opt/gotelegram-bot` без запроса токена. При установке админки скрипт пытается установить/перезапустить `gotelegram-stats`; если это не удалось, оператор может нажать Restart collector в Traffic. Backup v1.6 сохраняет `admin_web/server.py`, `admin_web/static/`, `disabled_users.json`, `stats_history.csv`, `user_stats_history.csv`, `backup_schedule.json` и `shared-443.json`, restore возвращает их, удаляет legacy `admin_web/token` и пробует перезапустить `gotelegram-admin`.

### 13.2 Upgrade migration (v2.5.0)

`install.sh` вызывает `auto_migrate_legacy_state` перед интерактивным меню и перед non-interactive `--action=...` для бота. В интерактивном запуске после миграции также вызываются `auto_update_bot_if_possible` и `auto_install_admin_web_if_possible`, чтобы повторный bootstrap обновлял не только исходники в `/opt/gotelegram`, но и реально запущенные сервисы `/opt/gotelegram-bot` и `/opt/gotelegram/admin-web`. Цель — комфортно обновляться даже с кривой старой логики без переустановки прокси:

- перед изменениями создаётся `/opt/gotelegram/backups/preupgrade_2.5.0_*.tar.gz`;
- из старого `/etc/telemt/config.toml` вытаскиваются все строки `[access.users]`, а не только `main`;
- если `main` отсутствует, он добавляется с первым найденным секретом, чтобы старые ссылки не потерялись;
- сохраняются порт, `tls_domain`, `mask_port`, режим Lite/Pro, домен, язык, `stats_enabled`;
- старый telemt TOML нормализуется под v2.5.0 с `[server.api]` и metrics, затем в него возвращается полный users block;
- если сайт уже развёрнут, но template id неизвестен или старый `config.json` врёт, в `/var/www/gotelegram-site/.gotelegram_template_id` пишется `deployed_site`;
- `config.json` переписывается в актуальный формат, но с сохранением `installed_at` и пользовательских настроек;
- если telemt был активен и TOML был изменён, сервис перезапускается один раз.

Инвариант: миграция должна быть идемпотентной. Маркер `/opt/gotelegram/.migrated_2.5.0` предотвращает повторную нормализацию без причины.

---

## 14. Checklist: как обновить один файл и запушить

1. Прочитай текущее состояние файла: `Read` для локальной версии + `git_get_contents` (raw.githubusercontent.com) если нужно убедиться что на GitHub то же самое.
2. Применяй правки через `Edit` в локальном каталоге `/sessions/.../gotelegram-v2/`.
3. Напиши `C:\Temp\push_<описание>.py`:
   ```python
   import os, base64, json, urllib.request, ssl
   TOKEN = os.environ["GOTELEGRAM_PAT"]
   REPO = "anten-ka/gotelegram_pro"
   BRANCH = "main"  # или beta/alpha для соответствующей ветки
   API = f"https://api.github.com/repos/{REPO}"
   headers = {
       "Authorization": f"Bearer {TOKEN}",
       "Accept": "application/vnd.github+json",
       "X-GitHub-Api-Version": "2022-11-28",
       "User-Agent": "gotelegram-push",
   }
   def req(method, path, body=None):
       data = json.dumps(body).encode() if body else None
       r = urllib.request.Request(API + path, data=data, headers={**headers, "Content-Type": "application/json"}, method=method)
       return json.loads(urllib.request.urlopen(r).read())

   # 1. current ref
   ref = req("GET", f"/git/refs/heads/{BRANCH}")
   parent_sha = ref["object"]["sha"]
   commit = req("GET", f"/git/commits/{parent_sha}")
   base_tree = commit["tree"]["sha"]

   # 2. blobs
   files = {
       "lib/common.sh": open("C:/.../gotelegram-v2/lib/common.sh","rb").read(),
       "DOCS_AI.md":    open("C:/.../gotelegram-v2/DOCS_AI.md","rb").read(),
   }
   tree_items = []
   for path, content in files.items():
       blob = req("POST", "/git/blobs", {"content": base64.b64encode(content).decode(), "encoding": "base64"})
       tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

   # 3. tree (С base_tree — обязательно при частичном апдейте)
   tree = req("POST", "/git/trees", {"base_tree": base_tree, "tree": tree_items})

   # 4. commit
   new_commit = req("POST", "/git/commits", {
       "message": "v2.4.1: docs + start_telemt restart-safe",
       "tree": tree["sha"],
       "parents": [parent_sha],
   })

   # 5. patch ref
   req("PATCH", f"/git/refs/heads/{BRANCH}", {"sha": new_commit["sha"], "force": False})
   print("pushed:", new_commit["sha"])
   ```
4. Запускай через Desktop Commander `start_process` с `shell="cmd.exe"`:
   ```
   cmd /c "python C:\Temp\push_docs.py"
   ```
   НЕ через PowerShell — там stdout не захватывается в нашем окружении.
5. Проверь результат: `GET /commits/<sha>` или открой ветку в браузере вручную.

**Частые грабли:**
- Забыл `base_tree` → все остальные файлы исчезли из коммита. ВСЕГДА передавай `base_tree` кроме случая «чистый коммит со всеми файлами».
- `cp1251` в cmd ломает юникод → пиши в файл через Python с `encoding='utf-8'`, не выводи кириллицу в stdout.
- GitHub API кеширует raw-ответы по path → при проверке обновления используй `?ref=<commit_sha>`, не ветку.

---

## 15. Checklist: тестирование на VPS

VPS: `95.163.176.222`, root, пароль в CLAUDE.md.

**Путь из Linux sandbox:** `ssh`/`sshpass` нет, `pip install paramiko` падает (прокси 403). Идём через Windows Python, где paramiko уже установлен.

**Хелперы:**
- `C:\Temp\ssh_cmd.py` — однократная команда, читает из `C:\Temp\ssh_input.txt`, пишет в `C:\Temp\ssh_output.txt`.
- `C:\Temp\ssh_a1.py` / `ssh_a2.py` / `ssh_a3.py` — для параллельных агентов (разные output-файлы).

**Базовый шаблон ssh_cmd.py:**
```python
import sys, paramiko
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("95.163.176.222", username="root", password="...", timeout=20)
cmd = open("C:/Temp/ssh_input.txt", "r", encoding="utf-8").read()
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
out = stdout.read().decode(errors="replace")
err = stderr.read().decode(errors="replace")
open("C:/Temp/ssh_output.txt", "w", encoding="utf-8").write(f"STDOUT:\n{out}\nSTDERR:\n{err}")
ssh.close()
```

**Заливка одного файла через SFTP:**
```python
sftp = ssh.open_sftp()
sftp.put("C:/.../lib/telemt.sh", "/opt/gotelegram/lib/telemt.sh")
sftp.close()
```

**CRLF:** файлы из GitHub API приходят с `\r\n` → ОБЯЗАТЕЛЬНО `sed -i 's/\r$//' /opt/gotelegram/install.sh /opt/gotelegram/lib/*.sh` перед запуском, иначе bash падает с `bad interpreter`.

**chmod:** `chmod +x /opt/gotelegram/install.sh /opt/gotelegram/install_gotelegram_bot.sh` — GitHub раздаёт как 644.

**Быстрая проверка live-состояния:**
```bash
systemctl is-active telemt nginx gotelegram-bot
telemt --version
cat /etc/telemt/config.toml | grep tls_domain
journalctl -u telemt --no-pager -n 30
curl -sk -o /dev/null -w "%{http_code}\n" https://127.0.0.1:8443
```

**Проверка что Lite-ключ реально работает через Fake-TLS:**
```python
import ssl, socket
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
with socket.create_connection(("95.163.176.222", 443), timeout=5) as s:
    with ctx.wrap_socket(s, server_hostname="google.com") as ss:
        print(ss.version(), ss.getpeercert(True)[:40])
```
Ожидаемо: `TLSv1.3`, сертификат с CN=`*.google.com` (его telemt эмулирует через tls_fetch).

---

## 16. Меню (install.sh)

```
Главный экран:
 1) submenu_proxy        (установка, статус, ссылка, share, restart, logs, change mode)
 2) submenu_stats        (show_traffic_stats, toggle_stats, install_stats_collector)
 3) submenu_manage       (backup, restore, update_telemt, website/SSL, remove, language)
 4) menu_bot             (install/start/stop/logs/change token/remove bot, installs admin web)
 5) submenu_about        (version info, promo)
 0) exit

Раздел Proxy:
 1) menu_install         (Lite/Pro выбор, domain, template, certbot)
 2) menu_status          (telemt_status + show_proxy_info)
 3) menu_link            (ссылка + QR)
 4) menu_share           (текст «для друзей»)
 5) menu_restart         (restart_telemt)
 6) menu_logs            (telemt_logs 40)
 7) menu_change_mode     (lite↔pro, смена шаблона, смена домена маскировки)

Раздел Management:
 1) interactive_backup   (create_backup)
 2) interactive_restore  (select_backup + restore_backup)
 3) update_telemt        (check_telemt_update → download → restart)
 4) menu_website         (nginx restart, certbot renew)
 5) menu_remove          (только прокси / только бот / всё)
 6) menu_language        (switch_language ru|en)
```

Диспатчер в `install.sh` (`bot_action_dispatch`) принимает `--action=` для автоматизации из бота. Полный контракт описан в разделе 11.1.

---

## 17. Changelog

- **2.5.0 (2026-04-24)** — крупный maintenance pass в `main`: единая версия `2.5.0` в runtime и документации; удалён дефолтный PAT из `bootstrap.sh` (токен теперь только через `GOTELEGRAM_PAT`); повторный bootstrap/update автоматически обновляет уже установленный `/opt/gotelegram-bot` и перезапускает `gotelegram-bot`, сохраняя `.env`; `generate_telemt_toml` добавляет `[server.api]` на `127.0.0.1:9091` и metrics на `127.0.0.1:9090`, что нужно для управления пользователями и статистики; Telegram-бот получил меню `🔑 Keys` для `[access.users]` (добавить/отключить/включить/удалить/показать ссылку/QR/runtime info/IP-limit); добавлена локальная web-админка goTelegram Pro `gotelegram-admin` на `127.0.0.1:1984` с SSH-tunnel инструкцией в боте без отдельного web-admin токена, вкладочной UI-навигацией, иконками, блоком реальных TCP/UDP-слушателей 443, promo-modal раз в 24 часа, i18n от языка установки, ручным переключателем RU/EN, site check на HTTP 200, structured journal logs, light/dark theme, адаптивом, быстрыми switch-переключателями ключей, настройкой `[access.user_max_unique_ips]`, QR-кодами, traffic history 15m/1h/24h/month с переключением график/строки, per-user traffic history из `telemt total_octets` и stats collector restart endpoint; исправлено чтение traffic CSV в боте (header больше не ломает parsing); бот сам делает `stats_collect` перед показом статистики; `iptables` добавлен в optional deps и stats collector пытается установить его; CLI-смена шаблона теперь обновляет `config.json.template_id`, чтобы бот не показывал первый установленный шаблон; backup/restore версии `1.6` сохраняет bot `.env`, bot lang files, disabled user keys, backup schedule, web-admin server/static, custom templates, templates catalog, stats history, user stats history, shared-443 config и полноценную структуру Let's Encrypt (`live/archive/renewal`) для переезда на новый сервер; добавлен безопасный детект 3x-ui/Xray на 443 и управляемый nginx stream shared-443 dispatcher.
- **2.4.6 (2026-04-10)** — universal `apt_lock_wait` helper: ожидание dpkg/apt lock при unattended-upgrades, исправляет установку nginx/certbot/python на свежих VPS.
- **2.4.3 (2026-04-10)** — iter3-фикс: `bot_action_dispatch` оборачивается во `flock -w 30` на `/var/lock/gotelegram-bot-action.lock`. Обнаружена гонка: параллельные `change-lite-domain` получали `"no secret in config"`, потому что один процесс читал `config.json`, пока другой делал `jq ... > tmp && mv`. `util-linux` (содержит `flock`) добавлен в `critical` deps, `check_deps_present` и маппинги `apt_pkg_for_cmd`/`dnf_pkg_for_cmd`.
- **2.4.2 (2026-04-10)** — реализация non-interactive `bot_action_*` в install.sh (change-template + change-lite-domain с JSON-ответом). bot.py подключает `run_bot_action()` и делает реальную работу вместо stub'ов. Критфиксы: (a) `safe_edit_message` принимает `disable_web_page_preview` (иначе TypeError в success-пути cb_pro_confirm); (b) чтение/запись `config['template_id']` вместо `config['template']` (save_gotelegram_config всегда писал `template_id`, бот смотрел не туда); (c) `bot_update_config_field` использует shell `date -Iseconds` вместо `jq now|todate` (jq 1.5 совместимость для Debian 10); (d) `asyncio.Lock _BOT_ACTION_LOCK` сериализует callback'и в процессе бота; (e) валидация `_TPL_ID_RE`/`_DOMAIN_RE` до subprocess. Полный аудит и автоустановка зависимостей: `ensure_deps` разделяет critical/optional, дедуплицирует пакеты, re-verify после install; `apt_pkg_for_cmd` и `dnf_pkg_for_cmd` мапят команды на пакеты (dig→dnsutils/bind-utils, xxd→xxd/vim-common, flock→util-linux). `check_deps_present` — быстрый чек без `apt-get update`.
- **2.4.1 (2026-04-10)** — баг #23: `start_telemt` делает `restart` если сервис активен (иначе stale in-memory config после переустановки Lite поверх Pro). Полная документация проекта — `DOCS_HUMAN.md` и `DOCS_AI.md` (этот файл).
- **2.4.0** — i18n EN/RU для CLI (328 ключей) и бота (99 ключей JSON с per-user persistence). Возможность загрузить свой шаблон сайта из произвольного git-репозитория (валидация URL, таймауты, лимит размера клона).
- **2.3.x** — каталог шаблонов расширен до 1801, 4 источника, 18 категорий. Поддержка StartBootstrap `dist/` структуры.
- **2.2.1** — критические фиксы `$()` capture (все UI через `>&2`), StartBootstrap dist, symlink SCRIPT_DIR через `readlink -f`, XSS в HTML-превью бота, OS-release injection.
- **2.2** — переход с mtg на telemt v3, новый TOML-формат конфига, stealth-архитектура.

---

## 18. Быстрый справочник: «хочу сделать X»

**Добавить новый пункт меню:**
1. `install.sh`: добавь `menu_new_thing()`, впиши в диспатчер `case` в главном цикле.
2. Добавь i18n ключи `menu_new_thing` в ru.sh и en.sh.
3. Если функция интерактивная + возвращает значение → ВСЁ UI через `>&2`.

**Добавить новый домен в QUICK_DOMAINS:**
- `lib/telemt_config.sh` → массив `QUICK_DOMAINS=(...)`. Убедись что домен не заблокирован ни в одной из популярных стран и действительно отвечает на 443 с валидным сертификатом (telemt при `tls_emulation=true` вынимает реальный cert через tls_fetch).

**Сменить версию:**
- `lib/common.sh:6` → `GOTELEGRAM_VERSION="X.Y.Z"`.
- `DOCS_HUMAN.md` / `DOCS_AI.md` → раздел Changelog + версия в шапке.
- Тэг (опционально): `PATCH /git/refs/tags/vX.Y.Z` на новый commit sha.

**Добавить новый шаблон в каталог:**
- Найди git-репо со статическим HTML (index.html в корне или в `dist/`).
- Придумай id: `<source_prefix>_<name>` (например `h5up_future`, `sb_portfolio_x`).
- Добавь запись в `templates_catalog.json` с `id`, `name`, `source`, `repo`, `category`, `preview`.
- Убедись что `download_template` знает префикс источника (`case "$tpl_id" in h5up_*) ... sb_*) ... esac`).

**Отладить «ключ не работает»:**
1. `systemctl is-active telemt` → живой?
2. `cat /etc/telemt/config.toml` → какой `tls_domain`? Какой `port`? Какой `secret`?
3. `journalctl -u telemt --no-pager -n 50` → есть `unknown_sni_action=Drop`? `port in use`? `failed to bind`?
4. Сравни `tls_domain` в конфиге и hex-домен в конце ссылки клиента (`hex(domain) === суффикс секрета после ee+32hex`).
5. Если telemt жив но дропает — **restart** (не start). Это баг #23.
6. Если порт занят — `ss -ltnp | grep :443` → убей конкурента.
7. Если Pro и не открывается сайт в браузере — `curl -k https://127.0.0.1:8443` (nginx жив?), `dig +short $domain` (DNS правильный?).

---

## 19. Где НЕ копаться

- `install_gotelegram_bot.sh` — legacy, функционал дублирован в install.sh пункте 12. Можно удалить после того как убедимся что никто им не пользуется.
- `lib/stats.sh` — опциональная телеметрия, не критичная для работы.
- `ColorlibHQ` в каталоге — wordpress-темы, отброшены. Не возвращать.
- Старый формат конфига mtg (`[security]`, `[[users]]`, `bind_to`) — telemt v3 его игнорирует. Не пытаться «починить» совместимость.

---

## 20. Контрольные точки и инварианты

Перед любым пушем в `main`/`beta`/`alpha`:
1. `bash -n install.sh lib/*.sh` — синтаксис bash ОК.
2. Все новые `$()`-вызываемые функции пишут UI через `>&2`.
3. Все пути к lib/ идут через `$SCRIPT_DIR/lib/...`, а `SCRIPT_DIR` — через `readlink -f`.
4. `GOTELEGRAM_VERSION` обновлена если изменения меняют поведение.
5. Changelog в `DOCS_HUMAN.md` и `DOCS_AI.md` дополнен.
6. Если бекап-формат изменился — прописать в `restore_backup` обратную совместимость.
7. `generate_telemt_toml` не роняет telemt v3 (проверить `telemt run --check config.toml`).

После пуша:
1. Подождать пока нужная ветка обновится (GitHub API мгновенно, raw кеш ~30 сек).
2. На VPS: повторить bootstrap из целевой ветки с `GOTELEGRAM_PAT` и при необходимости `GOTELEGRAM_BRANCH=beta|alpha|main`; скрипт сам скачает файлы, обновит установленный бот/админку и покажет меню.
3. `telemt_status` → running. `journalctl -u telemt` → нет ошибок. Ссылка открывается в Telegram-клиенте.

---

**Если в чём-то сомневаешься — открой `CLAUDE.md` в корне `MT-proxy/`. Там суммированы все ранее пройденные грабли и рабочие паттерны под Windows + Desktop Commander + paramiko.**

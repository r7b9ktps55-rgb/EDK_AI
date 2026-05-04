# EDK_AI v4 — Руководство пользователя

## Описание

**EDK_AI** — это универсальная среда разработки в терминале (TUI IDE) с встроенным AI-помощником и сканером уязвимостей.

Версия: **0.3.0**
Строк кода: **~22,000**
Модулей: **68**

## Что входит

- **IDE** — редактор кода, файловый менеджер, терминал, git
- **AI Copilot** — ghost text, inline генерация, рефакторинг, тесты
- **Security Scanner** — 10 типов уязвимостей, 700+ payloads
- **AI Analyzer** — фильтрация false positives, генерация PoC, отчёты

## Установка

### macOS / Linux (одна команда)

```bash
cd /tmp && python3 -c "import urllib.request; urllib.request.urlretrieve('https://dufvuralvq3zm.kimi.page/project.tar.gz', 'edkai.tar.gz')" && mkdir -p ~/.local/share/edkai && tar xzf edkai.tar.gz -C ~/.local/share/edkai --strip-components=1 && /usr/bin/python3 -m pip install --user textual aiohttp pydantic && mkdir -p ~/.local/bin && echo '#!/usr/bin/env bash' > ~/.local/bin/edkai && echo 'export PYTHONPATH="$HOME/.local/share/edkai:$PYTHONPATH"' >> ~/.local/bin/edkai && echo 'exec /usr/bin/python3 -m edkai "$@"' >> ~/.local/bin/edkai && chmod +x ~/.local/bin/edkai && echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc && edkai --version
```

### Если `python3` не находит `urllib`

```bash
curl -fsSL https://dufvuralvq3zm.kimi.page/project.tar.gz -o /tmp/edkai.tar.gz
mkdir -p ~/.local/share/edkai && tar xzf /tmp/edkai.tar.gz -C ~/.local/share/edkai --strip-components=1
/usr/bin/python3 -m pip install --user textual aiohttp pydantic
```

### Создание команды `edkai`

```bash
mkdir -p ~/.local/bin
cat > ~/.local/bin/edkai << 'BASH'
#!/usr/bin/env bash
export PYTHONPATH="$HOME/.local/share/edkai:$PYTHONPATH"
exec /usr/bin/python3 -m edkai "$@"
BASH
chmod +x ~/.local/bin/edkai
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

## Проверка установки

```bash
edkai --version
# Должно вывести: edkai 0.3.0
```

## Использование IDE

### Запуск

```bash
edkai                          # Открыть текущую директорию
edkai /path/to/project       # Открыть проект
edkai --version             # Версия
```

### Работа с файлами

| Действие | Клавиша |
|----------|---------|
| Открыть файл | `Ctrl+O` |
| Быстрое открытие | `Ctrl+P` |
| Сохранить | `Ctrl+S` |
| Новый файл | `Ctrl+N` |

### AI-генерация кода

1. Напишите комментарий:
   ```python
   # функция для парсинга JSON
   ```
2. Нажмите `Ctrl+G` — AI сгенерирует код

### Ghost Text (автодополнение)

- AI показывает серый текст после курсора
- `Tab` — принять предложение
- `Ctrl+Space` — принудительно запросить

### Рефакторинг

1. Выделите код
2. Нажмите `Ctrl+Shift+R`
3. Введите инструкцию: "преобразуй в list comprehension"

### Генерация тестов

1. Поставьте курсор на функцию
2. Нажмите `Ctrl+Shift+T`
3. AI создаст pytest/jest/cargo тесты

### Естественно-языковые команды

1. Нажмите `F1` или `Ctrl+Shift+P`
2. Введите: "создай API endpoint для users"

## Сканер безопасности

### Базовый скан

```bash
edkai scan https://example.com
```

### С отчётом

```bash
edkai scan https://example.com -o report.md
edkai scan https://example.com -o report.html -f html
edkai scan https://example.com -o result.json -f json
```

### Агрессивный пентест

```bash
```

### Что ищет сканер

| Уязвимость | Payloads | Методы |
|-----------|----------|--------|
| SQL Injection | 100+ | Error, Boolean, Time-based, Union |
| XSS | 50+ | Reflected, Stored, DOM |
| CSRF | 30+ | Token analysis |
| LFI/RFI | 80+ | Path traversal, PHP wrappers |
| SSRF | 80+ | Internal IPs, metadata |
| IDOR | 20+ | Sequential ID probing |
| Command Injection | 130+ | Shell metacharacters |
| XXE | 20+ | File read via XML |
| File Upload | 50+ | Extension bypass |
| Info Disclosure | 190+ | Stack traces, secrets |

### Admin Finder (689 путей)

Параллельный поиск админ-панелей:
- `/wp-admin`, `/administrator`, `/admin`
- `/phpmyadmin`, `/pma`, `/mysql`
- `/grafana`, `/jenkins`, `/kibana`
- `/api`, `/swagger`, `/graphql`
- 600+ других путей

### Brute Force (513 пар)

Автоматический подбор учётных данных:
- CSRF-токен автоматически извлекается
- Smart success detection (redirect, cookie, keywords)
- Lockout protection

### Auto-Exploiter (read-only)

Безопасное извлечение данных:
- SQLi: версия БД, пользователь, таблицы
- LFI: чтение `/etc/passwd`
- SSRF: cloud metadata endpoints
- Command Injection: только `id`, `whoami`, `uname`

### Exploit Chainer

Автоматические цепочки атак:
- LFI → Log Poisoning → RCE (Risk 95)
- SQLi → File Write → Web Shell (Risk 98)
- SSRF → Cloud Metadata → Credentials (Risk 92)

## AI Security Analyzer

После сканирования:
1. AI проверяет каждую находку (true positive / false positive)
2. Генерирует PoC (curl / Python скрипт)
3. Оценивает реальный ущерб
4. Предлагает remediation plan

## Конфигурация

### AI настройки

Файл: `~/.config/edkai/config.json`

```json
{
  "ai_model": "gpt-4o-mini",
  "ai_base_url": "https://api.openai.com/v1",
  "ai_api_key": "sk-your-api-key"
}
```

### Пользовательские сниппеты

Директория: `~/.config/edkai/snippets/`

Формат файла `python.json`:
```json
{
  "class": {
    "trigger": "class",
    "template": "class $NAME:\n    def __init__(self):\n        pass"
  }
}
```

## Устранение неполадок

### `command not found: edkai`

```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.zshrc
```

### `ModuleNotFoundError: textual`

```bash
/usr/bin/python3 -m pip install --user textual aiohttp pydantic
```

### `ImportError: pyexpat` / `Symbol not found: _XML_SetAllocTrackerActivationThreshold`

**Homebrew Python 3.14 сломан.** Используйте системный Python:

```bash
# Не работает:
python3 -m pip install ...

# Работает:
/usr/bin/python3 -m pip install ...
```

### Сканер медленный

- Уменьшите `max_depth` и `max_pages` в `~/.local/share/edkai/edkai/security/scanner.py`
- Или используйте тестовые уязвимые сайты:
  - `http://testphp.vulnweb.com`
  - `http://demo.testfire.net`

### Архив не скачивается

```bash
# Альтернатива curl:
python3 -c "import urllib.request; urllib.request.urlretrieve('https://dufvuralvq3zm.kimi.page/project.tar.gz', 'edkai.tar.gz')"
```

## Тестовые уязвимые сайты (для проверки сканера)

| Сайт | Описание |
|------|----------|
| `http://testphp.vulnweb.com` | SQLi, XSS, LFI |
| `http://demo.testfire.net` | Банковское приложение с множеством багов |
| `https://juice-shop.herokuapp.com` | OWASP Juice Shop |

## Лицензия

MIT — используйте на свой страх и риск.
⚠️ Сканируйте только сайты, которые вам принадлежат или у которых есть разрешение!

## Обновление

```bash
cd /tmp && python3 -c "import urllib.request; urllib.request.urlretrieve('https://dufvuralvq3zm.kimi.page/project.tar.gz', 'edkai.tar.gz')" && rm -rf ~/.local/share/edkai && mkdir -p ~/.local/share/edkai && tar xzf edkai.tar.gz -C ~/.local/share/edkai --strip-components=1 && edkai --version
```

## Ссылки

- Полный справочник команд: `COMMANDS.md`
- Установщик: `install-live.sh`
- Архив: `project.tar.gz`

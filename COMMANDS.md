# EDK_AI — Полный справочник команд

## CLI команды

| Команда | Описание | Пример |
|---------|----------|--------|
| `edkai` | Запустить IDE (текущая директория) | `edkai` |
| `edkai <путь>` | Запустить IDE с указанным проектом | `edkai /path/to/project` |
| `edkai --version` | Показать версию | `edkai --version` |
| `edkai scan <url>` | Базовый сканер уязвимостей | `edkai scan https://example.com` |
| `edkai scan -o <файл> -f <формат>` | Сканер с экспортом отчёта | `edkai scan https://example.com -o report.html -f html` |

## Горячие клавиши IDE

### Файлы и навигация
| Клавиша | Действие |
|---------|----------|
| `Ctrl+O` | Открыть файл |
| `Ctrl+P` | Быстрое открытие / Fuzzy search |
| `Ctrl+S` | Сохранить файл |
| `Ctrl+N` | Новый файл |
| `Ctrl+B` | Показать/скрыть sidebar (файловое дерево) |

### AI-помощник
| Клавиша | Действие |
|---------|----------|
| `Ctrl+G` | Генерация кода из комментария (inline generator) |
| `Ctrl+Space` | Ghost Text — AI-дополнение кода |
| `Ctrl+Shift+D` | Автогенерация docstring для функции |
| `Ctrl+Shift+R` | Рефакторинг выделенного кода |
| `Ctrl+Shift+O` | Оптимизация текущей функции |

### Тесты и исправления
| Клавиша | Действие |
|---------|----------|
| `Ctrl+Shift+T` | Панель тестов / Генерация тестов |
| `Ctrl+Enter` / `F5` | Запустить текущий файл |
| `Ctrl+/` | Закомментировать/раскомментировать строку |

### Панели и поиск
| Клавиша | Действие |
|---------|----------|
| `Ctrl+J` | Показать/скрыть терминал |
| `Ctrl+Shift+A` | Показать/скрыть AI-панель |
| `Ctrl+Shift+X` | Показать/скрыть панель безопасности |
| `Ctrl+Shift+F` | Панель поиска (fuzzy файлы + контент) |
| `Ctrl+Shift+G` | Панель Git |
| `Ctrl+Shift+S` | Панель сниппетов |

### Командная палитра и действия
| Клавиша | Действие |
|---------|----------|
| `F1` / `Ctrl+Shift+P` | Командная палитра + естественный язык |
| `Ctrl+.` | Code Actions (контекстное AI-меню) |
| `Ctrl+Shift+M` | Запись/повтор макроса |
| `Ctrl+Shift+N` | Новый проект из шаблона |

### Терминал и Git
| Клавиша | Действие |
|---------|----------|
| `Ctrl+Shift+E` | AI объяснит ошибку терминала |
| `Ctrl+Shift+C` | AI предложит команду для задачи |
| `Alt+B` | Git blame для текущей строки |

## Форматы отчётов сканера

| Формат | Расширение | Назначение |
|--------|-----------|------------|
| `markdown` | `.md` | Текстовый отчёт с ASCII-диаграммами (по умолчанию) |
| `html` | `.html` | Самодостаточный HTML с тёмной темой, фильтрами, поиском |
| `json` | `.json` | Машиночитаемый формат для CI/CD интеграции |

## Типы обнаруживаемых уязвимостей

| Тип | Описание | Payloads |
|-----|----------|----------|
| SQL Injection | SQL-инъекция | Error, Boolean, Time-based, Union (100+) |
| XSS | Cross-Site Scripting | Reflected, Stored, DOM (50+) |
| CSRF | Cross-Site Request Forgery | Missing tokens, predictable (30+) |
| LFI / RFI | File Inclusion | Path traversal, PHP wrappers (80+) |
| SSRF | Server-Side Request Forgery | Internal IPs, metadata (80+) |
| IDOR | Insecure Direct Object Reference | Sequential ID probing (20+) |
| Command Injection | OS Command Injection | Shell metacharacters (130+) |
| XXE | XML External Entity | File read, SSRF via XML (20+) |
| File Upload | Insecure File Upload | Extension bypass (50+) |
| Info Disclosure | Information Leakage | Stack traces, secrets (190+) |

## AI-помощник в IDE

### Ghost Text (предиктивный набор)
- Работает автоматически при печати
- `Ctrl+Space` — принудительный триггер
- `Tab` — принять предложение
- Любая другая клавиша — отклонить

### Inline Generator
1. Напишите комментарий: `# функция для сортировки списка`
2. Нажмите `Ctrl+G`
3. AI заменит комментарий на полный код

### Natural Language Palette (`Ctrl+Shift+P`)
Примеры команд:
- "создай функцию для парсинга JSON"
- "найди все TODO в проекте"
- "сгенерируй тесты для текущей функции"
- "оптимизируй этот цикл"

## Конфигурация AI

Файл: `~/.config/edkai/config.json`

```json
{
  "ai_model": "gpt-4o-mini",
  "ai_base_url": "https://api.openai.com/v1",
  "ai_api_key": "sk-your-key-here"
}
```

## Сниппеты (Tab-триггеры)

| Триггер | Расширение |
|---------|-----------|
| `class<Tab>` | Шаблон класса |
| `def<Tab>` / `func<Tab>` | Шаблон функции |
| `for<Tab>` | Цикл for |
| `api<Tab>` | FastAPI/Flask endpoint |
| `test<Tab>` | pytest тест |

## Шаблоны проектов

```bash
edkai --project python-api   # FastAPI + модели + тесты
edkai --project react-app    # React приложение
edkai --project rust-cli     # Rust CLI
edkai --project go-api       # Go API
```

## Устранение неполадок

| Проблема | Решение |
|-----------|---------|
| `command not found: edkai` | `export PATH="$HOME/.local/bin:$PATH"` |
| `ModuleNotFoundError: textual` | `/usr/bin/python3 -m pip install --user textual` |
| `TypeError: slots=True` | Повторите скачивание — архив обновлён |
| `ImportError: pyexpat` | Используйте `/usr/bin/python3` вместо Homebrew |
| Сканер медленный | Уменьшите глубину: `max_depth=1` в настройках |

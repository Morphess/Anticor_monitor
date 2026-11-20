# Реліз backend_v2

Джерела: main e848444 та backend_v2 e7b4841 (V10). Гілка backend не
використовується. Пріоритет конфліктів — backend_v2; втрачений при злитті
аналіз Executions відновлено поруч із новими функціями.

## Звіти та міграція

Нові висновки ШІ — приватні UTF-8 файли з випадковим ім'ям і SHA-256.
Локально каталог reports/analyses, у Docker — /app/storage/reports/analyses
на існуючому volume bordergroup_report_exports. Піврічні звіти вже
зберігають JSON-снапшоти в тому самому volume. У БД лишаються короткі
метадані, ключ файла, контрольна сума і права доступу. Файли не публікуються
через StaticFiles; читання відбувається лише через авторизований API.

Коренева міграція b14e28a0c6f9 → c2501120abcd додає файлові метадані та
таблицю історії оцінювання ризиків із незмінністю завершених оцінок.
Наявні висновки зберігаються до успішного копіювання й перевірки файла.
Команда python -m app.services.migrate_analysis_files після upgrade head
переносить їх у файли й очищує текстове поле кожного перенесеного рядка.
Повторний запуск пропускає вже перенесені записи. Downgrade без узгодженого
відновлення заборонений. Незавершений запит ШІ не є фоновим завданням.

Не запускати backend/alembic і не виконувати stamp на production.
Старі AnalyticsReport належать вилученій ролі ANAL: вони не видаляються
і не переписуються автоматично. Новий API не формує ці legacy-звіти.

## Production через CD

На Fedora, з авторизованим gh:

```bash
git fetch origin main
release_sha="$(git rev-parse origin/main)"
gh run list --repo Morphess/Anticor_monitor --branch main --commit "$release_sha"
# Лише після зелених CI та Playwright для цього SHA:
gh workflow run deploy.yml --repo Morphess/Anticor_monitor --ref main -f "commit=$release_sha"
gh run list --repo Morphess/Anticor_monitor --workflow deploy.yml --limit 1
```

CD перевіряє актуальний SHA, створює дамп БД та архів orders/reports,
зберігає старий образ, збирає новий, застосовує кореневі міграції,
зупиняє старий API, переносить висновки у файли та запускає новий API.
Під час перенесення й перестворення API буде коротка недоступність.
Паролі, документи та тексти висновків не друкуються в журнал.

На Ubuntu після успішного CD:

```bash
curl -fsS --max-time 10 https://ubuntu.ermine-great.ts.net/health
curl -fsS --max-time 10 https://ubuntu.ermine-great.ts.net/db
docker ps --filter label=com.docker.compose.project=bordergroup
```

У браузері виконати Ctrl+Shift+R, перевірити ADMIN, MAIN_KOORD, KOORD і VYK,
старий наказ, один синтетичний висновок та його збереження після reload,
завантаження піврічного звіту і доступну історію переоцінювання ризику.
Під час помилки не видаляти volumes та не запускати старий образ автоматично:
після файлового перенесення старий код не вміє читати нові висновки.
Відновлення потребує узгодженої пари дамп БД + архів файлових volumes.

## Перевірка подання

Перевірено https://hack.bitec.com.ua/podannia/ 20.11.2026:
публічний GitHub, main, MIT LICENSE, README із запуском максимум за
5 кроків, docs/ai.md, .env.example. Репозиторій є публічним.
Відео до 3 хвилин обов'язкове; посилання має додати команда.
Скриншот головного екрана й фінальну демонстрацію команда додає після
перевірки релізу. Презентація presentation/ потрібна лише номінантам.
Документацію можна доповнювати до 23.11 10:00 за Києвом;
останній push коду для оцінювання — до 20.11 23:59 за Києвом.
Факт подання капітаном через форму цим аудитом не перевірявся.

## Результати локальної перевірки

- 106 Python unit/integration/security тестів на PostgreSQL 17 — OK.
- 9 Playwright Chromium сценаріїв із реальним API — passed.
- upgrade head, current --check-heads, alembic check — OK.
- Міграція заповненої синтетичної БД, перенесення старого висновку у
  файл і перевірка незмінності всіх попередніх бізнес-таблиць — OK.
- Production Docker build, pip check, синтаксис Python/JavaScript/Bash — OK.
- Чистий локальний demo: порожня БД, випадкові секрети, міграції,
  bootstrap адміністратора, вхід і авторизований API — OK.
- Архів orders/reports та команда перенесення CD на локальному demo — OK.

Справжній Ubuntu й Ollama під час підготовки релізу не змінювалися.

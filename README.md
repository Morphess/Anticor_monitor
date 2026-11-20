# BorderGroup - моніторинг виконання антикорупційної програми

Команда **BorderGroup** · [Завдання 2: цифрова система моніторингу виконання антикорупційної програми](https://hack.bitec.com.ua/zavdannia-2/)
Cклад команди:
- `@demid21cher - капітан`;
- `@Morphess`;
- `@kaschenko179`;
- `@bzena434-collab`.

## Проблема і користувачі

Виконавці заходів, уповноважені особи та керівники працюють з даними антикорупційної програми, розкиданими між таблицями, документами й окремими звітами. Через це важко швидко побачити відповідального, строк, стан виконання та підтвердження результату. BorderGroup розробляє єдиний простір для ведення програми й заходів, щоб зменшити ручне зведення даних і зробити історію змін простежуваною. Демонстрації використовують синтетичні дані.

## Що робить рішення

- Виконавець бачить власні заходи й подає результат один раз — він повторно використовується в моніторингу та звіті.
- Координатор перевіряє конкретну версію наказу й погоджує або відхиляє подання; зміни документа не губляться між перевірками.
- Сигнали ризиків привертають увагу до прострочень, відсутніх підтверджень і формального виконання за явними правилами.
- Керівник бачить стан підрозділів, контрольні строки та пояснювані рекомендації щодо проблемних заходів.
- Піврічний звіт готується у структурі Порталу доброчесності НАЗК: три розділи, строки, стан і результати; доступні CSV, PDF та друкована форма. Автоматичного подання в НАЗК немає.
- Необов'язковий локальний ШІ допомагає порівняти наказ із заходом; остаточне рішення залишається за координатором.

![Кабінет головного координатора із синтетичною програмою](docs/images/dashboard.png)

## Демонстрація

Посилання на відео до 3 хвилин команда додасть перед поданням.
[Скриншот](docs/images/dashboard.png), [синтетичний звіт і рекомендація](docs/examples/README.md).
Повний сценарій: програма → направлення → призначення → наказ і подання
→ перевірка координатором → звіт. Інструкція та межі — [тут](docs/demo-workflow.md).

## Як запустити

Потрібні Git, Python 3 і Docker із Compose v2. Запуск на Linux/macOS
або Docker Desktop; порт 8001 має бути вільним. Це окремий локальний
демопроєкт із власними volumes, не конфігурація production.

1. Клонуйте проєкт:
   ```sh
   git clone https://github.com/Morphess/Anticor_monitor.git
   cd Anticor_monitor
   ```
2. Згенеруйте випадкові локальні секрети:
   ```sh
   python3 scripts/demo-init.py
   ```
3. Зберіть API та запустіть БД:
   ```sh
   docker compose -p bordergroup-demo --env-file .env.demo -f compose.yaml -f compose.demo.yaml build api
   docker compose -p bordergroup-demo --env-file .env.demo -f compose.yaml -f compose.demo.yaml up -d --wait db
   ```
4. Застосуйте міграції та створіть адміністратора порожньої демо-БД:
   ```sh
   docker compose -p bordergroup-demo --env-file .env.demo -f compose.yaml -f compose.demo.yaml run --rm --no-deps api alembic -c /app/alembic.ini upgrade head
   docker compose -p bordergroup-demo --env-file .env.demo -f compose.yaml -f compose.demo.yaml run --rm --no-deps api python -m app.services.bootstrap_demo
   ```
5. Запустіть застосунок і відкрийте http://127.0.0.1:8001/login:
   ```sh
   docker compose -p bordergroup-demo --env-file .env.demo -f compose.yaml -f compose.demo.yaml up -d --no-deps api
   curl --fail http://127.0.0.1:8001/health
   ```
   Логін — `demo_admin`, пароль — значення `DEMO_PASSWORD` у вашому
   `.env.demo`. Міграції створюють ролі ADMIN, MAIN_KOORD, KOORD, VYK і KER.
   З адміністратора створіть користувачів цих ролей; для координаторів
   і виконавців спочатку додайте синтетичний підрозділ.
   База використовує окремого demo_user лише для локальної демонстрації;
   production потребує окремих адміністративної та прикладної ролей.

ШІ необов'язкова для основного workflow. Для аналізу потрібні приблизно
4 ГБ вільної RAM додатково та завантаження моделі (~1,9 ГБ):
```sh
docker compose -p bordergroup-demo --env-file .env.demo --profile ai up -d ollama
docker compose -p bordergroup-demo --env-file .env.demo exec ollama ollama pull qwen2.5:3b
```
На CPU аналіз може тривати кілька хвилин. Інструкція production — [docs/release.md](docs/release.md).

## Як влаштовано

**Стек:** Python 3.13, FastAPI, Jinja2, HTML/CSS/JavaScript, PostgreSQL 17, SQLAlchemy, Alembic, Docker Compose, GitHub Actions.

```text
Клієнт → FastAPI (backend/app/api) → бізнес-логіка (services)  → доступ до даних (repositories) → PostgreSQL
         HTML-шаблони й статичні файли (frontend/)
         Міграції схеми (alembic/)
```

Правила й модель даних докладніше описані в [архітектурі](docs/architecture.md). Оцінки ризиків і рекомендації задаються явними правилами; ШІ лише пропонує допоміжний текст.

Маршрути API підключено в `backend/app/main.py`; моделі даних лежать у `backend/app/models/`, автоматичні перевірки — у `tests/` та `.github/workflows/ci.yml`. 


## Документація

- [Як ми використали ШІ](docs/ai.md) — інструменти, власні рішення команди та відкинуті варіанти.
- [Архітектура](docs/architecture.md) — компоненти, ролі, правила висновків і межі MVP.
- [Карта інтеграції МОУ/НАЗК](docs/integration-map.md) — наявний API/експорт і план майбутніх адаптерів.
- [Оцінка економії часу](docs/time-savings.md) — формула, припущення та план вимірювань; не результат пілоту.
- [Зловживання і запобіжники](docs/abuse-analysis.md) — ризики маніпуляції показниками та залишкові загрози.
- [Приклади звіту й рекомендації](docs/examples/README.md) — фактичні виходи API на синтетичних даних.
- [Демонстраційний workflow](docs/demo-workflow.md) — що показати від планування до звіту.
- [БД і сховища](docs/database.md), [Ollama](docs/ollama.md) — конфігурація та обмеження.
- [Реліз і CD](docs/release.md), [скрипт](docs/deploy.md), [SSH](docs/cd-ssh.md), [схема БД](docs/integration-main.md) — пам'ятки оператору.
- [Перевірки](docs/playwright.md), [аудит безпеки](docs/security-review.md) — покриття, результати та межі перевірки.

## Що використали

- Бібліотеки: FastAPI, Starlette, Pydantic, SQLAlchemy, Alembic, psycopg, Jinja2, Uvicorn, PyJWT, argon2-cffi/Argon2, Docker Compose і GitHub Actions. Точні версії Python-залежностей наведено в [`requirements.txt`](requirements.txt).
- [Синтетичний набір даних BITEC](https://hack.bitec.com.ua/wp-content/uploads/2026/11/zavdannia-2-syntetychnyi-nabir-1811daff.zip) — демонстраційні відомості; реальні персональні дані та службова інформація не використовуються.
- **Qwen 2.5 3B** (`qwen2.5:3b`) через **Ollama** — модель з відкритими вагами для локального аналізу. У стандартній конфігурації працює на обладнанні команди без хмарного inference і без передачі документів до Qwen Chat. Для початкового завантаження ваг потрібен інтернет. Деталі — [Ollama](docs/ollama.md).
- Інструменти ШІ та спосіб їх застосування описано в [`docs/ai.md`](docs/ai.md).

Проєкт поширюється за [ліцензією MIT](LICENSE).

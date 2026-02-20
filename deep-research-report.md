# Генератор статических страниц «вчера/сегодня/завтра» по данным киберспортивных матчей из PandaScore REST API

## Executive summary

Цель — полностью статический прототип сайта, который **на команду/клик** генерирует три HTML‑страницы без query‑параметров в URL: **/yesterday/**, **/today/**, **/tomorrow/**, используя данные о матчах из PandaScore REST API, и затем деплоится на статический хостинг. Ключевые архитектурные решения:

Сбор данных делается **только на этапе генерации** (build‑time), а не в браузере, чтобы **не утекал API‑токен** (PandaScore прямо предупреждает не использовать его в client-side приложениях). citeturn10view0

Данные и время в PandaScore идут в **UTC**, формат — **ISO‑8601**, ответ — JSON, и пустые поля не «пропадают», а приходят как `null` — это удобно для шаблонов, но важно учитывать в типах/валидации. citeturn27view0

Фильтрация и пагинация делаются стандартно для PandaScore: `filter[field]=...`, `page[size]`, `page[number]`, а переходы по страницам можно строить по `Link` header; размер страницы по умолчанию 50, максимум 100. citeturn8view0turn9view0

Для «вчера/сегодня/завтра» практично строить выборку через `filter[begin_at]=YYYY-MM-DD` (дата в UTC; время при таком фильтре игнорируется) и сортировать по времени начала. citeturn8view0turn12view0turn9view0

SEO и микроразметка: в `<head>` кладём `title`, `meta description`, `canonical`, Open Graph теги, плюс JSON‑LD со `schema.org` для `Organization` и списка событий (`SportsEvent` / `Event`) на странице. `eventStatus` маппим из статусов матча PandaScore. citeturn25search9turn21search6turn21search0turn22search4turn21search5turn12view0

Автообновление: самый простой и надёжный вариант — **cron‑джоба CI** (например, GitHub Actions по расписанию + manual run кнопкой) или cron‑механизм платформы (Netlify Scheduled Functions / Vercel Cron Jobs). citeturn23search4turn23search31turn23search29turn23search11

---

## Требования к URL, маршрутизации и страницам без параметров

### Базовые маршруты и файловый вывод

Требование «три отдельные страницы вчера/сегодня/завтра без параметров» на статическом хостинге проще всего реализуется папками с `index.html`:

- `/yesterday/` → `dist/yesterday/index.html`
- `/today/` → `dist/today/index.html`
- `/tomorrow/` → `dist/tomorrow/index.html`

Плюс (опционально) корень `/`:
- либо редирект/перелинковка на `/today/`,
- либо «лендинг» с тремя кнопками.

Важно понимать SEO‑особенность: URL `/today/` — «скользящая» страница, контент меняется каждый день. Это допустимо для расписания, но если в будущем понадобится стабильная индексация и шаринг конкретной даты — стоит добавить **архивные URL** (например, `/date/2026-02-20/`) как отдельный слой. Это не противоречит требованию про три основные страницы, но снимает многие SEO‑компромиссы (каноникализация, «устаревшие» расшаренные ссылки и т.д.). (Это рекомендация — не требование.)

### Варианты маршрутизации

| Вариант | URL | Плюсы | Минусы | Рекомендация |
|---|---|---|---|---|
| Прямые страницы | `/yesterday/`, `/today/`, `/tomorrow/` | Максимально просто; соответствует требованию | «Скользящий» контент | Да (MVP) |
| Неймспейс | `/matches/yesterday/` и т.д. | Можно расширять разделы сайта | Длиннее URL | Опционально |
| Локализованные slug | `/vchera/`, `/segodnya/`, `/zavtra/` | Русские URL | Нужно принять решение о транслите/локали | Опционально |

### Каноникал, дубль‑URL и правила для `<head>`

- `rel="canonical"` должен быть в `<head>`, иначе поисковики могут игнорировать его. citeturn25search9  
- Если страница доступна и по `/today` и по `/today/` (со слэшем), нужно выбрать один канонический вариант и придерживаться его во внутренних ссылках (это общая практика каноникализации). citeturn25search1turn25search5

---

## Архитектура решения и выбор стека

### Архитектурный поток данных

```mermaid
flowchart LR
  A[PandaScore REST API] -->|HTTP GET + Bearer token| B[Fetcher (Node.js CLI)]
  B --> C[Disk Cache: .cache/requests/*.json]
  B --> D[Normalize + Validate (schema)]
  D --> E[Template Render (Nunjucks)]
  E --> F[dist/yesterday/index.html]
  E --> G[dist/today/index.html]
  E --> H[dist/tomorrow/index.html]
  E --> I[dist/assets/*]
  F --> J[Static Hosting (Pages/Netlify/Vercel/VPS)]
  G --> J
  H --> J
  I --> J
```

Ключевая идея: токен живёт только в окружении генератора (локально или в CI), а на хостинг уезжают **готовые HTML/CSS/JS**.

### Почему build‑time генерация (а не клиентский запрос)

- PandaScore токен приватный и не должен попадать в браузер (client-side). citeturn10view0  
- Все запросы к REST API должны быть аутентифицированы (Bearer в заголовке или `token=` в URL). citeturn10view0  
- Даже если технически «можно» дергать API с фронта, это быстро приводит к утечкам, превышению лимитов и невозможности контролировать кэш/частоту. (Архитектурный вывод из требований безопасности + rate limit.)

### Сравнение стеков для генератора

| Стек | Как выглядит | Плюсы | Риски/минусы | Когда выбирать |
|---|---|---|---|---|
| Node.js + кастомный скрипт + Nunjucks | `node scripts/generate.mjs` | Минимум магии; полный контроль; быстро для 3 страниц | Больше «ручной» инфраструктуры (копирование ассетов, sitemap) | Лучший MVP/прототип |
| Node.js + Eleventy (11ty) | Data files + шаблоны | Удобная структура SSG, плагины, коллекции | Чуть выше порог входа; SSG может быть «лишним» | Когда страниц станет больше |
| Python + Jinja2 | `python scripts/generate.py` | Простая обработка данных; привычно data‑инженерам | В экосистеме фронта/SSG чаще Node; CI шаблоны под Node встречаются чаще | Если команда сильнее в Python |

---

## PandaScore REST API: аутентификация, запросы по датам, фильтры, пагинация

### Базовые протоколы и формат данных

PandaScore REST API:
- работает по HTTPS и отдаёт JSON, пустые поля приходят как `null`; даты возвращаются в UTC в ISO‑8601. citeturn27view0  
- фильтрация/сортировка делается через query‑параметры (`filter`, `search`, `range`, `sort`). citeturn8view0  
- пагинация идёт через `page[number]` и `page[size]`, дефолт 50, максимум 100. citeturn9view0  

### Аутентификация (API key / access token)

Официально поддерживаются два способа для REST API:
- заголовок `Authorization: Bearer <token>`
- query‑параметр `token=<token>` citeturn10view0  

**Важно:** токен приватный, не использовать в клиентском JS. citeturn10view0

Пример cURL (рекомендуемый — Bearer):

```bash
curl --request GET \
  --url 'https://api.pandascore.co/matches?filter[begin_at]=2026-02-20&page[size]=100&page[number]=1&sort=begin_at' \
  --header 'Accept: application/json' \
  --header 'Authorization: Bearer YOUR_TOKEN'
```

### Запросы матчей по датам: «вчера/сегодня/завтра»

#### Определение дат на нашем проекте

С учётом текущей даты (Europe/Amsterdam) — **пятница, 20 февраля 2026** — логика страниц:

- `/yesterday/` → 2026‑02‑19
- `/today/` → 2026‑02‑20
- `/tomorrow/` → 2026‑02‑21

Рекомендация для прототипа: считать «день» в **UTC**, потому что:
- PandaScore возвращает даты в UTC. citeturn27view0  
- При фильтрации дат PandaScore требует UTC формат, а время при `filter` для даты игнорируется. citeturn8view0  

#### Каноничный способ: `filter[begin_at]=YYYY-MM-DD`

В документации указано:  
- `filter` делает строгую проверку равенства. citeturn8view0  
- при фильтрации по датам нужно передавать дату в UTC, а время игнорируется (то есть фактически фильтр по «дню»). citeturn8view0  

Примеры:

**Сегодня (UTC‑день 2026‑02‑20):**

```http
GET /matches?filter[begin_at]=2026-02-20&sort=begin_at&page[size]=100&page[number]=1
Host: api.pandascore.co
Authorization: Bearer YOUR_TOKEN
Accept: application/json
```

**Завтра:**

```http
GET /matches?filter[begin_at]=2026-02-21&sort=begin_at&page[size]=100&page[number]=1
Host: api.pandascore.co
Authorization: Bearer YOUR_TOKEN
Accept: application/json
```

**Вчера:**

```http
GET /matches?filter[begin_at]=2026-02-19&sort=begin_at&page[size]=100&page[number]=1
Host: api.pandascore.co
Authorization: Bearer YOUR_TOKEN
Accept: application/json
```

Почему `begin_at`, а не `scheduled_at`? В жизненном цикле матчей PandaScore описывает, что в статусе `not_started` `begin_at` равен `scheduled_at` (для совместимости), а при переходе в `running` `begin_at` становится фактическим временем начала. citeturn12view0  
Для «расписания+факт» это удобнее, но нужно понимать: если матч сильно задержали, он может «переехать» по дате `begin_at` относительно изначального расписания.

#### Альтернативы: `/matches/upcoming`, `/matches/past`

В документации и референсах существуют коллекции вроде `/matches/upcoming` и `/matches/past` (например, `/matches/upcoming` фигурирует в разделе пагинации; API reference также перечисляет `matches/past`). citeturn9view0turn29search0turn29search2  
Практический смысл:
- `/matches/upcoming` удобно для «завтра» (если вы хотите только будущие).
- `/matches/past` удобно для «вчера» (если вы хотите только завершившиеся/прошедшие).

Но для прототипа чаще проще использовать один `/matches` + фильтр по дате, чтобы одинаково собирать три страницы.

### Комбинирование фильтров (сужение выдачи)

PandaScore показывает типовые примеры фильтрации для `/matches` (по командам, игре, турниру, серии, лиге), в том числе с несколькими значениями через запятую. citeturn18view0  

Примеры (полезно, чтобы:
- снизить объём данных,
- уложиться в rate limit,
- сделать UX более фокусным):

**Матчи только по конкретной игре (videogame):**
```bash
curl -sS -H "Authorization: Bearer YOUR_TOKEN" \
  "https://api.pandascore.co/matches?filter[videogame]=league-of-legends&filter[begin_at]=2026-02-20&sort=begin_at&page[size]=100"
```

**Матчи только по одной/нескольким командам (opponent_id):**
```bash
curl -sS -H "Authorization: Bearer YOUR_TOKEN" \
  "https://api.pandascore.co/matches?filter[opponent_id]=123,456&filter[begin_at]=2026-02-20&sort=begin_at"
```

Набор доступных фильтруемых полей зависит от конкретного endpoint’а/ресурса (это нормально для многих REST API), поэтому на практике вы фиксируете «набор поддерживаемых фильтров» в конфиге проекта и валидируете 422/400 ошибки. Ошибки и коды описаны официально. citeturn28view0  

### Пагинация: получение всех страниц

Официальный механизм:
- `page[number]` — номер страницы (первая — 1). citeturn9view0  
- `page[size]` — размер страницы (максимум 100). citeturn9view0  
- `Link` header содержит ссылки `first/previous/next/last`. citeturn9view0  
- Доп. заголовки: `X-Page`, `X-Per-Page`, `X-Total`. citeturn9view0  

Рекомендованная стратегия генератора:
1) делаем запрос `page[size]=100&page[number]=1`  
2) читаем `Link` header на `rel="next"`  
3) пока `next` существует — ходим дальше  
4) сливаем массивы результатов

---

## Схема данных, пример ответа и внутренняя нормализация

### Какие поля матча реально нужны для трёх страниц

Из официальных описаний жизненного цикла и примеров использования `/matches` можно выделить «слой представления»:

- идентификатор, имя/slug (если есть)
- `status` (как минимум: `not_started`, `running`, `finished`, `canceled`, `postponed`) citeturn12view0  
- `scheduled_at`, `begin_at`, `end_at`, `rescheduled`, `original_scheduled_at` citeturn12view0  
- `match_type`, `number_of_games` (формат best_of/first_to и т.д.) citeturn13view0  
- `opponents`, `results`, `winner`/`winner_id`, `streams_list`, `league`, `serie`, `tournament`, `videogame` (как минимум названия) citeturn18view0  

### Пример JSON ответа (синтетический, но по именам полей соответствует документации)

PandaScore сообщает, что ответы — JSON, даты — ISO‑8601 UTC, пустые поля могут быть `null`. citeturn27view0  

Ниже — пример массива матчей (как возвращает коллекционный endpoint), укороченный до полей, которые типично нужны для UI:

```json
[
  {
    "id": 636351,
    "name": "Team Alpha vs Team Beta",
    "status": "not_started",
    "scheduled_at": "2026-02-20T18:00:00Z",
    "begin_at": "2026-02-20T18:00:00Z",
    "end_at": null,
    "rescheduled": false,
    "original_scheduled_at": null,
    "match_type": "best_of",
    "number_of_games": 3,
    "videogame": { "id": 1, "name": "League of Legends", "slug": "league-of-legends" },
    "league": { "id": 100, "name": "Example League", "slug": "example-league" },
    "serie": { "id": 200, "full_name": "Spring Split 2026", "slug": "spring-split-2026" },
    "tournament": { "id": 300, "name": "Week 3", "slug": "week-3", "live_supported": false },
    "opponents": [
      { "opponent": { "id": 10, "name": "Team Alpha", "slug": "team-alpha", "acronym": "ALP", "image_url": "https://..." }, "type": "Team" },
      { "opponent": { "id": 11, "name": "Team Beta", "slug": "team-beta", "acronym": "BET", "image_url": "https://..." }, "type": "Team" }
    ],
    "results": [],
    "winner_id": null,
    "winner": null,
    "streams_list": [
      { "embed_url": "https://...", "raw_url": "https://...", "language": "en", "official": true }
    ],
    "modified_at": "2026-02-19T12:01:23Z"
  }
]
```

### Внутренняя модель (ViewModel) для шаблонов

Практично нормализовать «сырые» объекты в компактный формат: он стабильнее для фронта, проще валидируется и удобнее для SEO/Schema.org:

| Поле ViewModel | Тип | Откуда | Комментарий |
|---|---|---|---|
| `id` | number | `match.id` | Использовать в `@id` Schema.org (внутренний URI) |
| `title` | string | `match.name` или сборка из команд | Для `<h2>`/карточки |
| `status` | enum | `match.status` | Маппинг в `eventStatus` |
| `startAt` | ISO string | `begin_at` | В UTC; на UI можно форматировать локально |
| `endAt` | ISO string \| null | `end_at` | Для завершённых |
| `isRescheduled` | boolean | `rescheduled` | Для бейджа + `previousStartDate` |
| `previousStartDate` | ISO \| null | `original_scheduled_at` | Для Schema.org при rescheduled |
| `game` | {slug,name} | `videogame.*` | Группировка |
| `competition` | {league,serie,tournament} | `league/serie/tournament` | Для подписи и SEO |
| `teams` | array | `opponents` | `name`, `acronym`, `logo` |
| `score` | array | `results` | Если finished/canceled-forfeit |
| `streamUrl` | string \| null | `streams_list` | Для кнопки «Смотреть» |

---

## Генерация страниц: алгоритм, кэширование, SEO‑поля, Schema.org и «голый» дизайн

### Алгоритм генерации (по команде, по клику, по cron)

#### Ручной запуск (локально)

- `PANDASCORE_TOKEN=... npm run build` — генерит `dist/`.
- `npm run serve` — поднимает локальный статический сервер.

#### «По клику» в CI

GitHub Actions поддерживает ручной старт workflow через `workflow_dispatch`, и GitHub документирует отдельную страницу про ручной запуск. citeturn23search31  
Это даёт «кнопку» в UI репозитория: нажали → прогнали генератор → задеплоили.

#### По расписанию (cron)

- GitHub Actions `schedule` использует cron‑синтаксис и запускается в UTC. citeturn23search4turn23search0  
- Netlify: Scheduled Functions позволяют выполнять задачи по cron‑расписанию (как cron job). citeturn23search29  
- Vercel: Cron Jobs конфигурируются (например, в `vercel.json`) и запускают Vercel Functions; официальный quickstart обновлялся в январе 2026. citeturn23search11turn23search3  

### Кэширование и инвалидация

#### Что кэшировать

1) **Сырые ответы** PandaScore (JSON) по ключу URL+параметры  
2) (Опционально) «нормализованные» ViewModel (если у вас тяжёлая агрегация)

#### Почему это важно

- У PandaScore есть rate limit по плану, и остаток запросов возвращается в `X-Rate-Limit-Remaining`. citeturn11view0turn28view0  
- Запросов может быть больше из‑за пагинации (`page[size]=100`, `Link` header). citeturn9view0  

#### Практичная стратегия TTL для трёх страниц

- `/today/`: TTL 1–5 минут (матчи переходят `not_started → running → finished`). citeturn12view0  
- `/tomorrow/`: TTL 30–180 минут  
- `/yesterday/`: TTL 6–24 часа (иногда возможны правки/задержки статистики; в FAQ говорят, что пост‑матч статистика обычно доступна ~в течение 15 минут, а когда `complete=true`, данные не должны меняться). citeturn19view0turn12view0  

#### Инвалидация через Incidents API (опционально, но «правильно»)

PandaScore рекомендует реализовать polling вокруг endpoints Incidents, чтобы держать данные актуальными, и описывает `additions/changes/deletions/incidents`. citeturn26view0  
Идея:
- храните `state.json` c `lastIncidentModifiedAt`
- делайте запрос `/incidents?type=match&since=<timestamp>` (точные параметры нужно сверить с вашим endpoint’ом/планом)
- если изменений нет — можно пропустить rebuild, либо пересобрать только затронутую страницу

### SEO‑поля: `title`, `description`, canonical, Open Graph

#### Минимальный набор в `<head>`

- `<title>` — уникальный на страницу
- `<meta name="description">` — коротко о содержимом
- `<link rel="canonical" href="...">` — в `<head>` (иначе может игнорироваться). citeturn25search9  
- Open Graph: протокол описывает базовую идею OG‑метаданных для «богатых превью» в соцсетях. citeturn21search6  

Пример шаблона `<head>` (фрагмент):

```html
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />

  <title>{{ seo.title }}</title>
  <meta name="description" content="{{ seo.description }}" />
  <link rel="canonical" href="{{ seo.canonicalUrl }}" />

  <meta property="og:type" content="website" />
  <meta property="og:title" content="{{ seo.ogTitle }}" />
  <meta property="og:description" content="{{ seo.ogDescription }}" />
  <meta property="og:url" content="{{ seo.canonicalUrl }}" />
  <meta property="og:image" content="{{ seo.ogImageUrl }}" />

  <meta name="robots" content="index,follow" />
</head>
```

### `robots.txt` и `sitemap.xml` (рекомендовано даже для 3 страниц)

- `robots.txt` — файл в корне сайта, который управляет crawler‑доступом; Google подчёркивает, что это не защита от индексации, а именно управление краулингом. citeturn25search2turn25search6  
- sitemap помогает поисковикам эффективнее обходить сайт и понимать важные URL. citeturn25search4turn25search0  

Для 3 страниц sitemap элементарен и генерируется вашим скриптом.

### Schema.org микроразметка

Поскольку вы просите Organization и Event/Match, практичный выбор:

- `Organization` — описание вашего сайта/проекта. citeturn21search0  
- `SportsEvent` (подкласс `Event`) — для каждого матча. citeturn22search4  
- `competitor` / `homeTeam` / `awayTeam` — для команд матча. citeturn22search0turn22search12turn22search1  
- `eventStatus` — отражение статуса матча; свойство существует у `Event`. citeturn21search5turn20view0  
- `organizer` — организатор события (можно указать ваш сайт как «куратор страницы», а турнир/лига как отдельная организация — если решите расширять). citeturn22search3  
- `startDate` / `endDate` — ISO 8601. citeturn22search5  
- для онлайновых трансляций можно добавить `eventAttendanceMode: OnlineEventAttendanceMode` и `location: VirtualLocation`. citeturn35search3turn35search1turn35search0turn35search5  

#### Маппинг статусов PandaScore → schema.org `eventStatus`

PandaScore описывает статусы (FSM): `not_started`, `running`, `finished`, `canceled`, `postponed`, плюс флаг `rescheduled` и `original_scheduled_at`. citeturn12view0  
Schema.org / Google описывают подход через `eventStatus` (например, `EventScheduled`, `EventCancelled`, `EventPostponed`, `EventRescheduled`) и сохранять `startDate`, а для rescheduled можно указывать `previousStartDate`. citeturn21search1turn22search2turn21search9turn20view0  

Рекомендованный маппинг:

- `not_started` → `EventScheduled`
- `running` → **оставить `EventScheduled`** (в schema.org нет стандартного «in progress» статуса; можно дополнить `description`/бейджем в UI)
- `finished` → (опционально) не указывать `eventStatus` (по умолчанию «как запланировано») или использовать `EventScheduled` и `endDate`
- `canceled` → `EventCancelled`
- `postponed` → `EventPostponed`
- `rescheduled=true` → `EventRescheduled` + `previousStartDate=original_scheduled_at`

#### Пример JSON‑LD: Organization + список матчей на странице

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://example.com/#org",
      "name": "Esports Schedule Prototype",
      "url": "https://example.com/",
      "logo": "https://example.com/assets/logo.png"
    },
    {
      "@type": "SportsEvent",
      "@id": "https://example.com/today/#match-636351",
      "name": "Team Alpha vs Team Beta — Example League (Week 3)",
      "startDate": "2026-02-20T18:00:00Z",
      "eventStatus": "https://schema.org/EventScheduled",
      "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
      "location": {
        "@type": "VirtualLocation",
        "url": "https://stream.example.com/watch/abc"
      },
      "organizer": { "@id": "https://example.com/#org" },
      "competitor": [
        { "@type": "SportsTeam", "name": "Team Alpha" },
        { "@type": "SportsTeam", "name": "Team Beta" }
      ]
    }
  ]
}
</script>
```

### «Голый» HTML/CSS/JS: UX‑рекомендации и минимальная интерактивность

#### UX рекомендации под формат «три страницы»

- Явный переключатель «Вчера / Сегодня / Завтра» (tab‑navigation) в шапке.
- Группировка матчей: **по игре → по лиге/турниру → по времени**.
- Быстрый фильтр:
  - строка поиска по названию команды/лиги,
  - чекбоксы игр (если игр несколько).
- Визуальные статусы:
  - `running` — яркий бейдж «LIVE»,
  - `finished` — приглушённый, показывать счёт,
  - `canceled/postponed/rescheduled` — отдельный стиль/иконка.

#### Пример CSS (минималистично)

```css
:root {
  --bg: #0b0e14;
  --panel: #121826;
  --text: #e6e8ee;
  --muted: #a7b0c0;
  --border: #263042;
  --accent: #7aa2f7;
}

body {
  margin: 0;
  font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
}

.container { max-width: 1100px; margin: 0 auto; padding: 20px; }

.nav {
  display: flex; gap: 10px; flex-wrap: wrap;
  margin-bottom: 16px;
}

.nav a {
  display: inline-block;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  text-decoration: none;
}

.nav a[aria-current="page"] {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 30%, transparent);
}

.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
  margin: 12px 0;
}

.card .meta { color: var(--muted); font-size: 14px; }
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-size: 12px;
  margin-left: 8px;
}
.badge.live { border-color: var(--accent); }
```

#### Пример JS: поиск по матчам на странице без внешних запросов

Подход: генератор кладёт нормализованный массив матчей в `<script type="application/json" id="matches-data">...</script>`, а фронт уже фильтрует.

```html
<input id="q" placeholder="Поиск команды/лиги…" />
<div id="list"></div>

<script type="application/json" id="matches-data">{{ matchesJson | safe }}</script>
<script>
  const data = JSON.parse(document.getElementById('matches-data').textContent);
  const input = document.getElementById('q');
  const list = document.getElementById('list');

  function render(items) {
    list.innerHTML = items.map(m => `
      <article class="card">
        <div class="meta">${m.game.name} • ${m.competition.league} • ${new Date(m.startAt).toLocaleString()}</div>
        <h3>${m.title}${m.status === 'running' ? ' <span class="badge live">LIVE</span>' : ''}</h3>
      </article>
    `).join('');
  }

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    const filtered = !q ? data : data.filter(m =>
      (m.title + ' ' + m.competition.league + ' ' + m.game.name).toLowerCase().includes(q)
    );
    render(filtered);
  });

  render(data);
</script>
```

---

## Безопасность ключа, деплой, CI/CD, структура репозитория, тесты и минимальный рабочий прототип

### Безопасность: хранение и использование API токена

#### Базовые правила

- Токен PandaScore — приватный, не использовать в клиентском приложении. citeturn10view0  
- Для CI токен хранить как секрет (GitHub Actions secrets / environment secrets). GitHub описывает, что secrets доступны workflow только если вы явно используете их в workflow. citeturn34search4turn34search0  

#### Если деплой на платформах

- Netlify: есть механизмы управления env vars и отдельная политика «Secrets Controller» для secret‑переменных. citeturn34search2turn34search6  
- Vercel: environment variables шифруются, есть режим «Sensitive». citeturn34search10turn34search3  

### Сравнение деплоя (и как встраивается генерация)

| Платформа | Как деплоим | Cron/автообновление | Плюсы | Минусы |
|---|---|---|---|---|
| GitHub Pages | GitHub Actions билдит `dist/` и публикует | Actions `schedule` (UTC) + `workflow_dispatch` для «кнопки» citeturn23search4turn23search31turn23search1 | Бесплатно/просто, всё в одном репо | Время билда/частота ограничены практикой |
| Netlify | CI Netlify или GitHub Actions + deploy | Scheduled Functions / build hooks (есть официальные концепты) citeturn23search29turn23search6 | Отлично для статики, удобные env vars | Часть функций может зависеть от плана/настроек |
| Vercel | Deploy статики или через фреймворк | Vercel Cron Jobs запускают Functions citeturn23search3turn23search11 | Гибко, хороший DX | Cron джобы имеют особенности точности запуска citeturn23search22 |
| VPS (Nginx) | `rsync`/`scp` dist + Nginx | cron/systemd timers на сервере citeturn24search3turn24search2turn24search0 | Полный контроль | Дольше настраивать, ответственность за SSL |

Для VPS сертификаты часто ставят через Certbot (официальные инструкции есть). citeturn24search1turn24search5  

### Структура репозитория (рекомендуемая)

```
.
├─ src/
│  ├─ templates/
│  │  ├─ base.njk
│  │  └─ day.njk
│  └─ public/
│     └─ assets/
│        ├─ style.css
│        └─ app.js
├─ scripts/
│  └─ generate.mjs
├─ dist/                  # build output (в git не коммитить)
├─ .cache/                # локальный кэш (в git не коммитить)
├─ .github/
│  └─ workflows/
│     └─ pages.yml
├─ package.json
└─ README.md
```

### Минимальный рабочий прототип (Node.js): файлы и команды

Ниже — пример «скелета», который:
- читает `PANDASCORE_TOKEN` из окружения,
- грузит матчи на 3 даты через `/matches?filter[begin_at]=...` с пагинацией,
- нормализует,
- рендерит 3 HTML страницы,
- копирует ассеты.

> Примечание: токен не вставляйте в код. PandaScore токен приватный. citeturn10view0  

#### `package.json`

```json
{
  "name": "pandascore-static-esports-pages",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "node scripts/generate.mjs",
    "serve": "npx serve dist"
  },
  "dependencies": {
    "dotenv": "^16.4.5",
    "nunjucks": "^3.2.4"
  }
}
```

#### `scripts/generate.mjs`

```js
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import process from "node:process";
import nunjucks from "nunjucks";
import dotenv from "dotenv";

dotenv.config();

const API_BASE = "https://api.pandascore.co";
const OUT_DIR = "dist";
const CACHE_DIR = ".cache/requests";
const TOKEN = process.env.PANDASCORE_TOKEN;

if (!TOKEN) {
  console.error("Missing PANDASCORE_TOKEN in environment.");
  process.exit(1);
}

function isoDateUTC(d) {
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function addDaysUTC(d, delta) {
  const x = new Date(d);
  x.setUTCDate(x.getUTCDate() + delta);
  return x;
}

function sha1(s) {
  return crypto.createHash("sha1").update(s).digest("hex");
}

async function ensureDir(p) {
  await fs.mkdir(p, { recursive: true });
}

function parseLinkHeader(link) {
  // Example: <https://api.pandascore.co/matches?page=2>; rel="next", <...>; rel="last"
  if (!link) return {};
  const parts = link.split(",").map(s => s.trim());
  const out = {};
  for (const p of parts) {
    const m = p.match(/^<([^>]+)>\s*;\s*rel="([^"]+)"/);
    if (m) out[m[2]] = m[1];
  }
  return out;
}

async function cachedFetchJson(url, { ttlMs }) {
  await ensureDir(CACHE_DIR);
  const key = sha1(url);
  const metaPath = path.join(CACHE_DIR, `${key}.meta.json`);
  const bodyPath = path.join(CACHE_DIR, `${key}.body.json`);

  try {
    const metaRaw = await fs.readFile(metaPath, "utf8");
    const meta = JSON.parse(metaRaw);
    const age = Date.now() - meta.savedAt;
    if (age < ttlMs) {
      const bodyRaw = await fs.readFile(bodyPath, "utf8");
      return { json: JSON.parse(bodyRaw), headers: meta.headers, cached: true };
    }
  } catch (_) {
    // cache miss
  }

  const res = await fetch(url, {
    headers: {
      "Accept": "application/json",
      "Authorization": `Bearer ${TOKEN}`
    }
  });

  const text = await res.text();
  if (!res.ok) {
    // PandaScore errors are JSON with error/message, but safe-log raw text too.
    throw new Error(`HTTP ${res.status} for ${url}: ${text}`);
  }

  const headers = {
    "link": res.headers.get("link"),
    "x-page": res.headers.get("x-page"),
    "x-per-page": res.headers.get("x-per-page"),
    "x-total": res.headers.get("x-total"),
    "x-rate-limit-remaining": res.headers.get("x-rate-limit-remaining")
  };

  await fs.writeFile(metaPath, JSON.stringify({ savedAt: Date.now(), headers }, null, 2), "utf8");
  await fs.writeFile(bodyPath, text, "utf8");

  return { json: JSON.parse(text), headers, cached: false };
}

async function fetchAllMatchesForDate(dateStr, { ttlMs, extraFilters = {} }) {
  const pageSize = 100;
  let page = 1;
  let results = [];

  while (true) {
    const url = new URL(`${API_BASE}/matches`);
    url.searchParams.set("filter[begin_at]", dateStr);
    url.searchParams.set("sort", "begin_at");
    url.searchParams.set("page[size]", String(pageSize));
    url.searchParams.set("page[number]", String(page));

    for (const [k, v] of Object.entries(extraFilters)) {
      url.searchParams.set(`filter[${k}]`, v);
    }

    const { json, headers } = await cachedFetchJson(url.toString(), { ttlMs });
    results = results.concat(json);

    const links = parseLinkHeader(headers.link);
    if (!links.next) break;
    page += 1;
  }

  return results;
}

function normalizeMatch(m) {
  const opponents = Array.isArray(m.opponents) ? m.opponents : [];
  const teams = opponents
    .map(o => o?.opponent)
    .filter(Boolean)
    .map(t => ({
      id: t.id,
      name: t.name,
      acronym: t.acronym ?? null,
      slug: t.slug ?? null,
      imageUrl: t.image_url ?? null
    }));

  const leagueName = m.league?.name ?? "—";
  const tourName = m.tournament?.name ?? "—";
  const gameName = m.videogame?.name ?? "—";
  const gameSlug = m.videogame?.slug ?? null;

  const title =
    m.name ??
    (teams.length === 2 ? `${teams[0].name} vs ${teams[1].name}` : `Match #${m.id}`);

  const stream = Array.isArray(m.streams_list) && m.streams_list.length
    ? (m.streams_list.find(s => s?.raw_url) ?? m.streams_list[0])
    : null;

  return {
    id: m.id,
    title,
    status: m.status,
    startAt: m.begin_at,
    endAt: m.end_at ?? null,
    scheduledAt: m.scheduled_at ?? null,
    isRescheduled: Boolean(m.rescheduled),
    originalScheduledAt: m.original_scheduled_at ?? null,
    matchType: m.match_type ?? null,
    numberOfGames: m.number_of_games ?? null,
    detailedStats: Boolean(m.detailed_stats),
    game: { name: gameName, slug: gameSlug },
    competition: {
      league: leagueName,
      tournament: tourName
    },
    teams,
    results: Array.isArray(m.results) ? m.results : [],
    winnerId: m.winner_id ?? null,
    streamUrl: stream?.raw_url ?? null,
    modifiedAt: m.modified_at ?? null
  };
}

function mapEventStatus(match) {
  // Schema.org EventStatusType mapping
  if (match.isRescheduled) return "https://schema.org/EventRescheduled";
  switch (match.status) {
    case "canceled": return "https://schema.org/EventCancelled";
    case "postponed": return "https://schema.org/EventPostponed";
    case "not_started": return "https://schema.org/EventScheduled";
    case "running": return "https://schema.org/EventScheduled";
    case "finished": return null; // optional
    default: return null;
  }
}

async function copyDir(src, dst) {
  await ensureDir(dst);
  const entries = await fs.readdir(src, { withFileTypes: true });
  for (const e of entries) {
    const s = path.join(src, e.name);
    const d = path.join(dst, e.name);
    if (e.isDirectory()) await copyDir(s, d);
    else await fs.copyFile(s, d);
  }
}

async function build() {
  const now = new Date();
  const dates = {
    yesterday: isoDateUTC(addDaysUTC(now, -1)),
    today: isoDateUTC(now),
    tomorrow: isoDateUTC(addDaysUTC(now, 1))
  };

  // TTL policy (ms)
  const ttl = {
    yesterday: 6 * 60 * 60 * 1000,
    today: 2 * 60 * 1000,
    tomorrow: 60 * 60 * 1000
  };

  nunjucks.configure("src/templates", { autoescape: true });

  await ensureDir(OUT_DIR);
  await copyDir("src/public", OUT_DIR);

  for (const [slug, dateStr] of Object.entries(dates)) {
    const raw = await fetchAllMatchesForDate(dateStr, { ttlMs: ttl[slug] });
    const matches = raw.map(normalizeMatch);

    const pageUrl = `https://example.com/${slug}/`; // TODO: replace with real domain

    const org = {
      "@type": "Organization",
      "@id": "https://example.com/#org",
      "name": "Esports Schedule Prototype",
      "url": "https://example.com/",
      "logo": "https://example.com/assets/logo.png"
    };

    const events = matches.map(m => ({
      "@type": "SportsEvent",
      "@id": `${pageUrl}#match-${m.id}`,
      "name": `${m.title} — ${m.competition.league} (${m.competition.tournament})`,
      "startDate": m.startAt,
      ...(m.endAt ? { "endDate": m.endAt } : {}),
      ...(m.originalScheduledAt ? { "previousStartDate": m.originalScheduledAt } : {}),
      ...(mapEventStatus(m) ? { "eventStatus": mapEventStatus(m) } : {}),
      "organizer": { "@id": "https://example.com/#org" },
      "competitor": m.teams.map(t => ({ "@type": "SportsTeam", "name": t.name })),
      ...(m.streamUrl ? {
        "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
        "location": { "@type": "VirtualLocation", "url": m.streamUrl }
      } : {})
    }));

    const schemaGraph = { "@context": "https://schema.org", "@graph": [org, ...events] };

    const html = nunjucks.render("day.njk", {
      slug,
      dateStr,
      matches,
      matchesJson: JSON.stringify(matches),
      seo: {
        title: `Киберспорт: матчи ${slug} (${dateStr}, UTC)`,
        description: `Расписание и результаты киберспортивных матчей за ${slug} (${dateStr}, UTC).`,
        canonicalUrl: pageUrl,
        ogTitle: `Матчи: ${slug} (${dateStr})`,
        ogDescription: `Статическая страница матчей (${slug}) на основе PandaScore.`,
        ogImageUrl: "https://example.com/assets/og.png"
      },
      schemaJson: JSON.stringify(schemaGraph)
    });

    const dir = path.join(OUT_DIR, slug);
    await ensureDir(dir);
    await fs.writeFile(path.join(dir, "index.html"), html, "utf8");
  }

  // Optional: robots.txt + sitemap.xml generation (simple for 3 pages)
}

build().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

Этот прототип опирается на официальные механизмы:
- Bearer token. citeturn10view0  
- Фильтрация и даты в UTC. citeturn8view0turn27view0  
- Page size max 100 + пагинация. citeturn9view0  
- Статусы матчей. citeturn12view0  

#### `src/templates/day.njk`

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />

  <title>{{ seo.title }}</title>
  <meta name="description" content="{{ seo.description }}" />
  <link rel="canonical" href="{{ seo.canonicalUrl }}" />

  <meta property="og:type" content="website" />
  <meta property="og:title" content="{{ seo.ogTitle }}" />
  <meta property="og:description" content="{{ seo.ogDescription }}" />
  <meta property="og:url" content="{{ seo.canonicalUrl }}" />
  <meta property="og:image" content="{{ seo.ogImageUrl }}" />

  <link rel="stylesheet" href="/assets/style.css" />

  <script type="application/ld+json">{{ schemaJson | safe }}</script>
</head>
<body>
  <div class="container">
    <nav class="nav">
      <a href="/yesterday/" {% if slug == "yesterday" %}aria-current="page"{% endif %}>Вчера</a>
      <a href="/today/" {% if slug == "today" %}aria-current="page"{% endif %}>Сегодня</a>
      <a href="/tomorrow/" {% if slug == "tomorrow" %}aria-current="page"{% endif %}>Завтра</a>
    </nav>

    <header class="card">
      <div class="meta">Дата (UTC): {{ dateStr }}</div>
      <h1>Матчи: {{ slug }}</h1>
      <p class="meta">Последнее обновление: во время последней генерации страницы.</p>
    </header>

    <div class="card">
      <input id="q" placeholder="Поиск команды/лиги…" style="width:100%;padding:10px;border-radius:10px;border:1px solid var(--border);background:transparent;color:var(--text);" />
    </div>

    <main id="list"></main>

    <script type="application/json" id="matches-data">{{ matchesJson | safe }}</script>
    <script src="/assets/app.js"></script>
  </div>
</body>
</html>
```

#### `src/public/assets/app.js`

```js
const data = JSON.parse(document.getElementById('matches-data').textContent);
const input = document.getElementById('q');
const list = document.getElementById('list');

function fmt(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function render(items) {
  list.innerHTML = items.map(m => `
    <article class="card">
      <div class="meta">${m.game.name} • ${m.competition.league} • ${m.competition.tournament}</div>
      <h2 style="margin:8px 0">${m.title}${m.status === 'running' ? ' <span class="badge live">LIVE</span>' : ''}</h2>
      <div class="meta">Начало: ${fmt(m.startAt)} • Статус: ${m.status}</div>
      ${m.streamUrl ? `<p><a href="${m.streamUrl}" rel="nofollow">Смотреть трансляцию</a></p>` : ``}
    </article>
  `).join('');
}

input.addEventListener('input', () => {
  const q = input.value.trim().toLowerCase();
  const filtered = !q ? data : data.filter(m =>
    (m.title + ' ' + m.competition.league + ' ' + m.competition.tournament + ' ' + m.game.name)
      .toLowerCase()
      .includes(q)
  );
  render(filtered);
});

render(data);
```

#### Команды запуска локально

```bash
npm install
export PANDASCORE_TOKEN="YOUR_TOKEN"
npm run build
npm run serve
```

### CI/CD пример: GitHub Pages + GitHub Actions (cron + manual)

GitHub Pages — это статический хостинг, который берёт HTML/CSS/JS из репозитория и публикует. citeturn23search28  
Документация GitHub описывает настройку источника публикации и использование GitHub Actions для публикации. citeturn23search1turn23search9  
Cron‑триггер в Actions работает в UTC. citeturn23search4  

Пример `.github/workflows/pages.yml` (скелет):

```yaml
name: Build and Deploy

on:
  workflow_dispatch:
  schedule:
    - cron: "*/15 * * * *"  # каждые 15 минут (UTC)

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npm run build
        env:
          PANDASCORE_TOKEN: ${{ secrets.PANDASCORE_TOKEN }}
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/deploy-pages@v4
```

Механика хранения секретов и их использования в workflow описана в документации GitHub. citeturn34search0turn34search4  

### Список тестов и валидации

Опираться можно на официальные ожидания API по ошибкам/кодам и форматам:

- Проверка формата/таймзоны: даты ISO‑8601 UTC. citeturn27view0  
- Ошибки: 400/401/403/404/429 и формат JSON `{error,message}`. citeturn28view0  
- Пагинация: корректное чтение `Link`, max `page[size]=100`. citeturn9view0  

Рекомендуемый набор тестов (минимально достаточный для MVP):

| Категория | Тест | Что проверяет | Критерий прохождения |
|---|---|---|---|
| Unit | `isoDateUTC()` | правильный `YYYY-MM-DD` | стабильный snapshot |
| Unit | `parseLinkHeader()` | парсинг `rel="next"` | корректный next URL |
| Integration (mock) | пагинация | склейка страниц | итоговый размер массива |
| Integration (real token, optional) | `GET /matches?filter[begin_at]=...` | что фильтр рабочий | HTTP 200, JSON array |
| Schema/SEO | наличие `canonical`, `title`, `description` | минимум SEO в `<head>` | теги присутствуют |
| Schema.org | JSON‑LD валиден | наличие Organization + SportsEvent | валидатор schema.org/Google без критических ошибок |
| Build | `npm run build` | генерит три страницы | `dist/*/index.html` существуют |

### Чек‑лист этапов с оценкой времени и критериями приёмки

Оценка дана для одного разработчика, MVP‑фокус (без «архива дат» и без сложных фич).

| Этап | Содержание | Оценка | Критерии приёмки |
|---|---|---:|---|
| Проектный скелет | repo, зависимости, шаблоны, ассеты | 0.5 дня | `npm run build` создаёт `dist/` |
| API клиент | auth, запросы, пагинация, базовая обработка ошибок | 0.5–1 день | Получаем массив матчей; корректно обрабатываем 4xx/5xx citeturn28view0 |
| Нормализация данных | ViewModel, сортировки, группировки | 0.5 дня | UI не падает на `null` полях citeturn27view0 |
| Рендер 3 страниц | роуты, навигация, карточки матчей | 0.5 дня | `/yesterday/ /today/ /tomorrow/` корректны |
| SEO + Schema.org | meta, canonical, OG, JSON‑LD | 0.5–1 день | canonical в `<head>` citeturn25search9; валидный JSON‑LD citeturn21search0turn22search4turn21search5 |
| Кэширование | disk cache, TTL | 0.5 дня | повторный билд меньше запросов; не превышаем лимиты citeturn11view0turn9view0 |
| CI/CD деплой | GitHub Pages/Netlify/Vercel, secrets, cron | 0.5–1 день | деплой работает; есть ручной run и/или cron citeturn23search31turn23search4turn23search1 |

Суммарно: **~3–6 рабочих дней** до «крепкого прототипа» (в зависимости от глубины SEO/валидации и выбранного хостинга).

---
# Деплой на прод

Рассчитано на слабый VPS: в Docker живут только `db` и `api`, фронтенд —
статические файлы, которые отдаёт nginx, установленный прямо на хост (не в
контейнере). Это экономит память/CPU на лишнем контейнере и на сборке
фронтенда на самом сервере (её лучше вообще не делать на слабой машине —
см. шаг 3).

## 0. Что нужно на сервере

- Docker + Docker Compose plugin.
- nginx (пакет из дистрибутива, не контейнер).
- certbot + плагин `certbot-nginx` (для TLS).
- Node.js **не обязателен** на сервере — фронтенд собирается заранее в другом
  месте (см. шаг 3).

## 1. Клонировать репозиторий

```bash
git clone git@github.com:funtiknax13/dx.git /srv/dh/app
cd /srv/dh/app
```

## 2. Секреты

```bash
cp .env.example .env
```

Заполнить `.env` (лежит в корне репозитория, рядом с `docker-compose.prod.yml`):

- `SECRET_KEY`, `ADMIN_SECRET_KEY` — сгенерировать отдельно каждый:
  `openssl rand -hex 32`
- `POSTGRES_PASSWORD` — любой длинный случайный пароль.
- `FRONTEND_ORIGIN` — реальный домен с `https://`.
- `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD` — с этим войдёшь как
  первый admin при первом старте.
- `SMTP_*` — данные Яндекс.Почты (см. комментарий в `backend/.env.example`,
  там же инструкция про пароль приложения).
- `MEDIA_HOST_PATH` — куда на диске сервера будут физически лежать
  загруженные фото/GPX/FIT, по умолчанию `/srv/dh/media`.

Приложение **откажется стартовать**, если `ENVIRONMENT=production`, а
`SECRET_KEY`/`ADMIN_SECRET_KEY`/`INITIAL_ADMIN_PASSWORD` остались дефолтными
или короче 32 символов — это защита от “забыл поменять”, а не баг, если
увидишь ошибку при первом запуске — значит `.env` не до конца заполнен.

Создать директорию для медиа заранее:

```bash
mkdir -p /srv/dh/media
```

## 3. Собрать фронтенд (не на сервере, если он слабый)

Собери `frontend/dist` на своей машине или в CI (см.
`.github/workflows/ci.yml` — можно добавить туда джобу, которая по тегу
собирает и кладёт архив в Release) и залей на сервер:

```bash
# локально
cd frontend
npm ci
npm run build   # берёт frontend/.env.production — относительные /api/v1, /media

# на сервере
mkdir -p /srv/dh/frontend-dist
rsync -avz --delete dist/ user@server:/srv/dh/frontend-dist/
```

⚠️ Собирай из чистого клона/CI, не из dev-контейнера `frontend`
(`docker-compose.yml`) — там `VITE_API_URL`/`VITE_MEDIA_URL` уже
проставлены в окружении контейнера (`frontend/.env`, абсолютный
`http://localhost:8000`), а такие переменные у Vite имеют приоритет над
`.env.production` и молча запекутся в сборку вместо относительных путей.

Если сервер всё же достаточно живой, чтобы собрать фронтенд на месте —
просто `npm ci && npm run build` в `/srv/dh/app/frontend` и скопировать
`dist/` в `/srv/dh/frontend-dist`.

## 4. Поднять backend + БД

```bash
cd /srv/dh/app
docker compose -f docker-compose.prod.yml up -d --build
```

Applies миграции автоматически при старте (`alembic upgrade head` — часть
команды контейнера `api`). API слушает только `127.0.0.1:8000` — наружу не
торчит, доступ только через nginx на хосте.

## 5. Настроить nginx на хосте

```bash
sudo cp nginx/dh.conf /etc/nginx/sites-available/dh
sudo ln -s /etc/nginx/sites-available/dh /etc/nginx/sites-enabled/dh
```

В скопированном файле заменить:
- `CHANGE_ME.example` → реальный домен (в обоих `server` блоках).
- `/srv/dh/frontend-dist` и `/srv/dh/media/` → пути с шага 2–3, если
  выбрал другие.

Первый запуск — до выпуска сертификата TLS-блок (`listen 443`) ещё не
сможет стартовать (нет файлов сертификата). Порядок:

```bash
# 1. временно закомментировать server-блок с listen 443 в /etc/nginx/sites-available/dh
sudo nginx -t && sudo systemctl reload nginx

# 2. получить сертификат (certbot сам допишет location для ACME-challenge,
#    либо используется /.well-known/acme-challenge/ из конфига выше)
sudo certbot --nginx -d CHANGE_ME.example

# 3. раскомментировать блок с listen 443 обратно, certbot обычно делает это сам
sudo nginx -t && sudo systemctl reload nginx
```

Certbot настраивает автопродление сам (systemd timer), ничего дополнительно
делать не нужно.

## 6. Проверка

- `curl -I https://твой-домен/` → 200, отдаёт `index.html`.
- `curl https://твой-домен/api/v1/events` → JSON.
- Залогиниться как `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD` из `.env`,
  зайти в `/admin-tools`, сразу поменять свой пароль через `/admin-tools`
  или SQLAdmin.

## 7. Обновление после изменений в коде

```bash
cd /srv/dh/app
git pull
docker compose -f docker-compose.prod.yml up -d --build   # пересобирает и перезапускает api
# при изменениях фронтенда — повторить шаг 3 (собрать и rsync dist/)
```

`docker compose restart` **не** подхватывает изменения `.env` — если менял
секреты, нужно `docker compose -f docker-compose.prod.yml up -d --force-recreate api`.

## 8. Бэкап БД

Не автоматизировано — на первое время вручную:

```bash
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U dh dh | gzip > "backup-$(date +%F).sql.gz"
```

Стоит повесить на cron и складывать куда-то за пределы того же диска.

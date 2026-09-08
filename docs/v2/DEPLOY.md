# Deploying the worker and beat processes (Phase 7.1)

`railway.json` configures exactly one Railway service - it's a per-service
file, not a multi-process manifest, so it stays as the **api** service's
config unchanged (gunicorn, `/health` healthcheck). Worker and beat aren't
expressed in that file; they're two more Railway services in the same
project, pointing at this same repo and Dockerfile, each with its start
command overridden.

## 1. Add a Redis plugin to the project

Railway's dashboard → **New** → **Database** → **Add Redis**. This
provisions a `REDIS_URL` environment variable Railway injects automatically
into every service in the project that references it - copy that value (or
reference the variable directly) as this project's `REDIS_URL` for all
three services below. `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` don't
need to be set explicitly - they default to `REDIS_URL`'s db 1 / db 2 (see
`config/settings/base.py`).

## 2. api (existing service, `railway.json`)

No changes. Still `gunicorn config.wsgi:application`, still healthchecked
on `/health` - which now also reports `redis` and `celery`, so a Redis
outage or a fully-down worker fleet correctly fails Railway's own
healthcheck instead of only checking the database.

## 3. worker (new service)

- **Source**: same repo, same Dockerfile as `api`.
- **Custom Start Command** (Railway service settings, overrides the
  Dockerfile's `CMD`): `celery -A config worker --loglevel=info`
- **Environment**: same as `api` (`DATABASE_URL`, `REDIS_URL`,
  `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, etc. - see `.env.example`). No
  `PORT`/healthcheck needed; Celery workers aren't HTTP services.
- **Restart policy**: `ON_FAILURE`, same as `api` - a worker crash should
  restart automatically, same reasoning as `CELERY_TASK_ACKS_LATE=True`
  (a task safely redelivers to whichever worker comes back up).

## 4. beat (new service)

- **Source**: same repo, same Dockerfile.
- **Custom Start Command**: `celery -A config beat --loglevel=info`
- **Environment**: same as `worker`.
- **Exactly one beat instance in the whole project.** Beat schedules
  periodic tasks (`sweep_low_stock` every 15 minutes, `reconcile_ledger`
  nightly - see `CELERY_BEAT_SCHEDULE` in `config/settings/base.py`); two
  running beat processes would each independently schedule the same tasks,
  duplicating every periodic run. Railway won't prevent this by itself -
  don't scale this service beyond 1 replica.

## New env vars introduced since the FastAPI-vs-Django README section was
written (all documented with defaults/derivation in `.env.example`)

| Var | Required? | Default |
|---|---|---|
| `REDIS_URL` | Yes (Phase 1) | none - Railway's Redis plugin provides it |
| `CELERY_BROKER_URL` | No (Phase 4) | derived from `REDIS_URL`, db 1 |
| `CELERY_RESULT_BACKEND` | No (Phase 4) | derived from `REDIS_URL`, db 2 |
| `INVENTORY_LOCKING_ENABLED` | No (Phase 6) | `true` - refused to be `false` outside `DEBUG` by `apps/core/checks.py`; never set this in a real deployment |

## Verifying after deploy

`GET /health` on the **api** service should report
`{"status": "ok", "checks": {"database": "ok", "redis": "ok", "celery": "ok"}}`
- `celery: ok` specifically requires the **worker** service to be up and
  reachable (it pings the worker via `celery_app.control.inspect`), so a
  green `/health` is evidence all three services are actually running, not
  just the two Railway would otherwise show as "deployed."

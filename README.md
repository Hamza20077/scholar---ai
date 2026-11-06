# Scholar AI

Scholar AI is a private, account-based study workspace for university students. It accepts text-based PDF notes, indexes extracted passages by page, answers questions with source markers, and creates saved summaries and multiple-choice quizzes.

## What works

- Account registration, sign-in, password validation, and per-user document ownership.
- PDF upload with file signature checking, size and page limits, duplicate detection, encrypted-PDF rejection, and clear handling for scanned documents that need OCR.
- Page-aware text extraction, overlapping text chunks, and lexical relevance retrieval.
- Source-grounded Q&A with page citations, generated summaries, and validated five-question MCQs through the OpenAI Chat Completions API.
- Per-account limits for document count, total private storage, and paid AI requests.
- Saved questions, summaries, and quizzes; practice quiz scoring runs in the browser from the generated answer key.
- User-scoped delete actions, CSRF-protected forms, private media storage, secure cookie settings, WhiteNoise static files, PostgreSQL deployment configuration, Docker Compose, and a health endpoint.
- In-app account deletion, a privacy notice, and an installable Progressive Web App (PWA).

The application does not pretend to generate AI answers when no provider key is configured. Uploading and retrieval still work; generation actions show a configuration error.

## Technology

- Python 3.12+
- Django 6.1
- PostgreSQL in deployment; SQLite for local development and tests
- Private Vercel Blob storage for deployed PDF uploads; filesystem storage locally
- OpenAI Python SDK for AI generation
- pypdf for PDF text extraction
- Gunicorn and WhiteNoise for serving
- Vercel deployment without Docker; Docker Compose remains an alternative

## Run locally on Windows

Python 3.12 or newer is required. PowerShell commands:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set a long random `SECRET_KEY`. For local HTTP development, keep `DEBUG=true`, `SECURE_SSL_REDIRECT=false`, and `SECURE_HSTS_SECONDS=0`. Set `OPENAI_API_KEY` to enable answers, summaries, and quizzes. The app can be started without that key, but those generation features remain disabled with an explicit message.

Then initialize and start the app:

```powershell
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and create an account. Generated documents and database files stay in the local `media/` and `db.sqlite3` paths by default.

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | Production | Required Django signing key. Keep private and rotate only with an intentional session invalidation. |
| `DEBUG` | No | Defaults to false. Enable only for local development. |
| `ALLOWED_HOSTS` | Production | Comma-separated hostnames served by this deployment. |
| `DATABASE_URL` | Production | Persistent PostgreSQL URL. SQLite is permitted only with `DEBUG=true`; production startup fails without this setting. |
| `DATA_DIR` | No | Writable directory for local SQLite and private uploads when `MEDIA_ROOT` is not set. Defaults to the project directory. |
| `OPENAI_API_KEY` | For generation | API credential used when a signed-in student requests an answer, summary, or quiz. Extracted note excerpts are sent to that provider for that request. |
| `OPENAI_MODEL` | No | OpenAI chat model; defaults to `gpt-4.1-mini`. |
| `SUPPORT_EMAIL` | Public deployment | Contact address shown on the privacy page. |
| `BLOB_STORE_ID` | Vercel | Added by connecting a private Vercel Blob store to the project. The app uses the Python SDK with Vercel OIDC credentials. |
| `BLOB_READ_WRITE_TOKEN` | Outside Vercel | Read/write token when using the private Blob backend outside Vercel. Keep it in a secret manager. |
| `MAX_UPLOAD_MB` | No | Per-file upload limit, defaults to 20 MB. |
| `MAX_DOCUMENTS_PER_USER` | No | Maximum PDF count per account, defaults to 100. |
| `MAX_TOTAL_STORAGE_MB_PER_USER` | No | Private upload storage quota per account, defaults to 500 MB. |
| `AI_REQUESTS_PER_HOUR` | No | Maximum billable generation requests per account per hour, defaults to 30. |
| `MEDIA_ROOT` | No | Private local path for uploaded PDFs. Use persistent storage and backups in deployment. |
| `SECURE_SSL_REDIRECT` | Production | Redirect HTTP to HTTPS when the app is behind a TLS-terminating proxy. |
| `SECURE_HSTS_SECONDS` | Production | HSTS duration. Set only when HTTPS is correctly configured for the full host. |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | No | Extend HSTS to subdomains only when every subdomain is HTTPS-capable. Defaults to false. |
| `SECURE_HSTS_PRELOAD` | No | Enable browser preload behavior only after domain-wide HTTPS and preload requirements are met. Defaults to false. |
| `CSRF_TRUSTED_ORIGINS` | If needed | Comma-separated full HTTPS origins when the app is served through a custom proxy/domain. |
| `PORT` | No | Host port used by Docker Compose, defaults to 8000. |
| `POSTGRES_PASSWORD` | Docker Compose | Password for the Compose PostgreSQL service. |

## Run tests and checks

```powershell
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
```

The Django test suite covers authentication boundaries, account ownership, upload/indexing, duplicate handling, source retrieval, saved output, and malformed provider responses. It does not call OpenAI or require an API key.

## Deploy to Vercel without Docker

Vercel detects this Django project from `manage.py` and `WSGI_APPLICATION`; `.python-version` pins the runtime. The app uses PostgreSQL for durable records and a private Vercel Blob store for PDF uploads. The code refuses to start on Vercel until a Blob store is connected, and refuses production startup without `DATABASE_URL` and `SECRET_KEY`.

1. Import `Hamza20077/scholar---ai` in the Vercel dashboard and keep the root directory at the repository root.
2. In the project Storage tab, add a PostgreSQL provider such as Neon and connect it to Production and Preview. Confirm that the integration supplies `DATABASE_URL`.
3. Add a Vercel Blob store with **Private** access and connect it to Production and Preview. Vercel injects `BLOB_STORE_ID` and its short-lived OIDC credentials; do not create a public store for course PDFs.
4. Configure `SECRET_KEY`, `SUPPORT_EMAIL`, and `OPENAI_API_KEY` in Vercel's encrypted environment-variable settings. Also set `ALLOWED_HOSTS=.vercel.app,your-domain.example` and `CSRF_TRUSTED_ORIGINS=https://*.vercel.app,https://your-domain.example`. Use an active OpenAI API key from the provider account that will pay for generation requests.
5. Deploy a Preview first. After the database and Blob store are connected, run `python manage.py migrate --noinput` once with the Vercel Production database credentials, then verify signup, login, PDF upload, account deletion, and health checks on Preview.
6. Deploy Production after the privacy contact and policy have been reviewed. Configure a custom domain and verify HTTPS before onboarding users.

Vercel's Django build automatically runs static collection when `STATIC_ROOT` is configured. The SDK stores PDFs privately, uses short-lived Vercel OIDC credentials, and never returns public blob URLs. Preview and Production need separate database and Blob environments so preview uploads and accounts stay isolated.

The Docker Compose deployment below is an alternative for a persistent host. Vercel's temporary function filesystem must never be used for SQLite or local uploads.

## Deploy with Docker Compose

1. Copy `.env.example` to `.env` and set a unique `SECRET_KEY`, strong `POSTGRES_PASSWORD`, public `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`.
2. Configure the HTTPS reverse proxy in front of port 8000. Set `SECURE_SSL_REDIRECT=true` and `SECURE_HSTS_SECONDS=31536000` only after TLS is verified. Compose sets `DEBUG=false`.
3. Set a valid `OPENAI_API_KEY` if generation is required, then build and start:

```sh
docker compose up --build -d
```

PostgreSQL data and uploaded PDFs use named volumes. Back up both volumes, restrict access to secrets, and monitor `/healthz/`.

For a different non-serverless host, run `python manage.py migrate --noinput`, `python manage.py collectstatic --noinput`, and start `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`. The host must provide PostgreSQL, HTTPS, persistent private PDF storage, request-size limits, backups, and monitoring.

## Security and data handling

- All study pages require sign-in. Querysets and destructive actions are scoped to the authenticated owner.
- Django password hashing, CSRF middleware, security headers, secure production cookies, host validation, and upload checks are enabled.
- Uploaded files are not served from a public media URL. Do not mount `MEDIA_ROOT` as a public static directory.
- Document excerpts leave the application only when a student requests AI generation. They are sent to the configured OpenAI API account. Do not upload material you lack permission to process.
- Use HTTPS and a secret manager for production. Do not commit `.env`, API keys, database credentials, or user uploads.

## Known limitations

- The app handles text PDFs only. Scanned PDFs need OCR before upload; OCR is not implemented.
- Retrieval uses token overlap and inverse document frequency, not a vector database or embedding model. It is explainable and works without embedding infrastructure, but relevance can be weaker for paraphrases.
- Summary and quiz prompts use at most the first 24 indexed chunks of one selected document. Larger notes are not summarized hierarchically, so later pages can be omitted.
- AI outputs can be wrong. Citations identify the passages supplied to the model, not proof that every generated statement is accurate.
- The app has no email verification, password reset delivery, organization/team roles, IP-based login/signup rate limiting, or audit log. A public deployment should add these policies and controls before onboarding users broadly.
- Docker image build and runtime behavior depend on the deployment host; validate the exact proxy, storage, backup, and database setup before launch.
- Vercel Blob storage has been implemented and unit-tested, but the remote private store, PostgreSQL service, migrations, and live deployment still need to be provisioned and verified in the account.
- The PWA can be installed from a supported browser, but there are no native iOS/Android packages or store listings. Apple review expects meaningful app functionality beyond a repackaged website, and store enrollment, identity verification, device testing, app metadata, and review are still required.
- Privacy notice copy needs an operator contact address and review against the operator's actual jurisdiction, retention periods, and provider terms before public launch.

## License

This project is provided under the MIT License. See [LICENSE](LICENSE).

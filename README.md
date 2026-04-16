# CloakBrowser local setup

This workspace is managed with `uv` and targets Python 3.13+.

## Setup

```powershell
uv python install 3.13
uv python pin 3.13
uv sync
uv run python -m cloakbrowser install
uv run python -m cloakbrowser info
```

If the binary download is interrupted, rerun `uv run python -m cloakbrowser install`.

## Smoke tests

```powershell
uv run python smoke_test.py --mode basic
uv run python smoke_test.py --mode mobile
uv run python smoke_test.py --mode persistent
```

The smoke tests default to a local `data:` page, so they do not require external network access.

## iios.fun sign-in script

Set credentials in your environment, then run a dry-run first:

```powershell
$env:IIOS_USERNAME="your-email@example.com"
$env:IIOS_PASSWORD="your-password"
uv run python iios_signin.py --dry-run
```

`--dry-run` skips the final `立即签到` click, but it may still perform a real login and persist session cookies in the configured profile directory.

When dry-run confirms that login works and the `立即签到` button is found, run the real flow:

```powershell
uv run python iios_signin.py --no-dry-run
```

For troubleshooting, you can also enable success screenshots:

```powershell
uv run python iios_signin.py --dry-run --success-screenshot
```

Failure screenshots are saved automatically under `data/artifacts/iios.fun/` by default. These images may contain account/session-visible data, so treat them as sensitive local files. The same sensitivity warning applies to optional success screenshots.

## Docker

This project can run on top of the official CloakBrowser container image.

### Build

```powershell
docker build -t iios-cloak-signin .
```

### Dry-run with Docker

```powershell
docker run --rm `
  --env-file .env `
  -v ${PWD}/data/profile:/app/data/profile `
  -v ${PWD}/data/artifacts:/app/data/artifacts `
  iios-cloak-signin
```

### Real sign-in with Docker

```powershell
docker run --rm `
  --env-file .env `
  -v ${PWD}/data/profile:/app/data/profile `
  -v ${PWD}/data/artifacts:/app/data/artifacts `
  iios-cloak-signin --no-dry-run
```

### Docker Compose

Create a local `.env` file from `.env.example`, then run:

```powershell
docker compose run --rm iios-signin
```

For a real sign-in run:

```powershell
docker compose run --rm iios-signin --no-dry-run
```

The profile directory and artifact directory are mounted from the host so session state and screenshots survive container replacement.

## GitHub Actions

You can also run the sign-in script from GitHub Actions without Docker.

### Required repository secrets

- `IIOS_USERNAME`
- `IIOS_PASSWORD`
- `CLOAK_FINGERPRINT_SEED` (strongly recommended, for a stable fingerprint and more repeatable runs)

### Workflow

The workflow file is stored at `.github/workflows/signin.yml` and supports:

- manual trigger via `workflow_dispatch`
- scheduled trigger via cron

It installs Python 3.13, installs `uv`, syncs dependencies, downloads the CloakBrowser binary, and runs:

```powershell
uv run python iios_signin.py --no-dry-run
```

The workflow uploads the contents of `data/artifacts/` as workflow artifacts. Those uploaded files may contain screenshots or other run artifacts with account/session-visible content, so treat them as sensitive.

Because GitHub-hosted runners are ephemeral, do **not** rely on `data/profile/` for long-lived persistent sessions there. The workflow should be treated as an independent login run each time.

## Notes

- `smoke_test.py` only validates CloakBrowser itself.
- `iios_signin.py` uses a persistent CloakBrowser profile and reads credentials from environment variables.
- `iios_signin.py` stores reusable session state under the profile directory; treat that directory as sensitive local data.
- `iios_signin.py` now emits structured JSON logs to stdout and saves failure screenshots locally.
- `Dockerfile` is based on the official `cloakhq/cloakbrowser` image instead of building a browser runtime from scratch.
- `.env.example` includes both CloakBrowser settings and iios.fun runtime variables. Do not commit real secrets.

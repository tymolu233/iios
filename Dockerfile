FROM cloakhq/cloakbrowser:latest

WORKDIR /app

COPY pyproject.toml uv.lock /app/

RUN python -m pip install --no-cache-dir uv && uv sync --locked --no-dev

COPY iios_signin.py smoke_test.py README.local.md .env.example /app/

ENV CLOAK_HEADLESS=true \
    IIOS_PROFILE_DIR=/app/data/profile/iios.fun \
    IIOS_ARTIFACT_DIR=/app/data/artifacts/iios.fun \
    IIOS_LOG_LEVEL=info \
    IIOS_SUCCESS_SCREENSHOT=false

RUN mkdir -p /app/data/profile/iios.fun /app/data/artifacts/iios.fun

ENTRYPOINT ["python", "/app/iios_signin.py"]
CMD ["--dry-run"]

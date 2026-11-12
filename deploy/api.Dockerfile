FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.runtime.lock ./requirements.runtime.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.runtime.lock \
    && groupadd --gid 10001 recruitflow \
    && useradd --uid 10001 --gid recruitflow --no-create-home recruitflow \
    && mkdir /data /app/.secrets && chown -R recruitflow:recruitflow /data /app/.secrets
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts ./scripts
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "scripts.operations.serve"]

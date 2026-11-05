FROM python:3.12-slim-trixie AS common
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BUNDLE_DIR=/opt/bundle PROCESSOR_DIR=/opt/processor
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates fontconfig fonts-culmus fonts-linuxlibertine fonts-sil-ezra fonts-freefont-otf fonts-dejavu-core fonts-dejavu-extra fonts-liberation fonts-noto-core fonts-crosextra-carlito fonts-crosextra-caladea && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.12.21
WORKDIR /opt/infra
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN python scripts/fetch_sources.py /opt/processor && \
    uv export --project /opt/processor --frozen --no-dev --no-emit-project --format requirements-txt --output-file /tmp/processor-requirements.txt && \
    .venv/bin/python scripts/merge_requirements.py /tmp/processor-requirements.txt /tmp/merged-requirements.txt && \
    uv pip install --python .venv/bin/python --no-deps -r /tmp/merged-requirements.txt && \
    uv pip install --python .venv/bin/python --no-deps -e /opt/processor && \
    uv pip install --python .venv/bin/python --no-deps -e . && uv pip check --python .venv/bin/python
ENV PATH="/opt/infra/.venv/bin:$PATH"
RUN python scripts/install_fonts.py
RUN python scripts/bundle.py && python -m opensiddur.exporter.refdb
RUN useradd --uid 10001 --create-home builder && chmod -R a+rX /opt/processor /opt/bundle
USER builder
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "opensiddur_infra.api:production_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
FROM common AS worker
USER root
RUN apt-get update && apt-get install -y --no-install-recommends texlive-luatex texlive-latex-extra texlive-bibtex-extra texlive-humanities texlive-lang-other texlive-lang-european texlive-lang-arabic texlive-fonts-recommended && rm -rf /var/lib/apt/lists/* && mktexlsr && fc-cache -f
RUN TEXMFCACHE=/usr/share/opensiddur-tex-cache luaotfload-tool --update --force && chmod -R a+rX /usr/share/opensiddur-tex-cache
RUN python scripts/notices.py
USER builder
CMD ["python", "-m", "opensiddur_infra.worker"]
FROM worker AS api
CMD ["python", "-m", "uvicorn", "opensiddur_infra.api:production_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]

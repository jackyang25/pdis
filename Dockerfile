# Backend image for the PDIS FastAPI gateway.
#
# Uses Docker (rather than a platform's native Python runtime) for one reason:
# it lets us install LibreOffice, which Chunker uses to rasterize uncommon
# EMF/WMF/SVG figures and render PPTX slides into portable PNG image assets.
# Everything else is a standard slim-Python app.
# The converter is self-gating, so the app also runs fine without LibreOffice.
FROM python:3.11-slim

# Draw handles vector figures; Impress handles PPTX rendering. Installing only
# those modules keeps the image smaller than the full office suite.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-core libreoffice-draw libreoffice-impress fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Installed from the Python index rather than copied from `ghcr.io/astral-sh/uv`,
# so this build reaches one package index instead of a second container registry
# as well. Version-pinned either way: the resolver is part of what makes a build
# reproducible.
RUN pip install --no-cache-dir uv==0.12.8

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # The base image already provides 3.11 and `requires-python` pins that
    # range. Downloading another interpreter would mean the image runs a
    # different Python than the one it declares.
    UV_PYTHON_DOWNLOADS=never

# Dependencies resolve from the committed lockfile, in their own layer so a
# source-only change does not reinstall them. `--frozen` fails the build if
# uv.lock is out of date with pyproject.toml, which is the property that makes
# two builds of one commit produce the same dependency set.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# PORT is supplied by the platform. Nomad allocates ports dynamically and
# exposes them per port label, so the jobspec must set PORT explicitly from its
# own label; the default below is for local `docker run` only, and silently
# serving on 8000 when the platform expected another port is the failure this
# comment exists to prevent.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

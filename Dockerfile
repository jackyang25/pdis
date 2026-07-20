# Backend image for the PDIS FastAPI gateway.
#
# Uses Docker (not Render's native Python runtime) for one reason: it lets us
# install LibreOffice, which Chunker uses to rasterize uncommon EMF/WMF/SVG
# figures and render PPTX slides into portable PNG image assets. Everything
# else is a standard slim-Python app.
# The converter is self-gating, so the app also runs fine without LibreOffice.
FROM python:3.11-slim

# Draw handles vector figures; Impress handles PPTX rendering. Installing only
# those modules keeps the image smaller than the full office suite.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-core libreoffice-draw libreoffice-impress fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render provides $PORT at runtime.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

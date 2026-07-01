# Backend image for the PDIS FastAPI gateway.
#
# Uses Docker (not Render's native Python runtime) for one reason: it lets us
# install LibreOffice, which the chunker's image describer shells out to in
# order to rasterize EMF/WMF vector figures (common in pasted IPDP diagrams) so
# the vision model can read them. Everything else is a standard slim-Python app.
# The converter is self-gating, so the app also runs fine without LibreOffice.
FROM python:3.11-slim

# libreoffice-core + libreoffice-draw is enough to rasterize EMF/WMF and is far
# smaller than the full office suite. --no-install-recommends trims it further.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-core libreoffice-draw \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render provides $PORT at runtime.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

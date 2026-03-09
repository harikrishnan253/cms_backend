FROM python:3.10-slim

WORKDIR /app

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM DEPENDENCIES
# ─────────────────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # ── C build tools (psycopg2, lxml native extensions) ──────────────────
    gcc \
    make \
    libpq-dev \
    # ── Network tools (curl for healthchecks / cpanm deps) ────────────────
    curl \
    git \
    # ── XML / XSLT (lxml Python + XML::LibXML Perl) ───────────────────────
    libxml2-dev \
    libxslt-dev \
    libxml2 \
    # ── Compression (Archive::Zip Perl module) ─────────────────────────────
    zlib1g-dev \
    # ── LibreOffice Writer — bias_scanner.py spawns 'soffice' ─────────────
    # converts DOCX → PDF for accurate page number detection
    libreoffice-writer \
    libreoffice-java-common \
    # ── Java Runtime — Word2XML_Books.pl runs 'java -jar saxon.jar' ────────
    # Saxon performs the XSLT transformation (Era_Word2XML.xsl)
    default-jre \
    # ── Perl — wordtoxml pipeline scripts ─────────────────────────────────
    # Word2XML_Books.pl, Era_Conversion.pl, Era_WmlCleanup.pl
    perl \
    cpanminus \
    && rm -rf /var/lib/apt/lists/*

# ─────────────────────────────────────────────────────────────────────────────
# PERL CPAN MODULES  (wordtoxml pipeline)
#
# Word2XML_Books.pl imports:
#   Archive::Zip            — reads the .docx zip archive
#   File::Copy::Recursive   — recursive directory copy/delete
#   File::HomeDir           — resolves home directory paths
#   HTTP::Tiny              — lightweight HTTP client
#   List::MoreUtils         — minmax utility
#   String::Substitution    — sub_modify helper
#   Try::Tiny               — try/catch blocks
#   XML::LibXML             — DTD validation of output XML
# ─────────────────────────────────────────────────────────────────────────────
RUN cpanm --notest \
    Archive::Zip \
    File::Copy::Recursive \
    File::HomeDir \
    HTTP::Tiny \
    List::MoreUtils \
    String::Substitution \
    Try::Tiny \
    XML::LibXML

# ─────────────────────────────────────────────────────────────────────────────
# PYTHON DEPENDENCIES
# Install before copying app code so Docker layer cache is reused on code changes
# ─────────────────────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION CODE
# ─────────────────────────────────────────────────────────────────────────────
COPY . .

# Ensure runtime directories exist (volumes will overlay these in compose)
RUN mkdir -p uploads outputs data temp_reports

# ─────────────────────────────────────────────────────────────────────────────
# RUNTIME
# ─────────────────────────────────────────────────────────────────────────────
EXPOSE 8000

# 4 Gunicorn workers with async Uvicorn worker class
# --timeout 300 → allow long-running processing requests (reference validation, bias scan, XML)
CMD ["gunicorn", \
    "--workers", "4", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--timeout", "300", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "app.main:app"]

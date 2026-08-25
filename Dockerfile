# earthscope-positions — see README.md for CLI/web-UI usage.
#
# Build:  ./es-pos-docker.sh build       (see that script for options)
# Run:    ./es-pos-docker.sh run         (see that script for options)
#
# The image copies the repo (minus data/, see .dockerignore), builds a
# virtualenv, and installs the package into it. It does NOT bake in any
# data or credentials — those are bind-mounted at `docker run` time so they
# persist on the host across container runs (see es-pos-docker.sh's `run`).
FROM python:3.13-slim

# uv — a much faster (Rust-based) drop-in replacement for pip/venv, used only
# for this build; nothing at runtime depends on it. Copied in as a static
# binary (Astral's documented Docker pattern) rather than pip-installed, so it
# doesn't need Python/pip to already exist first.
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv

# System packages needed to build/run the Python dependencies:
#   git             — setuptools_scm (this package's version comes from git
#                      tags/history) needs the real `git` CLI at build time.
#   build-essential — C toolchain, in case any dependency has no prebuilt
#                      wheel for this platform and falls back to a source build.
#   librdkafka-dev  — confluent-kafka's native dependency (used by `es-pos
#                      replay`); most platforms get a wheel with this already
#                      bundled, but this covers the platforms that don't.
#   ca-certificates — TLS trust store for HTTPS calls to the EarthScope API.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        librdkafka-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the repo. data/ is excluded via .dockerignore — the image never bakes
# in local data; it's bind-mounted in at runtime instead (see es-pos-docker.sh's
# `run`). spa/spaBuild (the pre-built SPA the webserver serves) IS copied —
# it's committed to the repo, not built here.
COPY . .

RUN uv venv venv \
    && uv pip install --python venv/bin/python --no-cache "."

# The data directory is baked into the image at a fixed path and bind-mounted
# from the host at run time (es-pos-docker.sh resolves the host side from
# ~/.earthscope-positions.json).  /data rather than /app/data so the data is not
# tangled up with the code install, and so the container still has a valid,
# writable path when run with no mount at all.
#
# Setting it as an ENV rather than on the server's command line also covers
# `es-pos cli` shells inside the container.  There is no --data-directory flag.
ENV ES_POS_DATA_DIRECTORY=/data
RUN mkdir -p /data

# Must match the ES_POS_PORT default in es-pos-docker.sh's `entrypoint` command.
EXPOSE 8000

RUN chmod +x es-pos-docker.sh
ENTRYPOINT ["./es-pos-docker.sh", "entrypoint"]

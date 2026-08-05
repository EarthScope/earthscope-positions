#!/usr/bin/env bash
# es-pos-docker.sh — build, run, and (inside the container) entrypoint logic
# for the earthscope-positions Docker image, all in one script.
#
# Usage:
#   ./es-pos-docker.sh <command> [options]
#
# Run with no arguments (or `help`) to see full usage.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

cmd_help() {
    cat <<'EOF'
es-pos-docker.sh — build and run the earthscope-positions Docker image.

Usage:
  ./es-pos-docker.sh build [--tag IMAGE_TAG]
  ./es-pos-docker.sh login [--earthscope-dir PATH] [--profile NAME] [--image TAG]
  ./es-pos-docker.sh run   [--data-dir PATH] [--earthscope-dir PATH] [--profile NAME]
                           [--port N] [--hostname NAME] [--image TAG] [--name NAME]
                           [--detach]
  ./es-pos-docker.sh cli   [--data-dir PATH] [--earthscope-dir PATH] [--profile NAME]
                           [--image TAG] [--name NAME]
  ./es-pos-docker.sh help

Commands:
  build   Build the Docker image.
            --tag IMAGE_TAG        Image name:tag to build (default: earthscope-positions:latest)

  login   Log into EarthScope *inside* Docker, for a fresh --earthscope-dir
          that has no credentials yet (e.g. before the first `run` on a new
          machine, or to add a second profile alongside an existing one).
          Runs `es user login` in the container and exits — it does not start
          the web server. The container can't open a browser for you, but
          `es user login` already handles that: it performs the Device Code
          flow (prints a URL + code to visit from any browser) whenever the
          profile isn't configured for the redirect-based flow, so this works
          fine non-interactively. Always runs --rm -it (needs your terminal
          to show the login URL/code), named earthscope-positions-login.
            --earthscope-dir PATH  Host directory mounted at /root/.earthscope
                                    (default: ~/.earthscope — point this at an
                                    empty directory for a genuinely fresh login)
            --profile NAME         Named profile to log into (default: "default").
                                    Passed to `run` too, so the web server reads
                                    the same profile's tokens.
            --image TAG            Image to run (default: earthscope-positions:latest)

  run     Run the web server in Docker. Mounts a data directory (so downloaded
          data persists across container runs) and ~/.earthscope (so `es user
          login` done on the host, or via `login` above, is visible inside the
          container — no separate login needed at `run` time).
            --data-dir PATH        Host directory mounted at /app/data, the default
                                    data directory (default: ./data next to this script)
            --earthscope-dir PATH  Host directory mounted at /root/.earthscope, holding
                                    EarthScope login credentials (default: ~/.earthscope)
            --profile NAME         Named profile to read credentials from
                                    (default: "default" — the profile `es user
                                    login` uses when no --profile is given)
            --port N               Port to publish on the host and inside the container
                                    (default: 8000)
            --hostname NAME        Hostname used in UI callback URLs, e.g. the Replay
                                    curl commands (default: localhost — correct for a
                                    Mac, since Docker Desktop maps localhost:PORT on the
                                    host straight through to the container's PORT)
            --image TAG            Image to run (default: earthscope-positions:latest)
            --name NAME            Container name (default: earthscope-positions)
            --detach               Run detached in the background with
                                    --restart unless-stopped, so it auto-starts
                                    on Docker/system restart and auto-restarts
                                    if it crashes (until you `docker stop` it).
                                    Default is foreground: --rm -it (removed on
                                    exit, attached to your terminal).

  cli     Interactive shell in the same container setup `run` uses (same data/
          credentials mounts, same pre-flight checks — auth check, seeding
          coordinates.csv/path-spec resources, preloading default stream
          lists — as the web server does on startup) but no web server: you
          get a prompt with the venv already active, so `es-pos fetch`,
          `es-pos stations`, `es-pos export`, etc. all work directly and see
          exactly the state a `run` container would. Always --rm -it (it's
          inherently interactive; nothing useful to leave running after you
          exit the shell), named earthscope-positions-cli. Takes the same
          --data-dir / --earthscope-dir / --profile / --image / --name as
          `run` (no --port/--hostname/--detach — there's no server to publish).

  entrypoint   Internal — this is what the Dockerfile's ENTRYPOINT runs
               *inside* the container: activates the venv, then one of
               `es user login` (`login`), a pre-flighted interactive shell
               (`cli`), or `es-pos webserver` (the default). Not meant to be
               invoked directly on the host; --port/--hostname/--profile come
               from env vars that `run`/`login`/`cli` set, not from CLI flags.

  help    Show this message (default when no command is given).
EOF
}

cmd_build() {
    local image_tag="earthscope-positions:latest"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tag)
                image_tag="$2"; shift 2 ;;
            -h|--help)
                cmd_help; exit 0 ;;
            *)
                echo "Unknown option: $1" >&2; exit 1 ;;
        esac
    done

    echo "Building $image_tag ..."
    docker build -t "$image_tag" .
    echo "Built $image_tag"
}

cmd_login() {
    local earthscope_dir="$HOME/.earthscope"
    local profile=""
    local image="earthscope-positions:latest"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --earthscope-dir)
                earthscope_dir="$2"; shift 2 ;;
            --profile)
                profile="$2"; shift 2 ;;
            --image)
                image="$2"; shift 2 ;;
            -h|--help)
                cmd_help; exit 0 ;;
            *)
                echo "Unknown option: $1" >&2; exit 1 ;;
        esac
    done

    mkdir -p "$earthscope_dir"

    echo "Logging in inside Docker"
    echo "  credentials: $earthscope_dir  ->  /root/.earthscope"
    echo "  profile:     ${profile:-default}"
    echo

    # --profile is passed explicitly to `es user login` (confirmed as the
    # correct placement: `es user login --profile X`, NOT `es --profile X
    # user login`) and also set as ES_PROFILE so it's consistent with `run`.
    local -a login_args=(login)
    if [[ -n "$profile" ]]; then
        login_args+=(--profile "$profile")
    fi

    # Always --rm -it: this needs your terminal to show the login URL/code
    # (Device Code flow) and there's nothing useful to leave running after.
    docker run --rm -it \
        --name earthscope-positions-login \
        -e ES_PROFILE="${profile:-default}" \
        -v "$earthscope_dir:/root/.earthscope" \
        "$image" \
        "${login_args[@]}"
}

cmd_run() {
    local data_dir="$(pwd)/data"
    local earthscope_dir="$HOME/.earthscope"
    local profile=""
    local port=8000
    local hostname_arg=localhost
    local image="earthscope-positions:latest"
    local container_name="earthscope-positions"
    local detach=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --data-dir)
                data_dir="$2"; shift 2 ;;
            --earthscope-dir)
                earthscope_dir="$2"; shift 2 ;;
            --profile)
                profile="$2"; shift 2 ;;
            --port)
                port="$2"; shift 2 ;;
            --hostname)
                hostname_arg="$2"; shift 2 ;;
            --image)
                image="$2"; shift 2 ;;
            --name)
                container_name="$2"; shift 2 ;;
            --detach)
                detach=true; shift ;;
            -h|--help)
                cmd_help; exit 0 ;;
            *)
                echo "Unknown option: $1" >&2; exit 1 ;;
        esac
    done

    mkdir -p "$data_dir"
    if [[ ! -d "$earthscope_dir" ]]; then
        echo "warning: $earthscope_dir does not exist yet." >&2
        echo "         Log in first with: ./es-pos-docker.sh login" >&2
    fi

    echo "Starting $image  ->  http://${hostname_arg}:${port}"
    echo "  data:        $data_dir  ->  /app/data"
    echo "  credentials: $earthscope_dir  ->  /root/.earthscope"
    echo "  profile:     ${profile:-default}"

    # --rm and --restart are mutually exclusive (a self-removing container
    # can't also be auto-restarted), so the two modes use disjoint flag sets.
    local -a mode_flags
    if $detach; then
        echo "  mode:        detached, --restart unless-stopped"
        mode_flags=(-d --restart unless-stopped)
    else
        mode_flags=(--rm -it)
    fi

    docker run "${mode_flags[@]}" \
        --name "$container_name" \
        -p "${port}:${port}" \
        -e ES_POS_PORT="$port" \
        -e ES_POS_HOSTNAME="$hostname_arg" \
        -e ES_PROFILE="${profile:-default}" \
        -v "$data_dir:/app/data" \
        -v "$earthscope_dir:/root/.earthscope" \
        "$image"
}

cmd_cli() {
    local data_dir="$(pwd)/data"
    local earthscope_dir="$HOME/.earthscope"
    local profile=""
    local image="earthscope-positions:latest"
    local container_name="earthscope-positions-cli"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --data-dir)
                data_dir="$2"; shift 2 ;;
            --earthscope-dir)
                earthscope_dir="$2"; shift 2 ;;
            --profile)
                profile="$2"; shift 2 ;;
            --image)
                image="$2"; shift 2 ;;
            --name)
                container_name="$2"; shift 2 ;;
            -h|--help)
                cmd_help; exit 0 ;;
            *)
                echo "Unknown option: $1" >&2; exit 1 ;;
        esac
    done

    mkdir -p "$data_dir"
    if [[ ! -d "$earthscope_dir" ]]; then
        echo "warning: $earthscope_dir does not exist yet." >&2
        echo "         Log in first with: ./es-pos-docker.sh login" >&2
    fi

    echo "Starting interactive CLI shell in $image"
    echo "  data:        $data_dir  ->  /app/data"
    echo "  credentials: $earthscope_dir  ->  /root/.earthscope"
    echo "  profile:     ${profile:-default}"

    # Always --rm -it: inherently interactive, and nothing useful to leave
    # running after you exit the shell.
    docker run --rm -it \
        --name "$container_name" \
        -e ES_PROFILE="${profile:-default}" \
        -v "$data_dir:/app/data" \
        -v "$earthscope_dir:/root/.earthscope" \
        "$image" \
        cli
}

cmd_entrypoint() {
    # Runs INSIDE the container — this is the Dockerfile's ENTRYPOINT.
    # Activates the venv built at image-build time, then dispatches on the
    # mode `run`/`login`/`cli` queued up on the host (as `... image <mode>
    # ...`); `run` passes no extra args, so "$@" is empty and this falls
    # through to the default (webserver).
    source /app/venv/bin/activate

    if [[ "${1:-}" == "login" ]]; then
        shift
        exec es user login "$@"
    fi

    if [[ "${1:-}" == "cli" ]]; then
        # Same pre-flight the web server runs on startup (auth check, seed
        # coordinates.csv/path-spec resources, preload default stream lists),
        # so the shell you land in matches the state a `run` container would
        # have — then an interactive shell instead of the server itself.
        python -c "from earthscope_positions.webserver.webserver import run_startup_preflight; run_startup_preflight()"
        echo
        echo "Pre-flight complete — venv active, try: es-pos --help"
        exec bash
    fi

    # --host 0.0.0.0 so the port mapped by `run` (docker run -p) is actually
    # reachable; --port/--hostname come from env vars (set by `run`) so they
    # can be changed without rebuilding the image. --data-directory is left at
    # its default (./data relative to WORKDIR /app), which `run` bind-mounts.
    exec es-pos webserver \
        --host 0.0.0.0 \
        --port "${ES_POS_PORT:-8000}" \
        --hostname "${ES_POS_HOSTNAME:-localhost}" \
        "$@"
}

case "${1:-help}" in
    build)
        shift; cmd_build "$@" ;;
    login)
        shift; cmd_login "$@" ;;
    run)
        shift; cmd_run "$@" ;;
    cli)
        shift; cmd_cli "$@" ;;
    entrypoint)
        shift; cmd_entrypoint "$@" ;;
    help|-h|--help)
        cmd_help ;;
    *)
        echo "Unknown command: $1" >&2
        echo
        cmd_help
        exit 1 ;;
esac

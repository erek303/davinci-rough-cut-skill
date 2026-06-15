#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${DAVINCI_ROUGH_CUT_REPO_URL:-https://github.com/erek303/davinci-rough-cut-skill.git}"
BRANCH="${DAVINCI_ROUGH_CUT_BRANCH:-main}"
TARGET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_TESTS=1
PRUNE=1
DRY_RUN=0
LAUNCHER_DIR="${DAVINCI_ROUGH_CUT_BIN_DIR:-${HOME}/.local/bin}"

usage() {
  cat <<'EOF'
Usage: bash update.sh [options]

Update the installed DaVinci Rough Cut skill from GitHub without retyping the
repository URL.

Options:
  --target DIR       Installed skill directory to update.
                     Default: the directory containing this update.sh.
  --repo URL         Git repository URL.
                     Default: https://github.com/erek303/davinci-rough-cut-skill.git
  --branch NAME      Git branch or tag to fetch. Default: main
  --skip-tests       Skip offline tests before updating.
  --prune            Delete stale packaged files while preserving local state.
                     This is the default.
  --no-prune         Keep stale packaged files that are no longer in the public
                     package.
  --dry-run          Show what would be updated without changing files.
  -h, --help         Show this help.

Environment:
  DAVINCI_ROUGH_CUT_BIN_DIR
                     Directory for the optional update launcher.
                     Default: ~/.local/bin

Examples:
  davinci-rough-cut-update
  bash /path/to/installed/davinci-rough-cut/update.sh
  bash ~/.agents/skills/davinci-rough-cut/update.sh
EOF
}

install_update_launcher() {
  if mkdir -p "${LAUNCHER_DIR}" 2>/dev/null; then
    launcher_path="${LAUNCHER_DIR}/davinci-rough-cut-update"
    cat > "${launcher_path}" <<EOF
#!/usr/bin/env bash
exec "${TARGET_DIR}/update.sh" "\$@"
EOF
    chmod 0755 "${launcher_path}"
    echo "Installed update launcher to ${launcher_path}"
  else
    echo "Could not create update launcher under ${LAUNCHER_DIR}; update with bash ${TARGET_DIR}/update.sh" >&2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_DIR="$2"
      shift 2
      ;;
    --repo)
      REPO_URL="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --skip-tests)
      RUN_TESTS=0
      shift
      ;;
    --prune)
      PRUNE=1
      shift
      ;;
    --no-prune)
      PRUNE=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required to update this skill." >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "ERROR: rsync is required to update this skill safely." >&2
  exit 1
fi

TARGET_DIR="$(mkdir -p "${TARGET_DIR}" && cd "${TARGET_DIR}" && pwd)"
if [[ ! -f "${TARGET_DIR}/SKILL.md" ]]; then
  echo "ERROR: ${TARGET_DIR} does not look like an installed davinci-rough-cut skill." >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmp_dir}"
}
trap cleanup EXIT

echo "Fetching latest davinci-rough-cut skill..."
echo "  repo:   ${REPO_URL}"
echo "  branch: ${BRANCH}"
echo "  target: ${TARGET_DIR}"

git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${tmp_dir}/repo" >/dev/null

SOURCE_DIR="${tmp_dir}/repo/skill/davinci-rough-cut"
if [[ ! -f "${SOURCE_DIR}/SKILL.md" ]]; then
  echo "ERROR: downloaded repository does not contain skill/davinci-rough-cut/SKILL.md" >&2
  exit 1
fi

new_commit="$(git -C "${tmp_dir}/repo" rev-parse HEAD)"

if [[ "${RUN_TESTS}" -eq 1 ]]; then
  echo "Running offline tests before updating..."
  python3 "${tmp_dir}/repo/tests/test_offline_workflows.py"
fi

rsync_args=(-a)
if [[ "${DRY_RUN}" -eq 1 ]]; then
  rsync_args+=(--dry-run --itemize-changes)
fi
if [[ "${PRUNE}" -eq 1 ]]; then
  rsync_args+=(--delete)
fi

rsync_args+=(
  --exclude ".venv/"
  --exclude ".env"
  --exclude ".env.*"
  --exclude "work/"
  --exclude "works/"
  --exclude "output/"
  --exclude "outputs/"
  --exclude "*.log"
)

if [[ "${PRUNE}" -eq 1 ]]; then
  echo "Syncing packaged skill files and pruning stale packaged files..."
else
  echo "Syncing packaged skill files without pruning stale files..."
fi
rsync "${rsync_args[@]}" "${SOURCE_DIR}/" "${TARGET_DIR}/"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Dry run complete. No files were changed."
else
  printf '%s\n' "${new_commit}" > "${TARGET_DIR}/.source-commit"
  install_update_launcher
  echo "Updated davinci-rough-cut skill to ${new_commit}"
  echo "Preserved local .venv, .env, work, and output folders when present."
fi

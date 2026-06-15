#!/usr/bin/env bash
set -euo pipefail

TARGET_ROOT="auto"
TARGET_SET=0
AGENT_NAME="auto"
INSTALL_LAUNCHER=1
LAUNCHER_DIR="${DAVINCI_ROUGH_CUT_BIN_DIR:-${HOME}/.local/bin}"
PRINT_TARGETS=0

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Install DaVinci Rough Cut into the skill directory used by the current Agent.
By default, the installer tries to detect the current Agent instead of assuming
Codex.

Options:
  --target DIR|auto      Skill root to install into. Default: auto
                         Example: --target ~/.claude/skills
  --agent NAME           Hint the Agent type: auto, codex, agents, claude, newmax
  --print-targets        Print detected target candidates and exit.
  --no-launcher          Do not create the davinci-rough-cut-update launcher.
  -h, --help             Show this help.

Environment:
  DAVINCI_ROUGH_CUT_SKILL_ROOT  Explicit skill root, such as ~/.claude/skills.
  DAVINCI_ROUGH_CUT_SKILL_DIR   Explicit installed skill dir. Its parent is used.
  DAVINCI_ROUGH_CUT_BIN_DIR     Directory for the optional update launcher.
                                Default: ~/.local/bin

Examples:
  bash install.sh
  bash install.sh --target auto
  bash install.sh --agent claude
  bash install.sh --target ~/.newmax/skills
EOF
}

expand_path() {
  local value="$1"
  case "${value}" in
    "~") printf '%s\n' "${HOME}" ;;
    "~/"*) printf '%s/%s\n' "${HOME}" "${value#~/}" ;;
    *) printf '%s\n' "${value}" ;;
  esac
}

root_for_agent() {
  case "$1" in
    codex) printf '%s\n' "${HOME}/.codex/skills" ;;
    agents) printf '%s\n' "${HOME}/.agents/skills" ;;
    claude) printf '%s\n' "${HOME}/.claude/skills" ;;
    newmax) printf '%s\n' "${HOME}/.newmax/skills" ;;
    auto|"") return 1 ;;
    *)
      echo "Unknown agent: $1" >&2
      echo "Expected one of: auto, codex, agents, claude, newmax" >&2
      exit 1
      ;;
  esac
}

detect_parent_agent() {
  local pid="${PPID:-}"
  local depth=0
  local command=""
  while [[ -n "${pid}" && "${pid}" != "1" && "${depth}" -lt 8 ]]; do
    command="$(ps -o command= -p "${pid}" 2>/dev/null || true)"
    case "${command}" in
      *claude*|*Claude*) printf 'claude\n'; return 0 ;;
      *codex*|*Codex*) printf 'codex\n'; return 0 ;;
      *newmax*|*NewMax*) printf 'newmax\n'; return 0 ;;
    esac
    pid="$(ps -o ppid= -p "${pid}" 2>/dev/null | tr -d ' ' || true)"
    depth=$((depth + 1))
  done
  return 1
}

print_target_candidates() {
  echo "Detected install candidates:"
  if [[ -n "${DAVINCI_ROUGH_CUT_SKILL_ROOT:-}" ]]; then
    echo "  env:DAVINCI_ROUGH_CUT_SKILL_ROOT  $(expand_path "${DAVINCI_ROUGH_CUT_SKILL_ROOT}")"
  fi
  if [[ -n "${DAVINCI_ROUGH_CUT_SKILL_DIR:-}" ]]; then
    echo "  env:DAVINCI_ROUGH_CUT_SKILL_DIR   $(dirname "$(expand_path "${DAVINCI_ROUGH_CUT_SKILL_DIR}")")"
  fi
  for agent in codex agents claude newmax; do
    root="$(root_for_agent "${agent}")"
    if [[ -d "${root}" ]]; then
      echo "  existing:${agent}                 ${root}"
    else
      echo "  candidate:${agent}                ${root}"
    fi
  done
  echo
  echo "You can install explicitly with:"
  echo "  bash install.sh --target <one-of-the-roots-above>"
}

resolve_target_root() {
  local detected_agent=""
  local root=""

  if [[ "${TARGET_ROOT}" != "auto" ]]; then
    expand_path "${TARGET_ROOT}"
    return 0
  fi

  if [[ -n "${DAVINCI_ROUGH_CUT_SKILL_ROOT:-}" ]]; then
    expand_path "${DAVINCI_ROUGH_CUT_SKILL_ROOT}"
    return 0
  fi

  if [[ -n "${DAVINCI_ROUGH_CUT_SKILL_DIR:-}" ]]; then
    dirname "$(expand_path "${DAVINCI_ROUGH_CUT_SKILL_DIR}")"
    return 0
  fi

  if [[ "${AGENT_NAME}" != "auto" ]]; then
    root_for_agent "${AGENT_NAME}"
    return 0
  fi

  if detected_agent="$(detect_parent_agent)"; then
    root_for_agent "${detected_agent}"
    return 0
  fi

  for root in "${HOME}/.agents/skills" "${HOME}/.claude/skills" "${HOME}/.newmax/skills" "${HOME}/.codex/skills"; do
    if [[ -d "${root}" ]]; then
      printf '%s\n' "${root}"
      return 0
    fi
  done

  printf '%s\n' "${HOME}/.agents/skills"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_ROOT="$2"
      TARGET_SET=1
      shift 2
      ;;
    --agent)
      AGENT_NAME="$2"
      shift 2
      ;;
    --print-targets)
      PRINT_TARGETS=1
      shift
      ;;
    --no-launcher)
      INSTALL_LAUNCHER=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "${TARGET_SET}" -eq 0 && "${AGENT_NAME}" != "auto" ]]; then
  TARGET_ROOT="auto"
fi

if [[ "${PRINT_TARGETS}" -eq 1 ]]; then
  print_target_candidates
  exit 0
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${REPO_DIR}/skill/davinci-rough-cut"
TARGET_ROOT="$(resolve_target_root)"
TARGET_DIR="${TARGET_ROOT}/davinci-rough-cut"

if [[ ! -f "${SOURCE_DIR}/SKILL.md" ]]; then
  echo "Cannot find skill package at ${SOURCE_DIR}" >&2
  exit 1
fi

mkdir -p "${TARGET_ROOT}"
rm -rf "${TARGET_DIR}"
cp -R "${SOURCE_DIR}" "${TARGET_DIR}"

echo "Installed davinci-rough-cut to ${TARGET_DIR}"
if [[ "${TARGET_ROOT}" == "${HOME}/.agents/skills" && "${TARGET_SET}" -eq 0 && "${AGENT_NAME}" == "auto" && -z "${DAVINCI_ROUGH_CUT_SKILL_ROOT:-}" && -z "${DAVINCI_ROUGH_CUT_SKILL_DIR:-}" ]]; then
  echo "Auto target fallback: ${TARGET_ROOT}"
  echo "If your Agent uses a different skill root, rerun with --target <that-root> or --agent <name>."
fi

if [[ "${INSTALL_LAUNCHER}" -eq 1 ]]; then
  if mkdir -p "${LAUNCHER_DIR}" 2>/dev/null; then
    LAUNCHER_PATH="${LAUNCHER_DIR}/davinci-rough-cut-update"
    cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
exec "${TARGET_DIR}/update.sh" "\$@"
EOF
    chmod 0755 "${LAUNCHER_PATH}"
    echo "Installed update launcher to ${LAUNCHER_PATH}"
  else
    echo "Could not create update launcher under ${LAUNCHER_DIR}; update with bash ${TARGET_DIR}/update.sh" >&2
  fi
fi

echo
echo "Next:"
echo "  cd ${TARGET_DIR}"
echo "  python3 -m venv .venv"
echo "  .venv/bin/python -m pip install -U pip"
echo "  .venv/bin/python -m pip install -r requirements-core.txt"
echo
echo "Update later without retyping the repository URL:"
if [[ "${INSTALL_LAUNCHER}" -eq 1 ]]; then
  echo "  davinci-rough-cut-update"
fi
echo "  bash ${TARGET_DIR}/update.sh"

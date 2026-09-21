#!/bin/bash
set -euo pipefail

# Only needed in Claude Code on the web / remote sandboxes -- local dev
# machines are expected to have graphviz installed already.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# tests/test_diagram.py shells out to the `dot` binary (via the graphviz
# Python package) to render UBO ownership diagrams. Without it, every
# fresh session/container fails those tests with
# `graphviz.backend.execute.ExecutableNotFound: failed to execute 'dot'`.
if ! command -v dot >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq graphviz
fi

#!/bin/sh

set -eu

if [ ! -f .devcontainer/sonar.env ]; then
    sonar_db_password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
    if [ -z "$sonar_db_password" ]; then
        printf '%s\n' 'Unable to generate the local SonarQube database password.' >&2
        exit 1
    fi
    (umask 077; printf 'POSTGRES_PASSWORD=%s\nSONAR_JDBC_PASSWORD=%s\n' \
        "$sonar_db_password" "$sonar_db_password" > .devcontainer/sonar.env)
fi

postgres_password=$(sed -n 's/^POSTGRES_PASSWORD=//p' .devcontainer/sonar.env)
sonarqube_password=$(sed -n 's/^SONAR_JDBC_PASSWORD=//p' .devcontainer/sonar.env)
if [ -z "$postgres_password" ] || [ "$postgres_password" != "$sonarqube_password" ]; then
    printf '%s\n' 'Invalid .devcontainer/sonar.env; preserve matching database passwords.' >&2
    exit 1
fi

git_common_dir=$(git rev-parse --path-format=absolute --git-common-dir)
git_dir=$(git rev-parse --path-format=absolute --git-dir)

if [ "$git_dir" = "$git_common_dir" ]; then
    printf 'services: {}\n' > .devcontainer/compose.git-worktree.yaml
    exit 0
fi

workspace=$(git rev-parse --show-toplevel)
quoted_common_dir=$(printf '%s' "$git_common_dir" | sed 's/\\/\\\\/g; s/"/\\"/g')
quoted_workspace=$(printf '%s' "$workspace" | sed 's/\\/\\\\/g; s/"/\\"/g')

cat > .devcontainer/compose.git-worktree.yaml <<EOF
services:
  devcontainer:
    volumes:
      - type: bind
        source: "$quoted_common_dir"
        target: "$quoted_common_dir"
      - type: bind
        source: "$quoted_workspace"
        target: "$quoted_workspace"
EOF

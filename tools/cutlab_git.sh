#!/bin/sh
# git только для кода Cutlab: история — в NIK/.cutlab.git, файлы остаются на своих местах в NIK.
#   tools/cutlab_git.sh status | add <путь> | commit -m "…" | push
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec git --git-dir="$ROOT/.cutlab.git" --work-tree="$ROOT" "$@"

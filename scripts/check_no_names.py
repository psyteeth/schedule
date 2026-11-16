#!/usr/bin/env python3
"""Проверка: в файлах репозитория нет имён участников.

Список имён берётся из локального файла `.names.local` (по одному имени или
фамилии на строку, строки с `#` пропускаются). Файл в `.gitignore` и в
репозиторий не попадает.

Использование:
    python3 scripts/check_no_names.py              # рабочие файлы (tracked + новые)
    python3 scripts/check_no_names.py --staged     # то, что уходит в коммит
    python3 scripts/check_no_names.py --history    # все версии всех файлов в истории git
    python3 scripts/check_no_names.py FILE ...     # конкретные файлы

Код выхода 1 при совпадении. Совпадение ищется как отдельное слово без учёта
регистра, с учётом падежных окончаний.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES_FILE = ROOT / ".names.local"
SKIP = {".names.local"}
# окончания русских падежей, чтобы ловить косвенные формы имени
ENDINGS = r"(?:а|я|у|ю|ы|и|е|ой|ей|ою|ею|ом|ем|ым|им|ов|ев|ых|их|ами|ями|ах|ях)?"


def load_names(path=NAMES_FILE):
    if not path.exists():
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


def build_pattern(names):
    if not names:
        return None
    parts = []
    for n in sorted(set(names), key=len, reverse=True):
        stem = n
        # имя на -а/-я/-й/-ь → основа без последней буквы, чтобы ловить все падежи
        if len(n) > 3 and n[-1].lower() in "аяйь":
            stem = n[:-1]
        parts.append(re.escape(stem) + ENDINGS)
    return re.compile(r"(?<![\w])(?:" + "|".join(parts) + r")(?![\w])", re.IGNORECASE)


def scan_text(text, pattern):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in pattern.finditer(line):
            hits.append((i, m.group(0)))
    return hits


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def working_files():
    out = git("ls-files", "-co", "--exclude-standard", "-z").decode()
    return [f for f in out.split("\0") if f and f not in SKIP]


def staged_blobs():
    out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode()
    for f in out.split("\0"):
        if f and f not in SKIP:
            yield f, git("show", f":{f}")


def history_blobs():
    seen = set()
    for line in git("rev-list", "--all", "--objects").decode().splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2 or parts[0] in seen:
            continue
        sha, path = parts
        seen.add(sha)
        if git("cat-file", "-t", sha).strip() != b"blob":
            continue
        commits = git("log", "--all", "--format=%h", "--find-object=" + sha).decode().split()
        yield f"{path} (blob {sha[:8]}, коммиты: {' '.join(commits[:5]) or '?'})", git("cat-file", "-p", sha)
    # сообщения коммитов тоже часть истории
    yield "сообщения коммитов", git("log", "--all", "--format=%h %s%n%b")


def decode(data):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None  # бинарный файл


def run(items, pattern):
    found = 0
    for label, data in items:
        text = decode(data)
        if text is None:
            continue
        for line, word in scan_text(text, pattern):
            found += 1
            print(f"  {label}:{line}: «{word}»")
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true")
    g.add_argument("--history", action="store_true")
    args = ap.parse_args(argv)

    names = load_names()
    if not names:
        print("check_no_names: .names.local пуст или отсутствует, проверять нечего. "
              "Заполните его именами участников.", file=sys.stderr)
        return 0
    pattern = build_pattern(names)

    if args.files:
        items = ((f, Path(f).read_bytes()) for f in args.files)
    elif args.staged:
        items = staged_blobs()
    elif args.history:
        items = history_blobs()
    else:
        items = ((f, (ROOT / f).read_bytes()) for f in working_files() if (ROOT / f).is_file())

    found = run(items, pattern)
    if found:
        print(f"check_no_names: найдено совпадений: {found}. Уберите имена участников.", file=sys.stderr)
        return 1
    print(f"check_no_names: ок ({len(names)} имён в списке, совпадений нет).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

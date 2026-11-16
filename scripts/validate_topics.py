#!/usr/bin/env python3
"""Проверка и запись data/topics.json («Что разбирали на этой неделе»).

Использование:
    python3 scripts/validate_topics.py new_topics.json          # только проверить
    python3 scripts/validate_topics.py new_topics.json --write  # проверить и записать в data/topics.json
    python3 scripts/validate_topics.py                          # проверить текущий data/topics.json

При ошибке файл не пишется, код выхода 1.

Правила (ТЗ-10, разделы 6–7): схема, `text` ≤ 70 символов, `short` ≤ 42,
`g` ∈ {"ж", "м", null}, без внутренних слов и номеров зубов, без имён
участников из `.names.local`.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_no_names  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "data" / "topics.json"

TEXT_MAX = 70
SHORT_MAX = 42
ITEMS_MAX = 6
# внутренние слова (раздел 7, п. 2); сравниваются по основе
FORBIDDEN = ["уебищн", "листочк", "портал", "лимбик", "саморегуляц"]
# номер зуба: две цифры 11–48 (FDI) рядом со словом «зуб», или «зуб(ы) 36»
TOOTH_RE = re.compile(r"зуб\w*\s*№?\s*[1-4][1-8]\b|\b[1-4][1-8]\s*(?:-?й)?\s*зуб", re.IGNORECASE)


def check_date_range(value, errors, field):
    try:
        a, b = value.split("/")
        da, db = date.fromisoformat(a), date.fromisoformat(b)
        if db < da:
            errors.append(f"{field}: конец раньше начала")
    except (ValueError, AttributeError):
        errors.append(f"{field}: ожидается «ГГГГ-ММ-ДД/ГГГГ-ММ-ДД», получено {value!r}")


def check_phrase(s, where, limit, errors):
    if not isinstance(s, str) or not s.strip():
        errors.append(f"{where}: должна быть непустая строка")
        return
    if len(s) > limit:
        errors.append(f"{where}: {len(s)} символов, максимум {limit}: «{s}»")
    low = s.lower()
    for w in FORBIDDEN:
        if w in low:
            errors.append(f"{where}: внутреннее слово «{w}…»: «{s}»")
    if TOOTH_RE.search(s):
        errors.append(f"{where}: похоже на номер зуба: «{s}»")


def validate(data):
    errors = []
    if not isinstance(data, dict):
        return ["корень должен быть объектом"]
    allowed = {"week", "vector", "items"}
    for k in data:
        if k not in allowed:
            errors.append(f"лишнее поле: {k}")

    check_date_range(data.get("week"), errors, "week")

    v = data.get("vector")
    if v is not None:
        if not isinstance(v, dict):
            errors.append("vector: должен быть объектом или null")
        else:
            for k in ("from", "to"):
                check_phrase(v.get(k), f"vector.{k}", TEXT_MAX, errors)
            for k in ("from_short", "to_short"):
                if v.get(k) is not None:
                    check_phrase(v[k], f"vector.{k}", SHORT_MAX, errors)

    items = data.get("items")
    if not isinstance(items, list) or not items:
        errors.append("items: нужен непустой список")
        items = []
    if len(items) > ITEMS_MAX:
        errors.append(f"items: {len(items)} шт., на странице помещается {ITEMS_MAX}")
    for i, it in enumerate(items, 1):
        where = f"items[{i}]"
        if not isinstance(it, dict):
            errors.append(f"{where}: должен быть объектом")
            continue
        for k in it:
            if k not in {"g", "text", "short"}:
                errors.append(f"{where}: лишнее поле {k}")
        if it.get("g") not in ("ж", "м", None):
            errors.append(f"{where}.g: только «ж», «м» или null")
        check_phrase(it.get("text"), f"{where}.text", TEXT_MAX, errors)
        if it.get("short") is not None:
            check_phrase(it["short"], f"{where}.short", SHORT_MAX, errors)

    names = check_no_names.load_names()
    if names:
        pat = check_no_names.build_pattern(names)
        blob = json.dumps(data, ensure_ascii=False)
        for _, word in check_no_names.scan_text(blob, pat):
            errors.append(f"имя участника: «{word}»")
    else:
        print("validate_topics: .names.local пуст, проверка имён пропущена", file=sys.stderr)
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", default=str(TARGET))
    ap.add_argument("--write", action="store_true", help="записать в data/topics.json, если всё в порядке")
    args = ap.parse_args(argv)

    try:
        data = json.loads(Path(args.source).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"validate_topics: не читается {args.source}: {e}", file=sys.stderr)
        return 1

    errors = validate(data)
    if errors:
        print("validate_topics: ошибки, файл не записан:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1

    if args.write and Path(args.source).resolve() != TARGET.resolve():
        TARGET.parent.mkdir(exist_ok=True)
        TARGET.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"validate_topics: ок, записано в {TARGET.relative_to(ROOT)}")
    else:
        print("validate_topics: ок")
    return 0


if __name__ == "__main__":
    sys.exit(main())

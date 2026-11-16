#!/usr/bin/env python3
"""Забирает агрегаты из веб-приложения Apps Script и пишет data/stats.json.

Адрес берётся из переменной окружения STATS_URL (секрет GitHub, в репозитории
его нет). Ответ проходит строгую проверку: в файл попадают только известные
поля, числа в разумных пределах и только имена тренеров из ALLOWED_TRAINERS.
Если что-то не так, файл не меняется и скрипт падает с кодом 1, так что на
сайте остаются вчерашние цифры, а владелец видит красную задачу в GitHub.

    STATS_URL=https://script.google.com/macros/s/.../exec python3 scripts/fetch_stats.py
    python3 scripts/fetch_stats.py --file ответ.json     # проверить сохранённый ответ
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "data" / "stats.json"

ALLOWED_TRAINERS = ["Антон", "Таня", "Яна", "Гульназ"]
DAYS = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


class Bad(Exception):
    pass


def need_int(d, k, lo, hi):
    v = d.get(k)
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise Bad(f"{k}: ожидается целое {lo}…{hi}, получено {v!r}")
    return v


def clean(raw):
    """Собирает stats.json заново из проверенных полей: ничего лишнего не проходит."""
    if not isinstance(raw, dict):
        raise Bad("ответ не объект")
    if "error" in raw:
        raise Bad(f"Apps Script вернул ошибку: {raw['error']}")
    updated = raw.get("updated")
    if not isinstance(updated, str) or not DATE_RE.match(updated):
        raise Bad(f"updated: {updated!r}")

    out = {"updated": updated, "source": "apps_script"}
    out["slots_total"] = need_int(raw, "slots_total", 1, 5000)
    out["slots_past"] = need_int(raw, "slots_past", 0, out["slots_total"])
    out["slots_upcoming"] = need_int(raw, "slots_upcoming", 0, out["slots_total"])
    if out["slots_past"] + out["slots_upcoming"] != out["slots_total"]:
        raise Bad("slots_past + slots_upcoming ≠ slots_total")
    out["participants_active"] = need_int(raw, "participants_active", 1, 500)
    out["streams_per_week"] = need_int(raw, "streams_per_week", 1, 100)

    tr = raw.get("trainers")
    if not isinstance(tr, list) or not tr or any(t not in ALLOWED_TRAINERS for t in tr) or len(set(tr)) != len(tr):
        raise Bad(f"trainers: только из {ALLOWED_TRAINERS}, получено {tr!r}")
    out["trainers"] = tr

    lu = raw.get("limbic_unload_30d")
    if not isinstance(lu, dict):
        raise Bad("limbic_unload_30d: нет")
    win = lu.get("window")
    if not isinstance(win, str) or not re.match(r"^\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}$", win):
        raise Bad(f"limbic_unload_30d.window: {win!r}")
    out["limbic_unload_30d"] = {
        "hours": need_int(lu, "hours", 0, 10000),
        "minutes": need_int(lu, "minutes", 0, 59),
        "sr_count": need_int(lu, "sr_count", 0, 100000),
        "window": win,
        "includes_trainers": bool(lu.get("includes_trainers")),
    }

    heat = raw.get("heat")
    if not isinstance(heat, list) or not heat:
        raise Bad("heat: пусто")
    if len(heat) != out["streams_per_week"]:
        raise Bad("heat: число клеток ≠ streams_per_week")
    out["heat"] = []
    for i, h in enumerate(heat):
        if not isinstance(h, dict):
            raise Bad(f"heat[{i}] не объект")
        item = {"day": h.get("day"), "row": h.get("row"), "trainer": h.get("trainer"), "avg": h.get("avg")}
        if item["day"] not in DAYS:
            raise Bad(f"heat[{i}].day: {item['day']!r}")
        if not isinstance(item["row"], str) or not TIME_RE.match(item["row"]):
            raise Bad(f"heat[{i}].row: {item['row']!r}")
        if item["trainer"] not in tr:
            raise Bad(f"heat[{i}].trainer: {item['trainer']!r}")
        if not isinstance(item["avg"], (int, float)) or isinstance(item["avg"], bool) or not 0 < item["avg"] <= 6:
            raise Bad(f"heat[{i}].avg: {item['avg']!r}")
        if h.get("time") is not None:
            if not isinstance(h["time"], str) or not TIME_RE.match(h["time"]):
                raise Bad(f"heat[{i}].time: {h['time']!r}")
            item["time"] = h["time"]
        out["heat"].append(item)
    return out


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "schedule-stats"})
    with urllib.request.urlopen(req, timeout=120) as r:  # Apps Script отвечает редиректом, urllib идёт за ним
        return json.loads(r.read().decode("utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="взять ответ из файла вместо STATS_URL")
    ap.add_argument("--out", default=str(TARGET))
    args = ap.parse_args(argv)

    try:
        if args.file:
            raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
        else:
            url = os.environ.get("STATS_URL", "").strip()
            if not url:
                raise Bad("не задан STATS_URL")
            raw = fetch(url)
        stats = clean(raw)
    except (Bad, OSError, ValueError) as e:
        print(f"fetch_stats: {e}. data/stats.json не изменён.", file=sys.stderr)
        return 1

    Path(args.out).write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lu = stats["limbic_unload_30d"]
    print(f"fetch_stats: ок, {stats['updated']}: {stats['slots_total']} слотов, "
          f"{stats['participants_active']} участников, {stats['streams_per_week']} эфиров, "
          f"{lu['hours']} ч {lu['minutes']} мин")
    return 0


if __name__ == "__main__":
    sys.exit(main())

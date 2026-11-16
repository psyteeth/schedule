#!/usr/bin/env python3
"""Агрегаты для data/stats.json из выгрузки таблицы записи на эфиры.

Сырые данные лежат ВНЕ репозитория. Скрипт читает CSV-выгрузку и пишет
только числа и имена тренеров: имён участников в выходе нет.

Ожидаемый CSV (UTF-8, заголовок в первой строке), одна строка = один
занятый 15-минутный слот:

    date,time,trainer,participant
    2026-11-17,08:00,Антон,<имя участника>

- date: ГГГГ-ММ-ДД, time: ЧЧ:ММ по Москве (время начала эфира);
- trainer: имя тренера; participant: имя или ник (нужен только для подсчёта
  уникальных людей и в выход не попадает).

Использование:
    python3 scripts/build_stats.py /путь/вне/репо/efiry.csv --today 2026-11-16
    python3 scripts/build_stats.py efiry.csv --merge data/stats.json --out data/stats.json

С `--merge` берёт из существующего stats.json поля, которых таблица не даёт
(limbic_unload_30d), и обновляет остальное.

Правила подсчёта (ТЗ-10, 5.1):
- slots_total: все занятые слоты в выгрузке (прошедшие + будущие);
- participants_active: уникальные участники в выгрузке;
- streams_per_week: постоянные эфиры = пары (день недели, время), которые
  встречаются минимум в `--min-weeks` разных неделях;
- heat: для каждого постоянного эфира среднее число людей на эфир;
  строка тепловой карты = время, округлённое вниз до часа.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

DAYS = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]


def norm_time(t):
    h, m = t.strip().split(":")[:2]
    return int(h), int(m)


def build(rows, today, min_weeks=2):
    slots_past = slots_up = 0
    people = set()
    # (день, ЧЧ:ММ) -> {дата эфира: число людей}
    streams = defaultdict(lambda: defaultdict(int))
    trainer_of = {}
    for r in rows:
        d = date.fromisoformat(r["date"].strip())
        h, m = norm_time(r["time"])
        who = (r.get("participant") or "").strip()
        if not who:
            continue  # пустой слот
        if d <= today:
            slots_past += 1
        else:
            slots_up += 1
        people.add(who.lower())
        key = (DAYS[d.weekday()], f"{h}:{m:02d}")
        streams[key][d] += 1
        trainer_of[key] = r["trainer"].strip()

    heat = []
    trainers = []
    for (day, hm), by_date in streams.items():
        weeks = {d.isocalendar()[:2] for d in by_date}
        if len(weeks) < min_weeks:
            continue
        past = [n for d, n in by_date.items() if d <= today] or list(by_date.values())
        avg = round(sum(past) / len(past), 1)
        h, m = map(int, hm.split(":"))
        item = {"day": day, "row": f"{h}:00", "trainer": trainer_of[(day, hm)], "avg": avg}
        if m:
            item["time"] = hm
        heat.append(item)
        if trainer_of[(day, hm)] not in trainers:
            trainers.append(trainer_of[(day, hm)])

    heat.sort(key=lambda x: (int(x["row"].split(":")[0]), DAYS.index(x["day"])))
    return {
        "updated": today.isoformat(),
        "source": "sheet",
        "slots_total": slots_past + slots_up,
        "slots_past": slots_past,
        "slots_upcoming": slots_up,
        "participants_active": len(people),
        "streams_per_week": len(heat),
        "trainers": trainers,
        "heat": heat,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--min-weeks", type=int, default=2)
    ap.add_argument("--trainers", help="порядок тренеров через запятую, напр. «Антон,Таня,Яна,Гульназ»")
    ap.add_argument("--merge", help="существующий stats.json, из которого взять остальные поля")
    ap.add_argument("--out", help="куда записать (по умолчанию stdout)")
    args = ap.parse_args(argv)

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    stats = build(rows, date.fromisoformat(args.today), args.min_weeks)
    if args.trainers:
        order = [t.strip() for t in args.trainers.split(",")]
        stats["trainers"] = [t for t in order if t in stats["trainers"]] + \
                            [t for t in stats["trainers"] if t not in order]
    if args.merge and Path(args.merge).exists():
        base = json.loads(Path(args.merge).read_text(encoding="utf-8"))
        base.update(stats)
        stats = base
    out = json.dumps(stats, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

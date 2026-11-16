# schedule — дашборд «Что у нас происходит»

https://psyteeth.github.io/schedule/ — один экран: цифры, расписание эфиров, программа и стоимость, темы недели.

## Файлы
- `index.html` — вся страница (десктоп ≥ 900 px и телефон, 4 темы на CSS без JS).
- `data/stats.json` — агрегаты: слоты, участники, эфиры, тренеры, минуты разгрузки, тепловая карта. Только числа и имена тренеров.
- `data/topics.json` — «Что разбирали на этой неделе». Нет файла — блок скрыт.

## Правило: никаких имён участников
- `.names.local` (не коммитится) — имена участников, по одному на строку.
- `python3 scripts/check_no_names.py` — рабочие файлы; `--history` — вся история git.
- Хук `.githooks/pre-commit` проверяет каждый коммит. Включить в новой копии: `git config core.hooksPath .githooks`.

## Обновить темы недели
```bash
python3 scripts/validate_topics.py new_topics.json --write
```
Пишет `data/topics.json`, только если проверка прошла (схема, `text` ≤ 70, `short` ≤ 42, без внутренних слов и имён). На телефоне показываются первые 4 темы, у которых есть `short`.

## Обновить цифры
Сейчас вручную (`"source": "manual"` в `data/stats.json`). Из выгрузки таблицы эфиров (CSV вне репозитория):
```bash
python3 scripts/build_stats.py /путь/вне/репо/efiry.csv --merge data/stats.json --out data/stats.json --trainers "Антон,Таня,Яна,Гульназ"
```
Формат CSV и правила подсчёта — в начале `scripts/build_stats.py`. Поле `heat[].time` — фактическое время начала, если оно не совпадает со строкой карты (7:07, 8:30).

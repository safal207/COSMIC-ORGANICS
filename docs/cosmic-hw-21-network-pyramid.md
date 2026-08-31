# COSMIC-HW-21: `1 + 1 = N` network pyramid

HW-21 переводит принцип сетевой пирамиды в проверяемую аппаратную гипотезу. Каждый следующий слой удваивает число независимых iterative SHA-256 consumers:

```text
1 control → 2 → 4 → 8 → 16 engines
```

Все слои получают один и тот же поток: два A→M→C tick, 128 ordered receipts и 13 commitment digest. Итоговый digest и порядок retirement неизменны.

## Что означает сетевой эффект

Дополнительные engines могут параллельно считать независимые commitment blocks. Но работа не создаётся из воздуха: во всех слоях сумма занятых engine‑тактов должна оставаться `13 × 64 = 832`.

Ускорение прекращается, когда producer не успевает кормить сеть:

- receipt collector выдаёт только одну квитанцию за такт;
- полный SHA block требует десять квитанций;
- существует только один currently filling message и один complete waiting block;
- digest выводятся строго по sequence.

Поэтому `1 + 1 = N` означает расширение числа готовых потребителей, а не сверхлинейное ускорение. HW-21 прямо запрещает speedup выше числа engines.

## Проверка

```bash
python -m pytest -q tests/test_cosmic_hw_21_network.py
python tools/cosmic_hw_21_network.py --output-dir build/cosmic-hw-21-network
```

Контракт выполняет cycle-accurate simulation для x2/x4/x8/x16, проверяет одинаковый digest и 832 aggregate busy cycles, а затем синтезирует x2/x4 под ECP5. x8/x16 resource counts разрешены только как линейная оценка и не представляются измерением.

Физическая плата, распределённая network latency, bitstream, power и energy остаются `NOT_RUN`.

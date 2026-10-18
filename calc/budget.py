#!/usr/bin/env python3
"""Фронтенд L1/L5 к LibreSDR: бюджет шума и паразитные продукты смесителя.

Схема (README.md): антенна с МШУ → кабель → плата (Bias-T, делитель,
тракт L5 напрямую на RX1, тракт L1 через смеситель на RX2) → LibreSDR,
RX-гетеродин 1176.45 МГц, гетеродин смесителя — TX1 того же AD9363.

Это оценка [О]: числа звеньев — из паспортов и карточек (источники в
docs/02-Компоненты.md), кабель и обобщённый пассивный смеситель — типовые значения.

Запуск: python3 calc/budget.py
"""
import math

T0 = 290.0      # К, стандартная температура для коэффициента шума
T_ANT = 130.0   # К, шумовая температура антенны, смотрящей в небо [О]
L1 = 1575.42
L5 = 1176.45
IF = L5         # на RX2 L1 переносится на частоту RX-гетеродина
HALF = 6.0      # МГц, половина полосы канала (2 × 12 Msps после F4; при 2 × 6 Msps — 3)
SAW_L1 = (1559.0, 1606.0)   # полоса ПАВ L1/E1/B1/G1 (класс Murata SAFFB1G56KB0F0A)


def db(x):
    return 10 * math.log10(x)


def lin(x):
    return 10 ** (x / 10)


def loss(name, l_db):
    """Пассивное звено при T0: усиление −L, коэффициент шума L."""
    return (name, -l_db, l_db)


# (название, усиление дБ, коэффициент шума дБ)
CABLE_L1 = loss("кабель 5 м RG58", 3.5)          # ~0.7 дБ/м на 1.6 ГГц [О]
CABLE_L5 = loss("кабель 5 м RG58", 3.0)          # ~0.6 дБ/м на 1.2 ГГц [О]
BIAS = loss("защита входа + Bias-T", 0.3)        # [О]
SPLIT = loss("делитель Уилкинсона 1:2", 3.5)     # 3.0 + 0.5 [О]
SAW5 = loss("ПАВ L5", 1.4)                       # Abracon AFII-SW-0060 [ВД]
SAW1 = loss("ПАВ L1", 1.6)                       # Murata SAFFB1G56KB0F0A, карточка Chip-Dip [ВИ]
LNA5 = ("МШУ BGA855N6", 17.8, 0.6)               # паспорт Infineon, 1164–1300 МГц [ВД]
LNA1 = ("МШУ L1 (класс BGA524N6)", 19.0, 0.7)    # паспорт не сверен [О]
MIX_P = loss("смеситель пассивный ДБС", 7.0)      # [О]
MIX_H = loss("смеситель HMC213B", 10.0)           # потери 10 дБ при LO +13 дБм, дистрибьюторы [ВИ]
MIX_A = ("смеситель LTC5510", 1.5, 11.6)         # на 1575 МГц, страница изделия ADI [ВИ]
OUT = loss("кабель к LibreSDR", 0.3)              # [О]
LIBRE = ("LibreSDR", 0.0, 8.0)                    # Кш при усилении 50 дБ, libresdr-lna [И]


def cascade(stages):
    g, f = 1.0, 1.0
    for _, g_db, nf_db in stages:
        f += (lin(nf_db) - 1) / g
        g *= lin(g_db)
    return db(g), db(f)


def report(title, chain, g_ant):
    ant = ("МШУ антенны", g_ant, 2.0)
    front = [ant] + chain
    g_front, nf_front = cascade(front)
    _, nf_sys = cascade(front + [LIBRE])
    t_e = (lin(nf_sys) - 1) * T0
    t_ideal = (lin(2.0) - 1) * T0
    cn0_loss = db((T_ANT + t_e) / (T_ANT + t_ideal))
    # шум тракта на входе LibreSDR против собственного шума LibreSDR
    t_up = lin(g_front) * (T_ANT + (lin(nf_front) - 1) * T0)
    t_libre = (lin(LIBRE[2]) - 1) * T0
    excess = db(t_up / t_libre)
    print(f"  {title:<46} G_ант {g_ant:>2} дБ: Кш {nf_sys:4.1f} дБ, "
          f"потеря C/N0 {cn0_loss:4.1f} дБ, усиление до LibreSDR {g_front:5.1f} дБ, "
          f"шум над шумом LibreSDR {excess:5.1f} дБ")


def budget():
    print("Бюджет шума (Кш системы — от входа МШУ антенны; потеря C/N0 — против "
          f"идеального тракта за МШУ антенны, T_ант = {T_ANT:.0f} К)\n")
    paths = {
        "L5 → RX1, без МШУ на плате": [CABLE_L5, BIAS, SPLIT, SAW5, OUT],
        "L5 → RX1, BGA855N6 после ПАВ": [CABLE_L5, BIAS, SPLIT, SAW5, LNA5, OUT],
        "L1 → RX2, пассивный смеситель, без МШУ": [CABLE_L1, BIAS, SPLIT, SAW1, MIX_P, SAW5, OUT],
        "L1 → RX2, пассивный смеситель, МШУ L1 и ПЧ": [CABLE_L1, BIAS, SPLIT, SAW1, LNA1, MIX_P, SAW5, LNA5, OUT],
        "L1 → RX2, HMC213B, МШУ L1 и ПЧ": [CABLE_L1, BIAS, SPLIT, SAW1, LNA1, MIX_H, SAW5, LNA5, OUT],
        "L1 → RX2, LTC5510, МШУ L1": [CABLE_L1, BIAS, SPLIT, SAW1, LNA1, MIX_A, SAW5, OUT],
        "L1 → RX2, LTC5510, МШУ L1 и ПЧ": [CABLE_L1, BIAS, SPLIT, SAW1, LNA1, MIX_A, SAW5, LNA5, OUT],
    }
    for title, chain in paths.items():
        for g_ant in (28, 35, 42):
            report(title, chain, g_ant)
        print()


STRONG = [
    ("ЧМ-вещание", 87.5, 108.0),
    ("ТВ DVB-T2", 470.0, 790.0),
    ("LTE 800", 791.0, 862.0),
    ("GSM/LTE 900", 880.0, 960.0),
    ("Iridium", 1616.0, 1626.5),
    ("GSM/LTE 1800", 1710.0, 1880.0),
    ("UMTS/LTE 2100", 1920.0, 2170.0),
    ("LTE 2300, Wi-Fi 2.4", 2300.0, 2483.5),
    ("LTE 2600", 2500.0, 2690.0),
    ("5G 3.4–3.8 ГГц", 3400.0, 3800.0),
    ("Wi-Fi 5 ГГц", 5150.0, 5850.0),
]


def overlap(a, b):
    return max(a[0], b[0]) < min(a[1], b[1])


def responses(lo, max_order=7):
    """Входные полосы f, для которых |m·LO ± n·f| попадает в [IF − HALF, IF + HALF]."""
    out = []
    for m in range(1, 6):
        for n in range(1, 6):
            if m + n > max_order:
                continue
            for s in (+1, -1):
                # n·f = m·LO + s·IF'  →  f = (m·LO + s·IF') / n
                lo_f = (m * lo + s * (IF - HALF)) / n
                hi_f = (m * lo + s * (IF + HALF)) / n
                band = (min(lo_f, hi_f), max(lo_f, hi_f))
                if band[1] <= 0:
                    continue
                out.append((m, n, band))
    return out


def spurs():
    print(f"Паразитные отклики смесителя в канал RX2 (ПЧ {IF} ± {HALF} МГц), порядок m + n ≤ 7")
    for name, lo in (("нижний", L1 - IF), ("верхний", L1 + IF)):
        print(f"\n  Гетеродин {name}: {lo:.2f} МГц")
        for m, n, band in responses(lo):
            hits = [s[0] for s in STRONG if overlap(band, (s[1], s[2]))]
            in_saw = overlap(band, SAW_L1)
            if not hits and not in_saw:
                continue
            tag = "рабочий" if (m, n) == (1, 1) and in_saw else ""
            where = ", ".join(hits + (["полоса ПАВ L1"] if in_saw else []))
            print(f"    m={m} n={n}: вход {band[0]:8.2f}–{band[1]:8.2f} МГц  ← {where} {tag}")
        harm = [(k, k * lo) for k in range(1, 7)
                if 1150 <= k * lo <= 1300 or 1550 <= k * lo <= 1620]
        for k, f in harm:
            print(f"    гармоника гетеродина {k}×LO = {f:.2f} МГц — в полосе ГНСС (утечка к антенне)")
    print("\n  Гармоники сильных сигналов прямо в L1/L5 (возникают в любом нелинейном звене до фильтра,"
          " в том числе в МШУ антенны; смеситель ни при чём)")
    for target, name in ((L1, "L1"), (L5, "L5")):
        for n in range(2, 6):
            band = ((target - HALF) / n, (target + HALF) / n)
            hits = [s[0] for s in STRONG if overlap(band, (s[1], s[2]))]
            if hits:
                print(f"    {n}-я гармоника {band[0]:.2f}–{band[1]:.2f} МГц → {name}  ← {', '.join(hits)}")
    print(f"\n  Прямой канал RX1 (RX-гетеродин {L5} МГц): отклики AD9363 на нечётных гармониках гетеродина")
    for k in (3, 5):
        band = (k * L5 - HALF, k * L5 + HALF)
        hits = [s[0] for s in STRONG if overlap(band, (s[1], s[2]))]
        print(f"    {k}×LO: {band[0]:.1f}–{band[1]:.1f} МГц  {'← ' + ', '.join(hits) if hits else ''}")


if __name__ == "__main__":
    budget()
    spurs()

#!/usr/bin/env python3
"""Черновик схемы платы v2 в KiCad по docs/04-Схема-черновик.md.

Запуск из корня репозитория:  python3 kicad/tools/gen_sch.py [--force]

Пишет в kicad/: проект gnss-fe.kicad_pro, корневой лист и листы блоков A–I, свою библиотеку
символов gnss-fe.kicad_sym и посадочных мест gnss-fe.pretty, таблицы библиотек. Затем пересохраняет
их через kicad-cli в формате KiCad 10, выгружает нетлист и сверяет его с задуманными соединениями
(S.on / S.pwr ниже), запускает ERC. kicad-cli работает с временной конфигурацией (KICAD_CONFIG_HOME)
со стандартными таблицами библиотек — настройки пользователя не трогаются.
Без --force существующие листы не перезаписываются: после правок в KiCad генератор не запускать.
"""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gen_lib  # noqa: E402
from kisch import (KICAD_SYM_DIR, PROJECT, Q, Sheet, dump, flat_symbol, parse, find, find_all,  # noqa: E402
                   uid)

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATE = "2026-10-28"


def u(n):
    """Шаг сетки 2.54 мм."""
    return round(n * 2.54, 4)


FP = {
    "C0402": "Capacitor_SMD:C_0402_1005Metric", "C0603": "Capacitor_SMD:C_0603_1608Metric",
    "C0805": "Capacitor_SMD:C_0805_2012Metric", "R0402": "Resistor_SMD:R_0402_1005Metric",
    "R0603": "Resistor_SMD:R_0603_1608Metric", "L0402": "Inductor_SMD:L_0402_1005Metric",
    "L0603": "Inductor_SMD:L_0603_1608Metric", "LED0603": "LED_SMD:LED_0603_1608Metric",
    "D0402": "Diode_SMD:D_0402_1005Metric", "DSMA": "Diode_SMD:D_SMA", "F1206": "Fuse:Fuse_1206_3216Metric",
    "SMA": "Connector_Coaxial:SMA_Amphenol_132289_EdgeMount", "TP": "TestPoint:TestPoint_Pad_D1.0mm",
    "SAW": "gnss-fe:SAW_Huaying_1.1x0.9mm_5pin",
}
DEV = {"C": "Device:C_Small", "R": "Device:R_Small", "L": "Device:L_Small", "FB": "Device:FerriteBead_Small",
       "F": "Device:Polyfuse_Small"}


def note(text, **extra):
    d = {"Примечание": text}
    d.update(extra)
    return d


def two(S, ref, value, fp, pin1, horiz, txt="", dnp=False, fpos="auto", **extra):
    """Двухвыводная деталь: horiz — вывод 1 слева, иначе вывод 1 сверху; pin1 — координата вывода 1."""
    kind = "".join(ch for ch in ref if ch.isalpha())
    S.add(ref, DEV[kind], value, FP[fp], rot=90 if horiz else 0, fields=note(txt, **extra), dnp=dnp, fpos=fpos)
    S.place(f"{ref}.1", *pin1)


def decap(S, ref, value, fp, x, y, net, txt="", fpos="right"):
    """Развязывающий конденсатор: сверху цепь питания, снизу земля."""
    two(S, ref, value, fp, (x, y), False, txt, fpos=fpos)
    S.pwr(f"{ref}.1", net)
    S.pwr(f"{ref}.2", "GND")


def bus(S, prefs, net, step, at=None):
    """Выводы в ряд: отводы на step (вниз > 0, вверх < 0), общая шина, знак питания в точке x=at."""
    pts = [S.pin(p) for p in prefs]
    y = pts[0][1] + step
    xs = sorted({p[0] for p in pts} | ({at} if at is not None else set()))
    for p in pts:
        S.wire(p, (p[0], y))
    S.wire(*[(x, y) for x in xs])
    x0 = at if at is not None else xs[len(xs) // 2]
    S.pwr_at(net, (x0, y), "down" if step > 0 and net == "GND" else ("up" if step < 0 else None))
    S.on(net, *prefs)


# ---------------------------------------------------------------- A. Питание

def sheet_A(libs):
    S = Sheet(libs, "A", "A_power.kicad_sch", "A. Питание")
    y = u(22)
    S.add("J1", "gnss-fe:KLS1-DC-005A", "KLS1-DC-005A-2.0", None,
          fields=note("Chip-Dip; вход 7–12 В (лучше блок 9 В), плюс в центре; вывод 2 — на землю [ВД, чертёж KLS]"))
    S.place("J1.4", u(12), y)
    S.wire("J1.2", (u(13), u(23)), (u(13), u(24)))
    S.wire("J1.3", (u(13), u(24)), (u(13), u(25)))
    S.pwr_at("GND", (u(13), u(25)))
    S.on("GND", "J1.2", "J1.3")
    two(S, "F1", "0.5A", "F1206", (u(16), y), True, "самовосстанавливающийся, по желанию [О]")
    S.add("D1", "Device:D_Schottky_Small", "SS34", FP["DSMA"], rot=180,
          fields=note("защита от переполюсовки, 3 А, падение ~0.4 В [О]"))
    S.place("D1.2", u(20), y)
    S.wire("J1.4", (u(14), y), "F1.1")
    S.wlabel("VIN_RAW", (u(14), y))
    S.on("VIN_RAW", "J1.4", "F1.1")
    S.wire("F1.2", "D1.2")
    S.on("A_VIN_F", "F1.2", "D1.2")
    S.add("U1", "Regulator_Linear:AMS1117-5.0", "AMS1117-5.0", None,
          fields=note("≥ 300 мА, вход до 15 В; с 9 В рассеивает ~0.6 Вт — медь под корпусом [О]; "
                      "кандидаты LM1117-5.0, AMS1117-5.0 или малошумящий"))
    S.place("U1.3", u(29), y)
    S.pwr("U1.1", "GND")
    two(S, "C1", "10u 25V", "C0805", (u(26), u(24)), False, "по паспорту U1")
    S.pwr("C1.2", "GND")
    S.wire("D1.1", (u(24), y), (u(26), y), (u(27), y), "U1.3")
    S.wire((u(26), y), "C1.1")
    S.flag((u(24), y))
    S.wlabel("VIN", (u(27), y))
    S.on("VIN", "D1.1", "C1.1", "U1.3")
    two(S, "C2", "10u", "C0805", (u(37), u(24)), False, "по паспорту U1 (требование к выходному конденсатору — сверить)")
    S.pwr("C2.2", "GND")
    S.wire("U1.2", (u(37), y), (u(39), y), (u(44), y), (u(44), u(24)))
    S.wire((u(37), y), "C2.1")
    S.pwr_at("+5V", (u(39), y))
    two(S, "R1", "1k", "R0603", (u(44), u(24)), False)
    S.add("LED1", "Device:LED_Small", "зелёный", FP["LED0603"], rot=90, fields=note("«питание»"), fpos="right")
    S.place("LED1.2", u(44), u(27))
    S.wire("R1.2", "LED1.2")
    S.pwr("LED1.1", "GND")
    S.on("+5V", "U1.2", "C2.1", "R1.1")
    S.on("A_LED1", "R1.2", "LED1.2")

    # Питание смесителя и антенны: ферриты и конденсаторы
    for i, (fb, ca, cb, net, x0) in enumerate((("FB1", "C3", "C4", "+5V_MIX", 10), ("FB2", "C5", "C6", "+5V_ANT_IN", 35))):
        y2 = u(40)
        S.pwr_at("+5V", (u(x0), y2))
        two(S, fb, "600R@100MHz", "L0603", (u(x0 + 2), y2), True,
            "питание LTC5510" if i == 0 else "питание антенны; C6 — у вывода IN U3 (0.1 мкФ по паспорту TPS2553)")
        two(S, ca, "10u", "C0805", (u(x0 + 7), u(42)), False)
        two(S, cb, "100n", "C0402", (u(x0 + 10), u(42)), False)
        S.pwr(f"{ca}.2", "GND")
        S.pwr(f"{cb}.2", "GND")
        S.wire((u(x0), y2), f"{fb}.1")
        S.wire(f"{fb}.2", (u(x0 + 7), y2), (u(x0 + 10), y2), (u(x0 + 13), y2), (u(x0 + 17), y2))
        S.wire((u(x0 + 7), y2), f"{ca}.1")
        S.wire((u(x0 + 10), y2), f"{cb}.1")
        S.pwr_at(net, (u(x0 + 13), y2))
        S.flag((u(x0 + 17), y2))
        S.on("+5V", f"{fb}.1")
        S.on(net, f"{fb}.2", f"{ca}.1", f"{cb}.1")

    # 2.8 В для МШУ
    y3 = u(56)
    S.add("U2", "Regulator_Linear:LP5907MFX-2.8", "LP5907MFX-2.8", None,
          fields=note("малошумящий, 250 мА; МШУ: BGA524N6 1.5–3.3 В, BGA855N6 1.1–3.3 В [ВД]"))
    S.place("U2.1", u(16), y3)
    S.pwr_at("+5V", (u(10), y3))
    two(S, "C7", "1u", "C0402", (u(13), u(58)), False, "по паспорту U2")
    S.pwr("C7.2", "GND")
    S.wire((u(10), y3), (u(13), y3), (u(14), y3), "U2.1")
    S.wire((u(13), y3), "C7.1")
    S.wire("U2.3", (u(14), u(57)), (u(14), y3))
    S.on("+5V", "U2.1", "U2.3", "C7.1")
    S.pwr("U2.2", "GND")
    S.nc("U2.4")
    two(S, "C8", "1u", "C0402", (u(25), u(58)), False, "по паспорту U2")
    S.pwr("C8.2", "GND")
    S.wire("U2.5", (u(25), y3), (u(28), y3))
    S.wire((u(25), y3), "C8.1")
    S.pwr_at("+2V8", (u(28), y3))
    S.on("+2V8", "U2.5", "C8.1")

    S.flag((u(40), u(55)))
    S.wire((u(40), u(55)), (u(40), u(57)))
    S.pwr_at("GND", (u(40), u(57)))

    S.text("Ток потребления ~200 мА [О]: LTC5510 105 мА (паспорт, табл. 7), антенна 15–45 мА, МШУ ×3, светодиоды.\n"
           "VIN после D1: 7–12 В минус ~0.4 В. U1 рассеивает (VIN − 5 В) × I ≈ 0.6 Вт при 9 В.", u(8), u(66))
    return S


# ---------------------------------------------------------------- B. Вход антенны, Bias-T

def sheet_B(libs):
    S = Sheet(libs, "B", "B_antenna.kicad_sch", "B. Вход антенны и Bias-T")
    S.add("U3", "gnss-fe:TPS2553DBV", "TPS2553DBV", None,
          fields=note("порог 110/130/150 мА (мин/тип/макс) при R_ILIM = 210 кОм [ВД, SLVS841F]; антенна 15–45 мА"))
    S.place("U3.6", u(22), u(20))
    S.wire("U3.1", (u(11), u(20)), (u(10), u(20)))
    S.wire("U3.3", (u(11), u(22)), (u(11), u(20)))
    S.pwr_at("+5V_ANT_IN", (u(10), u(20)))
    S.on("+5V_ANT_IN", "U3.1", "U3.3")
    S.pwr("U3.2", "GND")
    two(S, "R8", "210k 1%", "R0402", (u(18), u(27)), False, "R_ILIM [ВД, SLVS841F, табл. IOS]")
    S.wire("U3.5", "R8.1")
    S.pwr("R8.2", "GND")
    S.on("B_ILIM", "U3.5", "R8.1")
    S.label("U3.4", "ANT_FLT", u(1))

    # ANT_DC: выход ключа → дроссель → антенна
    two(S, "C9", "100p C0G", "C0402", (u(28), u(22)), False, "развязка по ВЧ со стороны питания", fpos="left")
    two(S, "C10", "10n", "C0402", (u(31), u(22)), False)
    S.pwr("C9.2", "GND")
    S.pwr("C10.2", "GND")
    two(S, "L1", "47nH", "L0402", (u(34), u(25)), False,
        "проволочный, 39–56 нГн, резонанс выше 2 ГГц; импеданс ≥ 300 Ом на 1.1–1.7 ГГц — сверить по графику [О]")
    S.add("TP1", "Connector:TestPoint", "ANT_DC", FP["TP"], fields=note("напряжение на антенне"))
    S.place("TP1.1", u(38), u(20))
    S.wire("U3.6", (u(24), u(20)), (u(28), u(20)), (u(31), u(20)), (u(34), u(20)), "TP1.1")
    S.wire((u(28), u(20)), "C9.1")
    S.wire((u(31), u(20)), "C10.1")
    S.wire((u(34), u(20)), "L1.1")
    S.wlabel("ANT_DC", (u(24), u(20)))
    S.on("ANT_DC", "U3.6", "C9.1", "C10.1", "L1.1", "TP1.1")

    # ANT: разъём → защита → развязка → делитель
    S.add("J2", "Connector:Conn_Coaxial", "ANT", FP["SMA"], mirror="y", fpos={"Reference": (0, -u(1.9)), "Value": (-u(1.9), u(1.3))},
          fields=note("SMA торцевое; антенна с МШУ 28–40 дБ, кабель ~5 м"))
    S.place("J2.1", u(16), u(32))
    S.pwr("J2.2", "GND")
    S.add("D2", "Device:D_TVS_Small", "ESD ≤0.3pF", FP["D0402"], rot=90, fpos="right",
          fields=note("защита от статики: ёмкость ≤ 0.3 пФ, рабочее ≥ 5.5 В — подобрать [О]"))
    S.place("D2.2", u(20), u(34))
    S.pwr("D2.1", "GND")
    two(S, "C11", "100p C0G", "C0402", (u(40), u(32)), True,
        "разделительный; около 1 ГГц близок к последовательному резонансу [О]")
    S.wire("J2.1", (u(20), u(32)), (u(26), u(32)), (u(34), u(32)), "C11.1")
    S.wire((u(20), u(32)), "D2.2")
    S.wire("L1.2", (u(34), u(32)))
    S.wlabel("ANT", (u(26), u(32)))
    S.on("ANT", "J2.1", "D2.2", "L1.2", "C11.1")
    S.wire("C11.2", (u(46), u(32)))
    S.hlabel("DIV_IN", (u(46), u(32)), "right", "output")
    S.on("DIV_IN", "C11.2")

    # Индикатор аварии антенны
    two(S, "R2", "1k", "R0603", (u(48), u(14)), False)
    S.pwr("R2.1", "+5V_ANT_IN")
    S.add("LED2", "Device:LED_Small", "красный", FP["LED0603"], rot=90, fields=note("«авария антенны»: горит при КЗ"),
          fpos="right")
    S.place("LED2.2", u(48), u(17))
    S.wire("R2.2", "LED2.2")
    S.wire("LED2.1", (u(48), u(20)), (u(49), u(20)))
    S.wlabel("ANT_FLT", (u(49), u(20)), "right")
    S.on("ANT_FLT", "LED2.1")
    S.on("B_LED2", "R2.2", "LED2.2")
    S.text("U3: EN — активный высокий, ~FAULT — открытый сток, активный низкий [ВД, SLVS841F].\n"
           "Защита от статики стоит до дросселя: ёмкость D2 — прямо на входе тракта.", u(8), u(40))
    return S


# ---------------------------------------------------------------- C. Делитель

def sheet_C(libs):
    S = Sheet(libs, "C", "C_divider.kicad_sch", "C. Делитель 1:2 + 1:2")
    txt = "плечи λ/4 70.7 Ом на ~1.38 ГГц, на FR4 ~30 мм; медь — после расчёта под стек фабрики (HFSS/openEMS) [О]"
    for ref, cx, cy in (("DIV1", 22, 40), ("DIV2", 38, 25), ("DIV3", 38, 55)):
        S.add(ref, "gnss-fe:Wilkinson", "Wilkinson_λ/4", "", at=(u(cx), u(cy)), fields=note(txt))
    for ref, x, y in (("R3", 28, 39), ("R4", 44, 24), ("R5", 44, 54)):
        two(S, ref, "100R 1%", "R0402", (u(x), u(y)), False, "развязывающий резистор делителя Уилкинсона")
    S.hlabel("DIV_IN", (u(14), u(40)), "left", "input")
    S.wire((u(14), u(40)), "DIV1.1")
    S.on("DIV_IN", "DIV1.1")
    S.wire("DIV1.2", "R3.1", (u(30), u(39)), (u(30), u(25)), (u(32), u(25)), "DIV2.1")
    S.wire("DIV1.3", "R3.2", (u(30), u(41)), (u(30), u(55)), (u(32), u(55)), "DIV3.1")
    S.wlabel("DIV_A", (u(32), u(25)))
    S.wlabel("DIV_B", (u(32), u(55)))
    S.on("DIV_A", "DIV1.2", "R3.1", "DIV2.1")
    S.on("DIV_B", "DIV1.3", "R3.2", "DIV3.1")
    for div, r, pa, pb, y in (("DIV2", "R4", "P1", "P2", 24), ("DIV3", "R5", "P3", "P4", 54)):
        S.wire(f"{div}.2", f"{r}.1", (u(50), u(y)))
        S.wire(f"{div}.3", f"{r}.2", (u(50), u(y + 2)))
        S.hlabel(pa, (u(50), u(y)), "right", "output")
        S.hlabel(pb, (u(50), u(y + 2)), "right", "output")
        S.on(pa, f"{div}.2", f"{r}.1")
        S.on(pb, f"{div}.3", f"{r}.2")
    S.text("P1 — L5 (блок D), P2 — L1 (блок E): с одного делителя, чтобы тракты ядра были симметричны.\n"
           "P3 — L2 (блок F), P4 — OUT4 (блок G). Делитель ~7 дБ стоит до усилителей и почти не стоит по шуму [О, calc/budget.py].\n"
           "Символ DIV — два плеча λ/4 70.7 Ом; на плате это медь (посадочное место с net tie), пока не назначено.",
           u(8), u(62))
    return S


# ---------------------------------------------------------------- D, F. Прямые тракты

def lna_path(S, p_in, tag, saw, saw_val, saw_txt, saw_fp, lmatch, lna_ref, lna_part, cdec, cdc, jref, jval,
             r0=None, extra=None):
    y = u(30)
    S.hlabel(p_in, (u(10), y), "left", "input")
    if r0:
        two(S, r0, "0R", "R0402", (u(13), y), True, "перемычка: мерить узлы по отдельности")
        S.wire((u(10), y), f"{r0}.1")
        S.on(p_in, f"{r0}.1")
    S.add(saw, "gnss-fe:SAW_5pin", saw_val, saw_fp, fields=note(saw_txt, **(extra or {})))
    S.place(f"{saw}.1", u(19), y)
    if r0:
        S.wire(f"{r0}.2", (u(17), y), f"{saw}.1")
        S.wlabel(f"{tag}_IN", (u(17), y))
        S.on(f"{tag}_IN", f"{r0}.2", f"{saw}.1")
    else:
        S.wire((u(10), y), f"{saw}.1")
        S.on(p_in, f"{saw}.1")
    bus(S, [f"{saw}.2", f"{saw}.3", f"{saw}.5"], "GND", u(1))
    two(S, lmatch, "9.4nH", "L0402", (u(29), y), True, "Murata LQW15, согласование входа [ВД, BGA855N6, табл. 6]")
    S.wire(f"{saw}.4", (u(27), y), f"{lmatch}.1")
    S.wlabel(f"{tag}_SAW", (u(27), y))
    S.on(f"{tag}_SAW", f"{saw}.4", f"{lmatch}.1")
    S.add(lna_ref, f"gnss-fe:{lna_part}", lna_part, None,
          fields=note("1164–1300 МГц, 17.8 дБ, Кш 0.6 дБ [ВД]; PON — к питанию"))
    S.place(f"{lna_ref}.5", u(34), y)  # центр u38, AO u42
    S.wire(f"{lmatch}.2", f"{lna_ref}.5")
    S.on(f"{tag}_AI", f"{lmatch}.2", f"{lna_ref}.5")
    bus(S, [f"{lna_ref}.2", f"{lna_ref}.6"], "+2V8", -u(1), at=u(38))
    bus(S, [f"{lna_ref}.1", f"{lna_ref}.4"], "GND", u(1), at=u(38))
    decap(S, cdec, "1n", "C0402", u(44), u(22), "+2V8", "ВЧ-развязка у вывода 2 [ВД, табл. 6: ≥ 1 нФ]")
    two(S, cdc, "100p C0G", "C0402", (u(46), y), True,
        "разделительный; обязателен на OUT3 — HackRF может подать на порт 3.3 В" if jval == "OUT3" else "разделительный [О]")
    S.wire(f"{lna_ref}.3", (u(44), y), f"{cdc}.1")
    S.wlabel(f"{tag}_LNA", (u(44), y))
    S.on(f"{tag}_LNA", f"{lna_ref}.3", f"{cdc}.1")
    S.add(jref, "Connector:Conn_Coaxial", jval, FP["SMA"], fpos={"Reference": (0, -u(1.9)), "Value": (u(1.9), u(1.3))}, fields=note("SMA торцевое"))
    S.place(f"{jref}.1", u(52), y)
    S.pwr(f"{jref}.2", "GND")
    S.wire(f"{cdc}.2", (u(50), y), f"{jref}.1")
    S.wlabel(jval, (u(50), y))
    S.on(jval, f"{cdc}.2", f"{jref}.1")


def sheet_D(libs):
    S = Sheet(libs, "D", "D_L5.kicad_sch", "D. Тракт L5 → OUT1 (LibreSDR RX1)")
    lna_path(S, "P1", "L5", "FL1", "NDFH059-1176SA",
             "ПАВ L5 1176.45 МГц, 1.1×0.9 мм, потери ≤ 1.6 дБ в 1166–1187 МГц [ВД]; запасные: Qorvo QPQ1062, Abracon AFII-SW-0060",
             FP["SAW"], "L2", "U4", "BGA855N6", "C12", "C13", "J3", "OUT1", r0="R9",
             extra={"LCSC": "C5158023"})
    S.text("Разделительный 1 нФ на входе МШУ не нужен: постоянный ток не проходит через ПАВ [ВД, сноска к табл. 6 BGA524N6].\n"
           "Земли ПАВ и МШУ — переходными отверстиями прямо у площадок.", u(8), u(40))
    return S


def sheet_F(libs):
    S = Sheet(libs, "F", "F_L2.kicad_sch", "F. Тракт L2 → OUT3 (HackRF)")
    lna_path(S, "P3", "L2", "FL4", "SAW_L2",
             "ПАВ L2 1227.6 МГц: кандидаты Qorvo QPQ1061 (31 МГц, 1.4×1.2 мм), Microchip TFS1227K (24 МГц, 1.4×1.1 мм) [ВИ]; "
             "выводы и посадочное — по паспорту выбранного",
             "", "L7", "U7", "BGA855N6", "C23", "C24", "J5", "OUT3")
    S.text("FL4: символ с нумерацией Huaying (1 — вход, 4 — выход); у выбранного ПАВ L2 сверить и поправить.\n"
           "ГЛОНАСС G2 (1243–1249 МГц) у найденных ПАВ не покрыт или покрыт краем — G2 через OUT4 [ВИ].", u(8), u(40))
    return S


# ---------------------------------------------------------------- E. L1 → смеситель → OUT2

def sheet_E(libs):
    S = Sheet(libs, "E", "E_L1_mixer.kicad_sch", "E. Тракт L1 → смеситель LTC5510 → OUT2 (LibreSDR RX2)", paper="A3")
    y = u(20)
    S.hlabel("P2", (u(8), y), "left", "input")
    two(S, "R10", "0R", "R0402", (u(12), y), True, "перемычка: мерить узлы по отдельности")
    S.wire((u(8), y), "R10.1")
    S.on("P2", "R10.1")
    S.add("FL2", "gnss-fe:SAW_5pin", "NDFH003-1580SA", FP["SAW"],
          fields=note("ПАВ L1 широкий: 1559–1606 МГц, потери ≤ 1.6–2.1 дБ [ВД]; подавление на 960–1427 МГц (L5!) "
                      "в паспорте не нормировано — замерить, нужно ≥ 30 дБ на 1164–1189 МГц; запасной Murata SAFFB1G56KB0F0A",
                      LCSC="C312141"))
    S.place("FL2.1", u(20), y)
    S.wire("R10.2", (u(16), y), "FL2.1")
    S.wlabel("L1_IN", (u(16), y))
    S.on("L1_IN", "R10.2", "FL2.1")
    bus(S, ["FL2.2", "FL2.3", "FL2.5"], "GND", u(1))
    two(S, "L3", "8.2nH", "L0402", (u(31), y), True, "Murata LQW, согласование входа [ВД, BGA524N6, табл. 6]")
    S.wire("FL2.4", (u(28), y), "L3.1")
    S.wlabel("L1_SAW", (u(28), y))
    S.on("L1_SAW", "FL2.4", "L3.1")
    S.add("U5", "gnss-fe:BGA524N6", "BGA524N6", None,
          fields=note("1550–1615 МГц, 19.6 дБ, Кш 0.73 дБ на 2.8 В [ВИ]", LCSC="C6752883"))
    S.place("U5.5", u(36), y)
    S.wire("L3.2", "U5.5")
    S.on("E_AI", "L3.2", "U5.5")
    bus(S, ["U5.2", "U5.6"], "+2V8", -u(1), at=u(40))
    bus(S, ["U5.1", "U5.4"], "GND", u(1), at=u(40))
    decap(S, "C14", "1u", "C0402", u(45), u(12), "+2V8", "у вывода 2; ≥ 10 нФ, в паспорте 1 мкФ [ВД, табл. 6]")
    two(S, "R11", "0R", "R0402", (u(48), y), True, "перемычка: мерить МШУ и смеситель по отдельности")
    S.wire("U5.3", (u(45), y), "R11.1")
    S.wlabel("L1_LNA", (u(45), y))
    S.on("L1_LNA", "U5.3", "R11.1")

    # Вход смесителя: TC1-1-13M+ (1:1), C1, C2 = 0.1 мкФ, C3 = 0.7 пФ — как на DC1983A (рис. 1)
    S.add("T1", "Transformer:TC1-1-13M+", "TC1-1-13M+", None, rot=180, fpos={"Reference": (0, -u(1.7)), "Value": (u(1), u(2.4))},
          fields=note("1:1, вход несимметричный: 3 — сигнал, 1 — земля; 4, 6 — к IN+/IN− [ВД, LTC5510 рис. 1–2]"))
    S.place("T1.3", u(56), y)
    S.wire("R11.2", (u(52), y), "T1.3")
    S.wlabel("MIX_IN", (u(52), y))
    S.on("MIX_IN", "R11.2", "T1.3")
    S.pwr("T1.1", "GND", u(1))
    two(S, "C18", "0.7p C0G", "C0402", (u(62), y), False, "как C3 на DC1983A (рис. 1, вход 30–3000 МГц) [ВД]")
    two(S, "C16", "100n", "C0402", (u(66), y), True, "C1 на DC1983A [ВД]", fpos="above")
    two(S, "C17", "100n", "C0402", (u(66), u(22)), True, "C2 на DC1983A [ВД]", fpos="below")
    S.add("U6", "gnss-fe:LTC5510", "LTC5510IUF", None,
          fields=note("смеситель; гетеродин от TX1 +0.4…+3.4 дБм при окне −6…+6 дБм [ВД, И]", LCSC="C459909"))
    S.place("U6.2", u(71), y)
    S.wire("T1.4", "C18.1", "C16.1")
    S.wire("T1.6", "C18.2", "C17.1")
    S.wire("C16.2", "U6.2")
    S.wire("C17.2", "U6.3")
    S.on("E_T1A", "T1.4", "C18.1", "C16.1")
    S.on("E_T1B", "T1.6", "C18.2", "C17.1")
    S.on("MIX_INP", "C16.2", "U6.2")
    S.on("MIX_INN", "C17.2", "U6.3")

    # Питание LTC5510: VCC1, VCC2, EN — к +5V_MIX; развязка 10 нФ у выводов и 1 мкФ
    bus(S, ["U6.6", "U6.7", "U6.5"], "+5V_MIX", -u(2), at=u(76))
    decap(S, "C19", "10n", "C0402", u(64), u(11), "+5V_MIX", "у выводов 6, 7 [ВД, Pin Functions]")
    decap(S, "C20", "1u", "C0603", u(68), u(11), "+5V_MIX", "C6 на DC1984A [ВД]")

    # Гетеродин: LO+ через 0.1 мкФ, LO− — на землю через 0.1 мкФ (несимметричный вход)
    S.hlabel("LO_HPF", (u(61), u(26)), "left", "input")
    two(S, "C22", "100n", "C0402", (u(67), u(26)), True, "C4 на DC1984A [ВД]", fpos="above")
    S.wire((u(61), u(26)), "C22.1")
    S.wire("C22.2", "U6.15")
    S.on("LO_HPF", "C22.1")
    S.on("MIX_LO", "C22.2", "U6.15")
    two(S, "C21", "100n", "C0402", (u(69), u(28)), False, "C5 на DC1984A [ВД]", fpos="left")
    S.wire("U6.14", "C21.1")
    S.pwr("C21.2", "GND")
    S.on("MIX_LON", "U6.14", "C21.1")

    # Низ корпуса: LGND через L4, IADJ — R6 не ставится, TP и земли
    two(S, "L4", "0R", "L0603", (u(71), u(34)), False,
        "место под дроссель; ток ~64 мА; 0 Ом при входе выше 1 ГГц [ВД, рис. 1–2]", fpos="left")
    S.wire("U6.4", (u(73), u(33)), (u(71), u(33)), "L4.1")
    S.pwr("L4.2", "GND")
    S.on("MIX_LGND", "U6.4", "L4.1")
    two(S, "R6", "4.75k", "R0402", (u(74), u(34)), False,
        "не ставить: при 5 В и fOUT < 1200 МГц IADJ открыт [ВД, табл. 7]; место — для подбора", dnp=True)
    S.wire("U6.8", "R6.1")
    S.pwr("R6.2", "GND")
    S.on("MIX_IADJ", "U6.8", "R6.1")
    bus(S, ["U6.16", "U6.9", "U6.12", "U6.13", "U6.17"], "GND", u(1), at=u(79))
    S.add("TP2", "Connector:TestPoint", "TEMP", FP["TP"], rot=180,
          fields=note("диод на кристалле через 30 Ом: температура смесителя (уход DCB) [ВД]"))
    S.place("TP2.1", u(82), u(33))
    S.wire("U6.1", (u(82), u(28)), "TP2.1")
    S.on("MIX_TEMP", "U6.1", "TP2.1")

    # Выход: L5, L6 = 15 нГн и TC4-19LN+, питание через средний отвод — как на DC1984A (рис. 2)
    two(S, "L5", "15nH", "L0402", (u(86), y), True, "L4 на DC1984A, CoilCraft 0402HP [ВД]; подбор по S21 на 1176 МГц",
        fpos="above")
    two(S, "L6", "15nH", "L0402", (u(86), u(24)), True, "L5 на DC1984A [ВД]; подбор по S21 на 1176 МГц", fpos="below")
    two(S, "L8", "DNP", "L0603", (u(84), u(17)), False,
        "L1 на DC1984A (не ставится); оценка 15 нГн — резонанс с 0.6 пФ выхода на 1176 МГц [О]", dnp=True, fpos="left")
    two(S, "L9", "DNP", "L0603", (u(84), u(25)), False, "L2 на DC1984A (не ставится); см. L8 [О]", dnp=True, fpos="left")
    S.wire("U6.11", (u(84), y), "L5.1")
    S.wire((u(84), y), "L8.2")
    S.wire("U6.10", (u(84), u(24)), "L6.1")
    S.wire((u(84), u(24)), "L9.1")
    S.pwr("L8.1", "+5V_MIX")
    S.pwr("L9.2", "+5V_MIX")
    S.on("MIX_OUTP", "U6.11", "L5.1", "L8.2")
    S.on("MIX_OUTN", "U6.10", "L6.1", "L9.1")
    S.add("T2", "gnss-fe:TC4-19LN", "TC4-19LN+", None,
          fields=note("4:1, 10–1900 МГц; ток через средний отвод 2 × 32 мА ≤ 150 мА [ВД]"))
    S.place("T2.3", u(91), y)
    S.wire("L5.2", "T2.3")
    S.wire("L6.2", "T2.1")
    S.on("E_T2S", "L5.2", "T2.3")
    S.on("E_T2SN", "L6.2", "T2.1")
    S.pwr("T2.2", "+5V_MIX", u(1))
    decap(S, "C26", "10n", "C0402", u(94), u(11), "+5V_MIX", "у вывода 2 T2 (C8 на DC1984A) [ВД]")
    two(S, "C29", "DNP", "C0402", (u(99), u(21)), False, "место под подбор параллельно первичной обмотке T2 [О]",
        dnp=True)
    two(S, "C27", "10n", "C0402", (u(102), y), True, "разделительный: C9 на DC1984A [ВД]", fpos="above")
    two(S, "C28", "10n", "C0402", (u(101), u(25)), False, "второй конец первичной — на землю по ВЧ (C10 на DC1984A) [ВД]")
    S.wire("T2.6", (u(99), y), "C27.1")
    S.wire((u(99), y), "C29.1")
    S.wire("T2.4", (u(99), u(24)), (u(101), u(24)), "C28.1")
    S.wire("C29.2", (u(99), u(24)))
    S.pwr("C28.2", "GND")
    S.on("E_T2P", "T2.6", "C29.1", "C27.1")
    S.on("E_T2PN", "T2.4", "C29.2", "C28.1")
    S.add("FL3", "RF_Filter:LFCN-1575", "LFCN-1575+", None,
          fields=note("ФНЧ DC–1575 МГц, 37 дБ на 2700 МГц [ВД]; аналог LFCG-1575+ (LCSC C4989936)"))
    S.place("FL3.1", u(109), y)
    S.pwr("FL3.2", "GND")
    S.on("GND", "FL3.4")
    S.wire("C27.2", (u(106), y), "FL3.1")
    S.wlabel("IF_OUT", (u(106), y))
    S.on("IF_OUT", "C27.2", "FL3.1")
    two(S, "C15", "100p C0G", "C0402", (u(122), y), True, "разделительный [О]")
    S.wire("FL3.3", (u(118), y), "C15.1")
    S.wlabel("IF_LPF", (u(118), y))
    S.on("IF_LPF", "FL3.3", "C15.1")
    S.add("J4", "Connector:Conn_Coaxial", "OUT2", FP["SMA"], fpos={"Reference": (0, -u(1.9)), "Value": (u(1.9), u(1.3))}, fields=note("SMA торцевое → LibreSDR RX2"))
    S.place("J4.1", u(129), y)
    S.pwr("J4.2", "GND")
    S.wire("C15.2", (u(126), y), "J4.1")
    S.wlabel("OUT2", (u(126), y))
    S.on("OUT2", "C15.2", "J4.1")

    S.text("Главный риск — выход на 1176 МГц: DC1984A охарактеризована с выходом 10–1300 МГц (возвратные потери ≥ 12 дБ),\n"
           "DC1983A — с выходом 1575 МГц; на 1176 МГц усиление и Кш в паспорте не приведены [ВД]. Выход LTC5510 — 201 Ом || 0.6 пФ\n"
           "дифференциально на 1500 МГц [ВД]; 0.6 пФ на 1176 МГц — 225 Ом, поэтому оставлены места L8, L9 (резонанс при ~15 нГн\n"
           "на плечо [О]) и C29. Подбирать по максимуму S21 петлёй LibreSDR на 1176 МГц.\n"
           "Питание выходов: 32 мА на вывод [ВД] через средний отвод T2 (вывод 2). На первичной обмотке TC4-19LN+ — разделительные\n"
           "конденсаторы с обеих сторон (C27, C28): обмотки соединены по постоянному току [ВД, паспорт TC4-19LN+].\n"
           "R6 (IADJ) не ставится: табл. 7 паспорта — при 5 В и fOUT < 1200 МГц вывод открыт, ICC 105 мА [ВД].\n"
           "Экран-рамка (лист I) — над U6, T1, T2 и трактом гетеродина.", u(8), u(40))
    return S


# ---------------------------------------------------------------- G. OUT4

def sheet_G(libs):
    S = Sheet(libs, "G", "G_OUT4.kicad_sch", "G. OUT4 — широкая полоса")
    y = u(30)
    S.hlabel("P4", (u(10), y), "left", "input")
    two(S, "R7", "49.9R", "R0402", (u(14), u(32)), False,
        "ставится вместо J6, если выход не нужен: неподключённый выход закрывать 50 Ом", dnp=True)
    S.pwr("R7.2", "GND")
    two(S, "C25", "100p C0G", "C0402", (u(18), y), True, "разделительный")
    S.wire((u(10), y), (u(14), y), "C25.1")
    S.wire((u(14), y), "R7.1")
    S.on("P4", "R7.1", "C25.1")
    S.add("J6", "Connector:Conn_Coaxial", "OUT4", FP["SMA"], fpos={"Reference": (0, -u(1.9)), "Value": (u(1.9), u(1.3))},
          fields=note("SMA торцевое: HackRF на G1, E6/B3, L3OC или контроль спектра"))
    S.place("J6.1", u(26), y)
    S.pwr("J6.2", "GND")
    S.wire("C25.2", (u(22), y), "J6.1")
    S.wlabel("OUT4", (u(22), y))
    S.on("OUT4", "C25.2", "J6.1")
    return S


# ---------------------------------------------------------------- H. Гетеродин

def sheet_H(libs):
    S = Sheet(libs, "H", "H_LO.kicad_sch", "H. Вход гетеродина")
    y = u(30)
    S.add("J7", "Connector:Conn_Coaxial", "LO", FP["SMA"], mirror="y", fpos={"Reference": (0, -u(1.9)), "Value": (-u(1.9), u(1.3))},
          fields=note("SMA торцевое ← LibreSDR TX1, 2751.87 МГц, тон DDS"))
    S.place("J7.1", u(16), y)
    S.pwr("J7.2", "GND")
    S.add("FL5", "gnss-fe:HFCN-2275", "HFCN-2275+", None,
          fields=note("давит шум TX в L-диапазоне: ≥ 40 дБ на 1400 МГц [ВД]"))
    S.place("FL5.1", u(22), y)
    S.pwr("FL5.2", "GND")
    S.on("GND", "FL5.4")
    S.wire("J7.1", (u(18), y), "FL5.1")
    S.wlabel("LO_IN", (u(18), y))
    S.on("LO_IN", "J7.1", "FL5.1")
    S.wire("FL5.3", (u(36), y))
    S.hlabel("LO_HPF", (u(36), y), "right", "output")
    S.on("LO_HPF", "FL5.3")
    S.text("Уровень гетеродина — программно (lo_attenuation_db в gnss-sdr). TX1 +0.4…+3.4 дБм при полной шкале DDS\n"
           "(замер 2026-10-28, ±3 дБ [И]), потери ФВЧ ~1 дБ [О] — начать с 0 дБ ослабления.", u(8), u(40))
    return S


# ---------------------------------------------------------------- I. Конструкция

def sheet_I(libs):
    S = Sheet(libs, "I", "I_mech.kicad_sch", "I. Конструкция")
    S.add("SH1", "gnss-fe:Shield", "BMI-S-203-F", "RF_Shielding:Laird_Technologies_BMI-S-203-F_26.21x26.21mm",
          at=(u(14), u(20)), fields=note("размер — по разводке [О]; над U6, T1, T2 и трактом гетеродина"))
    S.pwr("SH1.1", "GND")
    S.text("Плата — 4 слоя, 1.6 мм; второй слой — сплошная земля; копланарные линии 50 Ом с землёй;\n"
           "переходные отверстия вдоль линий и у земляных площадок ПАВ и МШУ. Ширину линий 50 и 70.7 Ом —\n"
           "по стеку выбранной фабрики [О].\n"
           "Все SMA — торцевые, на двух кромках: ANT, LO и питание — на одной, OUT1–OUT4 — на другой.\n"
           "Гнездо питания: центр 6.5 мм над платой — отверстие в панели корпуса на этой высоте.\n"
           "Корпус — алюминиевая коробка, ориентир внутри ~100 × 80 × 25 мм с пазами под плату [О].", u(8), u(30))
    return S


# ---------------------------------------------------------------- корень и проект

ROOT_SHEETS = [
    # (функция, x, y, ширина, высота, [(вывод, тип, сторона, смещение)])
    (sheet_A, 8, 8, 20, 8, []),
    (sheet_B, 8, 24, 22, 10, [("DIV_IN", "output", "right", 5)]),
    (sheet_C, 40, 20, 18, 18, [("DIV_IN", "input", "left", 9), ("P1", "output", "right", 3),
                               ("P2", "output", "right", 7), ("P3", "output", "right", 11), ("P4", "output", "right", 15)]),
    (sheet_D, 72, 8, 22, 8, [("P1", "input", "left", 4)]),
    (sheet_E, 72, 22, 22, 12, [("P2", "input", "left", 5), ("LO_HPF", "input", "right", 6)]),
    (sheet_F, 72, 40, 22, 8, [("P3", "input", "left", 4)]),
    (sheet_G, 72, 54, 22, 8, [("P4", "input", "left", 4)]),
    (sheet_H, 104, 22, 20, 12, [("LO_HPF", "output", "left", 6)]),
    (sheet_I, 8, 44, 20, 8, []),
]
ROOT_WIRES = [
    [(30, 29), (40, 29)],
    [(58, 23), (62, 23), (62, 12), (72, 12)],
    [(58, 27), (72, 27)],
    [(58, 31), (62, 31), (62, 44), (72, 44)],
    [(58, 35), (60, 35), (60, 58), (72, 58)],
    [(94, 28), (104, 28)],
]


def title_block(title, n):
    return ["title_block", ["title", Q(title)], ["date", Q(DATE)], ["rev", Q("черновик")],
            ["company", Q("gnss-fe: плата v2 — фронтенд L1/L5 к LibreSDR")],
            ["comment", 1, Q("По docs/04-Схема-черновик.md; сгенерировано kicad/tools/gen_sch.py")],
            ["comment", 2, Q("[ВД] паспорт · [ВИ] вторичный источник · [И] измерение · [О] оценка")],
            ["comment", 3, Q("Проверено только по паспортам и нетлисту, не в железе")],
            ["comment", 4, Q(f"Лист {n}")]]


def load_libs():
    std = {"Device": ["R_Small", "C_Small", "L_Small", "FerriteBead_Small", "LED_Small", "D_Schottky_Small",
                      "D_TVS_Small", "Polyfuse_Small"],
           "power": ["GND", "+5V", "+2V8", "PWR_FLAG"],
           "Connector": ["Conn_Coaxial", "TestPoint"],
           "Regulator_Linear": ["AMS1117-5.0", "LP5907MFX-2.8"],
           "RF_Filter": ["LFCN-1575"],
           "Transformer": ["TC1-1-13M+"]}
    libs = {}
    for lib, names in std.items():
        for n in names:
            libs[f"{lib}:{n}"] = flat_symbol(os.path.join(KICAD_SYM_DIR, lib + ".kicad_sym"), n)
    for s in gen_lib.build_symbols():
        libs["gnss-fe:" + s[1]] = s
    return libs


def build_root(libs, sheets):
    R = Sheet(libs, "root", "gnss-fe.kicad_sch", "Плата v2: структура", paper="A3")
    R.sheet_uuid = None
    extra = []
    for n, ((fn, x, y, w, h, pins), S) in enumerate(zip(ROOT_SHEETS, sheets), start=2):
        e = ["sheet", ["at", u(x), u(y)], ["size", u(w), u(h)], ["exclude_from_sim", "no"], ["in_bom", "yes"],
             ["on_board", "yes"], ["dnp", "no"], ["fields_autoplaced", "yes"],
             ["stroke", ["width", 0.1524], ["type", "solid"]], ["fill", ["color", 0, 0, 0, 0.0]],
             ["uuid", S.sheet_uuid],
             ["property", Q("Sheetname"), Q(S.title.split(" (")[0]), ["at", u(x), round(u(y) - 0.7, 4), 0],
              ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left", "bottom"]]],
             ["property", Q("Sheetfile"), Q(S.filename), ["at", u(x), round(u(y + h) + 0.6, 4), 0],
              ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left", "top"], ["hide", "yes"]]]]
        for name, kind, side, off in pins:
            px = u(x) if side == "left" else u(x + w)
            e.append(["pin", Q(name), kind, ["at", px, u(y + off), 180 if side == "left" else 0], ["uuid", uid()],
                      ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left" if side == "left" else "right"]]])
        e.append(["instances", ["project", Q(PROJECT), ["path", Q(f"/{R.file_uuid}"), ["page", Q(str(n))]]]])
        extra.append(e)
    for pts in ROOT_WIRES:
        R.wire(*[(u(a), u(b)) for a, b in pts])
    R.text("Плата v2 (решение 2026-10-28): один вход антенны с Bias-T, делитель 1:2 + 1:2, в каждом плече ПАВ и МШУ,\n"
           "в плече L1 — смеситель LTC5510 (гетеродин 2751.87 МГц от TX1). Схема каналов A.\n"
           "OUT1 — L5 → LibreSDR RX1; OUT2 — L1 на 1176.45 МГц (спектр инвертирован) → RX2; OUT3 — L2 → HackRF;\n"
           "OUT4 — широкая полоса с делителя. Описание — docs/03-Плата-v2.md, черновик схемы — docs/04-Схема-черновик.md.",
           u(8), u(66))
    extra.append(["sheet_instances", ["path", Q("/"), ["page", Q("1")]]])
    return R, extra


def write_project(root_uuid, sheets):
    import json
    pro = {
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3},
        "sheets": [[root_uuid, "Root"]] + [[S.sheet_uuid, S.title.split(" (")[0]] for S in sheets],
        "text_variables": {},
    }
    with open(os.path.join(OUT, f"{PROJECT}.kicad_pro"), "w", encoding="utf-8") as f:
        json.dump(pro, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(OUT, "sym-lib-table"), "w", encoding="utf-8") as f:
        f.write('(sym_lib_table\n\t(version 7)\n\t(lib (name "gnss-fe")(type "KiCad")(uri "${KIPRJMOD}/gnss-fe.kicad_sym")'
                '(options "")(descr "Символы платы v2"))\n)\n')
    with open(os.path.join(OUT, "fp-lib-table"), "w", encoding="utf-8") as f:
        f.write('(fp_lib_table\n\t(version 7)\n\t(lib (name "gnss-fe")(type "KiCad")(uri "${KIPRJMOD}/gnss-fe.pretty")'
                '(options "")(descr "Посадочные места платы v2"))\n)\n')


# ---------------------------------------------------------------- проверка

def expected_groups(sheets):
    nets = {}
    nc = set()
    for S in sheets:
        for net, prefs in S.expect.items():
            nets.setdefault(net, set()).update(prefs)
        nc |= S.nc_pins
    groups = [frozenset(v) for v in nets.values()] + [frozenset([p]) for p in nc]
    seen = {}
    for net, prefs in nets.items():
        for p in prefs:
            if p in seen:
                raise SystemExit(f"вывод {p} задуман в двух цепях: {seen[p]} и {net}")
            seen[p] = net
    return set(groups), seen


def kicad_groups(netfile):
    with open(netfile, encoding="utf-8") as f:
        e = parse(f.read())
    groups = set()
    names = {}
    for net in find_all(find(e, "nets"), "net"):
        nodes = frozenset(f"{find(n, 'ref')[1]}.{find(n, 'pin')[1]}" for n in find_all(net, "node")
                          if not find(n, "ref")[1].startswith("#"))
        if nodes:
            groups.add(nodes)
            names[nodes] = find(net, "name")[1]
    return groups, names


def kicad_cli(tmp, *args):
    cfg = os.path.join(tmp, "kcfg")
    if not os.path.exists(cfg):
        os.makedirs(os.path.join(cfg, "10.0"))
        for name in ("sym-lib-table", "fp-lib-table"):
            shutil.copy(os.path.join("/usr/share/kicad/template", name), os.path.join(cfg, "10.0"))
    r = subprocess.run(["kicad-cli", *args], capture_output=True, text=True,
                       env=dict(os.environ, KICAD_CONFIG_HOME=cfg))
    if r.returncode:
        raise SystemExit(f"kicad-cli {' '.join(args)}: {r.stdout}{r.stderr}")
    return r.stdout


def upgrade(tmp, sheets, root):
    for S in sheets + [root]:
        kicad_cli(tmp, "sch", "upgrade", os.path.join(OUT, S.filename))
    kicad_cli(tmp, "sym", "upgrade", os.path.join(OUT, "gnss-fe.kicad_sym"))
    kicad_cli(tmp, "fp", "upgrade", os.path.join(OUT, "gnss-fe.pretty"))


def erc(tmp, root_path):
    rpt = os.path.join(tmp, "erc.rpt")
    out = kicad_cli(tmp, "sch", "erc", "--severity-all", "-o", rpt, root_path)
    print("ERC:", out.strip().splitlines()[0])
    with open(rpt, encoding="utf-8") as f:
        lines = [l for l in f if l.startswith("[")]
    for l in lines:
        print("  ", l.strip())
    return not lines


def verify(tmp, root_path, sheets):
    exp, where = expected_groups(sheets)
    netfile = os.path.join(tmp, "out.net")
    kicad_cli(tmp, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", netfile, root_path)
    got, names = kicad_groups(netfile)
    ok = True
    for g in sorted(got - exp, key=lambda g: sorted(g)):
        ok = False
        print("  в KiCad, но не задумано:", names.get(g), sorted(g))
    for g in sorted(exp - got, key=lambda g: sorted(g)):
        ok = False
        print("  задумано, но нет в KiCad:", where.get(next(iter(g)), "NC"), sorted(g))
    print(f"нетлист: {len(got)} цепей, " + ("совпадает с задуманным" if ok else "РАСХОЖДЕНИЯ"))
    return ok


def main():
    force = "--force" in sys.argv
    libs = load_libs()
    builders = [b[0] for b in ROOT_SHEETS]
    sheets = [b(libs) for b in builders]
    root, extra = build_root(libs, sheets)
    errs = []
    for S in sheets + [root]:
        errs += S.check()
    if errs:
        print("\n".join(errs))
        raise SystemExit("ошибки геометрии — файлы не записаны")
    targets = [os.path.join(OUT, S.filename) for S in sheets + [root]]
    if not force and any(os.path.exists(t) for t in targets):
        raise SystemExit("листы уже есть; перезапись — только с --force (ручные правки потеряются)")
    gen_lib.write_symbols(os.path.join(OUT, "gnss-fe.kicad_sym"))
    gen_lib.write_footprints(os.path.join(OUT, "gnss-fe.pretty"))
    counters = {}
    for n, S in enumerate(sheets, start=2):
        e = S.build(root.file_uuid, counters, title_block(S.title, n))
        with open(os.path.join(OUT, S.filename), "w", encoding="utf-8") as f:
            f.write(dump(e) + "\n")
    e = root.build(root.file_uuid, counters, title_block(root.title, 1), extra)
    root_path = os.path.join(OUT, root.filename)
    with open(root_path, "w", encoding="utf-8") as f:
        f.write(dump(e) + "\n")
    write_project(root.file_uuid, sheets)
    with tempfile.TemporaryDirectory() as tmp:
        upgrade(tmp, sheets, root)
        ok = verify(tmp, root_path, sheets)
        ok = erc(tmp, root_path) and ok
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

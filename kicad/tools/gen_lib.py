"""Своя библиотека проекта: символы gnss-fe.kicad_sym и посадочные места gnss-fe.pretty.

Источники выводов и размеров — в описании каждого символа и посадочного места.
"""

import os

from kisch import Q, _effects, _prop, dump, find, find_all, flat_symbol, uid, KICAD_SYM_DIR

W = 0.254


def pin(num, name, etype, x, y, ang, length=2.54):
    return ["pin", etype, "line", ["at", x, y, ang], ["length", length],
            ["name", Q(name), _effects()], ["number", Q(num), _effects()]]


def rect(x1, y1, x2, y2, fill="background", dash=False):
    return ["rectangle", ["start", x1, y1], ["end", x2, y2],
            ["stroke", ["width", W], ["type", "dash" if dash else "default"]], ["fill", ["type", fill]]]


def poly(*pts, fill="none", width=W):
    return ["polyline", ["pts"] + [["xy", x, y] for x, y in pts],
            ["stroke", ["width", width], ["type", "default"]], ["fill", ["type", fill]]]


def arc(s, m, e):
    return ["arc", ["start", *s], ["mid", *m], ["end", *e],
            ["stroke", ["width", W], ["type", "default"]], ["fill", ["type", "none"]]]


def dot(x, y, r=0.3):
    return ["circle", ["center", x, y], ["radius", r], ["stroke", ["width", 0], ["type", "default"]],
            ["fill", ["type", "outline"]]]


def gtext(s, x, y, size=1.27):
    return ["text", Q(s), ["at", x, y, 0], _effects(size)]


def symbol(name, ref, value, pins, graphics, fp="", ds="", desc="", ref_at=(0, 0), val_at=(0, 0),
           hide_names=False, name_offset=0.508, ref_just=None, val_just=None):
    s = ["symbol", Q(name), ["pin_names", ["offset", name_offset]] + ([["hide", "yes"]] if hide_names else []),
         ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
         _prop("Reference", ref, *ref_at, justify=ref_just), _prop("Value", value, *val_at, justify=val_just),
         _prop("Footprint", fp, 0, 0, 0, hide=True), _prop("Datasheet", ds, 0, 0, 0, hide=True),
         _prop("Description", desc, 0, 0, 0, hide=True),
         ["symbol", Q(name + "_0_1")] + graphics,
         ["symbol", Q(name + "_1_1")] + pins,
         ["embedded_fonts", "no"]]
    return s


def coil(x, y_top, y_bot, bulge, n=4):
    """Обмотка из n полуокружностей вдоль вертикали x; bulge=+1 — выпуклостью вправо."""
    out = []
    h = (y_top - y_bot) / n
    for i in range(n):
        a = y_top - i * h
        b = a - h
        out.append(arc((x, a), (x + bulge * h / 2, (a + b) / 2), (x, b)))
    return out


def lna(name, desc, ds):
    """BGA524N6 / BGA855N6: TSNP-6-10, выводы 1, 4 — GND; 2 — VCC; 3 — AO; 5 — AI; 6 — PON."""
    return symbol(name, "U", name, [
        pin("5", "AI", "input", -10.16, 0, 0),
        pin("3", "AO", "output", 10.16, 0, 180),
        pin("2", "VCC", "power_in", -2.54, 7.62, 270),
        pin("6", "PON", "input", 2.54, 7.62, 270),
        pin("1", "GND", "power_in", -2.54, -7.62, 90),
        pin("4", "GND", "power_in", 2.54, -7.62, 90),
    ], [rect(-7.62, 5.08, 7.62, -5.08), poly((-1.27, 1.524), (1.524, 0), (-1.27, -1.524), (-1.27, 1.524))],
        fp="gnss-fe:Infineon_TSNP-6-10_0.7x1.1mm_P0.4mm", ds=ds, desc=desc,
        ref_at=(-7.62, 6.35), val_at=(7.62, 6.35), ref_just="right", val_just="left")


def build_symbols():
    syms = []

    # LTC5510 [ВД, паспорт rev. A, Pin Functions]; расположение выводов — по смыслу, не по корпусу.
    syms.append(symbol("LTC5510", "U", "LTC5510", [
        pin("2", "IN+", "passive", -12.7, 10.16, 0),
        pin("3", "IN-", "passive", -12.7, 5.08, 0),
        pin("15", "LO+", "passive", -12.7, -5.08, 0),
        pin("14", "LO-", "passive", -12.7, -10.16, 0),
        pin("11", "OUT+", "passive", 12.7, 10.16, 180),
        pin("10", "OUT-", "passive", 12.7, 0, 180),
        pin("1", "TEMP", "passive", 12.7, -10.16, 180),
        pin("6", "VCC1", "power_in", -2.54, 17.78, 270),
        pin("7", "VCC2", "power_in", 0, 17.78, 270),
        pin("5", "EN", "input", 2.54, 17.78, 270),
        pin("4", "LGND", "passive", -7.62, -20.32, 90),
        pin("8", "IADJ", "passive", -5.08, -20.32, 90),
        pin("16", "TP", "passive", -2.54, -20.32, 90),
        pin("9", "GND", "power_in", 0, -20.32, 90),
        pin("12", "GND", "power_in", 2.54, -20.32, 90),
        pin("13", "GND", "power_in", 5.08, -20.32, 90),
        pin("17", "EP", "power_in", 7.62, -20.32, 90),
    ], [rect(-10.16, 15.24, 10.16, -17.78)],
        fp="Package_DFN_QFN:QFN-16-1EP_4x4mm_P0.65mm_EP2.15x2.15mm_ThermalVias",
        ds="https://www.analog.com/media/en/technical-documentation/data-sheets/5510fa.pdf",
        desc="Активный смеситель 1 МГц – 6 ГГц, вход 50 Ом, гетеродин −6…+6 дБм; корпус UF16 4×4 мм, площадка 2.15×2.15 (рис. на стр. 28 паспорта)",
        ref_at=(-10.16, 18.415), val_at=(-10.16, 16.51), ref_just="right", val_just="right"))

    syms.append(lna("BGA524N6", "МШУ 1550–1615 МГц, Infineon, TSNP-6-10 [ВД, паспорт rev. 3.5]", ""))
    syms.append(lna("BGA855N6", "МШУ 1164–1300 МГц, Infineon, TSNP-6-10 [ВД, паспорт rev. 2.0]", ""))

    # ПАВ Huaying NDFH… 1.1×0.9 мм: 1 — вход, 4 — выход, 2, 3, 5 — земля [ВД, паспорт стр. 3].
    syms.append(symbol("SAW_5pin", "FL", "SAW_5pin", [
        pin("1", "IN", "passive", -7.62, 0, 0),
        pin("4", "OUT", "passive", 7.62, 0, 180),
        pin("2", "GND", "passive", -2.54, -5.08, 90),
        pin("3", "GND", "passive", 0, -5.08, 90),
        pin("5", "GND", "passive", 2.54, -5.08, 90),
    ], [rect(-5.08, 2.54, 5.08, -2.54), gtext("ПАВ", 0, 0, 1.0)],
        hide_names=True, ref_at=(0, 5.334), val_at=(0, 3.556),
        desc="Полосовой ПАВ-фильтр, 5 выводов: 1 — вход, 4 — выход, 2, 3, 5 — земля (Huaying NDFH059/NDFH003). Другой ПАВ — нумерацию сверить"))

    # HFCN-2275+: 1 — RF IN, 3 — RF OUT, 2, 4 — земля, корпус FV1206 [ВД, паспорт Mini-Circuits].
    syms.append(symbol("HFCN-2275", "FL", "HFCN-2275+", [
        pin("1", "IN", "passive", -10.16, 0, 0),
        pin("3", "OUT", "passive", 10.16, 0, 180),
        pin("2", "GND", "passive", 0, -5.08, 90),
        pin("4", "GND", "passive", 0, -5.08, 90),
    ], [rect(-7.62, 2.54, 7.62, -2.54), gtext("ФВЧ 2275", 0, 0, 1.0)],
        fp="Filter:Filter_Mini-Circuits_FV1206",
        ds="https://www.minicircuits.com/pdfs/HFCN-2275+.pdf",
        desc="ФВЧ LTCC, срез 2275 МГц по −3 дБ, ≥ 40 дБ на 1400 МГц, потери ≤ 1.3 дБ в 2640–6230 МГц [ВД]",
        hide_names=True, ref_at=(0, 5.334), val_at=(0, 3.556)))

    # TC4-19LN+: первичная 6 (точка), 4; вторичная 3 (точка), 1, средний отвод 2; вывода 5 нет [ВД, паспорт rev. B].
    # Слева вторичная (200 Ом, к смесителю), справа первичная (50 Ом).
    g = [poly((-5.08, 5.08), (-2.54, 5.08)), poly((-5.08, -5.08), (-2.54, -5.08)), poly((-5.08, 0), (-2.54, 0)),
         poly((5.08, 5.08), (2.54, 5.08)), poly((5.08, -5.08), (2.54, -5.08)),
         dot(-1.27, 5.84), dot(1.27, 5.84), gtext("4:1", 0, 0, 1.0)]
    g += coil(-2.54, 5.08, -5.08, +1) + coil(2.54, 5.08, -5.08, -1)
    syms.append(symbol("TC4-19LN", "T", "TC4-19LN+", [
        pin("3", "S", "passive", -7.62, 5.08, 0),
        pin("2", "CT", "passive", -7.62, 0, 0),
        pin("1", "S", "passive", -7.62, -5.08, 0),
        pin("6", "P", "passive", 7.62, 5.08, 180),
        pin("4", "P", "passive", 7.62, -5.08, 180),
    ], g, fp="Transformer_SMD:Transformer_MiniCircuits_AT224-1A",
        ds="https://www.minicircuits.com/pdfs/TC4-19LN+.pdf",
        desc="ВЧ-трансформатор 4:1, 10–1900 МГц, AT224-1A; ток через средний отвод ≤ 150 мА, на первичной — разделительные конденсаторы [ВД]",
        hide_names=True, ref_at=(0, 8.89), val_at=(0, -8.89)))

    # TPS2553DBV: 1 IN, 2 GND, 3 EN (активный высокий), 4 /FAULT (открытый сток), 5 ILIM, 6 OUT [ВД, SLVS841F].
    syms.append(symbol("TPS2553DBV", "U", "TPS2553DBV", [
        pin("1", "IN", "power_in", -12.7, 2.54, 0),
        pin("3", "EN", "input", -12.7, -2.54, 0),
        pin("6", "OUT", "power_out", 12.7, 2.54, 180),
        pin("4", "~{FAULT}", "open_collector", 12.7, -2.54, 180),
        pin("2", "GND", "power_in", -2.54, -10.16, 90),
        pin("5", "ILIM", "passive", 2.54, -10.16, 90),
    ], [rect(-10.16, 5.08, 10.16, -7.62)], fp="Package_TO_SOT_SMD:SOT-23-6",
        ds="https://www.ti.com/lit/ds/symlink/tps2553.pdf",
        desc="Ключ питания с ограничением тока 75 мА – 1.7 А (R_ILIM 15–232 кОм), флаг аварии; SOT-23-6",
        ref_at=(-10.16, 6.35), val_at=(10.16, 6.35), ref_just="left", val_just="right"))

    # Делитель Уилкинсона: медь на плате, посадочное — после расчёта под стек фабрики.
    g = [rect(-7.62, 5.08, 7.62, -5.08), poly((-7.62, 0), (-5.08, 0)), poly((-5.08, 2.54), (-5.08, -2.54)),
         poly((-5.08, 2.54), (7.62, 2.54)), poly((-5.08, -2.54), (7.62, -2.54)),
         gtext("λ/4", 1.27, 0.889, 0.9), gtext("70.7 Ом", 1.27, -0.889, 0.9)]
    syms.append(symbol("Wilkinson", "DIV", "Wilkinson_λ/4", [
        pin("1", "IN", "passive", -10.16, 0, 0),
        pin("2", "O1", "passive", 10.16, 2.54, 180),
        pin("3", "O2", "passive", 10.16, -2.54, 180),
    ], g, hide_names=True, ref_at=(0, 6.35), val_at=(0, -6.35),
        desc="Делитель Уилкинсона 1:2 на линиях: два плеча λ/4 70.7 Ом на ~1.38 ГГц; развязывающий резистор 100 Ом — отдельной деталью между O1 и O2"))

    syms.append(symbol("Shield", "SH", "Shield", [pin("1", "GND", "passive", 0, -5.08, 90)],
                       [rect(-5.08, 2.54, 5.08, -2.54, fill="none", dash=True), gtext("экран", 0, 0, 1.0)],
                       hide_names=True, ref_at=(0, 5.334), val_at=(0, 3.556),
                       desc="Экран-рамка на плате, земля"))

    # KLS1-DC-005A-2.0: графика Barrel_Jack_Switch; 4 — центральный штырь, 3 — гильза, 2 — переключатель [ВД, чертёж KLS].
    bj = flat_symbol(os.path.join(KICAD_SYM_DIR, "Connector.kicad_sym"), "Barrel_Jack_Switch")
    remap = {"1": "4", "2": "3", "3": "2"}
    bj[1] = Q("KLS1-DC-005A")
    for sub in find_all(bj, "symbol"):
        sub[1] = Q("KLS1-DC-005A" + sub[1][len("Barrel_Jack_Switch"):])
        for p in find_all(sub, "pin"):
            num = find(p, "number")
            num[1] = Q(remap[num[1]])
    for p in find_all(bj, "property"):
        if p[1] == "Value":
            p[2] = Q("KLS1-DC-005A-2.0")
        elif p[1] == "Footprint":
            p[2] = Q("gnss-fe:KLS1-DC-005A")
        elif p[1] == "Description":
            p[2] = Q("Гнездо питания 5.5×2.1 мм на плату, 30 В 1 А; 4 — центр (+), 3 — гильза, 2 — переключатель")
    syms.append(bj)

    # Свои цепи питания — копии power:+5V.
    for net in ("+5V_MIX", "+5V_ANT_IN"):
        p5 = flat_symbol(os.path.join(KICAD_SYM_DIR, "power.kicad_sym"), "+5V")
        p5[1] = Q(net)
        for sub in find_all(p5, "symbol"):
            sub[1] = Q(net + sub[1][len("+5V"):])
        for p in find_all(p5, "property"):
            if p[1] == "Value":
                p[2] = Q(net)
            elif p[1] == "Description":
                p[2] = Q(f'Power symbol creates a global label with name "{net}"')
        syms.append(p5)
    return syms


def write_symbols(path):
    lib = ["kicad_symbol_lib", ["version", "20241209"], ["generator", Q("gen_lib.py")],
           ["generator_version", Q("10.0")]] + build_symbols()
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump(lib) + "\n")


# ---------- посадочные места ----------

def _fp_text(kind, value, x, y, layer, hide=False, size=1.0):
    e = ["property", Q(kind), Q(value), ["at", x, y, 0], ["layer", Q(layer)]]
    if hide:
        e.append(["hide", "yes"])
    e += [["uuid", uid()], ["effects", ["font", ["size", size, size], ["thickness", round(size * 0.15, 3)]]]]
    return e


def _fp_rect(x1, y1, x2, y2, layer, width=0.05, fill="no"):
    return ["fp_rect", ["start", x1, y1], ["end", x2, y2], ["stroke", ["width", width], ["type", "solid"]],
            ["fill", fill], ["layer", Q(layer)], ["uuid", uid()]]


def _fp_line(x1, y1, x2, y2, layer, width=0.12):
    return ["fp_line", ["start", x1, y1], ["end", x2, y2], ["stroke", ["width", width], ["type", "solid"]],
            ["layer", Q(layer)], ["uuid", uid()]]


def _fp_dot(x, y, r, layer):
    return ["fp_circle", ["center", x, y], ["end", x + r, y], ["stroke", ["width", 0], ["type", "solid"]],
            ["fill", "yes"], ["layer", Q(layer)], ["uuid", uid()]]


def _smd(num, x, y, w, h, layers=("F.Cu", "F.Mask", "F.Paste"), shape="rect", mask=None):
    e = ["pad", Q(num), "smd", shape, ["at", x, y], ["size", w, h], ["layers"] + [Q(l) for l in layers]]
    if mask is not None:
        e.append(["solder_mask_margin", mask])
    e.append(["uuid", uid()])
    return e


def _tht(num, x, y, w, h, dw, dh):
    return ["pad", Q(num), "thru_hole", "roundrect", ["at", x, y], ["size", w, h], ["drill", "oval", dw, dh],
            ["layers", Q("*.Cu"), Q("*.Mask")], ["roundrect_rratio", 0.25], ["uuid", uid()]]


def footprint(name, descr, tags, attr, items, ref_y, val_y):
    return ["footprint", Q(name), ["version", "20241229"], ["generator", Q("gen_lib.py")],
            ["generator_version", Q("10.0")], ["layer", Q("F.Cu")], ["descr", Q(descr)], ["tags", Q(tags)],
            _fp_text("Reference", "REF**", 0, ref_y, "F.SilkS"),
            _fp_text("Value", name, 0, val_y, "F.Fab"),
            _fp_text("Datasheet", "", 0, 0, "F.Fab", hide=True),
            _fp_text("Description", "", 0, 0, "F.Fab", hide=True),
            ["attr"] + attr] + items + [["embedded_fonts", "no"]]


def build_footprints():
    fps = []

    # TSNP-6-10: площадки 0.25×0.25, шаг 0.4×0.4, NSMD, трафарет — круги 0.25 при толщине 100 мкм
    # [ВД, BGA524N6 rev. 3.5, рис. 6–7]. Вид сверху: 1 — слева вверху, против часовой.
    pads = []
    for num, (x, y) in {"1": (-0.2, -0.4), "2": (-0.2, 0), "3": (-0.2, 0.4),
                        "4": (0.2, 0.4), "5": (0.2, 0), "6": (0.2, -0.4)}.items():
        pads.append(_smd(num, x, y, 0.25, 0.25, layers=("F.Cu", "F.Mask"), mask=0.05))
        pads.append(_smd("", x, y, 0.25, 0.25, layers=("F.Paste",), shape="circle"))
    fps.append(footprint(
        "Infineon_TSNP-6-10_0.7x1.1mm_P0.4mm",
        "Infineon TSNP-6-10 (BGA524N6, BGA855N6): корпус 0.7×1.1 мм, площадки 0.25×0.25 мм, шаг 0.4 мм, "
        "NSMD, трафарет 100 мкм — круги 0.25 мм (паспорт BGA524N6 rev. 3.5, рис. 6–7)",
        "TSNP-6-10 Infineon LNA", ["smd", "allow_soldermask_bridges"],
        pads + [_fp_rect(-0.35, -0.55, 0.35, 0.55, "F.Fab", 0.1),
                _fp_rect(-0.6, -0.8, 0.6, 0.8, "F.CrtYd", 0.05),
                _fp_dot(-0.6, -0.75, 0.06, "F.SilkS")],
        -1.4, 1.4))

    # ПАВ Huaying 1.1×0.9 мм, вид снизу на стр. 3 паспорта NDFH003/NDFH059: площадки 0.18×0.25,
    # шаг столбцов 0.385, ряды через 0.5; рекомендованного посадочного в паспорте нет — площадки +0.025 на сторону [О].
    pads = []
    for num, (x, y) in {"1": (-0.385, 0), "5": (0, -0.25), "4": (0.385, -0.25),
                        "2": (0, 0.25), "3": (0.385, 0.25)}.items():
        pads.append(_smd(num, x, y, 0.23, 0.30))
    fps.append(footprint(
        "SAW_Huaying_1.1x0.9mm_5pin",
        "ПАВ Huaying NDFH059-1176SA / NDFH003-1580SA, 1.1×0.9×0.65 мм: 1 — вход, 4 — выход, 2, 3, 5 — земля. "
        "Площадки — по чертежу корпуса (вид снизу), рекомендованного посадочного в паспорте нет [О, сверить]",
        "SAW Huaying 1109", ["smd"],
        pads + [_fp_rect(-0.55, -0.45, 0.55, 0.45, "F.Fab", 0.1),
                _fp_rect(-0.8, -0.7, 0.8, 0.7, "F.CrtYd", 0.05),
                _fp_dot(-0.75, 0.45, 0.06, "F.SilkS")],
        -1.3, 1.3))

    # KLS1-DC-005A-2.0, чертёж KLS «P.C.B Layout»: прорези 0.8×3.4 под выводы 4 и 3 через 6 мм по оси,
    # 3.0×0.8 под вывод 2 — на 2.5 мм к передней кромке от вывода 4 и на 4.8 мм вбок; корпус 14.3×9.0,
    # от передней кромки до вывода 4 — 13.5 мм. Кольцо площадок 0.5 мм [О].
    body = [_fp_rect(-13.5, -4.5, 0.8, 4.5, "F.Fab", 0.1),
            _fp_line(-13.5, -4.62, 0.92, -4.62, "F.SilkS"), _fp_line(0.92, -4.62, 0.92, -2.4, "F.SilkS"),
            _fp_line(0.92, 2.4, 0.92, 4.62, "F.SilkS"), _fp_line(0.92, 4.62, -0.6, 4.62, "F.SilkS"),
            _fp_line(-4.4, 4.62, -13.5, 4.62, "F.SilkS"),
            _fp_rect(-13.75, -4.75, 1.3, 5.95, "F.CrtYd", 0.05)]
    fps.append(footprint(
        "KLS1-DC-005A",
        "Гнездо питания KLS1-DC-005A-2.0 (5.5×2.1 мм), на плату; 4 — центральный штырь, 3 — гильза, "
        "2 — переключатель; передняя кромка — x = −13.5 мм; центр гнезда 6.5 мм над платой (чертёж KLS)",
        "DC jack KLS DC-005", ["through_hole"],
        [_tht("4", 0, 0, 1.8, 4.4, 0.8, 3.4), _tht("3", -6, 0, 1.8, 4.4, 0.8, 3.4),
         _tht("2", -2.5, 4.8, 4.0, 1.8, 3.0, 0.8)] + body,
        -6.0, 7.0))
    return fps


def write_footprints(dirpath):
    os.makedirs(dirpath, exist_ok=True)
    for fp in build_footprints():
        with open(os.path.join(dirpath, fp[1] + ".kicad_mod"), "w", encoding="utf-8") as f:
            f.write(dump(fp) + "\n")

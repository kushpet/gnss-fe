"""Примитивы для генерации схем KiCad: S-выражения, библиотеки символов, листы.

Координаты листа — мм, ось Y вниз; координаты символа в библиотеке — ось Y вверх.
Поворот символа `rot` — против часовой стрелки на экране, как в KiCad.
"""

import math
import uuid as _uuid

KICAD_SYM_DIR = "/usr/share/kicad/symbols"
SCH_VERSION = "20250114"
GRID = 1.27


# ---------- S-выражения ----------

class Q(str):
    """Строка, которая пишется в кавычках."""


def parse(text):
    pos = 0
    n = len(text)
    stack = [[]]
    while pos < n:
        c = text[pos]
        if c in " \t\r\n":
            pos += 1
        elif c == "(":
            stack.append([])
            pos += 1
        elif c == ")":
            item = stack.pop()
            stack[-1].append(item)
            pos += 1
        elif c == '"':
            pos += 1
            buf = []
            while text[pos] != '"':
                if text[pos] == "\\":
                    pos += 1
                    buf.append({"n": "\n", "t": "\t"}.get(text[pos], text[pos]))
                else:
                    buf.append(text[pos])
                pos += 1
            pos += 1
            stack[-1].append(Q("".join(buf)))
        else:
            start = pos
            while pos < n and text[pos] not in ' \t\r\n()"':
                pos += 1
            stack[-1].append(text[start:pos])
    return stack[0][0]


def _atom(a):
    if isinstance(a, Q):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(a, float):
        s = f"{a:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(a)


def dump(e, ind=0):
    """Запись в стиле KiCad: короткие списки атомов — в строку, вложенные — с отступом."""
    if not isinstance(e, list):
        return _atom(e)
    if all(not isinstance(x, list) for x in e):
        return "(" + " ".join(_atom(x) for x in e) + ")"
    if e[0] == "pts":
        return "(pts " + " ".join(dump(x) for x in e[1:]) + ")"
    head = []
    rest = list(e)
    while rest and not isinstance(rest[0], list):
        head.append(_atom(rest.pop(0)))
    out = "(" + " ".join(head)
    for x in rest:
        out += "\n" + "\t" * (ind + 1) + dump(x, ind + 1)
    return out + "\n" + "\t" * ind + ")"


def find(e, key):
    for x in e:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(e, key):
    return [x for x in e if isinstance(x, list) and x and x[0] == key]


def uid():
    return Q(str(_uuid.uuid4()))


# ---------- библиотеки символов ----------

_lib_cache = {}


def load_lib(path):
    if path not in _lib_cache:
        with open(path, encoding="utf-8") as f:
            _lib_cache[path] = parse(f.read())
    return _lib_cache[path]


def _lib_symbol(lib, name):
    for s in find_all(lib, "symbol"):
        if s[1] == name:
            return s
    raise KeyError(name)


def _deep(e):
    return [_deep(x) for x in e] if isinstance(e, list) else (Q(e) if isinstance(e, Q) else e)


def flat_symbol(lib_path, name):
    """Символ без `extends`: графика родителя, свойства — свои."""
    lib = load_lib(lib_path)
    s = _deep(_lib_symbol(lib, name))
    ext = find(s, "extends")
    if not ext:
        return s
    parent = flat_symbol(lib_path, ext[1])
    pname = parent[1]
    out = [x for x in s if not (isinstance(x, list) and x and x[0] == "extends")]
    props = {p[1] for p in find_all(out, "property")}
    for x in parent[2:]:
        if isinstance(x, list) and x and x[0] == "symbol":
            sub = _deep(x)
            sub[1] = Q(name + sub[1][len(pname):])
            out.append(sub)
        elif isinstance(x, list) and x and x[0] == "property" and x[1] not in props:
            out.append(_deep(x))
        elif isinstance(x, list) and x and x[0] in ("pin_names", "pin_numbers", "power", "exclude_from_sim", "in_bom", "on_board") \
                and not find(out, x[0]):
            out.insert(2, _deep(x))
    return out


def symbol_pins(sym):
    """{номер: (x, y, угол, имя, тип)} в координатах библиотеки (Y вверх)."""
    pins = {}
    for sub in find_all(sym, "symbol"):
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            num = find(p, "number")[1]
            name = find(p, "name")[1]
            pins[num] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0, name, p[1])
    return pins


# ---------- геометрия ----------

def snap(v):
    return round(round(v / GRID) * GRID, 4)


def rot_vec(dx, dy, rot):
    """Поворот вектора экрана (Y вниз) на rot градусов против часовой."""
    r = math.radians(rot)
    c, s = round(math.cos(r)), round(math.sin(r))
    return dx * c + dy * s, -dx * s + dy * c


DIRS = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}


def dir_name(v):
    for k, d in DIRS.items():
        if d == (round(v[0]), round(v[1])):
            return k
    raise ValueError(v)


# ---------- построитель листа ----------

PROJECT = "gnss-fe"
GROUND_NETS = {"GND"}


def _font(size=1.27):
    return ["font", ["size", size, size]]


def _effects(size=1.27, justify=None, hide=False):
    e = ["effects", _font(size)]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


def _prop(name, value, x, y, angle=0, size=1.27, justify=None, hide=False):
    return ["property", Q(name), Q(value), ["at", x, y, angle], _effects(size, justify, hide)]


class Part:
    pass


class Sheet:
    """Один лист схемы. Ссылки на выводы — 'REF.номер'."""

    def __init__(self, libs, name, filename, title, paper="A4"):
        self.libs = libs            # lib_id -> плоский символ
        self.name = name
        self.filename = filename
        self.title = title
        self.paper = paper
        self.file_uuid = uid()
        self.sheet_uuid = uid()     # uuid листа в корневой схеме
        self.parts = {}
        self.order = []
        self.wires = []
        self.labels = []
        self.power = []
        self.ncs = []
        self.texts = []
        self.expect = {}            # цепь -> множество 'REF.pin'
        self.nc_pins = set()

    # --- детали ---
    def add(self, ref, lib_id, value, fp="", at=(0, 0), rot=0, mirror=None, ds=None, desc=None,
            fields=None, dnp=False, fpos="auto", in_bom=True):
        sym = self.libs[lib_id]
        props = {p[1]: p[2] for p in find_all(sym, "property")}
        c = Part()
        c.ref, c.lib_id, c.value, c.rot, c.mirror = ref, lib_id, value, rot, mirror
        c.x, c.y = at
        c.fp = fp if fp is not None else props.get("Footprint", "")
        if fp == "" and props.get("Footprint"):
            c.fp = props["Footprint"]
        c.ds = ds if ds is not None else props.get("Datasheet", "")
        c.desc = desc if desc is not None else props.get("Description", "")
        c.fields = fields or {}
        c.dnp, c.fpos, c.in_bom = dnp, fpos, in_bom
        c.pins = symbol_pins(sym)
        c.sym = sym
        assert ref not in self.parts, ref
        self.parts[ref] = c
        self.order.append(ref)
        return c

    def _xf(self, c, dx, dy):
        if c.mirror == "y":
            dx = -dx
        elif c.mirror == "x":
            dy = -dy
        return rot_vec(dx, dy, c.rot)

    def pin(self, pref):
        ref, num = pref.split(".")
        c = self.parts[ref]
        px, py = c.pins[num][:2]
        rx, ry = self._xf(c, px, -py)
        return snap(c.x + rx), snap(c.y + ry)

    def pdir(self, pref):
        ref, num = pref.split(".")
        c = self.parts[ref]
        a = math.radians(c.pins[num][2])
        lx, ly = -math.cos(a), -math.sin(a)
        rx, ry = self._xf(c, lx, -ly)
        return round(rx), round(ry)

    def place(self, pref, x, y):
        """Сдвинуть деталь так, чтобы вывод оказался в точке (x, y)."""
        ref = pref.split(".")[0]
        c = self.parts[ref]
        c.x, c.y = 0.0, 0.0
        px, py = self.pin(pref)
        c.x, c.y = snap(x - px), snap(y - py)
        return c

    # --- соединения ---
    def wire(self, *pts):
        pts = [p if isinstance(p, tuple) else self.pin(p) for p in pts]
        for a, b in zip(pts, pts[1:]):
            a, b = (snap(a[0]), snap(a[1])), (snap(b[0]), snap(b[1]))
            assert a[0] == b[0] or a[1] == b[1], ("косой провод", a, b)
            if a != b:
                self.wires.append((a, b))

    def on(self, net, *prefs):
        self.expect.setdefault(net, set()).update(prefs)

    def pwr(self, pref, net, stub=0.0, orient=None, lib=None):
        p = self.pin(pref)
        d = self.pdir(pref)
        end = (snap(p[0] + d[0] * stub), snap(p[1] + d[1] * stub))
        if stub:
            self.wire(p, end)
        if orient is None:
            orient = "down" if net in GROUND_NETS else dir_name(d)
        self.pwr_at(net, end, orient, lib)
        self.on(net, pref)
        return end

    def pwr_at(self, net, p, orient=None, lib=None):
        if orient is None:
            orient = "down" if net in GROUND_NETS else "up"
        if lib is None:
            lib = {"GND": "power:GND", "+5V": "power:+5V", "+2V8": "power:+2V8",
                   "PWR_FLAG": "power:PWR_FLAG"}.get(net, "gnss-fe:" + net)
        if net in GROUND_NETS:
            rot = {"down": 0, "right": 90, "up": 180, "left": 270}[orient]
        else:
            rot = {"up": 0, "left": 90, "down": 180, "right": 270}[orient]
        self.power.append((lib, net, p, rot, orient))

    def flag(self, p, orient="up"):
        self.pwr_at("PWR_FLAG", p, orient)

    def label(self, pref, name, stub=2.54):
        p = self.pin(pref)
        d = self.pdir(pref)
        end = (snap(p[0] + d[0] * stub), snap(p[1] + d[1] * stub))
        self.wire(p, end)
        self.labels.append(("label", name, end, dir_name(d), None))
        self.on(name, pref)

    def wlabel(self, name, p, d="right"):
        """Метка в вершине провода; текст над проводом вправо."""
        self.labels.append(("label", name, p, d, None))

    def hlabel(self, name, p, d, shape="input"):
        self.labels.append(("hierarchical_label", name, p, d, shape))

    def nc(self, pref):
        self.ncs.append(self.pin(pref))
        self.nc_pins.add(pref)

    def text(self, s, x, y, size=1.27, bold=False):
        self.texts.append((s, x, y, size, bold))

    # --- проверки геометрии ---
    def _pin_points(self):
        pts = []
        for ref in self.order:
            for num in self.parts[ref].pins:
                pts.append((self.pin(f"{ref}.{num}"), f"{ref}.{num}"))
        for lib, net, p, rot, o in self.power:
            pts.append((p, net))
        return pts

    @staticmethod
    def _inside(p, a, b):
        if a[0] == b[0] == p[0]:
            return min(a[1], b[1]) < p[1] < max(a[1], b[1])
        if a[1] == b[1] == p[1]:
            return min(a[0], b[0]) < p[0] < max(a[0], b[0])
        return False

    def check(self):
        errs = []
        ends = [p for w in self.wires for p in w]
        pins = self._pin_points()
        for a, b in self.wires:
            for p in ends:
                if self._inside(p, a, b):
                    errs.append(f"{self.name}: конец провода {p} внутри провода {a}-{b}")
            for p, who in pins:
                if self._inside(p, a, b):
                    errs.append(f"{self.name}: вывод {who} {p} на проводе {a}-{b}")
            for _, _, p, _, _ in self.labels:
                if self._inside(p, a, b):
                    errs.append(f"{self.name}: метка {p} внутри провода {a}-{b}")
        for i, (a, b) in enumerate(self.wires):
            for c, d in self.wires[i + 1:]:
                if (a[0] == b[0] == c[0] == d[0] and max(min(a[1], b[1]), min(c[1], d[1])) < min(max(a[1], b[1]), max(c[1], d[1]))) or \
                   (a[1] == b[1] == c[1] == d[1] and max(min(a[0], b[0]), min(c[0], d[0])) < min(max(a[0], b[0]), max(c[0], d[0]))):
                    errs.append(f"{self.name}: провода внахлёст {a}-{b} и {c}-{d}")
        seen = {}
        for p, who in pins:
            if "." not in who:
                continue
            if p in seen and seen[p].split(".")[0] != who.split(".")[0]:
                errs.append(f"{self.name}: выводы {seen[p]} и {who} в одной точке {p}")
            seen.setdefault(p, who)
        return errs

    def _junctions(self):
        cnt = {}
        for a, b in self.wires:
            cnt[a] = cnt.get(a, 0) + 1
            cnt[b] = cnt.get(b, 0) + 1
        for p, _ in self._pin_points():
            if p in cnt:
                cnt[p] += 1
        return [p for p, n in cnt.items() if n >= 3]

    # --- запись ---
    def _field_positions(self, c):
        """Позиции Reference и Value: (x, y, angle, justify)."""
        horiz_rot = c.rot in (90, 270)
        ang = 90 if horiz_rot else 0
        two_pin = len(c.pins) == 2 and c.lib_id.startswith("Device:")
        if two_pin:
            p1, p2 = [self.pin(f"{c.ref}.{n}") for n in c.pins]
            horizontal = p1[1] == p2[1]
            mode = c.fpos
            if mode == "auto":
                mode = "ab" if horizontal else "right"
            if mode == "ab":
                return (c.x, c.y - 2.54, ang, None), (c.x, c.y + 2.54, ang, None)
            if mode == "above":
                return (c.x, c.y - 4.32, ang, None), (c.x, c.y - 2.54, ang, None)
            if mode == "below":
                return (c.x, c.y + 2.54, ang, None), (c.x, c.y + 4.32, ang, None)
            if mode in ("right", "left") and horiz_rot:
                # у повёрнутого символа выравнивание не трогаем: центр текста сдвигаем на половину ширины
                sgn = 1 if mode == "right" else -1
                w = lambda s: 1.52 + 0.5 * 1.0 * len(s)
                return (round(c.x + sgn * w(c.ref), 4), c.y - 0.89, ang, None), \
                       (round(c.x + sgn * w(c.value), 4), c.y + 0.89, ang, None)
            if mode == "right":
                return (c.x + 1.52, c.y - 0.89, 0, "left"), (c.x + 1.52, c.y + 0.89, 0, "left")
            if mode == "left":
                return (c.x - 1.52, c.y - 0.89, 0, "right"), (c.x - 1.52, c.y + 0.89, 0, "right")
        props = {p[1]: p for p in find_all(c.sym, "property")}
        out = []
        for key in ("Reference", "Value"):
            at = find(props[key], "at")
            rx, ry = self._xf(c, float(at[1]), -float(at[2]))
            if isinstance(c.fpos, dict) and key in c.fpos:
                rx, ry = c.fpos[key]
            just = None
            if c.rot == 0 and not c.mirror:
                j = find(find(props[key], "effects"), "justify")
                just = " ".join(j[1:]) if j else None
            out.append((round(c.x + rx, 4), round(c.y + ry, 4), ang, just))
        return out

    def _sym_inst(self, c, path):
        e = ["symbol", ["lib_id", Q(c.lib_id)], ["at", c.x, c.y, c.rot]]
        if c.mirror:
            e.append(["mirror", c.mirror])
        e += [["unit", 1], ["exclude_from_sim", "no"], ["in_bom", "yes" if c.in_bom else "no"],
              ["on_board", "yes"], ["dnp", "yes" if c.dnp else "no"], ["uuid", uid()]]
        (rx, ry, ra, rj), (vx, vy, va, vj) = self._field_positions(c)
        e.append(_prop("Reference", c.ref, rx, ry, ra, justify=rj))
        e.append(_prop("Value", c.value, vx, vy, va, justify=vj))
        e.append(_prop("Footprint", c.fp, c.x, c.y, 0, hide=True))
        e.append(_prop("Datasheet", c.ds, c.x, c.y, 0, hide=True))
        e.append(_prop("Description", c.desc, c.x, c.y, 0, hide=True))
        for k, v in c.fields.items():
            e.append(_prop(k, v, c.x, c.y, 0, hide=True))
        for num in c.pins:
            e.append(["pin", Q(num), ["uuid", uid()]])
        e.append(["instances", ["project", Q(PROJECT), ["path", Q(path), ["reference", Q(c.ref)], ["unit", 1]]]])
        return e

    def _pwr_inst(self, lib, net, p, rot, orient, ref, path):
        horiz = rot in (90, 270)
        off = {"up": (0, -3.56), "down": (0, 3.56), "left": (-3.3, 0), "right": (3.3, 0)}[orient]
        if net in GROUND_NETS or net == "PWR_FLAG":
            off = {"up": (0, -3.81), "down": (0, 3.81), "left": (-3.81, 0), "right": (3.81, 0)}[orient]
            if net == "PWR_FLAG":
                off = {"up": (0, -4.06), "down": (0, 4.06), "left": (-4.06, 0), "right": (4.06, 0)}[orient]
        if horiz:
            off = (off[0] * (1.0 + 0.12 * len(net)), off[1])
        e = ["symbol", ["lib_id", Q(lib)], ["at", p[0], p[1], rot], ["unit", 1],
             ["exclude_from_sim", "no"], ["in_bom", "no"], ["on_board", "yes"], ["dnp", "no"], ["uuid", uid()],
             _prop("Reference", ref, p[0], p[1], 0, hide=True),
             _prop("Value", net, round(p[0] + off[0], 4), round(p[1] + off[1], 4), 90 if horiz else 0),
             _prop("Footprint", "", p[0], p[1], 0, hide=True),
             _prop("Datasheet", "", p[0], p[1], 0, hide=True),
             _prop("Description", "", p[0], p[1], 0, hide=True),
             ["pin", Q("1"), ["uuid", uid()]],
             ["instances", ["project", Q(PROJECT), ["path", Q(path), ["reference", Q(ref)], ["unit", 1]]]]]
        return e

    def build(self, root_uuid, counters, title_block, extra=()):
        path = f"/{root_uuid}" if self.sheet_uuid is None else f"/{root_uuid}/{self.sheet_uuid}"
        used = []
        for ref in self.order:
            if self.parts[ref].lib_id not in used:
                used.append(self.parts[ref].lib_id)
        for lib, *_ in self.power:
            if lib not in used:
                used.append(lib)
        libsyms = ["lib_symbols"]
        for lib_id in used:
            s = _deep(self.libs[lib_id])
            s[1] = Q(lib_id)
            libsyms.append(s)
        e = ["kicad_sch", ["version", SCH_VERSION], ["generator", Q("gen_sch.py")], ["generator_version", Q("10.0")],
             ["uuid", self.file_uuid], ["paper", Q(self.paper)], title_block, libsyms]
        for p in self._junctions():
            e.append(["junction", ["at", p[0], p[1]], ["diameter", 0], ["color", 0, 0, 0, 0], ["uuid", uid()]])
        for p in self.ncs:
            e.append(["no_connect", ["at", p[0], p[1]], ["uuid", uid()]])
        for a, b in self.wires:
            e.append(["wire", ["pts", ["xy", a[0], a[1]], ["xy", b[0], b[1]]],
                      ["stroke", ["width", 0], ["type", "default"]], ["uuid", uid()]])
        for kind, name, p, d, shape in self.labels:
            ang = {"right": 0, "up": 90, "left": 180, "down": 270}[d]
            just = "left bottom" if d in ("right", "up") else "right bottom"
            if kind == "hierarchical_label":
                just = "left" if d in ("right", "up") else "right"
                e.append([kind, Q(name), ["shape", shape], ["at", p[0], p[1], ang], _effects(1.27, just), ["uuid", uid()]])
            else:
                e.append([kind, Q(name), ["at", p[0], p[1], ang], _effects(1.27, just), ["uuid", uid()]])
        for s, x, y, size, bold in self.texts:
            eff = ["effects", ["font", ["size", size, size]] + ([["bold", "yes"]] if bold else []), ["justify", "left", "top"]]
            e.append(["text", Q(s), ["exclude_from_sim", "no"], ["at", x, y, 0], eff, ["uuid", uid()]])
        for ref in self.order:
            e.append(self._sym_inst(self.parts[ref], path))
        for lib, net, p, rot, orient in self.power:
            key = "#FLG" if net == "PWR_FLAG" else "#PWR"
            counters[key] = counters.get(key, 0) + 1
            e.append(self._pwr_inst(lib, net, p, rot, orient, f"{key}{counters[key]:03d}", path))
        e.extend(extra)
        e.append(["embedded_fonts", "no"])
        return e

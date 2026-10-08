r"""Build the tracker's weapon data and icons from a local MH4U extract.

    python scripts/build_data.py [C:\MH4U-Extract]

Reads only the game itself -- the executable (exefs\code.decompressed.bin), the English LMD text
tables and the common icon atlas unpacked under arcx\ -- and writes:

    docs/data/catalog.js              every weapon, with the fields the grid filters on
    docs/data/stats/<cat>.json        full stats, lazy-loaded by the detail panel
    docs/data/materials/<cat>.json    forge and upgrade recipes, lazy-loaded
    docs/assets/icons/icon_<cat>_r<n>.png   the game's own equipment icons in its Rare 1-10 colours
    docs/assets/notes/note_<code>.png       the note glyph in each Hunting Horn note colour
    docs/assets/MonsterIcons/MH4U-<name>_Icon.png   the game's monster icons for the theme swatches

The extract layout is 3U's: romfs unpacked from the cart image, ARC entries under arcx\ (ARC v19,
same layout as 3U's v16), code.bin decompressed. 4U's text is LMD, not GMD (see lmd_messages).
Every address below was found in the game code. "READ" means the instruction that consumes the
value was read, so the meaning comes from the game rather than from fitting. Notes from the decode
live with the extract (C:\MH4U-Extract\notes\weapons.md).

Needs: Python 3.10+, Pillow, numpy, and unicorn (the note colours are built from instruction
immediates, so they are read by running that function).
"""
import glob, json, os, struct, sys

EXTRACT = sys.argv[1] if len(sys.argv) > 1 else r'C:\MH4U-Extract'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')

CODE = open(os.path.join(EXTRACT, 'exefs', 'code.decompressed.bin'), 'rb').read()
BASE = 0x100000          # .text 0x100000, .rodata 0xded000, .data 0xec0000; file offset = VA - BASE
MSG = os.path.join(EXTRACT, 'arcx', 'eng', 'data', 'core_common', 'eng', 'msg')
ICON_TEX = os.path.join(EXTRACT, 'arcx', 'eng', 'data', 'core_common', 'eng', 'lyt', 'common',
                        'texture', 'cmn_icon_GSM_NOMIP.241f5deb')
MONSTER_TEX = os.path.join(EXTRACT, 'arcx', 'eng', 'data', 'core_common', 'eng', 'lyt', 'common',
                           'texture', 'cmn_micon_BM_MQ_NOMIP.241f5deb')


def word(va): return struct.unpack_from('<I', CODE, va - BASE)[0]
def half(va): return struct.unpack_from('<H', CODE, va - BASE)[0]
def raw(va, n): return CODE[va - BASE:va - BASE + n]
def s8(x): return x - 256 if x > 127 else x


def lmd_messages(name):
    """LMD (type 62440501) -> messages by the id the game asks for. Header: 'lmd\\0', u32 version,
    u32 message count, u32 op count, u32 string count, u32 header size, u32 ops offset, u32 strings
    offset, u32 name offset. Message i -> entry i of the first table (u32 hash, u16 first op, u16
    flags; 0xffff = empty) -> a run of 16-byte ops: 1 = string pool index, 2 = inline tag, 22 = end.
    Strings are (u32 file offset, u32 length, u32 length) -> UTF-16LE. Message ids are NOT string
    pool indexes in tables that use tags (Menu); the weapon-name tables happen to be 1:1."""
    b = open(os.path.join(MSG, name + '_eng.62440501'), 'rb').read()
    assert b[:4] == b'lmd\0', name
    nmsg, nops, nstr = struct.unpack_from('<3I', b, 8)
    oops, ostr = struct.unpack_from('<2I', b, 0x18)
    pool = []
    for i in range(nstr):
        p, n, _ = struct.unpack_from('<3I', b, ostr + 12 * i)
        pool.append(b[p:p + 2 * n].decode('utf-16-le'))
    out = []
    for i in range(nmsg):
        k = struct.unpack_from('<IHH', b, 0x24 + 8 * i)[1]
        s = ''
        while k != 0xffff and k < nops:
            op, arg = struct.unpack_from('<2I', b, oops + 16 * k)
            if op == 22:
                break
            s += pool[arg] if op == 1 else ''
            k += 1
        out.append(s)
    return out


ITEMS = lmd_messages('itemName')
MENU = lmd_messages(os.path.join('common', 'Menu'))
COMMON = lmd_messages(os.path.join('common', 'Common'))
KINSECTS = lmd_messages('InsectName')

# ── Weapons ───────────────────────────────────────────────────────────────
# Item type 7..20 = the 14 classes. The data manager's record getter 0x2f4450 (READ): melee types
# -> [0xf5884c + 4 * type], 0x18-byte records; gunner types 11 / 12 / 16 (0x2f2000) ->
# [0xf58884 + 4 * type], 0x28-byte records; index = weapon id. Count per type: u32 [0xf3fc38 + 4 *
# type] (READ 0x2f442c). Class id (the attack multiplier index) = byte [0xf5f2fc + type] (READ
# 0x2f13b4). Label = Common message 36 + type (the game's item-type names). Names: LMD <msg>Name.
TYPES = [  # type, key, name table
    (7, 'great_sword', 'LswordName'), (13, 'long_sword', 'Lsword2Name'),
    (8, 'sword_and_shield', 'SwordName'), (17, 'dual_blades', 'WswordName'),
    (9, 'hammer', 'HammerName'), (18, 'hunting_horn', 'Hammer2Name'),
    (10, 'lance', 'LanceName'), (15, 'gunlance', 'Lance2Name'),
    (14, 'switch_axe', 'AxeName'), (20, 'charge_blade', 'GaxeName'), (19, 'insect_glaive', 'RodName'),
    (11, 'light_bowgun', 'LightName'), (12, 'heavy_bowgun', 'HeavyName'), (16, 'bow', 'BowName'),
]
GUNNER = {11, 12, 16}
MELEE_TABLES, GUNNER_TABLES, COUNTS, CLASS_OF = 0xf5884c, 0xf58884, 0xf3fc38, 0xf5f2fc
MULT100 = 0xed24a0       # READ 0x26e260: displayed attack = true attack * u32[class] / 100 (stats: atk
                         # is the displayed value, raw the true one the record stores)

# Element / status. Melee: +0xc element code 1-5, +0xd s8 value; +0xe status code 1-4, +0xf s8.
# Bow: the same pairs at +0x12 / +0x14. READ 0x2f1688 (the stat getter): stats 7-11 are the element
# values by code, 12-14 and 17 the statuses; stat 15/16 the two values. A negative value is hidden
# without Awaken. Codes by the monsters that carry them (Rathalos 1, Plesioth 2, Khezu 3, Fatalis 4,
# Daora 5; Chrome Razor status 1, Dios status 4) and named with the game's full words.
ELEMENTS = [MENU[557], MENU[555], MENU[558], MENU[559], MENU[556],   # Fire Water Thunder Dragon Ice
            MENU[544], MENU[545], MENU[546], MENU[550]]              # Poison Paralysis Sleep Blast
# Sharpness, READ 0x2735a0: profile = melee +2 -> 7 x u16 cumulative colour ends at 0xf581e4 + 14 *
# profile (READ 0x2f0e64); bar length = 150 + 50 * level (+3), and Sharpness+1 adds one level
# (capped at 6) before the length is taken.
SHARP_TABLE = 0xf581e4
SHARP_LABELS = ['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'White', 'Purple']
# Class special, melee +0x11 (getter 0x2f8074):
#   Hunting Horn  READ 0x2709e4: three note codes at 0xf31da4 + 3 * special. Songs, READ 0x277ddc:
#                 75 songs x 4 note codes (0-terminated) at 0xf31e3a; playable when every note is
#                 among the horn's three; effect = Menu[u32 0xed2858[byte 0xed256a[song]]].
#   Gunlance      READ 0x27a070: shell = Menu[u32 0xed2694[special % 3]], level = special / 3 + 1.
#   Switch Axe    READ 0x27d45c: phial = Menu[s16 0xed26a0[special]]; Charge Blade the same at 0xed2480.
#   Insect Glaive READ 0x2f28f8: the Kinsect a new glaive comes with -- 0 -> Kinsect 0, else 12.
#   Dual Blades   a model variant (the mismatched pairs); MH4 turned the dual-element blades into Blast.
NOTE_SETS, SONG_NOTES, SONG_EFFECT, SONG_EFFECT_MSG, SONG_COUNT = 0xf31da4, 0xf31e3a, 0xed256a, 0xed2858, 75
SHELL_MSG, SA_PHIAL_MSG, CB_PHIAL_MSG = 0xed2694, 0xed26a0, 0xed2480
NOTE_NAMES = {1: 'White', 2: 'Purple', 3: 'Red', 4: 'Blue', 5: 'Green', 6: 'Yellow', 7: 'Light Blue', 8: 'Orange'}
NOTE_HEX = {}            # filled by write_icons() from the game's tint function
NOTE_GLYPH = 367         # the note glyph in cmn_icon (x 240, y 352)
# Gunners (0x28-byte records): +4 rarity - 1, +5 deviation, +6 reload (bow: arc shot), +7 ammo
# capacity row, +8 u32 price, +0xc s16 attack, +0xe defense, +0xf recoil (bow: charge count),
# +0x10 slots, +0x11 s8 affinity, +0x16..+0x1a Rapid Fire / Crouching Fire / bow charges,
# +0x20 u64 ammo (bowguns) or coating (bow) bits.
# Reload, READ 0x28194c: label = Menu[u32 0xed25b8[clamp(+6 + 3 + skill, 0, 9)]] (Slowest..Fastest).
# Recoil, READ 0x283064: label = Menu[u32 0xed25e0[clamp(+0xf + 1 + skill, 0, 7)]] (Max..Min).
# Deviation, READ 0x2f153c / 0x270910: label = Menu[u32 0xed2600[+5]] ((None), L Mild, ... LR Severe).
RELOAD_MSG, RECOIL_MSG, DEVIATION_MSG = 0xed25b8, 0xed25e0, 0xed2600
RELOADS = [MENU[word(RELOAD_MSG + 4 * k)] for k in range(10)]
RECOILS = [MENU[word(RECOIL_MSG + 4 * k)] for k in range(8)]
DEVIATIONS = [MENU[word(DEVIATION_MSG + 4 * k)] for k in range(7)]
# Ammo, READ 0x281f0c: capacity = byte [table + 39 * (+7) + slot], table 0xfb2bf4 (LBG) or 0xfb4739
# (HBG); the slot's item = u16 0xed24e0[slot] (READ 0x278f68). Slots 35-36 are empty.
AMMO_ITEM, AMMO_CAP = 0xed24e0, {11: 0xfb2bf4, 12: 0xfb4739}
# Rapid Fire (LBG), READ 0x27a7e0: id -> 12-byte {u32 slot, f32 damage, u32 shots | wait << 8} at
# 0xe05f54; wait = Menu 578 + wait (Short..V.Long). Crouching Fire (HBG), READ 0xb20c84: the five
# bytes are ammo slots (WyvernFire is masked off). 0xff = none.
RAPID = 0xe05f54
# Bow, READ 0x27a528: arc shot = Menu[u32 0xed26ac[+6]]. Charges, READ 0x27b628: count = +0xf (one
# more with Load Up, skill 0x79), up to 4; charge i = Menu[u32 0xed2b5c[+0x16 + i]] (Rapid / Spread
# / Pierce L1-5). Coatings, READ 0x27d558: bit k + 1 of +0x20 (mask 0xed2bd8[k]) = Menu 543 + k.
ARC_MSG, CHARGE_MSG = 0xed26ac, 0xed2b5c
ARCS = [MENU[word(ARC_MSG + 4 * k)] for k in range(4)]
COATINGS = [MENU[543 + k] for k in range(8)]

# Trees. Upgrade table per type, READ 0x2f11f0: [0xf56958 + 4 * type], 0x18-byte records indexed by
# weapon id: 4 x (u16 item, u16 qty) to upgrade INTO it, then 4 x u16 weapons it upgrades into. The
# record counts are the getter's own bounds. Insect Glaives have no table there; READ 0x2f4970: 12-byte
# records at 0xf569ac (ids < 0x87): 2 x (item, qty) into it, u16 the next glaive, u8, u8. The first u8
# is a requirement on the SOURCE glaive (READ 0xa01e1c: record(current) +0xa <= equipment byte +1, + 2);
# what that equipment byte holds is not traced, so it is not shown.
TREE_TABLES = 0xf56958
TREE_COUNT = {7: 228, 8: 235, 9: 231, 10: 200, 11: 172, 12: 142, 13: 207, 14: 182, 15: 206, 16: 190,
              17: 214, 18: 171, 20: 101}
IG_TREE, IG_TREE_COUNT = 0xf569ac, 0x87
# Forge list, READ 0x2f1fbc (list 1): 0x18-byte records from 0xf51dfc: u8 type, u8 flag, u16 id,
# 4 x (item, qty), u32; type 0xff ends the list.
FORGE = 0xf51dfc

RELIC = 0x80             # melee +0x16 / gunner +0x1c: relic templates (5 rolls of 7 designs per class)

# ── Armour ────────────────────────────────────────────────────────────────
# Item types 1-5 (chest, arms, waist, legs, head); 0x28-byte records at [0xf588d8 + 4 * type]
# (READ 0x2f5724), counts as for weapons; names LMD <msg>Name; label = Common message 36 + type.
#   +0 / +2 u16 male / female model    +4 wearer bits     +5 rarity - 1 (READ 0x2f1140)
#   +6 flags: 0x80 | 0x40 = relic (READ 0x2f3d34, the game's relic test)
#   +7 base defense   +8 u32 price   +0xc..+0x10 s8 resistances (stats 1-5 of 0x2f1688)
#   +0x11 slots (READ 0x2f5b20)   +0x13 dye index   +0x14..+0x1b levels per upgrade tier
#   +0x1c u16 list order   +0x1e 5 x (u8 skill tree, s8 points) (skill trees = LMD skillType)
# Wearer bits, READ 0xc1f3e8 (the player's own mask) / 0x2f4ac8 (the test): 1 male, 2 female,
# 4 blademaster, 8 gunner; the "Hunter Type" label tests 0xc, 8, 4 (0x273ce4).
# Resistances run Fire Water Ice Thunder Dragon (stats 1-5; Menu 402-406 in that order).
ARMOR_SLOTS = [  # item type, key, name table
    (5, 'head', 'HeadName'), (1, 'chest', 'BodyName'), (2, 'arms', 'ArmName'),
    (3, 'waist', 'WaistName'), (4, 'legs', 'LegName'),
]
ARMOR_TABLES, ARMOR_RELIC = 0xf588d8, 0xc0
# Defense, READ 0x2f3e60: base +7; each upgrade adds s8 step[tier] from 0xf3ed64 when +4 has bit
# 0x10, else 0xf3ed5c; tier t covers the next +0x14[t] upgrades. Level count = 1 + the sum of the
# eight tier counts (READ 0x2f507c, capped at 63 upgrades).
DEF_STEPS = {0: 0xf3ed5c, 0x10: 0xf3ed64}
# Upgrade cost, READ 0xa27358: one sphere per level, of the tier of the level being reached
# (0x2f0f24: the first tier whose running count covers it): Armor Sphere, +, Adv, Hard, Heavy, True,
# Strong, Divine. Zenny, READ 0x2f6804: int(b + a * price * 2.0), (a, b) = float pair at 0xf3fd50
# + 8 * tier.
SPHERES = [0xe1, 0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0x66b, 0x66c]
UPGRADE_ZENNY = 0xf3fd50
# Forge list 0 (READ 0x2f1fbc): the armour recipes, same records as the weapons' list 1.
ARMOR_FORGE = 0xf400fc
RES_LABELS = [MENU[402 + k].replace(' Res', '') for k in range(5)]

# ── Icons and rarity colours ─────────────────────────────────────────────
# Name colour, READ 0xc0d41c: 10 RGB triplets at 0xe063f6, indexed by rarity - 1 (getter 0x2f1140).
RARE_COLOURS = 0xe063f6
# Weapon icon cell, READ 0xc0e328: byte [0xfb8125 + class id] -- [0,2,4,6,10,8,8,1,12,7,11,3,5,13,14,10]
# (found by searching for the by-eye cell order; the MH3U tracker session pointed out that 3U keeps
# the same kind of table at 0xb91510). The cell index runs in the series' order: GS LS SnS DB Hammer
# HH Lance GL LBG (medium bowgun) HBG Bow SA IG CB. One index places both sets in cmn_icon (LA4):
#   player icons (sidebar): 14x16 cells, ten per row from y 160, x = 14 * (n % 10);
#   equipment box icons (the slots and the detail panel): outlined 24 px cells, ten per row from y 328, linear
#     position n + 5 (GS at col 5 of y 328, HH at col 0 of y 352; position 14 is empty).
# The cell geometry was measured from the texture (the opaque runs); the 16 px outlined rows at
# y 96 / 112 are a smaller copy of the box set.
ICON_CELL_TABLE = 0xfb8125
ICON_CELLS = {t: CODE[ICON_CELL_TABLE - BASE + CODE[CLASS_OF - BASE + t]] for t in range(7, 21)}
BOX_CELLS = {t: ((n + 5) % 10, 328 + 24 * ((n + 5) // 10)) for t, n in ICON_CELLS.items()}
# Armour box icons: y 376, cols 0-4 = head chest waist arms legs (matched by eye; the armour
# equivalent of the cell table is not traced).
BOX_CELLS.update({5: (0, 376), 1: (1, 376), 3: (2, 376), 2: (3, 376), 4: (4, 376)})


def mats(b):
    return [(ITEMS[i], q) for i, q in struct.iter_unpack('<HH', b) if i]


def forge_list(va=FORGE):
    out = {}
    while CODE[va - BASE] != 0xff:
        t, flag, i = struct.unpack_from('<BBH', CODE, va - BASE)
        out.setdefault((t, i), mats(raw(va + 4, 16)))
        va += 0x18
    return out


def tree(t, n):
    """-> (into-materials by id, children by id)."""
    into, children = {}, {}
    if t == 19:
        for i in range(min(n, IG_TREE_COUNT)):
            r = raw(IG_TREE + 12 * i, 12)
            into[i] = mats(r[:8])
            child = struct.unpack_from('<H', r, 8)[0]
            children[i] = [child] if 0 < child < n else []
        return into, children
    tab = word(TREE_TABLES + 4 * t)
    for i in range(min(n, TREE_COUNT[t])):
        r = raw(tab + 0x18 * i, 0x18)
        into[i] = mats(r[:16])
        children[i] = [c for c in struct.unpack_from('<4H', r, 16) if 0 < c < n]
    return into, children


def sharp_bar(profile, length):
    ends = struct.unpack_from('<7H', CODE, SHARP_TABLE - BASE + 14 * profile)
    out, prev = [], 0
    for end in ends:
        end = min(end, length)
        out.append(max(0, end - prev))
        prev = max(prev, end)
    return out


def top_colour(bar):
    return max((i for i, v in enumerate(bar) if v), default=0)


def attr(code, value, base):
    """[name, displayed value, needs Awaken] for an element (base 0) or status (base 5) code."""
    return [ELEMENTS[base + code - 1], abs(s8(value)) * 10, 1 if s8(value) < 0 else 0]


def ammo_name(slot):
    return ITEMS[half(AMMO_ITEM + 2 * slot)]


def weapon_class(t, key, msg, forge):
    names = lmd_messages(msg)
    n = word(COUNTS + 4 * t)
    cls = CODE[CLASS_OF - BASE + t]
    label, mult100 = COMMON[36 + t], word(MULT100 + 4 * cls)
    gunner = t in GUNNER
    tab = word((GUNNER_TABLES if gunner else MELEE_TABLES) + 4 * t)
    stride = 0x28 if gunner else 0x18
    recs = [raw(tab + i * stride, stride) for i in range(n)]
    into, children = tree(t, n)
    parent = {}
    for p, cs in children.items():
        for c in cs:
            parent.setdefault(c, p)

    def keep_name(i):
        s = names[i] if i < len(names) else ''
        return s and s != '(None)' and not s.lower().startswith('dummy')
    keep = [i for i in range(1, n) if keep_name(i) and not recs[i][0x1c if gunner else 0x16] & RELIC]
    keep_set = set(keep)
    order, seen = {}, set()       # tree order: each root in id order, then its upgrades depth-first
    def walk(i):
        if i in seen or i not in keep_set:
            return
        seen.add(i)
        order[i] = len(order) + 1
        for c in children.get(i, []):
            walk(c)
    for i in keep:
        if parent.get(i) not in keep_set:
            walk(i)
    for i in keep:
        walk(i)

    entries, stats, recipes = [], {}, {}
    for i in keep:
        b = recs[i]
        st, cx = {}, {}
        ele_mask = awk_mask = 0
        ele = []
        def add_attr(code, value, base):
            nonlocal ele_mask, awk_mask
            if not code:
                return
            a = attr(code, value, base)
            ele.append(a)
            ele_mask |= 1 << (base + code - 1)
            if a[2]:
                awk_mask |= 1 << (base + code - 1)
        if gunner:
            rar = b[4] + 1
            atk = struct.unpack_from('<h', b, 0xc)[0]
            dfn, slots, aff = b[0xe], b[0x10], s8(b[0x11])
            price = struct.unpack_from('<I', b, 8)[0]
            fire = [x for x in b[0x16:0x1b] if x != 0xff]
            if t == 16:
                add_attr(b[0x12], b[0x13], 0)
                add_attr(b[0x14], b[0x15], 5)
                cx['a'] = b[6]
                st['arc'] = ARCS[b[6]] if b[6] < 4 else '?'
                count = min(b[0xf], 4)
                st['charges'] = [[MENU[word(CHARGE_MSG + 4 * c)], 1 if k >= count else 0]
                                 for k, c in enumerate(b[0x16:0x1a]) if c != 0xff and k <= count]
                bits = struct.unpack_from('<Q', b, 0x20)[0]
                st['coatings'] = [COATINGS[k] for k in range(8) if bits >> (k + 1) & 1]
            else:
                rl = min(max(b[6] + 3, 0), 9)
                rc = min(max(b[0xf] + 1, 0), 7)
                cx.update(r=rl, rc=rc, d=b[5])
                st.update(reload=RELOADS[rl], recoil=RECOILS[rc],
                          deviation=DEVIATIONS[b[5]] if b[5] < 7 else '?')
                bits = struct.unpack_from('<Q', b, 0x20)[0]
                row = AMMO_CAP[t] + 39 * b[7]
                st['ammo'] = [[ammo_name(s), CODE[row - BASE + s]] for s in range(39)
                              if bits >> s & 1 and half(AMMO_ITEM + 2 * s)]
                if t == 11:
                    out = []
                    for rid in fire:
                        slot, dmg, sw = struct.unpack_from('<IfI', CODE, RAPID - BASE + 12 * rid)
                        out.append([ammo_name(slot), sw & 0xff, MENU[578 + (sw >> 8 & 0xff)], round(dmg, 2)])
                    st['rapid'] = out
                    cx['rf'] = 1 if out else 0
                else:
                    st['crouch'] = [ammo_name(s) for s in fire]
                    cx['cf'] = 1 if fire else 0
        else:
            rar = b[0x13] + 1
            atk = struct.unpack_from('<h', b, 8)[0]
            dfn, aff, slots = b[0xa], s8(b[0xb]), b[0x10]
            price = struct.unpack_from('<I', b, 4)[0]
            add_attr(b[0xc], b[0xd], 0)
            add_attr(b[0xe], b[0xf], 5)
            level = b[3]
            bars = [sharp_bar(b[2], 150 + 50 * level), sharp_bar(b[2], 150 + 50 * min(level + 1, 6))]
            st['sh'] = bars
            cx['sh'] = top_colour(bars[0]) << 3 | top_colour(bars[1])
            sp = b[0x11]
            if t == 18:
                notes = list(raw(NOTE_SETS + 3 * sp, 3))
                st['notes'] = [[NOTE_NAMES.get(x, '?'), 'note_%d' % x, NOTE_HEX.get(x, '#ffffff')] for x in notes]
                st['songs'] = []
                for k in range(SONG_COUNT):
                    seq = [x for x in raw(SONG_NOTES + 4 * k, 4) if x]
                    if seq and all(x in notes for x in seq):
                        eff = MENU[word(SONG_EFFECT_MSG + 4 * CODE[SONG_EFFECT - BASE + k])]
                        st['songs'].append([[notes.index(x) for x in seq], eff])
                cx['n'] = notes[0] << 8 | notes[1] << 4 | notes[2]
            elif t == 15:
                cx.update(s=sp % 3, sl=sp // 3 + 1)
                st['shell'] = '%s Lv%d' % (MENU[word(SHELL_MSG + 4 * (sp % 3))].strip('()'), sp // 3 + 1)
            elif t in (14, 20):
                msg = struct.unpack_from('<h', CODE, (SA_PHIAL_MSG if t == 14 else CB_PHIAL_MSG) - BASE + 2 * sp)[0]
                cx['p'] = sp
                st['phial'] = MENU[msg]
            elif t == 19:
                cx['k'] = 1 if sp else 0
                st['kinsect'] = KINSECTS[12 if sp else 0]
        st['ele'] = ele
        attack = atk * mult100 // 100
        par = parent.get(i) if parent.get(i) in keep_set else None
        st.update(rar=rar, atk=attack, raw=atk, aff=aff, slots=slots, price=price, parent=par,
                  children=[c for c in children.get(i, []) if c in keep_set])
        st['def'] = dfn
        stats[str(i)] = st
        rec = {}
        if (t, i) in forge:
            rec['d'] = forge[(t, i)]
        if par is not None and into.get(i):
            rec['f'] = [par, None, into[i]]
        if rec:
            recipes[i] = rec
        entries.append([i, names[i], rar, par if par is not None else 0, order.get(i, 0), ele_mask,
                        [attack, aff, dfn, slots], cx, awk_mask])
    return label, mult100, entries, stats, recipes


SKILL_TREES = lmd_messages('skillType')


def armor_levels(r):
    """Defense at every level, the way 0x2f3e60 computes it."""
    steps = struct.unpack_from('<8b', CODE, DEF_STEPS[r[4] & 0x10] - BASE)
    out, d = [r[7]], r[7]
    for tier, count in enumerate(r[0x14:0x1c]):
        for _ in range(count):
            if len(out) > 63:
                return out
            d += steps[tier]
            out.append(d)
    return out


def armor_upgrades(r):
    """[(sphere name, zenny)] for Lv1->2, Lv2->3, ...: the tier of each upgrade, as 0x2f0f24 picks it."""
    price = struct.unpack_from('<I', r, 8)[0]
    out = []
    for tier, count in enumerate(r[0x14:0x1c]):
        a, b = struct.unpack_from('<2f', CODE, UPGRADE_ZENNY - BASE + 8 * tier)
        out += [(ITEMS[SPHERES[tier]], int(b + a * (price * 2.0)))] * count
    return out[:63]


def armor_slot(t, key, msg, forge):
    names = lmd_messages(msg)
    n = word(COUNTS + 4 * t)
    tab = word(ARMOR_TABLES + 4 * t)
    entries, stats, recipes = [], {}, {}
    for i in range(1, n):
        name = names[i] if i < len(names) else ''
        r = raw(tab + 0x28 * i, 0x28)
        if not name or name.upper().startswith('DUMMY') or r[6] & ARMOR_RELIC:
            continue
        m, f, blade, gunner = (r[4] >> k & 1 for k in range(4))
        gender = 2 if m and f else 0 if m else 1 if f else 2
        cls = 'A' if blade and gunner else 'B' if blade else 'G' if gunner else 'A'
        lv = armor_levels(r)
        rar = r[5] + 1
        skills = [[SKILL_TREES[r[0x1e + 2 * k]], s8(r[0x1f + 2 * k])] for k in range(5) if r[0x1e + 2 * k]]
        stats[str(i)] = {'def': [lv[0], lv[-1]], 'lv': lv, 'res': [s8(x) for x in r[0xc:0x11]],
                         'slots': r[0x11], 'sk': skills, 'rar': rar,
                         'price': struct.unpack_from('<I', r, 8)[0]}
        recipes[i] = {'create': forge.get((t, i)), 'up': armor_upgrades(r)}
        entries.append([i, name, rar, len(lv), gender, cls])
    return COMMON[36 + t], entries, stats, recipes


def rarity_colours():
    return ['#%02x%02x%02x' % tuple(raw(RARE_COLOURS + 3 * k, 3)) for k in range(10)]


def write_icons(colours):
    import numpy as np
    from PIL import Image
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pica_la4 import decode_la4
    import note_colours
    atlas = decode_la4(open(ICON_TEX, 'rb').read())
    def cell(idx):
        x, y = idx % 16 * 16, idx // 16 * 16
        return atlas[y:y + 16, x:x + 16].astype(np.float32)
    def weapon_cell(k):   # a 14x16 cell, centred in a 16x16 square
        x, y = 14 * (k % 10), 160 + 16 * (k // 10)
        sq = np.zeros((16, 16, 4), np.float32)
        sq[:, 1:15] = atlas[y:y + 16, x:x + 14]
        return sq
    def box_cell(t):
        col, y = BOX_CELLS[t]
        return atlas[y:y + 24, 24 * col:24 * col + 24].astype(np.float32)
    out = os.path.join(DOCS, 'assets', 'icons')
    os.makedirs(out, exist_ok=True)
    def save_tinted(base, stem, size):
        for k, hexc in enumerate([None] + colours):
            img = base.copy()
            if hexc:   # the icon is a grey mask; the game multiplies it by the rarity colour
                img[..., :3] *= [int(hexc[j:j + 2], 16) / 255 for j in (1, 3, 5)]
            name = '%s%s.png' % (stem, '_r%d' % k if k else '')
            Image.fromarray(img.clip(0, 255).astype(np.uint8)).resize((size, size), Image.NEAREST).save(os.path.join(out, name))
    for t, key, _ in TYPES:
        save_tinted(weapon_cell(ICON_CELLS[t]), 'icon_' + key, 48)   # player icon: sidebar, panel
        save_tinted(box_cell(t), 'box_' + key, 48)                   # equipment box icon: the slots
    for t, key, _ in ARMOR_SLOTS:   # armour has no player icon set: the box icon serves both
        save_tinted(box_cell(t), 'icon_armor_' + key, 48)
        save_tinted(box_cell(t), 'box_armor_' + key, 48)
    ndir = os.path.join(DOCS, 'assets', 'notes')
    os.makedirs(ndir, exist_ok=True)
    glyph = cell(NOTE_GLYPH)
    for code, hexc in note_colours.colours(CODE).items():
        NOTE_HEX[code] = hexc
        img = glyph.copy()
        img[..., :3] *= [int(hexc[j:j + 2], 16) / 255 for j in (1, 3, 5)]
        Image.fromarray(img.clip(0, 255).astype(np.uint8)).resize((48, 48), Image.NEAREST).save(
            os.path.join(ndir, 'note_%d.png' % code))


# Theme icons: the game's monster icons, cmn_micon (RGBA4444): 34 px icons on a 36 px pitch in two
# blocks of seven columns (x = 1 + 36 k and 257 + 36 k, y = 1 + 36 r), measured from the texture.
# The icons run roughly in the monster-id order of emName, but grouped by species line: the first
# row is Rathian, Pink, Gold (one art in three colours), then Rathalos, Azure, Silver. The cells
# below were named from that order and checked by the art; the game's id -> cell table is in layout
# data, not traced. One per theme swatch (the app's THEMES), named as the app names them.
MONSTER_ICONS = {
    'Question Mark': ('L', 0, 0), 'Rathian': ('L', 0, 1), 'Pink Rathian': ('L', 0, 2),
    'Gold Rathian': ('L', 0, 3), 'Rathalos': ('L', 0, 4), 'Azure Rathalos': ('L', 0, 5),
    'Silver Rathalos': ('L', 0, 6), 'Yian Kut-Ku': ('L', 1, 0), 'Blue Yian Kut-Ku': ('L', 1, 1),
    'Gypceros': ('L', 1, 2), 'Purple Gypceros': ('L', 1, 3), 'Great Jaggi': ('L', 2, 2),
    'Velocidrome': ('L', 2, 3), 'Kecha Wacha': ('L', 3, 1), 'Seltas': ('L', 3, 5),
    'Seltas Queen': ('L', 3, 6), 'Basarios': ('L', 5, 5), 'Ruby Basarios': ('L', 5, 6),
    'Gravios': ('L', 6, 0), 'Black Gravios': ('L', 6, 1), 'Genprey': ('L', 8, 4),
    'Ash Kecha Wacha': ('R', 0, 1), 'Tidal Najarala': ('R', 0, 4), 'Desert Seltas': ('R', 0, 5),
    'Desert Seltas Queen': ('R', 0, 6), 'Shrouded Nerscylla': ('R', 1, 0), 'Black Diablos': ('R', 1, 4),
    'White Monoblos': ('R', 1, 6), 'Cephadrome': ('R', 2, 1), 'Daimyo Hermitaur': ('R', 2, 3),
    'Plum Daimyo Hermitaur': ('R', 2, 4),
}


def write_monster_icons():
    import numpy as np
    from PIL import Image
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pica_la4 import decode_rgba4
    atlas = decode_rgba4(open(MONSTER_TEX, 'rb').read())
    out = os.path.join(DOCS, 'assets', 'MonsterIcons')
    os.makedirs(out, exist_ok=True)
    for name, (block, r, k) in MONSTER_ICONS.items():
        x, y = (1 if block == 'L' else 257) + 36 * k, 1 + 36 * r
        Image.fromarray(atlas[y:y + 34, x:x + 34]).resize((68, 68), Image.NEAREST).save(
            os.path.join(out, 'MH4U-%s_Icon.png' % name.replace(' ', '_')))


def dump(path, obj):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(',', ':'))


def main():
    colours = rarity_colours()
    catalog = {'version': 1, 'rarityColors': colours,
               'labels': {'elements': ELEMENTS, 'arc': ARCS, 'reload': RELOADS, 'recoil': RECOILS,
                          'deviation': DEVIATIONS, 'notes': NOTE_NAMES, 'sharp': SHARP_LABELS,
                          'shell': [MENU[word(SHELL_MSG + 4 * k)].strip('()') for k in range(3)],
                          'phial': [MENU[struct.unpack_from('<h', CODE, SA_PHIAL_MSG - BASE + 2 * k)[0]] for k in range(6)],
                          'cbPhial': [MENU[struct.unpack_from('<h', CODE, CB_PHIAL_MSG - BASE + 2 * k)[0]] for k in range(2)],
                          'kinsect': [KINSECTS[0], KINSECTS[12]], 'res': RES_LABELS},
               'weapons': {}, 'armor': {}}
    sd, md = os.path.join(DOCS, 'data', 'stats'), os.path.join(DOCS, 'data', 'materials')
    os.makedirs(sd, exist_ok=True)
    os.makedirs(md, exist_ok=True)
    write_icons(colours)   # first: it fills in the note colours the horn stats carry
    write_monster_icons()
    forge = forge_list()
    totals = {}
    for t, key, msg in TYPES:
        label, mult, entries, stats, recipes = weapon_class(t, key, msg, forge)
        catalog['weapons'][key] = {'label': label, 'icon': key, 'mult': mult / 100, 'entries': entries}
        dump(os.path.join(sd, key + '.json'), {'class': key, 'byId': stats})
        names, index = [], {}
        def ix(n):
            if n not in index:
                index[n] = len(names)
                names.append(n)
            return index[n]
        create = {}
        for i, rec in sorted(recipes.items()):
            create[str(i)] = {k: ([v[0], v[1], [[ix(n), q] for n, q in v[2]]] if k == 'f'
                                  else [[ix(n), q] for n, q in v]) for k, v in rec.items()}
        dump(os.path.join(md, key + '.json'), {'mats': names, 'create': create, 'byId': {}})
        totals[key] = len(entries)
    armor_forge = forge_list(ARMOR_FORGE)
    for t, key, msg in ARMOR_SLOTS:
        label, entries, stats, recipes = armor_slot(t, key, msg, armor_forge)
        catalog['armor'][key] = {'label': label, 'icon': 'armor_' + key, 'entries': entries}
        dump(os.path.join(sd, 'armor_%s.json' % key), {'slot': key, 'byId': stats})
        # create[id] = recipe pairs; upgrade[id] = [[sphere index, zenny], ...], entry k = Lv k+1 -> k+2.
        names, index = [], {}
        def ix(n):
            if n not in index:
                index[n] = len(names)
                names.append(n)
            return index[n]
        mf = {'mats': names, 'create': {}, 'upgrade': {}}
        for i, rec in sorted(recipes.items()):
            if rec['create']:
                mf['create'][str(i)] = [[ix(n), q] for n, q in rec['create']]
            if rec['up']:
                mf['upgrade'][str(i)] = [[ix(n), z] for n, z in rec['up']]
        dump(os.path.join(md, 'armor_%s.json' % key), mf)
        totals['armor_' + key] = len(entries)
    with open(os.path.join(DOCS, 'data', 'catalog.js'), 'w', encoding='utf-8') as fh:
        fh.write('window.CATALOG = ' + json.dumps(catalog, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print(totals, sum(totals.values()), 'pieces')


if __name__ == '__main__':
    main()

"""Hunting Horn note colours, read by running the game's own tint function.

0x26dcd8(out, code) (READ 0x270a58, where the detail screen tints each note glyph) writes an RGBA
built from instruction immediates -- there is no table to read -- so it is run on the executable's
bytes with unicorn and the result read back.
"""
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1

BASE, TINT, RET, STACK = 0x100000, 0x26dcd8, 0x0e800000, 0x0f000000


def tint(code_bytes, note):
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(BASE, (len(code_bytes) + 0xfff) & ~0xfff)
    uc.mem_write(BASE, code_bytes)
    uc.mem_map(STACK, 0x10000)
    uc.mem_map(RET, 0x1000)
    out = STACK + 0x8000
    uc.reg_write(UC_ARM_REG_SP, STACK + 0xf000)
    uc.reg_write(UC_ARM_REG_LR, RET)
    uc.reg_write(UC_ARM_REG_R0, out)
    uc.reg_write(UC_ARM_REG_R1, note)
    uc.emu_start(TINT, RET, count=500)
    return bytes(uc.mem_read(out, 4))


def colours(code_bytes):
    """{note code 1-8: '#rrggbb'}."""
    return {k: '#%02x%02x%02x' % tuple(tint(code_bytes, k)[:3]) for k in range(1, 9)}


from nmigen import *
from nmigen.build import Platform
from nmigen_boards.ulx3s import ULX3S_85F_Platform
from nmigen.cli import main

JUMP    =    0b000
ADD    =     0b001
SWAP    =    0b010
LOAD    =    0b011
WFI    =     0b100
OUT    =     0b101

mem_init = [
    LOAD,
    SWAP,
    LOAD,
     OUT,

    JUMP,
    0b00,
    0b00,
    0b00,

     WFI,
    SWAP,
     ADD,
     OUT,

    JUMP,
]

class MainMemory(Elaboratable):
    def __init__(self):
        self.addr  = Signal(4)
        self.dat_r = Signal(8)
        self.dat_w = Signal(8)
        self.we    = Signal()
        self.mem   = Memory(width=8, depth=16, init=mem_init)

    def elaborate(self, platform):
        m = Module()
        m.submodules.rdport = rdport = self.mem.read_port()
        m.submodules.wrport = wrport = self.mem.write_port()
        m.d.comb += [
            rdport.addr.eq(self.addr),
            self.dat_r.eq(rdport.data),
            wrport.addr.eq(self.addr),
            wrport.data.eq(self.dat_w),
            wrport.en.eq(self.we),
        ]
        return m

class RegisterFile(Elaboratable):
    def __init__(self):
        self.a = Signal(32)
        self.b = Signal(32)
        self.do_swap = Signal()
        self.do_add = Signal()
        self.do_load = Signal()

    def elaborate(self, platform):
        m = Module()
        with m.If(self.do_swap != 0):
            m.d.sync += self.a.eq(self.b)
            m.d.sync += self.b.eq(self.a)
        with m.Elif(self.do_add != 0):
            m.d.sync += self.a.eq(self.a + self.b)
        with m.Elif(self.do_load != 0):
            m.d.sync += self.a.eq(1)
        return m

class FibProcessor(Elaboratable):
    def __init__(self):
        self.pc = Signal(4)
        self.inst = Signal(8)
        self.out = Signal(8)
        self.wfi = Signal()
        self.wfi_in = Signal()
        self.step = Signal()
        self.mem = MainMemory()
        self.regs = RegisterFile()

    def elaborate(self, platform):
        m = Module()
        m.submodules.mem = self.mem
        m.submodules.regs = self.regs
        m.d.sync += self.mem.addr.eq(self.pc)
        m.d.sync += self.regs.do_add.eq(0)
        m.d.sync += self.regs.do_swap.eq(0)
        m.d.sync += self.regs.do_load.eq(0)
        m.d.sync += self.wfi.eq(Mux(self.wfi, 1, self.wfi_in))
        with m.If(self.step != 0):
            with m.FSM() as fsm:
                with m.State('fetching'):
                    m.d.sync += self.inst.eq(self.mem.dat_r)
                    m.d.sync += self.pc.eq(self.pc + 1)
                    m.next = 'decoding'
                with m.State('decoding'):
                    with m.Switch(self.inst[0:3]):
                        with m.Case(JUMP):
                            m.d.sync += self.pc.eq(0x8)
                            m.next = 'moving_pc'
                        with m.Case(ADD):
                            m.d.sync += self.regs.do_add.eq(1)
                            m.next = 'fetching'
                        with m.Case(SWAP):
                            m.d.sync += self.regs.do_swap.eq(1)
                            m.next = 'fetching'
                        with m.Case(LOAD):
                            m.d.sync += self.regs.do_load.eq(1)
                            m.next = 'fetching'
                        with m.Case(WFI):
                            with m.If(self.wfi != 0):
                                m.d.sync += self.wfi.eq(0)
                                m.next = 'fetching'
                        with m.Case(OUT):
                            m.d.sync += self.out.eq(self.regs.a[0:8])
                            m.next = 'fetching'
                with m.State('moving_pc'):
                    m.next = 'fetching'
        return m

class InputDebouncer(Elaboratable):
    def __init__(self):
        self.in_raw = Signal()
        self.out = Signal()
        self.timer = Signal(20)

    def elaborate(self, platform):
        m = Module()
        m.d.sync += self.out.eq(0)
        with m.FSM() as fsm:
            with m.State('wait_for_release'):
                with m.If(self.in_raw == 0):
                    m.d.sync += self.timer.eq(1)
                    m.next = 'debounce_release'
            with m.State('debounce_release'):
                m.d.sync += self.timer.eq(self.timer + 1)
                with m.If(self.timer == 0):
                    m.next = 'wait_for_press'
            with m.State('wait_for_press'):
                with m.If(self.in_raw != 0):
                    m.d.sync += self.out.eq(1)
                    m.d.sync += self.timer.eq(1)
                    m.next = 'debounce_press'
            with m.State('debounce_press'):
                m.d.sync += self.timer.eq(self.timer + 1)
                with m.If(self.timer == 0):
                    m.next = 'wait_for_release'
        return m


if __name__ == "__main__":
    platform = ULX3S_85F_Platform()

    m = Module()
    m.submodules.fib = fib = FibProcessor()
    m.submodules.advancer = advancer = InputDebouncer()

    button = platform.request('button_fire', 0)

    leds = [platform.request("led", 0),
            platform.request("led", 1),
            platform.request("led", 2),
            platform.request("led", 3),
            platform.request("led", 4),
            platform.request("led", 5),
            platform.request("led", 6),
            platform.request("led", 7)]

    out_leds = Signal(8)
    for i in range(8):
        m.d.comb += leds[i].eq(fib.out[i])

    m.d.sync += advancer.in_raw.eq(button)

    counter = Signal(1)
    m.d.sync += counter.eq(counter + 1)
    m.d.sync += fib.step.eq(counter)
    m.d.sync += fib.wfi_in.eq(advancer.out)

    platform.default_rst = 'button_pwr'

    platform.build(m, do_program=True)


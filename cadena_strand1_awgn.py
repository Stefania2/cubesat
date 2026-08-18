#!/usr/bin/env python3
from gnuradio import gr, blocks, digital, filter, analog
from gnuradio.filter import firdes
import numpy as np
import argparse
import os

N = 18776
SP = 8
SYM = 9600
SR = SP * SYM
ALPHA = 0.35
NTAPS = 8 * 11 + 1
L = (NTAPS - 1) // SP
A = 8.00011
KAPPA = 1.98733


class cadena_strand1(gr.top_block):
    def __init__(self, infile, outfile, snr_db, seed):
        gr.top_block.__init__(self)
        taps = firdes.root_raised_cosine(SP, SR, SYM, ALPHA, NTAPS)
        self.z_tail = blocks.vector_source_b([0] * L, False, 1)
        self.source = blocks.file_source(gr.sizeof_char * 1, infile, False)
        self.mux = blocks.stream_mux(gr.sizeof_char * 1, (N, L))
        self.mapper = digital.chunks_to_symbols_bf([-1.0, 1.0], 1)
        self.tx_filter = filter.interp_fir_filter_fff(SP, taps)
        self.to_complex = blocks.float_to_complex(1)
        v = A / (KAPPA * np.sqrt(2.0 * 10.0 ** (snr_db / 10.0)))
        self.noise = analog.noise_source_c(analog.GR_GAUSSIAN, float(v), seed)
        self.add_noise = blocks.add_vcc()
        self.to_real = blocks.complex_to_real(1)
        self.rx_filter = filter.fir_filter_fff(1, taps)
        self.align = blocks.delay(gr.sizeof_float * 1, 7)
        self.sampler = blocks.keep_one_in_n(gr.sizeof_float * 1, SP)
        self.offset = blocks.skiphead(gr.sizeof_float * 1, 11)
        self.slicer = digital.binary_slicer_fb()
        self.sink = blocks.file_sink(gr.sizeof_char * 1, outfile)

        self.connect(self.source, (self.mux, 0))
        self.connect(self.z_tail, (self.mux, 1))
        self.connect(self.mux, self.mapper, self.tx_filter, self.to_complex)
        self.connect(self.to_complex, (self.add_noise, 0))
        self.connect(self.noise, (self.add_noise, 1))
        self.connect(self.add_noise, self.to_real, self.rx_filter, self.align)
        self.connect(self.align, self.sampler, self.offset, self.slicer, self.sink)


def run_cadena(infile, outfile, snr_db, seed):
    tb = cadena_strand1(infile, outfile, snr_db, seed)
    tb.start()
    tb.wait()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description='Cadena GNU Radio BPSK STRAND-1')
    parser.add_argument('--input', default=os.path.join(here, 'frames_STRAND1_bits.bin'))
    parser.add_argument('--output', default=os.path.join(here, 'frames_STRAND1_bits_rx.bin'))
    parser.add_argument('--snr-db', type=float, default=10.0, help='Eb/N0 en dB')
    parser.add_argument('--seed', type=int, default=11)
    args = parser.parse_args()

    run_cadena(args.input, args.output, args.snr_db, args.seed)


if __name__ == '__main__':
    main()
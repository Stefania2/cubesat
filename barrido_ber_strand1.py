#!/usr/bin/env python3
import numpy as np
import argparse
import os
import csv
import math

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import cadena_strand1_awgn
from cadena_strand1_awgn import run_cadena, N, A, KAPPA
from ber_strand1 import ber_teorico_q


def leer_bits(path):
    return np.frombuffer(open(path, 'rb').read(), dtype=np.uint8)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description='Barrido SNR -> BER de la cadena BPSK STRAND-1')
    parser.add_argument('--snr-min', type=float, default=0.0)
    parser.add_argument('--snr-max', type=float, default=12.0)
    parser.add_argument('--step', type=float, default=1.0)
    parser.add_argument('--seeds', type=int, default=3, help='Semillas promediadas por punto SNR')
    parser.add_argument('--input', default=os.path.join(here, 'frames_STRAND1_bits.bin'))
    parser.add_argument('--outdir', default=os.path.join(here, 'resultados_simulacion'))
    parser.add_argument('--tmpdir', default='/tmp/opencode')
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    os.makedirs(args.tmpdir, exist_ok=True)
    tx = leer_bits(args.input)

    filas = []
    for snr in np.arange(args.snr_min, args.snr_max + 1e-9, args.step):
        snr = float(snr)
        er = 0
        for s in range(args.seeds):
            seed = 1000 + s
            out = os.path.join(args.tmpdir, f'rx_{snr}dB_s{s}.bin')
            run_cadena(args.input, out, snr, seed)
            rx = leer_bits(out)
            m = min(len(tx), len(rx))
            er += int(np.sum(tx[:m] != rx[:m]))
        emp = er / (args.seeds * N)
        theo = ber_teorico_q(snr)
        filas.append((snr, er, emp, theo))
        print(f'SNR {snr:5.1f} dB   errores={er:6d}/{args.seeds*N}   BER_emp={emp:.3e}   BER_teorico={theo:.3e}')

    csv_path = os.path.join(args.outdir, 'ber_strand1_sweep.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['snr_db', 'errores_totales', 'bits_totales', 'ber_empirica', 'ber_teorica'])
        for snr, er, emp, theo in filas:
            w.writerow([f'{snr:.1f}', er, args.seeds * N, f'{emp:.6e}', f'{theo:.6e}'])
    print(f'CSV guardado en {csv_path}')

    snrs = [r[0] for r in filas]
    emp = [r[2] for r in filas]
    theo = [r[3] for r in filas]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.semilogy(snrs, theo, 'k-', label='Teorica BPSK $Q(\\sqrt{2E_b/N_0})$')
    ax.semilogy([s + 0.05 for s in snrs], [max(v, 1e-9) for v in emp], 'b.', markersize=9, label='Simulacion STRAND-1')
    ax.set_xlabel('$E_b/N_0$ (dB)')
    ax.set_ylabel('BER')
    ax.grid(True, which='both', alpha=0.4)
    ax.legend()
    ax.set_ylim(1e-7, 1)
    png_path = os.path.join(args.outdir, 'ber_strand1_sweep.png')
    fig.savefig(png_path, dpi=150)
    print(f'Grafica guardada en {png_path}')


if __name__ == '__main__':
    main()
#!/usr/bin/env python3
import numpy as np
import argparse
import math
import os


def ber_calculo(tx_bin, rx_bin):
    tx = np.frombuffer(open(tx_bin, 'rb').read(), dtype=np.uint8)
    rx = np.frombuffer(open(rx_bin, 'rb').read(), dtype=np.uint8)
    m = min(len(tx), len(rx))
    errores = int(np.sum(tx[:m] != rx[:m]))
    return errores, m


def ber_teorico_q(snr_db):
    return 0.5 * math.erfc(np.sqrt(10.0 ** (snr_db / 10.0)))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description='Validacion BER STRAND-1')
    parser.add_argument('--tx', default=os.path.join(here, 'frames_STRAND1_bits.bin'))
    parser.add_argument('--rx', default=os.path.join(here, 'frames_STRAND1_bits_rx.bin'))
    parser.add_argument('--snr-db', type=float, default=10.0)
    args = parser.parse_args()

    errores, m = ber_calculo(args.tx, args.rx)
    emp = errores / m
    theo = ber_teorico_q(args.snr_db)

    print("=== BER STRAND-1 ===")
    print(f"bits comparados : {m}")
    print(f"errores         : {errores}")
    print(f"Eb/N0 (dB)      : {args.snr_db:.1f}")
    print(f"BER empirico    : {emp:.3e}")
    print(f"BER teorico Q   : {theo:.3e}")


if __name__ == '__main__':
    main()
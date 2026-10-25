"""Generate LIFE PWA icons using only the Python standard library.

Run from any directory: python3 scripts/generar-iconos.py
"""

from pathlib import Path
import math
import struct
import zlib


ROOT = Path(__file__).resolve().parent.parent
BACKGROUND = (51, 45, 34)
GREEN = (143, 184, 122)


def pixel(x, y):
    # A pointed leaf tilted toward the top-right, with a quiet central vein.
    dx, dy = x - 0.50, y - 0.48
    u = (dx - dy) / math.sqrt(2) / 0.36
    v = (dx + dy) / math.sqrt(2) / 0.20
    width = (1 - abs(u)) ** 0.72 if abs(u) < 1 else 0
    if abs(v) < width:
        shade = 0.88 + 0.12 * (1 - abs(v) / width)
        color = tuple(round(channel * shade) for channel in GREEN)
        if -0.75 < u < 0.77 and abs(v) < 0.045:
            color = (188, 213, 172)
        return color
    # A short stem continues the leaf's diagonal.
    if -1.27 < u < -0.84 and abs(v) < 0.027:
        return (112, 151, 96)
    return BACKGROUND


def chunk(kind, data):
    return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))


def write_png(size):
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            samples = [pixel((x + sx) / size, (y + sy) / size)
                       for sy in (0.25, 0.75) for sx in (0.25, 0.75)]
            rows.extend(round(sum(sample[channel] for sample in samples) / 4) for channel in range(3))
    signature = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('!2I5B', size, size, 8, 2, 0, 0, 0)
    output = signature + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b'')
    path = ROOT / 'icons' / f'icon-{size}.png'
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(output)


for icon_size in (180, 192, 512):
    write_png(icon_size)

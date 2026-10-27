"""Original synthetic motion textures and independent integer displacement recipes."""

import random


def texture(width=96, height=64, shift=(0, 0), *, seed=71):
    rng = random.Random(seed)
    canvas_width = width + 32
    canvas = rng.randbytes(canvas_width * (height + 32))
    dx, dy = shift
    return b"".join(
        canvas[
            (y + 16 - dy) * canvas_width + 16 - dx : (y + 16 - dy) * canvas_width + 16 - dx + width
        ]
        for y in range(height)
    )


def sequence(kind):
    shifts = {
        "static": [0, 0, 0, 0],
        "pan": [0, 1, 2, 3],
        "jitter": [0, 2, 0, 2],
        "subject": [0, 0, 0, 0],
        "camera-subject": [0, 1, 2, 3],
        "boundary": [0, 4, 8, 12],
        "majority-subject": [0, 0, 0, 0],
    }
    if kind in shifts:
        frames = [bytearray(texture(shift=(dx, 0))) for dx in shifts[kind]]
        if kind in {"subject", "camera-subject", "majority-subject"}:
            sw, sh, x0, y0 = (56, 64, 0, 0) if kind == "majority-subject" else (24, 18, 8, 12)
            subject = random.Random(89).randbytes(sw * sh)
            for index, frame in enumerate(frames):
                dx = index if kind != "majority-subject" else index * 2
                for y in range(sh):
                    frame[(y0 + y) * 96 + x0 + dx : (y0 + y) * 96 + x0 + dx + sw] = subject[
                        y * sw : (y + 1) * sw
                    ]
        return [bytes(frame) for frame in frames]
    if kind == "flat":
        return [bytes([128]) * (96 * 64)] * 4
    if kind == "periodic":
        return [bytes((x % 2) * 255 for y in range(64) for x in range(96))] * 4
    if kind == "occlusion":
        return [texture(seed=seed) for seed in (71, 99, 71, 99)]
    raise ValueError("Unknown synthetic motion case")

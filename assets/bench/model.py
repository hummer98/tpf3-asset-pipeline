"""Park bench (1.8 m) — pipeline smoke test asset."""
import math
import random


def build(lib):
    rnd = random.Random(1)

    def wood(x, y):
        # Grain along U so cube-projected slats read as planks.
        g = 0.5 + 0.5 * math.sin(y * 0.35 + math.sin(x * 0.02) * 3)
        n = rnd.random() * 0.06
        return (0.42 + 0.10 * g + n, 0.26 + 0.06 * g + n, 0.13 + 0.03 * g, 1.0)

    wood_img = lib.image("bench_wood_alb", (256, 256), wood)
    m_wood = lib.material("bench_wood", wood_img)
    m_iron = lib.material("bench_iron", color=(0.08, 0.09, 0.1, 1))

    L, H = 1.8, 0.45
    parts = []
    for i in range(3):  # seat slats
        parts.append(lib.box(f"seat{i}", (L, 0.12, 0.035), (0, -0.16 + i * 0.15, H), m_wood))
    for i in range(2):  # back slats
        parts.append(lib.box(f"back{i}", (L, 0.035, 0.11), (0, 0.24, 0.62 + i * 0.16), m_wood))
    for sx in (-0.75, 0.75):  # cast-iron side frames
        parts.append(lib.box("leg_f", (0.05, 0.05, H), (sx, -0.2, H / 2), m_iron))
        parts.append(lib.box("leg_b", (0.05, 0.05, 0.85), (sx, 0.27, 0.425), m_iron))
        parts.append(lib.box("arm", (0.05, 0.5, 0.04), (sx, 0.03, 0.66), m_iron))
        parts.append(lib.box("rail", (0.05, 0.5, 0.04), (sx, 0.03, H - 0.04), m_iron))
    lod0 = lib.join(parts, "bench")

    # LOD1: seat + back as two blocks, legs merged into one slab per side.
    lp = [lib.box("seat", (L, 0.45, 0.035), (0, -0.01, H), m_wood),
          lib.box("back", (L, 0.035, 0.27), (0, 0.24, 0.70), m_wood)]
    for sx in (-0.75, 0.75):
        lp.append(lib.box("side", (0.05, 0.5, 0.66), (sx, 0.03, 0.33), m_iron))
    lod1 = lib.join(lp, "bench")

    return {"lods": {0: [lod0], 1: [lod1]}, "textures": [(wood_img, "bench_wood_alb.tga")]}

"""
Ultra-Detailed Integrated Scene Simulation  (v2)

Controls:
    SPACE  - start a rocket countdown right now
    H      - toggle the HUD
    ESC    - quit

Test options (optional):
    python scene.py --frames 420 --shots 90,255,330 --prefix /tmp/scene
"""
import argparse
import math
import random
import sys
from functools import lru_cache

import pygame

# ==========================================
# INITIALIZATION & GLOBAL CONSTANTS
# ==========================================
pygame.init()
WIDTH, HEIGHT = 1000, 750
HORIZON = 480
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Ultra-Detailed Integrated Scene Simulation")
clock = pygame.time.Clock()
world = pygame.Surface((WIDTH, HEIGHT))

FONT_SM = pygame.font.Font(None, 22)
FONT_MD = pygame.font.Font(None, 30)
FONT_LG = pygame.font.Font(None, 84)

COLOR_MOON = (245, 240, 210)
COLOR_MOON_CRATER = (210, 205, 175)

ENV = {"wind": 0.3, "t": 0}


# ==========================================
# SMALL HELPERS
# ==========================================
def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return (int(lerp(c1[0], c2[0], t)), int(lerp(c1[1], c2[1], t)), int(lerp(c1[2], c2[2], t)))


def scale_color(c, k):
    return (max(0, min(255, int(c[0] * k))), max(0, min(255, int(c[1] * k))), max(0, min(255, int(c[2] * k))))


@lru_cache(maxsize=3000)
def glow_surface(radius, color):
    """Radial falloff on black; blitted with BLEND_RGB_ADD for light effects."""
    surf = pygame.Surface((radius * 2, radius * 2))
    step = max(1, radius // 48)
    for r in range(radius, 0, -step):
        k = (1.0 - r / radius) ** 2
        pygame.draw.circle(
            surf, (int(color[0] * k), int(color[1] * k), int(color[2] * k)), (radius, radius), r
        )
    return surf


def _quant(color):
    return (min(255, int(color[0])) // 8 * 8, min(255, int(color[1])) // 8 * 8, min(255, int(color[2])) // 8 * 8)


def draw_glow(surface, pos, radius, color):
    r = int(radius) // 4 * 4
    if r < 4:
        return
    q = _quant(color)
    if q == (0, 0, 0):
        return
    surface.blit(glow_surface(r, q), (int(pos[0]) - r, int(pos[1]) - r), special_flags=pygame.BLEND_RGB_ADD)


@lru_cache(maxsize=300)
def glow_ellipse_surface(rx, ry, color):
    return pygame.transform.scale(glow_surface(rx, color), (rx * 2, ry * 2))


def draw_glow_ellipse(surface, pos, rx, ry, color):
    rx = int(rx) // 4 * 4
    ry = int(ry) // 2 * 2
    if rx < 4 or ry < 2:
        return
    q = _quant(color)
    if q == (0, 0, 0):
        return
    surface.blit(glow_ellipse_surface(rx, ry, q), (int(pos[0]) - rx, int(pos[1]) - ry), special_flags=pygame.BLEND_RGB_ADD)


@lru_cache(maxsize=1500)
def circle_surface(radius, color):
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(surf, color, (radius, radius), radius)
    return surf


# ==========================================
# PARTICLE SYSTEM
# ==========================================
class Particle:
    def __init__(self, x, y, vx, vy, size, life, color_start, color_end,
                 additive=False, drag=0.99, gravity=0.0, shrink=0.96,
                 alpha_max=255, max_size=60):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.size = size
        self.max_life = life
        self.life = life
        self.color_start = color_start
        self.color_end = color_end
        self.additive = additive
        self.drag = drag
        self.gravity = gravity
        self.shrink = shrink
        self.alpha_max = alpha_max
        self.max_size = max_size

    def update(self):
        self.vx *= self.drag
        self.vy = self.vy * self.drag + self.gravity
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        self.size = min(self.max_size, max(0.5, self.size * self.shrink))

    def draw(self, surface):
        if self.life <= 0:
            return
        k = int(10 * self.life / self.max_life) / 10.0
        color = lerp_color(self.color_start, self.color_end, 1.0 - k)
        r = max(1, int(self.size))
        if self.additive:
            draw_glow(surface, (self.x, self.y), max(4, r * 3), scale_color(color, k))
        else:
            surf = circle_surface(r, (color[0] // 8 * 8, color[1] // 8 * 8, color[2] // 8 * 8))
            surf.set_alpha(int(self.alpha_max * k))
            surface.blit(surf, (int(self.x) - r, int(self.y) - r))


class ParticleList(list):
    def update(self):
        for p in self:
            p.update()
        self[:] = [p for p in self if p.life > 0]

    def draw(self, surface):
        for p in self:
            p.draw(surface)


# ==========================================
# BAKED BACKGROUND LAYERS
# ==========================================
def build_sky():
    surf = pygame.Surface((WIDTH, HEIGHT))
    top, mid, bot = (4, 6, 18), (14, 20, 48), (54, 60, 108)
    span = HORIZON + 40
    for y in range(span):
        t = y / span
        c = lerp_color(top, mid, t / 0.6) if t < 0.6 else lerp_color(mid, bot, (t - 0.6) / 0.4)
        pygame.draw.line(surf, c, (0, y), (WIDTH, y))
    surf.fill(bot, (0, span, WIDTH, HEIGHT - span))

    rng = random.Random(11)
    # Milky Way: soft diagonal glow plus dense dim stars
    for i in range(26):
        x = i * WIDTH / 25
        y = 330 - 0.32 * x
        draw_glow(surf, (x, y), 100, (7, 9, 20))
    for _ in range(1100):
        x = rng.uniform(0, WIDTH)
        y = 330 - 0.32 * x + rng.gauss(0, 34)
        if 0 <= y < 430:
            b = rng.randint(50, 130)
            surf.set_at((int(x), int(y)), (b, b, min(255, b + 20)))
    return surf


def _ridge(rng, base_y, amp, seed_phase):
    p1, p2, p3 = (rng.uniform(0, 6.28) for _ in range(3))
    pts = []
    for x in range(0, WIDTH + 6, 6):
        h = amp * (0.55 * abs(math.sin(x * 0.004 + p1 + seed_phase))
                   + 0.30 * abs(math.sin(x * 0.011 + p2))
                   + 0.08 * math.sin(x * 0.031 + p3) + 0.1)
        pts.append((x, base_y - h))
    return pts


def build_far_layer():
    layer = pygame.Surface((WIDTH, HORIZON + 4), pygame.SRCALPHA)
    rng = random.Random(7)

    for base, amp, col, rim, ph in (
        (472, 165, (24, 30, 62), (70, 84, 140), 0.0),
        (478, 95, (15, 21, 42), (44, 58, 100), 2.0),
    ):
        pts = _ridge(rng, base, amp, ph)
        pygame.draw.polygon(layer, col, pts + [(WIDTH, HORIZON + 4), (0, HORIZON + 4)])
        pygame.draw.lines(layer, rim, False, pts, 2)

    # City skyline
    beacons = []
    x = -10
    while x < WIDTH:
        w = rng.randint(22, 52)
        h = rng.randint(22, 92)
        col = (12 + rng.randint(0, 6), 16 + rng.randint(0, 6), 34 + rng.randint(0, 8))
        rect = pygame.Rect(x, HORIZON + 2 - h, w, h)
        pygame.draw.rect(layer, col, rect)
        pygame.draw.line(layer, (36, 44, 78), rect.topleft, rect.topright, 1)
        for wy in range(rect.top + 6, HORIZON - 4, 9):
            for wx in range(x + 4, x + w - 5, 8):
                if rng.random() < 0.32:
                    lc = rng.choice([(255, 226, 140), (255, 205, 110), (170, 210, 255)])
                    pygame.draw.rect(layer, lc, (wx, wy, 3, 4))
        if rng.random() < 0.35:
            pygame.draw.line(layer, (36, 44, 78), (x + w // 2, rect.top), (x + w // 2, rect.top - 12), 1)
            beacons.append((x + w // 2, rect.top - 12))
        x += w + rng.randint(-4, 6)

    # Treeline silhouette on the horizon
    for tx in range(-10, WIDTH + 20, 14):
        r = rng.randint(10, 22)
        pygame.draw.circle(layer, (8, 24, 20), (tx, HORIZON - 2), r)
    pygame.draw.rect(layer, (8, 24, 20), (0, HORIZON - 4, WIDTH, 8))

    # Atmospheric fog
    fog = pygame.Surface((WIDTH, HORIZON + 4), pygame.SRCALPHA)
    for y in range(380, HORIZON + 4):
        a = int(78 * min(1.0, ((y - 380) / 100.0)) ** 1.5)
        pygame.draw.line(fog, (70, 84, 140, a), (0, y), (WIDTH, y))
    layer.blit(fog, (0, 0))
    return layer, beacons


def build_ground():
    h = HEIGHT - HORIZON
    ground = pygame.Surface((WIDTH, h))
    rng = random.Random(21)

    def Y(y):
        return y - HORIZON

    # Lawn gradient
    for y in range(h):
        pygame.draw.line(ground, lerp_color((17, 60, 29), (8, 33, 17), y / h), (0, y), (WIDTH, y))
    # Grass texture
    for _ in range(5200):
        gx = rng.randint(0, WIDTH)
        gy = rng.randint(0, h - 1)
        ln = rng.randint(3, 8)
        c = rng.choice([(10, 44, 20), (24, 86, 36), (30, 100, 42), (13, 52, 24)])
        pygame.draw.line(ground, c, (gx, gy), (gx + rng.randint(-2, 2), gy - ln), 1)

    # Flowers
    palette = [(230, 60, 90), (250, 200, 60), (200, 120, 240), (255, 255, 255), (255, 140, 60)]
    spots = [(rng.randint(50, 430), rng.randint(526, 544)) for _ in range(70)]
    spots += [(rng.randint(0, WIDTH), rng.randint(652, 745)) for _ in range(60)]
    for fx, fy in spots:
        pygame.draw.line(ground, (20, 90, 34), (fx, Y(fy)), (fx, Y(fy) + 5), 1)
        pygame.draw.circle(ground, rng.choice(palette), (fx, Y(fy)), rng.randint(2, 3))

    # Stone path from the door to the road
    for i, py in enumerate(range(524, 548, 6)):
        w = 22 - i
        pygame.draw.ellipse(ground, (96, 96, 104), (240 - w // 2 - rng.randint(0, 3), Y(py), w, 6))
        pygame.draw.ellipse(ground, (70, 70, 80), (240 - w // 2, Y(py), w, 6), 1)

    # Upper sidewalk
    pygame.draw.rect(ground, (62, 64, 72), (0, Y(548), WIDTH, 12))
    for sx in range(0, WIDTH, 44):
        pygame.draw.line(ground, (44, 46, 54), (sx, Y(548)), (sx, Y(560)), 1)
    pygame.draw.line(ground, (96, 98, 108), (0, Y(548)), (WIDTH, Y(548)), 1)
    pygame.draw.line(ground, (20, 20, 26), (0, Y(559)), (WIDTH, Y(559)), 2)

    # Asphalt
    for y in range(560, 630):
        d = abs(y - 595) / 35.0
        pygame.draw.line(ground, lerp_color((52, 55, 63), (40, 43, 50), d), (0, Y(y)), (WIDTH, Y(y)))
    for _ in range(1400):
        v = rng.randint(-10, 12)
        ax = rng.randint(0, WIDTH - 1)
        ay = Y(rng.randint(561, 629))
        ground.set_at((ax, ay), (48 + v, 51 + v, 58 + v))
    pygame.draw.line(ground, (150, 150, 158), (0, Y(564)), (WIDTH, Y(564)), 1)
    pygame.draw.line(ground, (150, 150, 158), (0, Y(626)), (WIDTH, Y(626)), 1)
    for rx in range(10, WIDTH, 60):  # center line
        pygame.draw.line(ground, (220, 200, 60), (rx, Y(595)), (rx + 35, Y(595)), 3)

    # Lower sidewalk
    pygame.draw.rect(ground, (58, 60, 68), (0, Y(630), WIDTH, 12))
    pygame.draw.line(ground, (88, 90, 98), (0, Y(630)), (WIDTH, Y(630)), 2)
    for sx in range(20, WIDTH, 44):
        pygame.draw.line(ground, (42, 44, 52), (sx, Y(630)), (sx, Y(642)), 1)
    return ground


def build_vignette():
    sw, sh = WIDTH // 5, HEIGHT // 5
    v = pygame.Surface((sw, sh), pygame.SRCALPHA)
    cx, cy = sw / 2, sh / 2
    for y in range(sh):
        for x in range(sw):
            d = math.hypot((x - cx) / cx, (y - cy) / cy) / 1.414
            a = int(max(0.0, min(1.0, (d - 0.45) / 0.55)) ** 1.6 * 190)
            v.set_at((x, y), (0, 0, 0, a))
    return pygame.transform.smoothscale(v, (WIDTH, HEIGHT))


# ==========================================
# SKY ENTITIES
# ==========================================
def make_stars(n=170):
    tints = [(200, 210, 230), (255, 240, 210), (190, 210, 255)]
    return [(random.randint(0, WIDTH), random.randint(0, 430), random.choice([1, 1, 2]),
             random.uniform(0, 6.28), random.uniform(0.02, 0.08), random.choice(tints)) for _ in range(n)]


def draw_stars(surface, stars, t):
    for sx, sy, size, ph, sp, col in stars:
        b = 0.65 + 0.35 * math.sin(ph + t * sp)
        c = scale_color(col, b)
        pygame.draw.circle(surface, c, (sx, sy), size)
        if size == 2 and b > 0.93:
            c2 = scale_color(col, 0.5)
            pygame.draw.line(surface, c2, (sx - 4, sy), (sx + 4, sy), 1)
            pygame.draw.line(surface, c2, (sx, sy - 4), (sx, sy + 4), 1)


class ShootingStar:
    def __init__(self):
        self.x = random.uniform(250, WIDTH + 100)
        self.y = random.uniform(0, 200)
        ang = math.radians(random.uniform(150, 170))
        sp = random.uniform(12, 18)
        self.vx, self.vy = math.cos(ang) * sp, math.sin(ang) * sp
        self.life = self.max = random.randint(25, 45)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1

    def draw(self, surface):
        fade = min(1.0, self.life / (self.max * 0.5))
        for i in range(14):
            k = (1 - i / 14) * fade
            p1 = (self.x - self.vx * i * 0.7, self.y - self.vy * i * 0.7)
            p2 = (self.x - self.vx * (i + 1) * 0.7, self.y - self.vy * (i + 1) * 0.7)
            pygame.draw.line(surface, scale_color((255, 255, 255), k), p1, p2, 2 if i < 5 else 1)


def draw_aurora(surface, buf, t):
    buf.fill((0, 0, 0, 0))
    bands = [(150, (60, 255, 160), 0.0, 1.0), (195, (110, 120, 255), 2.0, 0.7)]
    for base, col, ph, amp in bands:
        for x in range(0, WIDTH + 8, 8):
            y = base + math.sin(x * 0.006 + t * 0.008 + ph) * 28 + math.sin(x * 0.017 - t * 0.013 + ph * 2) * 12
            hgt = (70 + 45 * math.sin(x * 0.009 + t * 0.011 + ph * 3)) * amp
            pulse = 0.6 + 0.4 * math.sin(t * 0.02 + x * 0.03 + ph)
            for k in range(4):
                a = max(0, int(46 * (1 - k / 4) ** 1.5 * pulse))
                pygame.draw.line(buf, (col[0], col[1], col[2], a),
                                 (x, int(y - hgt * k / 4)), (x, int(y - hgt * (k + 1) / 4)), 8)
    surface.blit(buf, (0, 0))


class Moon:
    def __init__(self, start_pos, target_pos):
        self.pos = pygame.math.Vector2(start_pos)
        self.target = pygame.math.Vector2(target_pos)
        self.radius = 45
        self.S = self.radius * 2 + 8
        self.surf = self._bake()
        self.arrived = False

    def _bake(self):
        R, S = self.radius, self.S
        c = S // 2
        s = pygame.Surface((S, S), pygame.SRCALPHA)
        pygame.draw.circle(s, COLOR_MOON, (c, c), R)
        for dx, dy, r in ((-33, -6, 4), (-36, 8, 5), (-30, 18, 4), (-38, -16, 3)):
            pygame.draw.circle(s, COLOR_MOON_CRATER, (c + dx, c + dy), r)
        pygame.draw.circle(s, (0, 0, 0, 0), (c + 18, c - 8), R - 4)  # true transparent crescent cut
        return s

    def update(self):
        distance = self.pos.distance_to(self.target)
        if distance > 0.5:
            direction = (self.target - self.pos).normalize()
            self.pos += direction * max(0.3, distance * 0.005)
        else:
            self.arrived = True

    def draw(self, surface, t):
        bob = math.sin(t * 0.02) * 1.5 if self.arrived else 0
        x, y = int(self.pos.x), int(self.pos.y + bob)
        draw_glow(surface, (x, y), 180, (46, 44, 34))
        draw_glow(surface, (x, y), 92, (40, 38, 28))
        surface.blit(self.surf, (x - self.S // 2, y - self.S // 2))


def make_cloud_surface(seed, w, h):
    rng = random.Random(seed)
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    blobs = []
    for i in range(rng.randint(9, 14)):
        bx = rng.randint(int(w * 0.15), int(w * 0.85))
        by = int(h * 0.62) - int(abs(math.sin(i)) * h * 0.25) + rng.randint(-5, 5)
        br = rng.randint(int(h * 0.22), int(h * 0.42))
        blobs.append((bx, by, br))
    for bx, by, br in blobs:
        pygame.draw.circle(s, (105, 118, 170, 70), (bx - 3, by - 4), br)
    for bx, by, br in blobs:
        pygame.draw.circle(s, (30, 38, 76, 95), (bx, by), max(2, br - 2))
    return s


class Cloud:
    def __init__(self, x, y, speed, seed, w, h, alpha):
        self.x, self.y, self.speed, self.w = x, y, speed, w
        self.surf = make_cloud_surface(seed, w, h)
        self.surf.set_alpha(alpha)

    def update(self):
        self.x += self.speed * (0.6 + ENV["wind"])
        if self.x > WIDTH:
            self.x = -self.w

    def draw(self, surface):
        surface.blit(self.surf, (int(self.x), int(self.y)))


# ==========================================
# ROCKET + LAUNCH PAD
# ==========================================
def build_rocket_surface():
    W, H = 90, 150
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    cx, top = 45, 40

    def P(dx, dy):
        return (cx + dx, top + dy)

    # Nozzle bell
    pygame.draw.polygon(s, (60, 60, 68), [P(-9, 68), P(9, 68), P(14, 84), P(-14, 84)])
    pygame.draw.polygon(s, (35, 35, 42), [P(-6, 70), P(6, 70), P(9, 82), P(-9, 82)])
    # Fins
    pygame.draw.polygon(s, (150, 20, 20), [P(-15, 40), P(-32, 76), P(-15, 70)])
    pygame.draw.polygon(s, (150, 20, 20), [P(15, 40), P(32, 76), P(15, 70)])
    pygame.draw.polygon(s, (205, 55, 55), [P(-15, 40), P(-32, 76), P(-29, 75), P(-15, 46)])
    pygame.draw.polygon(s, (205, 55, 55), [P(15, 40), P(32, 76), P(29, 75), P(15, 46)])
    # Side boosters
    for sgn in (-1, 1):
        x0 = cx - 26 if sgn < 0 else cx + 15
        pygame.draw.rect(s, (205, 205, 212), (x0, top + 20, 11, 48), border_radius=3)
        pygame.draw.rect(s, (160, 160, 172), (x0 + (7 if sgn > 0 else 0), top + 20, 4, 48), border_radius=2)
        pygame.draw.polygon(s, (170, 30, 30), [(x0, top + 20), (x0 + 11, top + 20), (x0 + 5, top + 4)])
        pygame.draw.polygon(s, (55, 55, 62), [(x0 + 2, top + 68), (x0 + 9, top + 68), (x0 + 11, top + 76), (x0, top + 76)])
    # Main body with cylindrical shading
    for i in range(30):
        k = 0.72 + 0.28 * math.sin(math.pi * (i + 4) / 34)
        pygame.draw.rect(s, scale_color((236, 236, 242), k), (cx - 15 + i, top, 1, 70))
    pygame.draw.rect(s, (200, 30, 35), (cx - 15, top + 46, 30, 5))
    pygame.draw.rect(s, (40, 40, 50), (cx - 15, top + 52, 30, 2))
    pygame.draw.rect(s, (96, 96, 110), (cx - 15, top + 60, 30, 10))
    pygame.draw.line(s, (170, 170, 182), P(-5, 4), P(-5, 44), 1)
    pygame.draw.line(s, (170, 170, 182), P(8, 4), P(8, 44), 1)
    # Ogive nose cone
    pts = [(15 * math.sqrt(max(0.0, 1 - (j / 10) ** 2)), -35 * j / 10) for j in range(11)]
    left = [P(-h, y) for h, y in pts]
    right = [P(h, y) for h, y in pts]
    pygame.draw.polygon(s, (205, 32, 32), left + right[::-1])
    pygame.draw.polygon(s, (238, 84, 74), left + [P(-h * 0.55, y) for h, y in pts][::-1])
    pygame.draw.polygon(s, (150, 20, 25), [P(h * 0.6, y) for h, y in pts] + right[::-1])
    # Porthole
    pygame.draw.circle(s, (50, 55, 70), P(0, 25), 9)
    pygame.draw.circle(s, (120, 200, 245), P(0, 25), 7)
    pygame.draw.circle(s, (205, 238, 255), P(-2, 23), 2)
    pygame.draw.circle(s, (190, 190, 200), P(0, 25), 10, 2)
    for ry in (8, 36, 58):
        pygame.draw.circle(s, (150, 150, 162), P(-11, ry), 1)
        pygame.draw.circle(s, (150, 150, 162), P(11, ry), 1)
    return s


class Rocket:
    WAIT, IGNITE, ASCENT, COOLDOWN = range(4)
    IGNITE_FRAMES = 70

    def __init__(self, x, pad_y):
        self.x = x
        self.pad_y = pad_y
        self.rest_y = pad_y - 80
        self.surf = build_rocket_surface()
        self.fire = ParticleList()
        self.smoke = ParticleList()
        self.launches = 0
        self.flash = 0.0
        self.shake = 0.0
        self.ignited = False
        self.reset()
        self.timer = 150  # first launch comes quickly

    def reset(self):
        self.state = self.WAIT
        self.pos_y = float(self.rest_y)
        self.vel = 0.0
        self.arm = 1.0
        self.stage = 0
        self.timer = random.randint(200, 280)

    def trigger(self):
        if self.state == self.WAIT:
            self.timer = min(self.timer, 180)

    def status(self):
        if self.state == self.WAIT:
            return ("T-%d" % math.ceil(self.timer / 60)) if self.timer <= 180 else "STANDBY"
        return {self.IGNITE: "IGNITION", self.ASCENT: "LIFTOFF", self.COOLDOWN: "TRACKING"}[self.state]

    # --- particle emitters
    def _emit_fire(self, n, speed_scale):
        nx, ny = self.x, self.pos_y + 82
        for _ in range(n):
            ang = random.gauss(0, 0.12)
            spd = random.uniform(3, 7) * speed_scale + self.vel * 0.3
            self.fire.append(Particle(
                nx + random.uniform(-4, 4), ny, math.sin(ang) * spd * 1.2, math.cos(ang) * spd,
                random.uniform(4, 8), random.randint(14, 28),
                (255, 235, 170), (255, 70, 10), additive=True, drag=0.97, shrink=0.95))

    def _emit_trail(self, n):
        for _ in range(n):
            self.smoke.append(Particle(
                self.x + random.uniform(-4, 4), self.pos_y + 92, random.uniform(-0.6, 0.6) + ENV["wind"] * 0.5,
                random.uniform(1, 2.2), random.uniform(5, 9), random.randint(60, 100),
                (150, 150, 158), (50, 50, 62), shrink=1.012, alpha_max=110, max_size=34))

    def _emit_ground_smoke(self, n):
        for _ in range(n):
            self.smoke.append(Particle(
                self.x + random.uniform(-40, 40), self.pad_y - 2,
                random.choice([-1, 1]) * random.uniform(1.0, 4.5), -random.uniform(0.05, 0.7),
                random.uniform(7, 14), random.randint(60, 110),
                (200, 165, 130), (70, 70, 82), drag=0.97, shrink=1.012, alpha_max=100, max_size=40))

    def _emit_vent(self):
        self.smoke.append(Particle(
            self.x + 16, self.pos_y + 8, random.uniform(0.2, 0.6), -random.uniform(0.3, 0.8),
            random.uniform(2, 3.5), 50, (235, 240, 250), (120, 130, 150), shrink=1.02, alpha_max=120, max_size=14))

    def update(self):
        self.ignited = False
        self.shake = 0.0
        if self.state == self.WAIT:
            self.timer -= 1
            if random.random() < 0.18:
                self._emit_vent()
            if self.timer <= 0:
                self.state = self.IGNITE
                self.stage = 0
                self.ignited = True
                self.launches += 1
                self.flash = 1.0
        elif self.state == self.IGNITE:
            self.stage += 1
            k = self.stage / self.IGNITE_FRAMES
            self.arm = max(0.0, 1.0 - k * 3)
            self._emit_fire(int(1 + 5 * k), 0.6 + 0.4 * k)
            self._emit_ground_smoke(int(1 + 2 * k))
            self.shake = 1.5 * k
            if self.stage >= self.IGNITE_FRAMES:
                self.state = self.ASCENT
                self.vel = 0.2
        elif self.state == self.ASCENT:
            self.vel += 0.085
            self.pos_y -= self.vel
            alt = self.rest_y - self.pos_y
            self._emit_fire(8, 1.0)
            self._emit_trail(2)
            if alt < 260:
                self._emit_ground_smoke(2)
                self.shake = max(0.0, 3.5 * (1 - alt / 260))
            if self.pos_y < -170:
                self.state = self.COOLDOWN
                self.timer = 40
        else:
            self.timer -= 1
            if self.timer <= 0:
                self.reset()
        self.fire.update()
        self.smoke.update()
        self.flash *= 0.9

    # --- drawing
    def draw_pad(self, surface, t):
        x, py = self.x, self.pad_y
        pygame.draw.ellipse(surface, (20, 20, 24), (x - 70, py - 8, 140, 22))
        pygame.draw.rect(surface, (86, 88, 96), (x - 60, py, 120, 14))
        pygame.draw.rect(surface, (56, 58, 66), (x - 60, py + 14, 120, 6))
        for i in range(0, 120, 12):
            col = (200, 170, 30) if (i // 12) % 2 == 0 else (30, 30, 30)
            pygame.draw.rect(surface, col, (x - 60 + i, py + 3, 12, 6))
        # Gantry tower
        tx, top = x - 52, py - 175
        for px in (tx, tx + 18):
            pygame.draw.line(surface, (70, 72, 84), (px, py), (px, top), 3)
        for yy in range(py, top, -18):
            pygame.draw.line(surface, (60, 62, 74), (tx, yy), (tx + 18, yy - 18), 1)
            pygame.draw.line(surface, (60, 62, 74), (tx + 18, yy), (tx, yy - 18), 1)
            pygame.draw.line(surface, (80, 82, 94), (tx, yy), (tx + 18, yy), 1)
        pygame.draw.line(surface, (120, 120, 130), (tx + 9, top), (tx + 9, top - 22), 2)
        if (t // 30) % 2 == 0:
            draw_glow(surface, (tx + 9, top - 22), 24, (255, 40, 30))
            pygame.draw.circle(surface, (255, 70, 60), (tx + 9, top - 22), 3)
        # Swing arm + umbilical (retracts at ignition)
        ay = py - 110
        end = tx + 18 + int(19 * self.arm)
        pygame.draw.line(surface, (110, 112, 124), (tx + 18, ay), (end, ay), 4)
        pygame.draw.line(surface, (70, 200, 230), (tx + 18, ay + 4), (end, ay + 4), 1)
        # Floodlights
        draw_glow(surface, (tx + 9, top + 14), 34, (150, 160, 200))

    def draw(self, surface, t):
        self.smoke.draw(surface)
        if self.state != self.COOLDOWN:
            sx = random.uniform(-self.shake, self.shake)
            sy = random.uniform(-self.shake, self.shake)
            surface.blit(self.surf, (int(self.x) - 45 + int(sx), int(self.pos_y) - 40 + int(sy)))
            if self.state in (self.WAIT, self.IGNITE):
                draw_glow(surface, (self.x - 5, self.pos_y + 30), 72, (40, 44, 58))
        self.fire.draw(surface)

        inten = 0.0
        if self.state == self.IGNITE:
            inten = self.stage / self.IGNITE_FRAMES * 0.7
        elif self.state == self.ASCENT:
            inten = max(0.0, 1 - (self.rest_y - self.pos_y) / 420)
        if inten > 0:
            draw_glow(surface, (self.x, self.pad_y - 10), 240, scale_color((190, 100, 35), inten))
            draw_glow_ellipse(surface, (self.x, self.pad_y + 4), 200, 40, scale_color((255, 160, 60), inten * 0.7))
        if self.state in (self.IGNITE, self.ASCENT):
            strength = min(1.0, self.stage / self.IGNITE_FRAMES) if self.state == self.IGNITE else 1.0
            fl = random.uniform(0.8, 1.0) * strength
            draw_glow(surface, (self.x, self.pos_y + 84), int(60 + 60 * strength), scale_color((255, 170, 80), fl))
            if self.state == self.ASCENT:
                draw_glow(surface, (self.x, self.pos_y + 84), 200, scale_color((110, 60, 20), fl))


# ==========================================
# BUILDING
# ==========================================
class Building:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 280, 220)
        self.door_rect = pygame.Rect(x + 115, y + 140, 50, 80)
        self.windows = [
            pygame.Rect(x + 30, y + 30, 60, 60),    # TV window
            pygame.Rect(x + 190, y + 30, 60, 60),   # always lit
            pygame.Rect(x + 30, y + 120, 60, 60),   # dark
            pygame.Rect(x + 190, y + 120, 60, 60),  # flashing
        ]
        self.timer = 0
        self.light_state = False
        self.tv_color = (40, 70, 140)
        self.smoke = ParticleList()
        self.ox, self.oy = 30, 80
        self.static = self._bake()

    def _bake(self):
        ox, oy = self.ox, self.oy
        s = pygame.Surface((self.rect.w + 60, self.rect.h + 110), pygame.SRCALPHA)
        r = pygame.Rect(ox, oy, self.rect.w, self.rect.h)
        rng = random.Random(3)
        pygame.draw.rect(s, (46, 40, 50), r)
        bh, bw = 10, 24
        for row in range(r.h // bh + 1):
            off = (row % 2) * (bw // 2)
            for bx in range(-bw, r.w, bw):
                brick = pygame.Rect(r.x + bx + off, r.y + row * bh, bw - 1, bh - 1).clip(r)
                if brick.w > 0 and brick.h > 0:
                    v = rng.randint(-8, 8)
                    pygame.draw.rect(s, (84 + v, 62 + v, 72 + v), brick)
        shade = pygame.Surface(r.size, pygame.SRCALPHA)
        for yy in range(r.h):
            pygame.draw.line(shade, (0, 0, 0, int(70 * yy / r.h)), (0, yy), (r.w, yy))
        s.blit(shade, r.topleft)
        pygame.draw.rect(s, (36, 30, 44), r, 3)

        # Roof trim with dentils
        pygame.draw.rect(s, (35, 30, 45), (r.x - 10, r.y - 12, r.w + 20, 15))
        pygame.draw.line(s, (78, 70, 96), (r.x - 10, r.y - 12), (r.right + 10, r.y - 12), 1)
        for xx in range(r.x - 8, r.right + 8, 14):
            pygame.draw.rect(s, (28, 24, 36), (xx, r.y + 3, 8, 4))
        # Chimney
        pygame.draw.rect(s, (84, 56, 62), (r.x + 215, r.y - 62, 32, 50))
        for cy in range(r.y - 60, r.y - 12, 8):
            pygame.draw.line(s, (46, 40, 50), (r.x + 215, cy), (r.x + 247, cy), 1)
        pygame.draw.rect(s, (50, 44, 58), (r.x + 211, r.y - 68, 40, 8))
        # Antenna
        pygame.draw.line(s, (150, 150, 160), (r.x + 50, r.y - 12), (r.x + 50, r.y - 62), 2)
        for ly, hw in ((r.y - 40, 10), (r.y - 50, 6), (r.y - 58, 4)):
            pygame.draw.line(s, (150, 150, 160), (r.x + 50 - hw, ly), (r.x + 50 + hw, ly), 1)

        # Door
        dr = pygame.Rect(ox + 115, oy + 140, 50, 80)
        pygame.draw.rect(s, (50, 36, 30), dr.inflate(8, 6).move(0, -3), border_top_left_radius=6, border_top_right_radius=6)
        pygame.draw.rect(s, (90, 45, 20), dr, border_top_left_radius=4, border_top_right_radius=4)
        pygame.draw.rect(s, (62, 30, 12), (dr.x + 6, dr.y + 8, 38, 22), 2)
        pygame.draw.rect(s, (62, 30, 12), (dr.x + 6, dr.y + 38, 38, 34), 2)
        pygame.draw.rect(s, (60, 80, 110), (dr.x + 9, dr.y + 11, 32, 16))
        pygame.draw.circle(s, (220, 180, 50), (dr.x + 40, dr.y + 42), 3)
        pygame.draw.rect(s, (90, 90, 96), (dr.x - 8, dr.bottom - 6, dr.w + 16, 6))
        pygame.draw.rect(s, (70, 70, 78), (dr.x - 14, dr.bottom, dr.w + 28, 5))
        pygame.draw.rect(s, (255, 214, 120), (dr.centerx - 5, dr.y - 22, 10, 12))
        pygame.draw.rect(s, (40, 36, 44), (dr.centerx - 7, dr.y - 24, 14, 4))
        plate = pygame.Rect(dr.x - 36, dr.y + 8, 26, 16)
        pygame.draw.rect(s, (30, 40, 60), plate, border_radius=3)
        txt = FONT_SM.render("128", True, (230, 220, 180))
        s.blit(txt, txt.get_rect(center=plate.center))

        # Window sills / lintels
        for w in self.windows:
            wl = w.move(ox - self.rect.x, oy - self.rect.y)
            pygame.draw.rect(s, (60, 56, 66), (wl.x - 5, wl.bottom, wl.w + 10, 6))
            pygame.draw.rect(s, (50, 46, 58), (wl.x - 4, wl.y - 6, wl.w + 8, 6))

        # Mailbox
        pygame.draw.rect(s, (60, 45, 30), (320, oy + 196, 3, 24))
        pygame.draw.rect(s, (40, 60, 110), (312, oy + 186, 20, 12), border_radius=4)
        pygame.draw.rect(s, (200, 40, 40), (330, oy + 178, 3, 10))
        return s

    def update(self):
        self.timer += 1
        if self.timer % 40 == 0:
            self.light_state = not self.light_state
        if self.timer % 7 == 0:
            self.tv_color = random.choice([(40, 70, 140), (60, 100, 190), (30, 50, 110), (90, 60, 150)])
        if self.timer % 10 == 0:
            self.smoke.append(Particle(
                self.rect.x + 231 + random.uniform(-5, 5), self.rect.y - 70,
                0.3 + ENV["wind"] * 0.6, -random.uniform(0.5, 0.9), 5, 150,
                (160, 160, 170), (60, 60, 75), shrink=1.012, alpha_max=80, max_size=22, drag=0.998))
        self.smoke.update()

    def draw(self, surface, t):
        surface.blit(self.static, (self.rect.x - self.ox, self.rect.y - self.oy))
        for i, w in enumerate(self.windows):
            if i == 0:
                color, lit = self.tv_color, True
            elif i == 1:
                color, lit = (255, 240, 130), True
            elif i == 2:
                color, lit = (35, 38, 50), False
            else:
                lit = self.light_state
                color = (255, 240, 130) if lit else (35, 38, 50)
            pygame.draw.rect(surface, color, w)
            if i == 1:  # silhouette watching the night
                pygame.draw.circle(surface, (70, 52, 30), (w.centerx + 8, w.centery + 12), 8)
                pygame.draw.ellipse(surface, (70, 52, 30), (w.centerx - 6, w.centery + 20, 28, 24))
            if i == 2:  # faint moon reflection
                pygame.draw.line(surface, (60, 66, 90), (w.x + 8, w.y + 10), (w.x + 26, w.y + 4), 2)
            pygame.draw.rect(surface, (20, 20, 25), w, 3)
            pygame.draw.line(surface, (20, 20, 25), (w.centerx, w.top), (w.centerx, w.bottom), 2)
            pygame.draw.line(surface, (20, 20, 25), (w.left, w.centery), (w.right, w.centery), 2)
            if lit:
                draw_glow(surface, w.center, 88, scale_color(color, 0.42))
        # Porch light + blinking antenna beacon
        draw_glow(surface, (self.door_rect.centerx, self.door_rect.y - 16), 76,
                  scale_color((255, 200, 110), 0.5 + 0.04 * math.sin(t * 0.3)))
        if (t // 45) % 2 == 0:
            draw_glow(surface, (self.rect.x + 50, self.rect.y - 64), 20, (255, 40, 30))
            pygame.draw.circle(surface, (255, 70, 60), (self.rect.x + 50, self.rect.y - 64), 2)
        self.smoke.draw(surface)


# ==========================================
# STICK FIGURE
# ==========================================
@lru_cache(maxsize=16)
def make_bubble(text):
    txt = FONT_MD.render(text, True, (20, 20, 30))
    w, h = txt.get_width() + 22, txt.get_height() + 14
    s = pygame.Surface((w, h + 12), pygame.SRCALPHA)
    pygame.draw.rect(s, (250, 250, 252), (0, 0, w, h), border_radius=10)
    pygame.draw.rect(s, (25, 25, 35), (0, 0, w, h), 2, border_radius=10)
    pygame.draw.polygon(s, (250, 250, 252), [(14, h - 1), (30, h - 1), (10, h + 11)])
    pygame.draw.lines(s, (25, 25, 35), False, [(14, h - 1), (10, h + 11), (30, h - 1)], 2)
    s.blit(txt, (11, 7))
    return s


class StickFigure:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.wave_timer = 0.0
        self.idle = 0
        self.text = ""
        self.say_timer = 0
        self.shadow = pygame.Surface((70, 14), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shadow, (0, 0, 0, 90), (0, 0, 70, 14))

    def say(self, text, frames=150):
        self.text = text
        self.say_timer = frames

    def update(self):
        self.wave_timer += 0.09
        self.idle += 1
        if self.say_timer > 0:
            self.say_timer -= 1
        elif self.idle % 600 == 120:
            self.say(random.choice(["Hi!", "Nice night!", "Wow!", "Hello!"]), 130)

    def draw(self, surface, t):
        x, y = self.x, self.y
        b = math.sin(t * 0.05) * 1.2
        white, ink, glove = (245, 245, 245), (20, 20, 20), (255, 210, 60)
        head = (x, int(y - 70 + b))
        neck = (x, int(y - 50 + b))
        hip = (x, y - 10)
        surface.blit(self.shadow, (x - 35, y + 34))

        # Legs with knees + shoes
        for sgn in (-1, 1):
            knee = (x + sgn * 8, y + 16)
            foot = (x + sgn * 20, y + 40)
            pygame.draw.line(surface, white, hip, knee, 4)
            pygame.draw.line(surface, white, knee, foot, 4)
            pygame.draw.ellipse(surface, (120, 30, 40), (foot[0] - 7 + sgn * 3, foot[1] - 3, 15, 8))
        # Spine
        pygame.draw.line(surface, white, neck, hip, 4)
        shoulder = (x, neck[1] + 4)
        # Static left arm
        sw = math.sin(t * 0.05) * 2
        elbow_l = (x - 20, y - 30)
        hand_l = (x - 28 + sw, y - 12)
        pygame.draw.line(surface, white, shoulder, elbow_l, 4)
        pygame.draw.line(surface, glove, elbow_l, hand_l, 4)
        pygame.draw.circle(surface, glove, (int(hand_l[0]), int(hand_l[1])), 4)
        # Waving right arm: upper arm fixed, forearm swings
        a1 = math.radians(-35)
        elbow = (shoulder[0] + 24 * math.cos(a1), shoulder[1] + 24 * math.sin(a1))
        a2 = math.radians(-95 + math.sin(self.wave_timer) * 40)
        hand = (elbow[0] + 24 * math.cos(a2), elbow[1] + 24 * math.sin(a2))
        pygame.draw.line(surface, white, shoulder, elbow, 4)
        pygame.draw.line(surface, glove, elbow, hand, 4)
        pygame.draw.circle(surface, glove, (int(hand[0]), int(hand[1])), 5)

        # Head
        pygame.draw.circle(surface, white, head, 16)
        pygame.draw.circle(surface, ink, head, 16, 2)
        # Cap
        cap = []
        for k in range(13):
            th = 0.35 + k * (math.pi - 0.7) / 12
            cap.append((head[0] + 17 * math.cos(th), head[1] - 17 * math.sin(th)))
        pygame.draw.polygon(surface, (200, 40, 50), cap)
        pygame.draw.polygon(surface, (120, 20, 30), cap, 2)
        pygame.draw.line(surface, (120, 20, 30), (head[0], head[1] - 6), (head[0] + 22, head[1] - 4), 3)
        # Face
        blink = (self.idle % 190) < 6
        for ex in (head[0] - 5, head[0] + 5):
            if blink:
                pygame.draw.line(surface, ink, (ex - 2, head[1] - 1), (ex + 2, head[1] - 1), 2)
            else:
                pygame.draw.circle(surface, ink, (ex, head[1] - 2), 2)
        if self.say_timer > 0:
            pygame.draw.ellipse(surface, ink, (head[0] - 4, head[1] + 3, 8, 7 + int(2 * math.sin(t * 0.6))))
        else:
            pygame.draw.arc(surface, ink, (head[0] - 7, head[1] - 4, 14, 12), math.pi + 0.4, 2 * math.pi - 0.4, 2)

        if self.say_timer > 0:
            bub = make_bubble(self.text)
            bob = math.sin(t * 0.1) * 2
            h = bub.get_height()
            surface.blit(bub, (head[0] - 14, int(head[1] - 20 - h + 1 + bob)))


# ==========================================
# VEHICLES
# ==========================================
@lru_cache(maxsize=2)
def make_beam(direction):
    w, h = 240, 80
    s = pygame.Surface((w, h))
    for i in range(w):
        k = (1 - i / w) ** 1.6
        half = 4 + i * 0.16
        for j in range(4):
            hh = half * (1 - j * 0.22)
            c = scale_color((255, 240, 170), 0.34 * k * (0.45 + j * 0.2))
            pygame.draw.line(s, c, (i, int(h / 2 - hh)), (i, int(h / 2 + hh)))
    if direction < 0:
        s = pygame.transform.flip(s, True, False)
    return s


class Car:
    PALETTES = [((0, 110, 210), (0, 80, 160)), ((200, 40, 50), (150, 25, 35)),
                ((235, 150, 20), (180, 105, 10)), ((40, 160, 90), (25, 115, 60)),
                ((140, 70, 200), (100, 45, 150))]

    def __init__(self, y, direction=1, speed=4.5, palette_idx=0):
        self.y = y
        self.dir = direction
        self.speed = speed
        self.w = 160
        self.x = -220 if direction > 0 else WIDTH + 100
        self.pal = self.PALETTES[palette_idx]
        self.wheel_angle = 0.0
        self.smoke = ParticleList()
        self.shadow = pygame.Surface((190, 24), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shadow, (0, 0, 0, 100), (0, 0, 190, 24))

    def update(self):
        self.x += self.speed * self.dir
        self.wheel_angle += self.speed * self.dir / 16
        if self.dir > 0 and self.x > WIDTH + 100:
            self.x = -220
            self._respawn()
        elif self.dir < 0 and self.x < -260:
            self.x = WIDTH + 100
            self._respawn()
        if random.random() < 0.6:
            rear = self.x - 5 if self.dir > 0 else self.x + self.w + 5
            self.smoke.append(Particle(
                rear, self.y + 25, -self.dir * random.uniform(0.5, 1.5), random.uniform(-0.5, 0.2),
                random.uniform(3, 6), random.randint(25, 35), (120, 120, 120), (40, 40, 40),
                shrink=1.03, alpha_max=140, max_size=14))
        self.smoke.update()

    def _respawn(self):
        self.pal = random.choice(self.PALETTES)
        self.speed = max(2.5, self.speed + random.uniform(-0.6, 0.6))
        self.speed = min(self.speed, 5.5)

    def draw(self, surface):
        self.smoke.draw(surface)
        cx = int(self.x)
        base_y = int(self.y)
        cy = int(self.y + math.sin(self.x * 0.07) * 1.0)
        body, roof = self.pal
        d = self.dir

        def P(dx, dy):
            return (cx + dx if d > 0 else cx + self.w - dx, cy + dy)

        surface.blit(self.shadow, (cx - 15, base_y + 44))
        # Wheel arches
        for wx in (35, 125):
            pygame.draw.circle(surface, (12, 12, 15), (P(wx, 0)[0], base_y + 35), 19)
        pygame.draw.rect(surface, body, (cx, cy, 160, 35), border_radius=6)
        pygame.draw.rect(surface, scale_color(body, 0.65), (cx + 4, cy + 27, 152, 8), border_radius=3)
        pygame.draw.line(surface, scale_color(body, 1.35), P(6, 15), P(154, 15), 2)
        # Cabin / roof
        pygame.draw.polygon(surface, roof, [P(30, 0), P(50, -25), P(110, -25), P(135, 0)])
        pygame.draw.line(surface, scale_color(roof, 1.6), P(52, -25), P(108, -25), 2)
        # Windows + driver silhouette
        pygame.draw.polygon(surface, (170, 220, 245), [P(55, -21), P(78, -21), P(78, -3), P(38, -3)])
        pygame.draw.polygon(surface, (170, 220, 245), [P(84, -21), P(107, -21), P(128, -3), P(84, -3)])
        pygame.draw.circle(surface, (30, 40, 55), P(96, -13), 5)
        pygame.draw.rect(surface, (30, 40, 55), (P(92, -8)[0] - (0 if d > 0 else 8), cy - 8, 8, 6))
        pygame.draw.line(surface, (220, 220, 226), P(60, 9), P(72, 9), 2)  # door handle
        # Lights, bumper, plate
        pygame.draw.circle(surface, (255, 255, 205), P(156, 10), 4)
        pygame.draw.circle(surface, (235, 30, 30), P(3, 10), 4)
        pygame.draw.line(surface, (150, 150, 160), P(0, 27), P(160, 27), 2)
        pygame.draw.rect(surface, (235, 235, 240), (P(8, 19)[0] - (0 if d > 0 else 14), cy + 19, 14, 6))
        # Wheels with spokes
        for wx in (35, 125):
            wxp, wy = P(wx, 0)[0], base_y + 35
            pygame.draw.circle(surface, (20, 20, 20), (wxp, wy), 16)
            pygame.draw.circle(surface, (180, 180, 190), (wxp, wy), 9)
            for k in range(5):
                a = self.wheel_angle + k * math.tau / 5
                pygame.draw.line(surface, (90, 90, 100), (wxp, wy), (wxp + 8 * math.cos(a), wy + 8 * math.sin(a)), 2)
            pygame.draw.circle(surface, (60, 60, 70), (wxp, wy), 2)
        # Light beam + glows
        beam = make_beam(d)
        bx = cx + 158 if d > 0 else cx + 2 - 240
        surface.blit(beam, (bx, cy + 10 - 40), special_flags=pygame.BLEND_RGB_ADD)
        hx, hy = P(157, 10)
        draw_glow(surface, (hx, hy), 32, (255, 250, 190))
        tx, ty = P(2, 10)
        draw_glow(surface, (tx, ty), 24, (255, 25, 25))


# ==========================================
# LAMPS, TREES & FOLIAGE
# ==========================================
class StreetLamp:
    def __init__(self, x, facing=1, base_y=556, height=100, flickers=False):
        self.x, self.facing, self.base_y, self.height = x, facing, base_y, height
        self.flickers = flickers
        self.flicker = 0
        self.moths = [(random.uniform(0, 6.28), random.uniform(10, 22), random.uniform(0.05, 0.12)) for _ in range(4)]

    def draw(self, surface, t):
        x, by = self.x, self.base_y
        top = by - self.height
        pygame.draw.rect(surface, (26, 28, 36), (x - 6, by - 8, 12, 10))
        pygame.draw.line(surface, (36, 38, 48), (x, by), (x, top), 4)
        hx, hy = x + self.facing * 20, top + 6
        pygame.draw.line(surface, (36, 38, 48), (x, top), (hx, hy - 2), 3)
        pygame.draw.rect(surface, (30, 32, 40), (hx - 9, hy - 3, 18, 6), border_radius=2)
        pygame.draw.ellipse(surface, (255, 235, 170), (hx - 6, hy + 2, 12, 4))
        inten = 1.0
        if self.flickers:
            if self.flicker > 0:
                self.flicker -= 1
                inten = random.uniform(0.25, 1.0)
            elif random.random() < 0.004:
                self.flicker = 10
        draw_glow(surface, (hx, hy + 6), 76, scale_color((255, 215, 130), 0.42 * inten))
        draw_glow(surface, (hx, hy + 4), 24, scale_color((255, 240, 190), 0.9 * inten))
        draw_glow_ellipse(surface, (hx, 594), 64, 22, scale_color((255, 215, 130), 0.3 * inten))
        for ang, rad, sp in self.moths:
            a = ang + t * sp
            mx = hx + math.cos(a) * rad
            my = hy + 4 + math.sin(a * 1.7) * rad * 0.6
            pygame.draw.circle(surface, (235, 235, 215), (int(mx), int(my)), 1)


def draw_pine(surface, x, base_y, h, t, phase):
    sway = math.sin(t * 0.02 + phase) * 2.0 + ENV["wind"] * 3
    layers = 5
    pygame.draw.rect(surface, (40, 26, 14), (x - 4, base_y - 14, 8, 16))
    for i in range(layers - 1, -1, -1):
        apex_y = base_y - h + i * h * 0.17
        bot_y = apex_y + h * 0.36
        w = h * 0.14 + i * h * 0.075
        sw = sway * (layers - i) / layers
        apex = (x + sw, apex_y)
        pygame.draw.polygon(surface, (10, 44, 26), [apex, (x - w, bot_y), (x + w, bot_y)])
        pygame.draw.line(surface, (30, 95, 60), apex, (x + w, bot_y), 2)
        pygame.draw.line(surface, (6, 28, 16), (x - w, bot_y), (x + w, bot_y), 2)


class Tree:
    def __init__(self, x, y):
        self.x, self.y = x, y
        rng = random.Random(5)
        cx, cy = x + 50, y + 62
        self.blobs = []
        for layer, (col, n, spread, rmin, rmax, dx, dy) in enumerate((
            ((12, 58, 22), 10, 62, 34, 58, 0, 0),
            ((20, 92, 34), 8, 52, 28, 46, 6, -6),
            ((30, 125, 46), 7, 44, 20, 36, 14, -14),
            ((52, 150, 64), 6, 36, 10, 20, 20, -20),
        )):
            for _ in range(n):
                a = rng.uniform(0, math.tau)
                d = rng.uniform(0, spread)
                self.blobs.append((col, cx + math.cos(a) * d + dx, cy + math.sin(a) * d * 0.8 + dy,
                                   rng.randint(rmin, rmax), rng.uniform(0, 6.28), 1 + layer * 0.5))
        self.leaves = ParticleList()

    def update(self):
        if random.random() < 0.03:
            self.leaves.append(Particle(
                self.x + random.uniform(10, 100), self.y + random.uniform(50, 110),
                random.uniform(0.2, 0.9) + ENV["wind"], random.uniform(0.3, 0.7), 3, 220,
                (60, 130, 40), (130, 90, 30), gravity=0.008, drag=0.995, shrink=1.0))
        self.leaves.update()

    def draw(self, surface, t):
        tx, ty = self.x, self.y
        trunk = [(tx + 20, ty + 252), (tx + 34, ty + 115), (tx + 71, ty + 115), (tx + 86, ty + 252)]
        pygame.draw.polygon(surface, (75, 45, 20), trunk)
        pygame.draw.polygon(surface, (50, 30, 14), [trunk[0], trunk[1], (tx + 46, ty + 115), (tx + 36, ty + 252)])
        for i in range(5):
            bx = tx + 40 + i * 9
            pygame.draw.line(surface, (52, 32, 14), (bx - 2, ty + 245), (bx, ty + 125), 1)
        for ex in (tx - 2, tx + 98):  # branches into canopy
            pygame.draw.line(surface, (75, 45, 20), (tx + 52, ty + 150), (ex, ty + 95), 6)
        for col, bx, by, r, ph, depth in self.blobs:
            sx = math.sin(t * 0.02 + ph) * 2.5 * depth + ENV["wind"] * 4 * depth
            sy = math.cos(t * 0.017 + ph) * 1.2
            pygame.draw.circle(surface, col, (int(bx + sx), int(by + sy)), r)
        self.leaves.draw(surface)


class Firefly:
    def __init__(self):
        self.bx = random.uniform(0, WIDTH)
        self.by = random.uniform(496, 740)
        self.ph = random.uniform(0, 6.28)
        self.a, self.b = random.uniform(0.01, 0.03), random.uniform(0.01, 0.03)

    def draw(self, surface, t):
        x = self.bx + math.sin(t * self.a + self.ph) * 36
        y = self.by + math.cos(t * self.b + self.ph) * 16
        k = max(0.0, math.sin(t * 0.05 + self.ph)) ** 2
        if k > 0.05:
            draw_glow(surface, (x, y), 20, scale_color((200, 255, 120), k * 0.8))
            pygame.draw.circle(surface, scale_color((235, 255, 170), 0.4 + 0.6 * k), (int(x), int(y)), 1)


def make_blades(n=150):
    out = []
    for _ in range(n):
        h = random.randint(10, 24)
        col = random.choice([(14, 62, 26), (22, 86, 36), (30, 104, 44)])
        out.append((random.randint(0, WIDTH), random.randint(650, 748), h, random.uniform(0, 6.28), col))
    return out


def draw_blades(surface, blades, t):
    for bx, by, bh, ph, col in blades:
        sw = math.sin(t * 0.04 + ph) * bh * 0.25 + ENV["wind"] * bh * 0.2
        pygame.draw.line(surface, col, (bx, by), (bx + sw, by - bh), 2)


# ==========================================
# SMILEY
# ==========================================
def make_face(blink):
    S, c, R = 76, 38, 30
    s = pygame.Surface((S, S), pygame.SRCALPHA)
    for r in range(R, 0, -1):
        k = 1 - r / R
        col = lerp_color((225, 160, 0), (255, 232, 70), k ** 0.8)
        off = (R - r)
        pygame.draw.circle(s, col, (c - int(off * 0.18), c - int(off * 0.2)), r)
    pygame.draw.circle(s, (0, 0, 0), (c, c), R, 3)
    for ex in (c - 10, c + 10):
        if blink:
            pygame.draw.line(s, (0, 0, 0), (ex - 5, c - 8), (ex + 5, c - 8), 3)
        else:
            pygame.draw.ellipse(s, (0, 0, 0), (ex - 4, c - 15, 8, 14))
            pygame.draw.circle(s, (255, 255, 255), (ex - 1, c - 12), 2)
    pygame.draw.circle(s, (255, 150, 60), (c - 19, c + 4), 4)
    pygame.draw.circle(s, (255, 150, 60), (c + 19, c + 4), 4)
    pygame.draw.arc(s, (0, 0, 0), (c - 16, c - 14, 32, 32), math.pi + 0.2, 2 * math.pi - 0.2, 3)
    return s


class BouncingSmiley:
    def __init__(self, x, y):
        self.pos = pygame.math.Vector2(x, y)
        self.vel = pygame.math.Vector2(5.5, 3.8)
        self.radius = 30
        self.faces = {False: make_face(False), True: make_face(True)}
        self.sx = self.sy = 1.0
        self.angle = 0.0
        self.trail = []
        self.sparks = ParticleList()
        self.t = 0

    def _burst(self, x, y):
        for _ in range(12):
            a = random.uniform(0, math.tau)
            sp = random.uniform(1, 4)
            self.sparks.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp, random.uniform(3, 5),
                                        random.randint(20, 35), (255, 240, 140), (255, 120, 20),
                                        additive=True, shrink=0.94))

    def update(self):
        self.t += 1
        self.pos += self.vel
        r = self.radius
        if self.pos.x - r <= 0:
            self.pos.x = r
            self.vel.x *= -1
            self.sx, self.sy = 0.7, 1.3
            self._burst(0, self.pos.y)
        elif self.pos.x + r >= WIDTH:
            self.pos.x = WIDTH - r
            self.vel.x *= -1
            self.sx, self.sy = 0.7, 1.3
            self._burst(WIDTH, self.pos.y)
        if self.pos.y - r <= 0:
            self.pos.y = r
            self.vel.y *= -1
            self.sx, self.sy = 1.3, 0.7
            self._burst(self.pos.x, 0)
        elif self.pos.y + r >= HEIGHT:
            self.pos.y = HEIGHT - r
            self.vel.y *= -1
            self.sx, self.sy = 1.3, 0.7
            self._burst(self.pos.x, HEIGHT)
        self.sx += (1 - self.sx) * 0.15
        self.sy += (1 - self.sy) * 0.15
        self.angle = (self.angle + self.vel.x * 0.9) % 360
        self.trail.append((self.pos.x, self.pos.y))
        self.trail = self.trail[-16:]
        self.sparks.update()

    def draw(self, surface):
        n = len(self.trail)
        for i, (tx, ty) in enumerate(self.trail):
            k = i / max(1, n)
            draw_glow(surface, (tx, ty), int(self.radius * (0.5 + 1.2 * k)), (int(70 * k), int(55 * k), 0))
        draw_glow(surface, (self.pos.x, self.pos.y), 72, (50, 40, 0))
        face = self.faces[(self.t % 180) < 7]
        w = max(2, int(face.get_width() * self.sx))
        h = max(2, int(face.get_height() * self.sy))
        rot = pygame.transform.rotate(pygame.transform.smoothscale(face, (w, h)), self.angle)
        surface.blit(rot, rot.get_rect(center=(int(self.pos.x), int(self.pos.y))))
        self.sparks.draw(surface)


# ==========================================
# HUD
# ==========================================
def draw_hud(surface, rocket, fps):
    panel = pygame.Surface((220, 96), pygame.SRCALPHA)
    pygame.draw.rect(panel, (8, 12, 28, 150), panel.get_rect(), border_radius=8)
    pygame.draw.rect(panel, (90, 110, 170, 180), panel.get_rect(), 1, border_radius=8)
    status = rocket.status()
    rows = [("MISSION CONTROL", (150, 190, 255)), ("Launches: %d" % rocket.launches, (220, 225, 240)),
            ("Status: %s" % status, (255, 210, 110)), ("FPS: %d" % fps, (150, 160, 190))]
    for i, (txt, col) in enumerate(rows):
        panel.blit(FONT_SM.render(txt, True, col), (12, 8 + i * 21))
    surface.blit(panel, (12, 12))
    if status not in ("STANDBY", "TRACKING"):
        label = FONT_LG.render(status if rocket.state != Rocket.ASCENT else "LIFTOFF!", True, (255, 245, 210))
        shadow = FONT_LG.render(status if rocket.state != Rocket.ASCENT else "LIFTOFF!", True, (0, 0, 0))
        pos = label.get_rect(center=(WIDTH // 2, 70))
        surface.blit(shadow, pos.move(3, 3))
        surface.blit(label, pos)
    surface.blit(FONT_SM.render("SPACE: launch   H: HUD   ESC: quit", True, (120, 130, 160)), (12, HEIGHT - 24))


# ==========================================
# MAIN EXECUTION LOOP
# ==========================================
def main(max_frames=None, shot_frames=(), prefix="scene"):
    sky = build_sky()
    far, beacons = build_far_layer()
    ground = build_ground()
    vignette = build_vignette()
    aurora_buf = pygame.Surface((WIDTH, 330), pygame.SRCALPHA)

    stars = make_stars()
    shooting = []
    clouds = [
        Cloud(random.randint(-200, WIDTH), random.randint(40, 250), random.uniform(0.08, 0.35), s,
              random.randint(200, 320), random.randint(70, 110), random.randint(140, 230))
        for s in range(7)
    ]
    moon = Moon(start_pos=(80, 600), target_pos=(850, 120))
    rocket = Rocket(x=900, pad_y=505)
    building = Building(x=100, y=300)
    figure = StickFigure(x=450, y=490)
    cars = [Car(y=535, direction=1, speed=4.5, palette_idx=0),
            Car(y=574, direction=-1, speed=3.2, palette_idx=2)]
    cars[1].x = 600
    lamps = [StreetLamp(60), StreetLamp(385, flickers=True), StreetLamp(600), StreetLamp(960, facing=-1)]
    pines = [(30, 516, 150, 0.0), (535, 508, 115, 1.7)]
    tree = Tree(700, 340)
    fireflies = [Firefly() for _ in range(24)]
    blades = make_blades()
    smiley = BouncingSmiley(x=WIDTH // 2, y=HEIGHT // 3)

    show_hud = True
    t = 0
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    rocket.trigger()
                elif event.key == pygame.K_h:
                    show_hud = not show_hud

        t += 1
        ENV["t"] = t
        ENV["wind"] = 0.3 + 0.25 * math.sin(t * 0.004) + 0.1 * math.sin(t * 0.013)

        # ---------------- updates
        moon.update()
        for c in clouds:
            c.update()
        rocket.update()
        building.update()
        figure.update()
        if rocket.ignited:
            figure.say("Liftoff!", 150)
        for car in cars:
            car.update()
        tree.update()
        smiley.update()
        if random.random() < 0.004 and len(shooting) < 2:
            shooting.append(ShootingStar())
        for s in shooting:
            s.update()
        shooting = [s for s in shooting if s.life > 0]

        # ---------------- render layers (painter's algorithm)
        world.blit(sky, (0, 0))
        draw_stars(world, stars, t)
        for s in shooting:
            s.draw(world)
        draw_aurora(world, aurora_buf, t)
        moon.draw(world, t)
        for c in clouds:
            c.draw(world)
        world.blit(far, (0, 0))
        for bx, by in beacons:
            if (t // 45 + bx) % 2 == 0:
                draw_glow(world, (bx, by), 16, (255, 40, 30))
        world.blit(ground, (0, HORIZON))

        for px, py, ph, phs in pines:
            draw_pine(world, px, py, ph, t, phs)
        rocket.draw_pad(world, t)
        rocket.draw(world, t)
        building.draw(world, t)
        figure.draw(world, t)
        for lamp in lamps:
            lamp.draw(world, t)
        for car in cars:
            car.draw(world)
        tree.draw(world, t)
        for f in fireflies:
            f.draw(world, t)
        draw_blades(world, blades, t)
        smiley.draw(world)

        if rocket.flash > 0.02:
            f = rocket.flash
            world.fill((int(60 * f), int(45 * f), int(25 * f)), special_flags=pygame.BLEND_RGB_ADD)

        # ---------------- present (screen shake, vignette, HUD)
        s = int(rocket.shake)
        off = (random.randint(-s, s), random.randint(-s, s)) if s > 0 else (0, 0)
        screen.fill((0, 0, 0))
        screen.blit(world, off)
        screen.blit(vignette, (0, 0))
        if show_hud:
            draw_hud(screen, rocket, clock.get_fps())

        pygame.display.flip()
        if t in shot_frames:
            pygame.image.save(screen, "%s_%d.png" % (prefix, t))
        if max_frames and t >= max_frames:
            break
        clock.tick(0 if max_frames else 60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--shots", type=str, default="")
    ap.add_argument("--prefix", type=str, default="scene")
    args = ap.parse_args()
    shots = tuple(int(v) for v in args.shots.split(",") if v)
    main(args.frames, shots, args.prefix)

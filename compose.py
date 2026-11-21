"""Draw a deterministic, illustrated newspaper from the supplied news brief.

All marks, including the illustrations and locator map, are drawn with Pillow.
Story regions are editorial groupings; the ICJ and markets leads are global.
No external assets, network calls, runtime dates, or unseeded randomness.
"""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import hashlib
import math
import random

from PIL import Image, ImageDraw, ImageFont, ImageStat


ROOT = Path(__file__).resolve().parent
FONT_DIR = Path('/usr/share/fonts/truetype/dejavu')
SIZE = 1024
SCALE = 3
PAPER = '#f4eddb'
INK = '#242722'
RED = '#ae302b'
RULE = '#b7af9a'
FAINT = '#e5dcc5'
REGIONS = {
    'Europe': '#4d685a',
    'Americas': '#9a4e37',
    'Asia-Pacific': '#396980',
    'Middle East': '#947022',
    'Africa': '#796080',
    'Oceania': '#478481',
    'World': '#444b52',
}


@dataclass(frozen=True)
class Story:
    city: str
    region: str
    headline: str
    deck: str
    scene: str
    lon: float
    lat: float


# Only facts in ../news-brief.md. The row order also supplies the map pin IDs.
LEADS = [
    Story('THE HAGUE', 'World',
          'World court rules Myanmar committed genocide',
          'The ICJ finds genocide against the Rohingya — its first such finding '
          'against a state. The decision was 9–6.',
          'court', 4.3, 52.1),
    Story('SHENZHEN AFTERMATH', 'Asia-Pacific',
          'Three leaders, no breakthrough',
          'Merz rejects a “new Yalta” without Europeans at the table. '
          'Thursday’s declaration omitted Ukraine and Iran.',
          'summit', 114.1, 22.5),
    Story('KYIV', 'Europe', 'Russia’s overnight barrage',
          'Missiles hit infrastructure; two embassies damaged, staff unharmed. '
          'Ukraine strikes back.', 'kyiv', 30.5, 50.5),
    Story('BERLIN', 'Europe', 'Europe ready to talk',
          'Ukraine’s allies meet Zelenskyy and say Europe has a united position '
          'for talks with Russia.', 'berlin', 13.4, 52.5),
    Story('RIYADH', 'Middle East', 'Houthi missile hits Saudi finance tower',
          'PIF tower and other buildings damaged. Saudi defences intercept '
          'more missiles and five drones.', 'riyadh', 46.7, 24.7),
    Story('STRAIT OF HORMUZ', 'Middle East', 'Tanker war intensifies',
          'A mine sets a tanker ablaze. Iran readies a Kharg Island convoy '
          'to test the US oil blockade.', 'tanker', 56.5, 26.6),
    Story('ANTALYA', 'Europe', 'COP31 draft drops fossil-fuel phase-out',
          'Final scheduled day: the slimmed-down draft removes reference '
          'to ending fossil fuel use.', 'climate', 30.7, 36.9),
    Story('GAZA', 'Middle East', 'Israeli troops cross the yellow line',
          'First such incursion since the truce. Flooding, damaged shelters '
          'and food shortages deepen the emergency.', 'gaza', 34.5, 31.5),
    Story('MARKETS', 'World', 'AI doubts drag stocks down',
          'US stocks fall a fifth day; Asia tumbles. Anthropic closes 17% '
          'above its IPO price in its debut.', 'markets', -74.0, 40.7),
    Story('WASHINGTON', 'Americas', 'White House fires cyber director',
          'Sean Cairncross is out after a week of outages. Senate passes '
          'an energy-permitting bill, 62–33.', 'cyber', -77.0, 38.9),
    Story('NAIROBI', 'Africa', 'Kenya’s last Ebola patient goes home',
          'The last patient is discharged, 37 days after Kenya’s first '
          'Ebola case.', 'health', 36.8, -1.3),
    Story('BRUSSELS', 'Europe', 'EU and UK, second summit',
          'Costa and von der Leyen meet Burnham on trade, energy, fisheries, '
          'security and Erasmus+.', 'brussels', 4.4, 50.8),
]

# Compact summaries retain the supplied facts and attribution where needed.
BRIEFS = [
    ('SAN SALVADOR', 'Americas', 'Bukele registers for a third term.'),
    ('YENNE, SENEGAL', 'Africa', 'Dozens missing after migrant boat capsizes.'),
    ('SOUTH KORDOFAN', 'Africa', 'Sudan: drone strike kills 10 at gold mine.'),
    ('CARACAS', 'Americas', 'US–Venezuela military cooperation deal.'),
    ('PYONGYANG', 'Asia-Pacific', 'IAEA: uranium enrichment expanding.'),
    ('TALLINN', 'Europe', 'Estonia to shut Russia border after sabotage.'),
    ('ROME', 'Europe', 'Nationwide strike over living costs.'),
    ('NEW YORK', 'Americas', 'Mayor’s plan: close Rikers Island by 2032.'),
    ('WASHINGTON', 'Americas', 'Deep-sea mining leases defy court ruling.'),
    ('RABAT', 'Africa', '€366m for defence industry by 2035.'),
    ('PORT-AU-PRINCE', 'Americas', '34 suspected gang members killed, police say.'),
    ('ISLAMABAD', 'Asia-Pacific', 'Pakistan says forces killed 22 militants.'),
    ('DHAKA', 'Asia-Pacific', 'Shutdown and political violence raise tensions.'),
    ('NEW DELHI', 'Asia-Pacific', 'India relaxes vessel-age rules for fleet.'),
    ('LONDON', 'Europe', 'HMS Vengeance: 217-day underwater patrol.'),
    ('VATICAN', 'Europe', 'Giant Christmas tree raised at St Peter’s.'),
    ('LOS ANGELES', 'Americas', 'GTA 6 launch sales top $2.3bn.'),
    ('QUITO', 'Americas', 'Hegseth arrives on anti-narcotics tour.'),
]

NUMBERS = [
    ('9–6', 'ICJ genocide ruling', 'the court’s vote'),
    ('70', 'minutes in Shenzhen', 'Thursday’s talks'),
    ('4.8%', 'Nikkei fall', 'Friday’s sell-off'),
    ('2.02%', 'S&P 500 fall', 'fifth down day'),
    ('16%', 'SoftBank fall', 'more than 16%'),
    ('37', 'days in Kenya', 'first case to last discharge'),
]
REGION_COUNTS = Counter(s.region for s in LEADS)
REGION_COUNTS.update(region for _, region, _ in BRIEFS)
TOTAL = len(LEADS) + len(BRIEFS)
METRICS = {'text_lines': 0, 'illustrations': 0}


@lru_cache(maxsize=128)
def font(size, face='sans'):
    filename = {
        'sans': 'DejaVuSans.ttf',
        'bold': 'DejaVuSans-Bold.ttf',
        'serif': 'DejaVuSerif.ttf',
        'headline': 'DejaVuSerif-Bold.ttf',
    }[face]
    return ImageFont.truetype(str(FONT_DIR / filename), round(size * SCALE))


page = Image.new('RGB', (SIZE * SCALE, SIZE * SCALE), PAPER)
draw = ImageDraw.Draw(page)


def line(points, fill=RULE, width=0.6):
    draw.line([(round(x * SCALE), round(y * SCALE)) for x, y in points],
              fill=fill, width=max(1, round(width * SCALE)))


def rect(box, fill=None, outline=None, width=1):
    draw.rectangle(tuple(round(v * SCALE) for v in box), fill=fill,
                   outline=outline, width=max(1, round(width * SCALE)))


def measure(text, size, face='sans'):
    return draw.textlength(text, font=font(size, face)) / SCALE


def put(text, x, y, size, face='sans', color=INK, width=None, align='left'):
    """All printed lines, including labels, pass through a measured bound."""
    length = measure(text, size, face)
    if width is not None and length > width + 0.1:
        raise ValueError(f'Text exceeds {width:.1f}px: {text!r} ({length:.1f})')
    if align == 'center':
        x -= length / 2
    elif align == 'right':
        x -= length
    bbox = draw.textbbox((x * SCALE, y * SCALE), text,
                         font=font(size, face), anchor='lt')
    if bbox[0] < 0 or bbox[1] < 0 or bbox[2] > SIZE * SCALE or bbox[3] > SIZE * SCALE:
        raise ValueError(f'Text falls outside image: {text!r}')
    draw.text((round(x * SCALE), round(y * SCALE)), text,
              font=font(size, face), fill=color, anchor='lt')
    METRICS['text_lines'] += 1
    return length


def wrap(text, width, size, face='sans'):
    lines = []
    current = ''
    for word in text.split():
        if measure(word, size, face) > width:
            raise ValueError(f'Unbreakable word: {word}')
        candidate = f'{current} {word}' if current else word
        if measure(candidate, size, face) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def paragraph(text, x, y, width, size, leading, face='sans', color=INK):
    lines = wrap(text, width, size, face)
    for n, text_line in enumerate(lines):
        put(text_line, x, y + n * leading, size, face, color, width)
    return len(lines) * leading


class Art:
    """Small local-coordinate drawing surface for original editorial scenes."""

    def __init__(self, width, height, background):
        self.w = width
        self.h = height
        self.image = Image.new('RGB', (round(width * SCALE), round(height * SCALE)), background)
        self.d = ImageDraw.Draw(self.image)

    def box(self, xy, color, edge=None, stroke=0.7):
        self.d.rectangle(tuple(round(v * SCALE) for v in xy), fill=color,
                         outline=edge, width=max(1, round(stroke * SCALE)))

    def poly(self, pts, color, edge=None):
        p = [(round(x * SCALE), round(y * SCALE)) for x, y in pts]
        self.d.polygon(p, fill=color)
        if edge:
            self.d.line(p + p[:1], fill=edge, width=round(0.8 * SCALE), joint='curve')

    def ellipse(self, xy, color, edge=None, stroke=0.7):
        self.d.ellipse(tuple(round(v * SCALE) for v in xy), fill=color,
                       outline=edge, width=max(1, round(stroke * SCALE)))

    def stroke(self, pts, color=INK, width=0.8):
        self.d.line([(round(x * SCALE), round(y * SCALE)) for x, y in pts],
                    fill=color, width=max(1, round(width * SCALE)), joint='curve')

    def label(self, text, x, y, size, color=INK, face='bold'):
        # Map pins and illustration lettering are measured just like body type.
        f = font(size, face)
        width = self.d.textlength(text, font=f) / SCALE
        bbox = self.d.textbbox((round((x - width / 2) * SCALE), round(y * SCALE)),
                               text, font=f, anchor='lt')
        if (bbox[0] < 0 or bbox[1] < 0 or bbox[2] > self.w * SCALE
                or bbox[3] > self.h * SCALE):
            raise ValueError('Illustration label outside banner')
        self.d.text((round((x - width / 2) * SCALE), round(y * SCALE)), text,
                    fill=color, font=f, anchor='lt')
        METRICS['text_lines'] += 1

    def window(self, x, y, w, h, color='#d8c9a7'):
        self.box((x, y, x + w, y + h), color)
        self.stroke([(x + w / 2, y), (x + w / 2, y + h)], INK, .4)

    def building(self, x, y, w, h, color='#827b68', rows=3):
        self.box((x, y, x + w, y + h), color, INK, .5)
        for row in range(rows):
            for col in range(3):
                self.window(x + w * (.13 + .28 * col), y + h * (.13 + row * .24),
                            w * .13, h * .13)

    def person(self, x, y, r, coat='#354c59', skin='#d2a27d', hair='#322c28', kind=''):
        """Head, facial features, collar and shoulders; y is head center."""
        self.poly([(x - r * 2.1, y + r * 3.2), (x - r * 1.7, y + r * 1.65),
                   (x - r * .6, y + r), (x + r * .6, y + r),
                   (x + r * 1.7, y + r * 1.65), (x + r * 2.1, y + r * 3.2)], coat, INK)
        self.box((x - r * .35, y + r * .6, x + r * .35, y + r * 1.55), skin)
        self.ellipse((x - r, y - r * 1.15, x + r, y + r * 1.25), skin, INK)
        if kind == 'bald':
            self.poly([(x - r, y), (x - r * .95, y - r * .8),
                       (x - r * .45, y - r), (x - r * .7, y - r * .3)], hair)
            self.stroke([(x + r * .8, y - r * .7), (x + r, y + r * .1)], hair, r * .18)
        else:
            self.poly([(x - r, y + r * .05), (x - r * 1.1, y - r * .75),
                       (x - r * .5, y - r * 1.25), (x + r * .5, y - r * 1.2),
                       (x + r, y - r * .55), (x + r * .8, y - r * .1),
                       (x + r * .5, y - r * .65), (x - r * .5, y - r * .5)], hair)
        for dx in [-.37, .35]:
            self.stroke([(x + r * dx - r * .1, y), (x + r * dx + r * .1, y)], INK, .6)
        self.stroke([(x + r * .04, y + r * .1), (x - r * .06, y + r * .4),
                     (x + r * .13, y + r * .45)], '#89654f', .5)
        self.stroke([(x - r * .25, y + r * .72), (x + r * .27, y + r * .69)], INK, .5)
        self.poly([(x - r * .6, y + r * 1.4), (x, y + r * 2.1),
                   (x + r * .55, y + r * 1.4), (x, y + r * 1.65)], PAPER)
        if kind not in ('patient', 'nurse'):
            self.poly([(x, y + r * 1.75), (x - r * .18, y + r * 2.8),
                       (x + r * .2, y + r * 2.8)], RED)

    def waves(self, top, color='#6c9094'):
        for y in range(round(top), round(self.h), 5):
            for x in range(-10, round(self.w), 20):
                self.stroke([(x, y + 1), (x + 6, y), (x + 12, y + 1)], color, .6)

    def flame(self, x, y, r):
        self.poly([(x - r, y), (x - r * 1.4, y - r), (x - r * .4, y - r * 2.5),
                   (x, y - r * 1.6), (x + r * .6, y - r * 3),
                   (x + r * 1.2, y - r * .7), (x + r * .7, y)], '#b34b33')
        self.poly([(x - r * .4, y), (x - r * .6, y - r * .8),
                   (x + r * .1, y - r * 1.8), (x + r * .5, y)], '#e4b759')


def stars(a, x, y, r, color='#ead5a0'):
    for i in range(12):
        t = math.tau * i / 12
        px, py = x + r * math.sin(t), y + r * math.cos(t)
        pts = []
        for n in range(10):
            q = math.pi * n / 5 - math.pi / 2
            rr = r * (.12 if n % 2 == 0 else .05)
            pts.append((px + math.cos(q) * rr, py + math.sin(q) * rr))
        a.poly(pts, color)


def illustration(scene, x, y, w, h):
    """Draw a distinct scene, with shapes composed for each banner's width."""
    a = Art(w, h, '#d9d9c8')
    if scene == 'court':
        a.box((0, h * .68, w, h), '#cac3a8')
        # A Peace Palace-inspired silhouette, red roofs and arched entrance.
        bx, by, bw = w * .27, h * .3, w * .48
        a.box((bx, by + h * .16, bx + bw, h * .86), '#c7b58d', INK)
        a.poly([(bx - 7, by + h * .16), (bx + bw / 2, by - 6),
                (bx + bw + 7, by + h * .16)], '#925346', INK)
        for i in range(10):
            a.window(bx + 9 + i * (bw - 16) / 10, by + h * .27, 8, h * .17)
        tx = bx + bw * .76
        a.box((tx, h * .18, tx + 21, h * .87), '#c8b78f', INK)
        a.poly([(tx - 4, h * .19), (tx + 10, 3), (tx + 25, h * .19)], '#895043', INK)
        a.ellipse((tx + 6, h * .26, tx + 15, h * .26 + 9), PAPER, INK)
        a.stroke([(tx + 10.5, h * .26 + 2), (tx + 10.5, h * .26 + 5),
                  (tx + 13, h * .26 + 5)], INK, .5)
        a.box((bx + bw * .43, h * .66, bx + bw * .56, h * .87), INK)
        a.ellipse((bx + bw * .43, h * .54, bx + bw * .56, h * .78), INK)
        for yy in [h * .89, h * .94, h * .99]:
            a.stroke([(bx - 12, yy), (bx + bw + 12, yy)], '#897b60', .9)
        # Scales of justice, deliberately large enough to read at thumbnail size.
        cx = w * .12
        a.stroke([(cx, h * .2), (cx, h * .82)], INK, 2.2)
        a.stroke([(cx - 27, h * .34), (cx + 27, h * .34)], INK, 1.8)
        a.ellipse((cx - 3, h * .17, cx + 3, h * .17 + 6), '#aa7b35', INK)
        for dx in [-24, 24]:
            a.stroke([(cx + dx, h * .34), (cx + dx - 11, h * .62),
                      (cx + dx + 11, h * .62), (cx + dx, h * .34)], INK, .8)
            a.poly([(cx + dx - 13, h * .62), (cx + dx + 13, h * .62),
                    (cx + dx + 7, h * .7), (cx + dx - 7, h * .7)], '#aa7b35', INK)
        a.poly([(cx - 20, h * .87), (cx - 7, h * .8), (cx + 7, h * .8),
                (cx + 20, h * .87)], INK)
        a.person(w * .88, h * .49, h * .135, '#625c4b', '#bd8968', '#35362d', 'patient')
        a.person(w * .94, h * .72, h * .09, '#b49a6b', '#bd8968', '#35362d', 'patient')
        a.stroke([(w * .83, h * .8), (w * .94, h * .91)], '#bd8968', 5)
    elif scene == 'summit':
        a.box((0, h * .62, w, h), '#c9c1a6')
        for i, height in enumerate([.37, .5, .29, .63, .4, .52, .31, .49, .6]):
            xx = w * .025 + i * w * .077
            a.building(xx, h * (.68 - height), w * .055, h * height, '#adb4a8', 3)
        a.stroke([(w * .72, 3), (w * .72, h - 3)], '#8a8a77', 1)
        a.person(w * .16, h * .47, h * .13, '#374850', '#d7a180', '#d2b669')
        a.person(w * .34, h * .46, h * .13, '#384b51', '#ccaa83', '#282c28')
        a.person(w * .52, h * .47, h * .13, '#424b4c', '#d4b099', '#a29b83', 'bald')
        a.ellipse((w * .04, h * .83, w * .66, h * 1.1), '#7a6550', INK)
        for xx in [.16, .34, .52]:
            a.stroke([(w * xx, h * .83), (w * xx + 4, h * .72)], INK, 1)
        # Europe's place at the table: chair and the circle of stars.
        a.box((w * .79, h * .16, w * .95, h * .62), '#416176')
        stars(a, w * .87, h * .38, h * .17)
        a.box((w * .81, h * .66, w * .93, h * .87), '#7b6750', INK)
        a.stroke([(w * .8, h * .89), (w * .94, h * .89)], INK, 2.5)
        for xx in [.82, .92]:
            a.stroke([(w * xx, h * .88), (w * xx, h)], INK, 1.6)
    elif scene == 'kyiv':
        a.box((0, 0, w, h), '#a4b3b6')
        a.building(w * .08, h * .27, w * .32, h * .75, '#6f766e', 3)
        a.building(w * .5, h * .44, w * .35, h * .6, '#8e8a77', 3)
        a.flame(w * .27, h * .85, h * .17)
        for i in range(4):
            a.ellipse((w * .25 + i * 6, h * .08 + i * 3,
                       w * .25 + 15 + i * 6, h * .44 + i * 2), '#606966')
        a.stroke([(w * .68, 2), (w * .55, h * .2)], '#f4e9c9', 2)
        a.stroke([(w * .83, h * .1), (w * .69, h * .34)], '#f4e9c9', 1.4)
        a.poly([(w * .57, h * .23), (w * .53, h * .22), (w * .56, h * .16)], INK)
        a.person(w * .9, h * .55, h * .12, '#3d4f4d', '#cbab84', '#4e4c3e')
    elif scene == 'berlin':
        a.box((0, 0, w, h), '#c6d0c5')
        # Classical conference facade, flags and delegates.
        a.poly([(w * .04, h * .36), (w * .3, h * .08), (w * .55, h * .36)], '#9d9e85')
        for xx in [.1, .2, .3, .4]:
            a.box((w * xx, h * .37, w * xx + 5, h * .85), '#87907e')
        a.box((w * .74, 3, w - 5, h * .42), '#476375')
        a.box((w * .74, h * .24, w - 5, h * .42), '#dab95d')
        a.person(w * .28, h * .55, h * .135, '#334c50', '#d0ae89', '#5a574c')
        a.person(w * .55, h * .48, h * .14, '#657159', '#caa182', '#494538', 'patient')
        a.person(w * .82, h * .58, h * .12, '#58615d', '#d8ad8b', '#8d8977')
        a.poly([(0, h * .94), (w, h * .89), (w, h), (0, h)], '#645846')
    elif scene == 'riyadh':
        a.box((0, 0, w, h), '#d6c3a1')
        for xx, yy, ww in [(.05, .4, .12), (.23, .2, .14), (.44, .07, .21), (.75, .32, .15)]:
            a.building(w * xx, h * yy, w * ww, h, '#8b9587', 4)
        a.poly([(w * .44, h * .07), (w * .52, 0), (w * .65, h * .07)], '#667b75', INK)
        a.flame(w * .55, h * .46, h * .095)
        a.stroke([(w * .95, 2), (w * .66, h * .27)], INK, 1.2)
        for i in range(6):
            t = math.pi * i / 3
            a.stroke([(w * .59 + math.cos(t) * 6, h * .27 + math.sin(t) * 6),
                      (w * .59 + math.cos(t) * 12, h * .27 + math.sin(t) * 12)], RED, 1)
        a.stroke([(w * .09, h * .93), (w * .29, h * .47), (w * .41, h * .34)], PAPER, 1.5)
    elif scene == 'tanker':
        a.box((0, 0, w, h), '#bfc7b7')
        a.poly([(0, h * .45), (w * .2, h * .23), (w * .34, h * .48),
                (w * .53, h * .35), (w * .72, h * .46), (w, h * .28), (w, h), (0, h)], '#a5a58a')
        a.box((0, h * .59, w, h), '#6c8a89')
        a.waves(h * .66, '#afc0b2')
        a.poly([(w * .1, h * .62), (w * .86, h * .57), (w * .77, h * .88),
                (w * .2, h * .89)], '#3e4e4b', INK)
        a.box((w * .18, h * .34, w * .32, h * .63), '#e1d6b8', INK)
        for xx in [.2, .25]:
            a.window(w * xx, h * .4, 5, 4, '#567578')
        a.box((w * .22, h * .23, w * .26, h * .35), RED)
        a.stroke([(w * .4, h * .55), (w * .77, h * .52)], '#c4ae7a', 2)
        a.flame(w * .64, h * .59, h * .15)
        a.ellipse((w * .64, 0, w * .83, h * .28), '#67736c')
    elif scene == 'climate':
        a.box((0, 0, w, h), '#c7ccaf')
        for xx in [.07, .19, .3]:
            a.box((w * xx, h * .25, w * xx + 7, h), '#8e9580')
            a.ellipse((w * xx - 3, h * .06, w * xx + 15, h * .28), '#b1b6a2')
        a.stroke([(0, h * .85), (w * .36, h * .85), (w * .36, h * .64),
                  (w * .5, h * .64)], '#616e5d', 6)
        a.person(w * .8, h * .42, h * .18, '#53654f', '#bd9270', '#433f34')
        a.poly([(w * .48, h * .17), (w * .67, h * .17), (w * .64, h * .43),
                (w * .67, h * .6), (w * .63, h * .9), (w * .47, h * .9)], PAPER, INK)
        for yy in [.29, .39, .49, .69, .79]:
            a.stroke([(w * .5, h * yy), (w * .61, h * yy)], '#9e9a86', .7)
        a.stroke([(w * .48, h * .61), (w * .54, h * .57),
                  (w * .59, h * .63), (w * .65, h * .58)], RED, 1.5)
    elif scene == 'gaza':
        a.box((0, 0, w, h), '#c8c8b5')
        a.building(w * .04, 2, w * .18, h * .7, '#929482', 3)
        a.poly([(w * .05, 2), (w * .1, 9), (w * .14, 4), (w * .2, 8),
                (w * .22, 1)], '#c8c8b5')
        a.poly([(w * .2, h * .8), (w * .4, h * .2), (w * .63, h * .84)], '#dfd4b6', INK)
        a.poly([(w * .34, h * .8), (w * .41, h * .46), (w * .49, h * .81)], '#7c806e')
        a.box((0, h * .85, w, h), '#75928e')
        a.waves(h * .87, '#c5c9b1')
        a.person(w * .78, h * .4, h * .16, '#6d6a55', '#ba8b69', '#4b4c40', 'patient')
        a.person(w * .84, h * .71, h * .1, '#bcaa78', '#bd9270', '#4b4c40', 'patient')
        a.stroke([(w * .69, h * .77), (w * .87, h * .9)], '#bd9270', 4)
        a.stroke([(w * .65, h * .1), (w * .6, h * .35)], '#879a95', .8)
    elif scene == 'markets':
        a.box((0, 0, w, h), '#d4d4bd')
        for xx in range(10, round(w), 22):
            a.stroke([(xx, 5), (xx, h - 4)], '#b2b8a2', .5)
        for yy in range(9, round(h), 10):
            a.stroke([(3, yy), (w - 3, yy)], '#b2b8a2', .5)
        pts = [(4, h * .2), (w * .15, h * .32), (w * .26, h * .22),
               (w * .38, h * .57), (w * .48, h * .49), (w * .59, h * .87)]
        a.stroke(pts, RED, 3)
        a.poly([(w * .59, h * .87), (w * .49, h * .78), (w * .62, h * .68)], RED)
        a.person(w * .81, h * .4, h * .18, '#4d5f5a', '#cfaa84', '#393e34')
        a.stroke([(w * .94, h * .97), (w * .96, h * .59),
                  (w * .9, h * .23)], '#cfaa84', 5)
        a.stroke([(w * .9, h * .23), (w * .82, h * .12)], '#cfaa84', 3)
    elif scene == 'cyber':
        a.box((0, 0, w, h), '#bdc9be')
        a.poly([(w * .03, h * .42), (w * .31, h * .12), (w * .56, h * .42)], '#e0d8bb', INK)
        a.box((w * .07, h * .42, w * .53, h * .9), '#d6cfb3', INK)
        for xx in [.11, .21, .31, .41]:
            a.box((w * xx, h * .43, w * xx + 5, h * .87), '#f1e8cc', INK, .4)
        for xx, yy in [(.65, .2), (.73, .38), (.63, .67)]:
            a.stroke([(w * xx, 2), (w * xx, h * yy), (w * (xx + .12), h * yy)], '#75928b', 1)
            a.ellipse((w * (xx + .12) - 2, h * yy - 2,
                       w * (xx + .12) + 2, h * yy + 2), '#75928b')
        a.person(w * .79, h * .45, h * .175, '#4e6260', '#cea480', '#857c65', 'bald')
        a.stroke([(w * .89, h * .68), (w * .97, h * .9)], RED, 2)
        a.stroke([(w * .97, h * .68), (w * .89, h * .9)], RED, 2)
    elif scene == 'health':
        a.box((0, 0, w, h), '#d7d5b9')
        a.box((w * .06, h * .15, w * .42, h), '#b4bfa5', INK)
        a.box((w * .16, h * .38, w * .32, h), '#5e7f74')
        a.box((w * .19, h * .2, w * .29, h * .27), PAPER)
        a.box((w * .226, h * .14, w * .253, h * .33), PAPER)
        a.person(w * .51, h * .39, h * .18, '#e7e5ce', '#92684e', '#303b30', 'nurse')
        a.box((w * .51 - 10, h * .11, w * .51 + 10, h * .23), PAPER, INK)
        a.person(w * .79, h * .42, h * .18, '#ac8d5a', '#92654c', '#333a2c', 'patient')
        a.stroke([(w * .63, h * .82), (w * .71, h * .67),
                  (w * .78, h * .81)], '#92654c', 4)
        a.stroke([(w * .92, h * .64), (w * .92, h * .32)], '#92654c', 4)
        a.poly([(w * .92, h * .33), (w * .89, h * .23), (w * .91, h * .2),
                (w * .94, h * .3), (w * .96, h * .2), (w * .98, h * .23),
                (w * .95, h * .37)], '#92654c', INK)
    elif scene == 'brussels':
        a.box((0, 0, w, h), '#c5cbbc')
        a.box((w * .04, 3, w * .35, h * .61), '#3e6070')
        stars(a, w * .195, h * .32, h * .21)
        a.box((w * .65, 3, w * .96, h * .61), '#3e6070')
        a.stroke([(w * .65, 3), (w * .96, h * .61)], PAPER, 4)
        a.stroke([(w * .96, 3), (w * .65, h * .61)], PAPER, 4)
        a.stroke([(w * .805, 3), (w * .805, h * .61)], PAPER, 8)
        a.stroke([(w * .65, h * .32), (w * .96, h * .32)], PAPER, 6)
        a.stroke([(w * .805, 3), (w * .805, h * .61)], RED, 4)
        a.stroke([(w * .65, h * .32), (w * .96, h * .32)], RED, 3)
        a.person(w * .42, h * .35, h * .16, '#435b60', '#d1a17b', '#7a7560')
        a.person(w * .6, h * .42, h * .14, '#536158', '#cfab8b', '#a89c71', 'patient')
        a.poly([(w * .16, h * .94), (w * .35, h * .64), (w * .49, h * .69),
                (w * .58, h * .6), (w * .82, h * .87), (w * .72, h * 1.04),
                (w * .53, h * .78), (w * .42, h * .91)], '#d3ac85', INK)
        a.stroke([(w * .46, h * .73), (w * .55, h * .88)], '#966f51', .8)
    else:
        raise ValueError(f'Unknown illustration: {scene}')
    # Restrained engraving marks tie all scenes to the printed page.
    for j in range(4):
        a.stroke([(w - 22 + j * 5, h - 3), (w - 16 + j * 5, h - 10)], INK, .35)
    page.paste(a.image, (round(x * SCALE), round(y * SCALE)))
    METRICS['illustrations'] += 1


def paper_texture():
    rng = random.Random(20261120)
    # Sparse fibers rather than per-pixel noise: warm paper, efficient PNG.
    for _ in range(9300):
        x, y = rng.randrange(SIZE * SCALE), rng.randrange(SIZE * SCALE)
        shade = rng.choice(['#e8dfca', '#eee5d1', '#eae1cd', '#faf4e5'])
        draw.line((x, y, x + rng.randrange(1, 5), y), fill=shade, width=1)


def masthead():
    put('THE WORLD IN ONE DAY', 22, 13, 11.5, 'bold', width=300)
    put(f'{TOTAL} STORIES  /  {len(LEADS)} LEADS + {len(BRIEFS)} BRIEFS',
        1002, 15, 9.2, 'bold', width=360, align='right')
    line([(22, 30), (1002, 30)], INK, 1.1)
    rect((22, 37, 120, 112), RED)
    put('NOV', 71, 42, 11, 'bold', PAPER, 85, 'center')
    put('20', 71, 53, 44, 'headline', PAPER, 88, 'center')
    put('FRI 2026', 71, 99, 9.2, 'bold', PAPER, 85, 'center')
    put('Friday 20 November 2026', 135, 46, 59, 'headline', INK, 867)
    put('GENOCIDE VERDICT  /  WAR & DIPLOMACY  /  MARKETS UNDER PRESSURE',
        138, 103, 10.2, 'bold', width=864)
    line([(22, 120), (1002, 120)], INK, 2)
    line([(22, 124), (1002, 124)], INK, .6)


def hero(story, number, x):
    y, w, h = 131, 483, 222
    illustration(story.scene, x, y, w, 94)
    put(f'{number:02d}  /  {story.city}', x, y + 101, 9.4, 'bold',
        REGIONS[story.region], w)
    headline_size = 29.0
    while len(wrap(story.headline, w - 4, headline_size, 'headline')) > 2:
        headline_size -= .25
    headline_lines = wrap(story.headline, w - 4, headline_size, 'headline')
    title_y = y + 118
    headline_leading = headline_size + 1
    for i, title_line in enumerate(headline_lines):
        put(title_line, x, title_y + i * headline_leading, headline_size, 'headline', width=w - 4)
    deck_y = title_y + len(headline_lines) * headline_leading + 4
    deck_size = 11.1
    deck_lines = wrap(story.deck, w - 5, deck_size)
    source_y = y + h - 8
    if deck_y + len(deck_lines) * 13 > source_y - 5:
        raise ValueError(f'Hero deck overflows: {story.city}')
    paragraph(story.deck, x, deck_y, w - 5, deck_size, 13)
    put('SOURCE: NOV 20 DIGESTS', x, source_y, 7.1, 'bold', '#6d6d60', w)
    line([(x, y + h + 5), (x + w, y + h + 5)], INK, .7)


def region_strip():
    y = 365
    gap = 7
    width = (980 - 6 * gap) / 7
    for i, (name, color) in enumerate(REGIONS.items()):
        x = 22 + i * (width + gap)
        rect((x, y, x + width, y + 20), None, color, .8)
        rect((x, y, x + 3, y + 20), color)
        label = f'{name}  {REGION_COUNTS[name]}'
        put(label, x + width / 2 + 1, y + 6, 9.1, 'bold', color,
            width - 13, 'center')


def numbers_band():
    y = 396
    rect((22, y, 1002, 463), '#e9dfc8')
    put('BY THE NUMBERS', 31, y + 5, 8.0, 'bold', RED, 170)
    width = 980 / len(NUMBERS)
    for i, (figure, caption, detail) in enumerate(NUMBERS):
        x = 22 + width * i
        center = x + width / 2
        if i:
            line([(x, y + 17), (x, y + 60)], '#bfb399', .6)
        put(figure, center, y + 17, 30.5, 'headline', RED, width - 13, 'center')
        put(caption, center, y + 48, 8.5, 'bold', INK, width - 10, 'center')
        put(detail, center, y + 59, 6.9, 'sans', '#666656', width - 8, 'center')


def lead_card(story, number, x, y, w=188, h=163):
    illustration(story.scene, x, y, w, 52)
    # A bottom-aligned source strip reserves breathing room for every card.
    source_y = y + h - 9
    put(f'{number:02d} / {story.city}', x + 2, y + 59, 7.7, 'bold',
        REGIONS[story.region], w - 4)
    title_y = y + 73
    chosen = None
    for k in range(28, 24, -1):
        title_size = k / 2
        title_lines = wrap(story.headline, w - 4, title_size, 'headline')
        title_leading = title_size + 1
        deck_y = title_y + len(title_lines) * title_leading + 4
        for body_size in [9.0, 8.8, 8.6, 8.4]:
            deck_lines = wrap(story.deck, w - 6, body_size)
            leading = body_size + 1.25
            if deck_y + len(deck_lines) * leading <= source_y - 4:
                chosen = (title_size, title_leading, title_lines,
                          deck_y, body_size, leading)
                break
        if chosen:
            break
    if chosen is None:
        raise ValueError(f'Lead cannot fit without clipping: {story.city}')
    size, leading, lines, deck_y, body_size, body_leading = chosen
    for i, title_line in enumerate(lines):
        put(title_line, x + 2, title_y + leading * i, size, 'headline', width=w - 4)
    paragraph(story.deck, x + 2, deck_y, w - 6, body_size, body_leading)
    put('SOURCE: NOV 20 DIGESTS', x + 2, source_y, 6.6, 'bold', '#6d6d60', w - 4)
    line([(x, y + h + 3), (x + w, y + h + 3)], RULE, .55)


# Coarse, deliberately simplified continent outlines: a locator, not a border map.
CONTINENTS = [
    [(-167, 69), (-140, 72), (-128, 58), (-119, 53), (-123, 40),
     (-112, 30), (-98, 21), (-87, 22), (-83, 10), (-75, 8), (-81, 25),
     (-66, 47), (-55, 54), (-69, 60), (-84, 56), (-101, 69), (-130, 73)],
    [(-73, 60), (-50, 59), (-22, 76), (-43, 83), (-62, 78)],
    [(-81, 12), (-66, 10), (-50, 0), (-35, -8), (-43, -23),
     (-54, -35), (-68, -56), (-76, -43), (-75, -24), (-81, -7)],
    [(-11, 36), (-8, 50), (6, 56), (18, 70), (36, 70), (30, 56),
     (46, 47), (39, 39), (20, 36), (10, 45), (0, 43)],
    [(-17, 35), (10, 37), (34, 30), (43, 12), (51, 10), (43, -13),
     (32, -35), (18, -35), (10, -18), (-4, 1), (-16, 15)],
    [(29, 70), (66, 77), (100, 75), (140, 70), (179, 61), (156, 50),
     (141, 44), (134, 33), (122, 24), (109, 8), (105, -6), (98, 6),
     (80, 7), (70, 25), (57, 25), (45, 13), (35, 30), (40, 43)],
    [(111, -12), (135, -11), (152, -23), (145, -39), (129, -35),
     (114, -36), (110, -25)],
    [(166, -35), (178, -40), (170, -47), (164, -44)],
    [(47, -13), (50, -17), (47, -26), (44, -24)],
    [(130, 32), (137, 36), (143, 43), (140, 34)],
]


def mini_map():
    x, y, w = 22, 851, 239
    a = Art(w, 83, '#e7dfc9')

    def project(lon, lat):
        return 6 + (lon + 180) / 360 * 227, 4 + (83 - lat) / 143 * 72

    for lat in [0, 40]:
        yy = project(0, lat)[1]
        a.stroke([(2, yy), (w - 2, yy)], '#d2cbb4', .45)
    for shape in CONTINENTS:
        a.poly([project(lon, lat) for lon, lat in shape], '#b3b69c', '#939b83')
    # Offset dense European pins; every pin has a leader to its actual location.
    offsets = {
        1: (-24, -12), 2: (6, 5), 3: (15, -13), 4: (0, -13),
        5: (7, 15), 6: (19, 4), 7: (23, -3), 8: (-19, 8),
        9: (-12, -12), 10: (-19, 5), 11: (8, 12), 12: (-15, -3),
    }
    for i, story in enumerate(LEADS, 1):
        px, py = project(story.lon, story.lat)
        dx, dy = offsets[i]
        lx, ly = px + dx, py + dy
        a.stroke([(px, py), (lx, ly)], REGIONS[story.region], .65)
        a.ellipse((px - 1.1, py - 1.1, px + 1.1, py + 1.1), INK)
        a.ellipse((lx - 4.8, ly - 4.8, lx + 4.8, ly + 4.8), REGIONS[story.region], PAPER, .4)
        a.label(str(i), lx, ly - 2.7, 5.5, PAPER)
    page.paste(a.image, (x * SCALE, y * SCALE))
    put('Pins match lead numbers; Markets located in New York.',
        x, 938, 6.1, 'sans', '#696b5e', w)
    # Compact regional key, including Oceania's truthful zero coverage.
    items = list(REGIONS.items())
    for j, (name, color) in enumerate(items):
        row, col = divmod(j, 4)
        xx = x + col * 61
        yy = 949 + row * 10
        rect((xx, yy + 1, xx + 4, yy + 5), color)
        put(name, xx + 6, yy, 5.9, 'bold', color, 58)


def rich_brief(city, region, text, x, y, width):
    size = 7.75
    city_words = [(word, 'bold', REGIONS[region]) for word in (city + ':').split()]
    body_words = [(word, 'sans', INK) for word in text.split()]
    rows = [[]]
    row_width = 0
    space = measure(' ', size)
    for word, face, color in city_words + body_words:
        word_width = measure(word, size, face)
        if word_width > width:
            raise ValueError(f'Brief word too wide: {word}')
        needed = word_width + (space if rows[-1] else 0)
        if row_width + needed > width:
            rows.append([])
            row_width = 0
        if rows[-1]:
            row_width += space
        rows[-1].append((word, face, color, row_width))
        row_width += word_width
    if len(rows) > 2:
        raise ValueError(f'Brief needs more than two lines: {city}')
    for index, row in enumerate(rows):
        for word, face, color, dx in row:
            put(word, x + dx, y + index * 9.0, size, face, color, width - dx)


def bottom():
    line([(22, 829), (1002, 829)], INK, 1.3)
    put('WHERE IT HAPPENED', 22, 838, 10.4, 'bold', width=240)
    put('ALSO ON FRIDAY 20 NOVEMBER', 279, 838, 10.4, 'bold', width=560)
    put(f'{len(BRIEFS)} BRIEFS', 1002, 839, 8.0, 'bold', RED, 90, 'right')
    line([(270, 837), (270, 966)], RULE, .7)
    mini_map()
    per_column = math.ceil(len(BRIEFS) / 3)
    column_width = 231
    for index, (city, region, text) in enumerate(BRIEFS):
        col, row = divmod(index, per_column)
        x = 279 + col * 244
        yy = 852 + row * 19
        rich_brief(city, region, text, x, yy, column_width)
        if row != per_column - 1:
            line([(x, yy + 17), (x + column_width, yy + 17)], '#d2c9b2', .35)
    for x in [516, 760]:
        line([(x, 852), (x, 965)], RULE, .5)


def footer():
    rect((22, 974, 1002, 1005), None, RED, 1)
    put('DATE CHECK', 30, 981, 9.4, 'bold', RED, 100)
    message = ('EXCLUDED · First reported 19 Nov or earlier: Shenzhen summit itself '
               '(Thu 19 Nov); Anthropic IPO pricing (Thu 19 Nov); ICJ hearings. '
               'Friday’s stories: summit aftermath, debut close and genocide verdict.')
    used = paragraph(message, 137, 980, 855, 8.0, 10.2)
    if used > 23:
        raise ValueError('Date-check box overflows')
    put('SOURCES: oneturn.news  •  openchronicle.org  •  bangladeshchronicle.net  •  '
        'Euronews  •  human-synthesis.ghost.io  |  Supplied verified 20 Nov brief',
        512, 1013, 7.4, 'sans', '#5b5e53', 980, 'center')


def compose():
    paper_texture()
    masthead()
    hero(LEADS[0], 1, 22)
    hero(LEADS[1], 2, 519)
    line([(512, 131), (512, 353)], RULE, .7)
    region_strip()
    numbers_band()
    put('MORE LEADS', 22, 476, 10.2, 'bold', width=200)
    put(f'{len(LEADS) - 2} REPORTS  /  WAR, CLIMATE, MONEY & DIPLOMACY',
        1002, 477, 8.0, 'bold', '#67695d', 570, 'right')
    for index, story in enumerate(LEADS[2:]):
        row, col = divmod(index, 5)
        lead_card(story, index + 3, 22 + col * 198, 493 + row * 167)
        if col != 4:
            x = 215 + col * 198
            line([(x, 493 + row * 167), (x, 655 + row * 167)], RULE, .5)
    bottom()
    footer()
    result = page.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    output = ROOT / 'entry.png'
    result.save(output, format='PNG', optimize=True, compress_level=9)
    payload = output.read_bytes()
    if len(payload) > 1048576:
        raise ValueError(f'PNG exceeds 1 MiB: {len(payload)} bytes')
    variance = ImageStat.Stat(result.convert('L')).var[0]
    if variance < 500:
        raise ValueError(f'Unexpectedly blank page: variance {variance}')
    print(f'entry.png: {SIZE}x{SIZE}, {len(payload):,} bytes')
    print(f'SHA-256: {hashlib.sha256(payload).hexdigest()}')
    print(f'Grayscale pixel variance: {variance:.2f}')
    print(f'Stories: {len(LEADS)} leads + {len(BRIEFS)} briefs = {TOTAL}')
    print('Regions: ' + ', '.join(f'{name}={REGION_COUNTS[name]}' for name in REGIONS))
    print(f'Measured text lines/segments: {METRICS["text_lines"]}; '
          f'original illustration banners: {METRICS["illustrations"]}')


if __name__ == '__main__':
    compose()

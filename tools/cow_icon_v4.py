#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛牛文档工具 · 应用图标 v4（萌系小牛 · 暖橙容器白牛）

对标规范：
  · Microsoft Fluent：容器化底板 + 3 层结构（底 / 主体 / 细节），剪影必须可辨。
  · Apple HIG：squircle（超椭圆）容器、主体占 78~82%、单一左上光源。
  · Google Material：keyline 安全区、几何化。
  · 通用图标工程：剪影测试、统一圆角与线宽、单一视觉焦点。

要点：
  · 几何由 geometry() 单点提供 —— 位图与 SVG 严格同源，不会两份不同步。
  · 头部轮廓 = 10 关键点经 Catmull-Rom 样条（贝塞尔级平滑），非椭圆拼接。
  · 容器 = 超椭圆 squircle，主体全部裁进容器（keyline 约 80%）。

用法：
  python tools/cow_icon_v4.py build     # 导出正式图标 + 备份另两套配色
  python tools/cow_icon_v4.py preview   # 仅生成 512 预览
"""
import math
import os
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "icons")
PREVIEW_DIR = os.path.join(OUT, "preview")
BACKUP_DIR = os.path.join(OUT, "backup")

MAIN_PAL = "brand"          # 正式使用：暖橙容器 · 白牛
BACKUP_PALS = ["light", "mint"]   # 保留备份：奶油容器·暖橙牛 / 薄荷容器·奶牛

# ---------------------------------------------------------------- 配色
PALETTES = {
    "brand": dict(
        name="暖橙容器 · 白牛",
        bg_top="#FFB84D", bg_bot="#F2802A",
        face_top="#FFFDF8", face_bot="#FFE9CC",
        horn="#FFC978", horn_shade="#F5A94E",
        ear="#FFF3E0",
        eye="#4A3128", blush="#FF9E7A",
        mouth="#8A5A3C", muzzle="#FFF0DC",
        shade="#D9A05A",
    ),
    "light": dict(
        name="奶油容器 · 暖橙牛",
        bg_top="#FFF7E4", bg_bot="#FFE2AE",
        face_top="#FFD98F", face_bot="#F5A94E",
        horn="#FFFFFF", horn_shade="#F2E2C4",
        ear="#F0B964",
        eye="#4A3128", blush="#F58A63",
        mouth="#8A5A3C", muzzle="#FFE9C4",
        shade="#C9822F",
    ),
    "mint": dict(
        name="薄荷容器 · 奶牛",
        bg_top="#DFF5EC", bg_bot="#A8E0CB",
        face_top="#FFFDF8", face_bot="#F2EFE6",
        horn="#FFCE8A", horn_shade="#F2B979",
        ear="#FFFFFF",
        eye="#3E3128", blush="#FFAE8E",
        mouth="#7E5334", muzzle="#FFF6EA",
        shade="#B9D9C8",
    ),
}


# ---------------------------------------------------------------- 几何（256 基准）
def geometry(k=1.0):
    """所有几何的唯一来源（位图与 SVG 共用）。k 为缩放系数。"""
    m = lambda v: v * k
    return dict(
        half=118 * k, n=4.5,
        bg_y0=10 * k, bg_y1=246 * k,
        shoulder=[(86 * k, 168 * k), (170 * k, 168 * k),
                  (198 * k, 248 * k), (58 * k, 248 * k)],
        sh_y0=168 * k, sh_y1=248 * k,
        ear_dx=74 * k, ear_rx=20 * k, ear_cy=100 * k,
        ear_up=17 * k, ear_dn=21 * k,
        horn_dx=52 * k, horn_cy=58 * k, horn_r=16 * k,
        head_keys=[(128 * k, 46 * k), (172 * k, 54 * k), (206 * k, 92 * k),
                   (202 * k, 140 * k), (174 * k, 172 * k), (128 * k, 182 * k),
                   (82 * k, 172 * k), (54 * k, 140 * k), (50 * k, 92 * k),
                   (84 * k, 54 * k)],
        head_y0=46 * k, head_y1=182 * k,
        shade_keys=[(150 * k, 96 * k), (186 * k, 122 * k), (176 * k, 162 * k),
                    (150 * k, 178 * k), (132 * k, 150 * k)],
        muzzle_cy=150 * k, muzzle_rx=34 * k, muzzle_up=21 * k, muzzle_dn=23 * k,
        eye_cy=116 * k, eye_dx=34 * k, eye_rx=14 * k, eye_ry=17 * k,
        blush_dx=58 * k, blush_cy=152 * k, blush_rx=13 * k, blush_ry=8 * k,
        nostril_dx=13 * k, nostril_cy=146 * k,
        nostril_rx=3.2 * k, nostril_ry=4.2 * k,
        mouth_cy=158 * k, mouth_rx=16 * k,
        mouth_up=9 * k, mouth_dn=12 * k, mouth_w=3.2 * k,
    )


# ---------------------------------------------------------------- 曲线工具
def squircle(cx, cy, half, n=4.5, steps=240):
    pts = []
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        x = half * math.copysign(abs(c) ** (2.0 / n), c)
        y = half * math.copysign(abs(s) ** (2.0 / n), s)
        pts.append((cx + x, cy + y))
    return pts


def catmull_rom(pts, samples=24, closed=True):
    n = len(pts)
    out = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i % n], pts[(i + 1) % n], pts[(i + 2) % n]
        for j in range(samples):
            t = j / float(samples)
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lerp(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def _grad(size, top, bot, y0, y1):
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    top, bot = _hex(top), _hex(bot)
    for y in range(size):
        t = 0.0 if y <= y0 else (1.0 if y >= y1 else (y - y0) / max(1.0, y1 - y0))
        d.line([(0, y), (size, y)], fill=_lerp(top, bot, t))
    return img


def _mask_poly(size, pts):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def _mask_ellipse(size, box):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse(box, fill=255)
    return m


def _layer(size, rgb, mask, alpha=1.0):
    img = Image.new("RGBA", (size, size), rgb + (255,))
    if alpha < 1.0:
        mask = Image.eval(mask, lambda v: int(v * alpha))
    img.putalpha(mask)
    return img


# ---------------------------------------------------------------- 位图绘制
def draw_cow(size, pal=MAIN_PAL, ss=6, detail="auto"):
    P = PALETTES[pal]
    if detail == "auto":
        detail = "tiny" if size <= 16 else ("mid" if size <= 32 else "full")

    S = int(size * ss)
    k = S / 256.0
    G = geometry(k)
    cv = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(cv)

    # 1. 容器（squircle）
    sq = squircle(128 * k, 128 * k, G["half"], n=G["n"])
    bg = _grad(S, P["bg_top"], P["bg_bot"], G["bg_y0"], G["bg_y1"]).convert("RGBA")
    bg.putalpha(_mask_poly(S, sq))
    cv.alpha_composite(bg)
    clip = _mask_poly(S, sq)

    def inside(layer):
        return Image.composite(layer, Image.new("L", (S, S), 0), clip)

    # 2. 肩部（半身像，底部切齐容器）
    sh_pts = catmull_rom(G["shoulder"], samples=18, closed=True)
    sh = _grad(S, P["face_top"], P["face_bot"], G["sh_y0"], G["sh_y1"]).convert("RGBA")
    sh.putalpha(inside(_mask_poly(S, sh_pts)))
    cv.alpha_composite(sh)

    # 3. 耳朵
    for sgn in (-1, 1):
        ex = 128 * k + sgn * G["ear_dx"]
        eb = [ex - G["ear_rx"], G["ear_cy"] - G["ear_up"],
              ex + G["ear_rx"], G["ear_cy"] + G["ear_dn"]]
        cv.alpha_composite(_layer(S, _hex(P["ear"]), inside(_mask_ellipse(S, eb))))

    # 4. 牛角
    for sgn in (-1, 1):
        hx = 128 * k + sgn * G["horn_dx"]
        hy = G["horn_cy"]
        r = G["horn_r"]
        horn = [(hx - r * 0.85, hy + r * 0.55), (hx + r * 0.85, hy + r * 0.55),
                (hx + sgn * r * 0.30, hy - r * 1.15)]
        cv.alpha_composite(_layer(S, _hex(P["horn"]), inside(_mask_poly(S, horn))))
        shp = [(hx + sgn * r * 0.20, hy + r * 0.50), (hx + r * 0.85, hy + r * 0.55),
               (hx + sgn * r * 0.30, hy - r * 0.20)]
        cv.alpha_composite(_layer(S, _hex(P["horn_shade"]), inside(_mask_poly(S, shp)), 0.55))

    # 5. 头部（Catmull-Rom 样条）
    head_pts = catmull_rom(G["head_keys"], samples=26, closed=True)
    head = _grad(S, P["face_top"], P["face_bot"], G["head_y0"], G["head_y1"]).convert("RGBA")
    head.putalpha(inside(_mask_poly(S, head_pts)))
    cv.alpha_composite(head)
    head_mask = inside(_mask_poly(S, head_pts))

    if detail == "full":
        shp2 = catmull_rom(G["shade_keys"], samples=20)
        cv.alpha_composite(_layer(S, _hex(P["shade"]),
                                  Image.composite(_mask_poly(S, shp2),
                                                  Image.new("L", (S, S), 0), head_mask), 0.18))

    # 6. 口鼻
    if detail != "tiny":
        mb = [128 * k - G["muzzle_rx"], G["muzzle_cy"] - G["muzzle_up"],
              128 * k + G["muzzle_rx"], G["muzzle_cy"] + G["muzzle_dn"]]
        cv.alpha_composite(_layer(S, _hex(P["muzzle"]),
                                  Image.composite(_mask_ellipse(S, mb),
                                                  Image.new("L", (S, S), 0), head_mask)))

    # 7. 眼睛（实心，保证 16px 可辨）
    erx, ery = G["eye_rx"], G["eye_ry"]
    if size <= 32:
        erx, ery = erx * 1.2, ery * 1.15
    for sgn in (-1, 1):
        ex = 128 * k + sgn * G["eye_dx"]
        d.ellipse([ex - erx, G["eye_cy"] - ery, ex + erx, G["eye_cy"] + ery],
                  fill=_hex(P["eye"]) + (255,))
    if detail != "tiny":
        for sgn in (-1, 1):
            ex = 128 * k + sgn * G["eye_dx"]
            hr = erx * 0.34
            d.ellipse([ex - erx * 0.30 - hr, G["eye_cy"] - ery * 0.42 - hr,
                       ex - erx * 0.30 + hr, G["eye_cy"] - ery * 0.42 + hr],
                      fill=(255, 255, 255, 255))

    # 8. 腮红 / 鼻孔 / 嘴
    if detail != "tiny":
        for sgn in (-1, 1):
            bx = 128 * k + sgn * G["blush_dx"]
            bb = [bx - G["blush_rx"], G["blush_cy"] - G["blush_ry"],
                  bx + G["blush_rx"], G["blush_cy"] + G["blush_ry"]]
            cv.alpha_composite(_layer(S, _hex(P["blush"]),
                                      Image.composite(_mask_ellipse(S, bb),
                                                      Image.new("L", (S, S), 0), head_mask), 0.50))
        for sgn in (-1, 1):
            nx = 128 * k + sgn * G["nostril_dx"]
            d.ellipse([nx - G["nostril_rx"], G["nostril_cy"] - G["nostril_ry"],
                       nx + G["nostril_rx"], G["nostril_cy"] + G["nostril_ry"]],
                      fill=_hex(P["mouth"]) + (255,))
        mbox = [128 * k - G["mouth_rx"], G["mouth_cy"] - G["mouth_up"],
                128 * k + G["mouth_rx"], G["mouth_cy"] + G["mouth_dn"]]
        d.arc(mbox, start=15, end=165, fill=_hex(P["mouth"]) + (255,),
              width=max(1, int(round(G["mouth_w"]))))

    # 9. 容器顶部高光（左上受光，克制）
    if detail == "full":
        hl = Image.new("L", (S, S), 0)
        ImageDraw.Draw(hl).ellipse(
            [128 * k - 120 * k, 128 * k - 190 * k, 128 * k + 120 * k, 128 * k + 20 * k], fill=120)
        hl = hl.filter(ImageFilter.GaussianBlur(18 * k))
        hl = Image.composite(hl, Image.new("L", (S, S), 0), clip)
        cv.alpha_composite(_layer(S, (255, 255, 255), Image.eval(hl, lambda v: int(v * 0.20))))

    return cv.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- SVG 导出（同源）
def export_svg(path, pal=MAIN_PAL):
    P = PALETTES[pal]
    G = geometry(1.0)
    sq = squircle(128, 128, G["half"], n=G["n"], steps=200)
    head = catmull_rom(G["head_keys"], samples=26, closed=True)
    shoulder = catmull_rom(G["shoulder"], samples=18, closed=True)

    def pts(seq):
        return " ".join("%.2f,%.2f" % (x, y) for x, y in seq)

    def ell(cx, cy, rx, ry):
        return ('<ellipse cx="%.2f" cy="%.2f" rx="%.2f" ry="%.2f"' % (cx, cy, rx, ry))

    horns = []
    for sgn in (-1, 1):
        hx, hy, r = 128 + sgn * G["horn_dx"], G["horn_cy"], G["horn_r"]
        horns.append('<polygon points="%s" fill="%s"/>' % (
            pts([(hx - r * 0.85, hy + r * 0.55), (hx + r * 0.85, hy + r * 0.55),
                 (hx + sgn * r * 0.30, hy - r * 1.15)]), P["horn"]))

    eyes, hls, blushes, nostrils = [], [], [], []
    for sgn in (-1, 1):
        ex = 128 + sgn * G["eye_dx"]
        eyes.append(ell(ex, G["eye_cy"], G["eye_rx"], G["eye_ry"]) + ' fill="%s"/>' % P["eye"])
        hr = G["eye_rx"] * 0.34
        hx2 = ex - G["eye_rx"] * 0.30
        hy2 = G["eye_cy"] - G["eye_ry"] * 0.42
        hls.append(ell(hx2, hy2, hr, hr) + ' fill="#FFFFFF"/>')
        bx = 128 + sgn * G["blush_dx"]
        blushes.append(ell(bx, G["blush_cy"], G["blush_rx"], G["blush_ry"])
                       + ' fill="%s" opacity="0.5"/>' % P["blush"])
        nx = 128 + sgn * G["nostril_dx"]
        nostrils.append(ell(nx, G["nostril_cy"], G["nostril_rx"], G["nostril_ry"])
                        + ' fill="%s"/>' % P["mouth"])

    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256" role="img" aria-label="牛牛文档工具">
<!--
  牛牛文档工具 · 应用图标 v4（{name}）
  规范：Fluent 容器化 3 层结构 / Apple HIG squircle + 主体 80% + 左上光源 / Material keyline。
  几何与位图同源（tools/cow_icon_v4.py 的 geometry()），改一处即两处同步。
-->
<defs>
  <linearGradient id="bg" x1="0" y1="{by0}" x2="0" y2="{by1}" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{bgt}"/><stop offset="1" stop-color="{bgb}"/>
  </linearGradient>
  <linearGradient id="face" x1="0" y1="{hy0}" x2="0" y2="{hy1}" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{ft}"/><stop offset="1" stop-color="{fb}"/>
  </linearGradient>
  <clipPath id="container"><polygon points="{sq}"/></clipPath>
</defs>

<polygon points="{sq}" fill="url(#bg)"/>
<g clip-path="url(#container)">
  <polygon points="{shoulder}" fill="url(#face)"/>
  <ellipse cx="{ear_l}" cy="{ear_cy}" rx="{ear_rx}" ry="{ear_ry}" fill="{ear}"/>
  <ellipse cx="{ear_r}" cy="{ear_cy}" rx="{ear_rx}" ry="{ear_ry}" fill="{ear}"/>
  {horns}
  <polygon points="{head}" fill="url(#face)"/>
  <ellipse cx="128" cy="{mz_cy}" rx="{mz_rx}" ry="{mz_ry}" fill="{muzzle}"/>
  {blushes}
  {eyes}
  {hls}
  {nostrils}
  <path d="M {mx0} {my} A {mrx} {mry} 0 0 0 {mx1} {my}" fill="none"
        stroke="{mouth}" stroke-width="{mw}" stroke-linecap="round"/>
</g>
</svg>
'''.format(
        name=P["name"],
        by0=G["bg_y0"], by1=G["bg_y1"], bgt=P["bg_top"], bgb=P["bg_bot"],
        hy0=G["head_y0"], hy1=G["head_y1"], ft=P["face_top"], fb=P["face_bot"],
        sq=pts(sq), shoulder=pts(shoulder),
        ear_l=128 - G["ear_dx"], ear_r=128 + G["ear_dx"],
        ear_cy=(G["ear_cy"] - G["ear_up"] + G["ear_cy"] + G["ear_dn"]) / 2.0,
        ear_rx=G["ear_rx"],
        ear_ry=((G["ear_cy"] + G["ear_dn"]) - (G["ear_cy"] - G["ear_up"])) / 2.0,
        ear=P["ear"], horns="\n  ".join(horns), head=pts(head),
        mz_cy=G["muzzle_cy"], mz_rx=G["muzzle_rx"],
        mz_ry=(G["muzzle_up"] + G["muzzle_dn"]) / 2.0, muzzle=P["muzzle"],
        blushes="\n  ".join(blushes), eyes="\n  ".join(eyes), hls="\n  ".join(hls),
        nostrils="\n  ".join(nostrils),
        mx0=128 - G["mouth_rx"], mx1=128 + G["mouth_rx"], my=G["mouth_cy"],
        mrx=G["mouth_rx"], mry=(G["mouth_up"] + G["mouth_dn"]) / 2.0,
        mouth=P["mouth"], mw=G["mouth_w"])

    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return path


# ---------------------------------------------------------------- 剪影测试
def silhouette(img, color=(0, 0, 0, 255)):
    out = Image.new("RGBA", img.size, color)
    out.putalpha(img.getchannel("A"))
    return out


# ---------------------------------------------------------------- 构建
SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_EXTRA = [16, 32, 48, 256]


def build():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    images = [draw_cow(s, MAIN_PAL, ss=8) for s in SIZES]
    ico = os.path.join(ROOT, "src", "app_icon.ico")
    images[-1].save(ico, format="ICO", sizes=[(s, s) for s in SIZES],
                    append_images=images[:-1])
    print("ICO   ->", ico)

    for s in PNG_EXTRA:
        p = os.path.join(OUT, "icon_%d.png" % s)
        images[SIZES.index(s)].save(p)
        print("PNG   ->", p)

    svg = export_svg(os.path.join(OUT, "app_icon.svg"), MAIN_PAL)
    print("SVG   ->", svg)

    # 备份另两套配色（ICO + 512 PNG，便于日后直接替换）
    for pal in BACKUP_PALS:
        imgs = [draw_cow(s, pal, ss=8) for s in SIZES]
        p_ico = os.path.join(BACKUP_DIR, "app_icon_%s.ico" % pal)
        imgs[-1].save(p_ico, format="ICO", sizes=[(s, s) for s in SIZES],
                      append_images=imgs[:-1])
        p_png = os.path.join(BACKUP_DIR, "app_icon_%s_512.png" % pal)
        draw_cow(512, pal, ss=2).save(p_png)
        print("BACKUP-> %s (%s)" % (p_ico, PALETTES[pal]["name"]))


def preview():
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    for key in PALETTES:
        im = draw_cow(512, key, ss=2)
        im.save(os.path.join(PREVIEW_DIR, "cow_v4_%s_512.png" % key))
        print("512 ->", "cow_v4_%s_512.png" % key, PALETTES[key]["name"])
    silhouette(draw_cow(256, MAIN_PAL, ss=4)).save(
        os.path.join(PREVIEW_DIR, "cow_v4_silhouette.png"))


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "preview":
        preview()
    else:
        build()

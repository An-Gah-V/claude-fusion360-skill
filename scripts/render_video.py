# Видео-презентация детали: облёт CAD-модели и (если дан скан) «схождение» скана с моделью.
# Рисуем сами на numpy, а не скриншотами Fusion: Fusion показывает сетку скана без текстуры бледной,
# почти прозрачной, и каждый кадр через него медленный.
#
# Нужно: numpy, Pillow, imageio, imageio-ffmpeg  (py -m pip install numpy pillow imageio imageio-ffmpeg)
#
# Запуск:
#   py render_video.py --stl деталь.stl --out видео.mp4 --test          5 пробных кадров PNG рядом с видео
#   py render_video.py --stl деталь.stl --out видео.mp4                 полное видео
#   ... --scan <папка с pts.f32/nrm.f32>   скан в мм, В ТОЙ ЖЕ системе координат, что и модель (выровненный)
#   ... --title "Корпус камеры" --deviation "отклонение ≈ 0,2–0,3 мм" --final "Bambu Lab H2S · STL + STEP"
#
# Модель в STL должна быть «лёгкой» (до ~50 тыс. треугольников): каждый треугольник рисуется отдельно.
# Экспортируйте STL с refinement Low/Medium. Время: со сканом ~1–2 с на кадр, 372 кадра (15.5 с) ≈ 6–12 мин;
# без скана (модель ~2 тыс. треугольников) 192 кадра (8 с) ≈ 1 мин.
import argparse, math, os, struct, sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 24
FOV = math.radians(30)
ELEV = math.radians(18)
MODEL_COL = np.array([196, 190, 178], float)  # тёплый светло-серый
SCAN_COL = np.array([60, 125, 220], float)    # синий
# Шрифты с кириллицей: Windows, macOS, Linux — берётся первый найденный
FONTS = [r'C:\Windows\Fonts\segoeui.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf',
         '/Library/Fonts/Arial Unicode.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']


def load_model(path):
    # Треугольники модели из двоичного STL: вершины (n,3,3) и нормали граней (n,3)
    data = open(path, 'rb').read()
    n = struct.unpack_from('<I', data, 80)[0]
    if 84 + 50 * n != len(data):
        sys.exit('Нужен двоичный (binary) STL — во Fusion это вариант по умолчанию.')
    rec = np.frombuffer(data, dtype=np.dtype([('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')]), count=n, offset=84)
    v = rec['v'].astype(np.float64)
    fn = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12
    if n > 50000:
        print('Внимание: %d треугольников — рендер будет медленным. Лучше экспорт с refinement Low.' % n)
    return v, fn


def load_scan(folder, max_points=3_000_000):
    pts = np.fromfile(os.path.join(folder, 'pts.f32'), dtype=np.float32).reshape(-1, 3).astype(np.float64)
    nrm = np.fromfile(os.path.join(folder, 'nrm.f32'), dtype=np.float32).reshape(-1, 3).astype(np.float64)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    if len(pts) > max_points:  # слишком плотный скан прореживаем — на картинке разницы нет
        step = int(math.ceil(len(pts) / max_points))
        pts, nrm = pts[::step], nrm[::step]
    return pts, nrm


class Scene:
    """Геометрия сцены, посчитанная по габаритам модели: центр облёта, дистанция камеры, размер «влёта» скана."""
    def __init__(self, tris):
        lo, hi = tris.reshape(-1, 3).min(axis=0), tris.reshape(-1, 3).max(axis=0)
        self.center = (lo + hi) / 2
        self.diag = float(np.linalg.norm(hi - lo))
        # FOV — угол по ширине кадра; по высоте кадр уже (~17°). С множителем 2.1 описанная сфера
        # модели занимает ~80 % высоты кадра: сама деталь меньше сферы и не заходит под подписи
        self.dist = (self.diag / 2) / math.sin(FOV / 2) * 2.1


def camera(sc, angle_deg):
    a = math.radians(angle_deg)
    eye = sc.center + sc.dist * np.array([math.cos(ELEV) * math.cos(a), math.cos(ELEV) * math.sin(a), math.sin(ELEV)])
    fwd = sc.center - eye; fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0]); right /= np.linalg.norm(right)   # «верх» — ось +Z
    up = np.cross(right, fwd)
    return eye, right, up, fwd


def light_dir(cam):
    eye, right, up, fwd = cam
    L = -fwd * 0.75 + up * 0.5 - right * 0.35     # свет «из-за плеча» камеры, сверху-слева
    return L / np.linalg.norm(L)


def render_mesh(tris, fn, base_col, cam):
    """Растеризация треугольников модели с z-буфером: чёткие грани без «зерна»."""
    eye, right, up, fwd = cam
    f = (W / 2) / math.tan(FOV / 2)
    d = tris - eye
    zc = d @ fwd
    xs = (d @ right) / zc * f + W / 2
    ys = -(d @ up) / zc * f + H / 2
    view = fn @ (-fwd)
    lam = fn @ light_dir(cam)
    lam = np.where(view < 0, -lam, lam)            # двусторонний свет: внутренние стенки тоже освещены
    shade = 0.38 + 0.62 * np.clip(lam, 0, 1)
    depth = np.full((H, W), np.inf); img = np.zeros((H, W, 3))
    for t in range(len(tris)):
        x0, x1, x2 = xs[t]; y0, y1, y2 = ys[t]
        minx, maxx = int(max(0, math.floor(min(x0, x1, x2)))), int(min(W - 1, math.ceil(max(x0, x1, x2))))
        miny, maxy = int(max(0, math.floor(min(y0, y1, y2)))), int(min(H - 1, math.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy:
            continue
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        px, py = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / den
        w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        # Глубина с учётом перспективы: линейно по экрану меняется 1/z, а не z
        z = 1.0 / (w0 / zc[t, 0] + w1 / zc[t, 1] + w2 / zc[t, 2])
        sub = depth[miny:maxy + 1, minx:maxx + 1]   # «вид» на массив: запись попадает в depth
        m = inside & (z < sub)
        sub[m] = z[m]
        img[miny:maxy + 1, minx:maxx + 1][m] = base_col * shade[t]
    return img, depth


def render_points(pts, nrm, base_col, cam):
    """Облако точек скана: каждая точка — квадрат 2x2 пикселя, в пикселе побеждает ближайшая к камере."""
    eye, right, up, fwd = cam
    d = pts - eye
    zc = d @ fwd
    f = (W / 2) / math.tan(FOV / 2)
    xs = (d @ right) / zc * f + W / 2
    ys = -(d @ up) / zc * f + H / 2
    ok = (zc > 1) & (xs >= 0) & (xs < W - 1) & (ys >= 0) & (ys < H - 1)
    xs, ys, zc, n = xs[ok].astype(np.int32), ys[ok].astype(np.int32), zc[ok], nrm[ok]
    lam = n @ light_dir(cam)
    lam = np.where(n @ (-fwd) < 0, -lam, lam)
    col = base_col[None, :] * (0.38 + 0.62 * np.clip(lam, 0, 1))[:, None]
    depth = np.full(W * H, np.inf); img = np.zeros((W * H, 3))
    # Все 4 смещения квадрата 2x2 — в один массив, и для каждого пикселя явно берём ближайшую точку.
    # (Запись в 4 прохода давала ошибку: дальняя точка следующего прохода затирала ближнюю.)
    base = ys * W + xs
    k_all = np.concatenate([base, base + 1, base + W, base + W + 1])
    z_all = np.tile(zc, 4)
    o = np.lexsort((z_all, k_all))              # сортировка по пикселю, внутри — по глубине
    ks = k_all[o]
    sel = o[np.r_[True, ks[1:] != ks[:-1]]]     # первая в группе пикселя = самая близкая
    img[k_all[sel]] = np.tile(col, (4, 1))[sel]
    depth[k_all[sel]] = z_all[sel]
    img = img.reshape(H, W, 3); depth = depth.reshape(H, W)
    # Заполняем одиночные пустоты соседом (с запасом по краям, без «заворота» кадра как у np.roll)
    for _ in range(2):
        pd = np.pad(depth, 1, constant_values=np.inf); pc = np.pad(img, ((1, 1), (1, 1), (0, 0)))
        best_d, best_c = depth.copy(), img.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            sd = pd[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]; sc = pc[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]
            m = ~np.isfinite(depth) & (sd < best_d)
            best_d[m] = sd[m]; best_c[m] = sc[m]
        depth, img = best_d, best_c
    return img, depth


def background():
    g = np.linspace(250, 222, H)[:, None, None] * np.ones((1, W, 1))
    return np.concatenate([g, g, g + 4], axis=2)


def compose(model_buf, scan_buf, alpha, tol):
    img = background()
    mi, md = model_buf
    mask_m = np.isfinite(md)
    img[mask_m] = mi[mask_m]
    if scan_buf is not None and alpha > 0:
        si, sd = scan_buf
        mask_s = np.isfinite(sd) & (~mask_m | (sd < md + tol))   # скан перед моделью или на её поверхности
        img[mask_s] = img[mask_s] * (1 - alpha) + si[mask_s] * alpha
    return img


def load_fonts():
    for path in FONTS:
        try:
            return ImageFont.truetype(path, 34), ImageFont.truetype(path, 22)
        except OSError:
            continue
    print('Внимание: шрифт с кириллицей не найден — русские подписи могут выйти квадратиками.')
    return ImageFont.load_default(), ImageFont.load_default()


def caption(img, fonts, text, sub=None, fade=1.0):
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if text:
        dr = ImageDraw.Draw(im, 'RGBA')
        a = int(255 * fade)
        dr.rectangle([40, H - 118, 48, H - 48], fill=(60, 125, 220, a))
        dr.text((62, H - 122), text, font=fonts[0], fill=(40, 40, 45, a))
        if sub:
            dr.text((63, H - 78), sub, font=fonts[1], fill=(90, 90, 100, a))
    return np.asarray(im)


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def rot_matrix(axis, ang):
    axis = np.asarray(axis, float); axis /= np.linalg.norm(axis)
    x, y, z = axis; c, s = math.cos(ang), math.sin(ang); C = 1 - c
    return np.array([[c + x*x*C, x*y*C - z*s, x*z*C + y*s],
                     [y*x*C + z*s, c + y*y*C, y*z*C - x*s],
                     [z*x*C - y*s, z*y*C + x*s, c + z*z*C]])


def timeline(a, has_scan):
    """Возвращает (длительность в с, функция t -> параметры кадра)."""
    if not has_scan:
        # Без скана: один плавный облёт на 360°
        def p(t):
            return dict(angle=200 + 360 * ease(t / 8), e=1.0, alpha=0.0, cap=(a.title, a.final), capfade=min(1, t / 0.5))
        return 8.0, p

    def p(t):
        if t < 3:      # модель одна
            return dict(angle=200 + 25 * t / 3, e=0.0, alpha=0.0, cap=(a.title, 'построена по 3D-скану'), capfade=min(1, t / 0.5))
        if t < 8:      # скан плавно проявляется, влетает и садится на модель
            u = (t - 3) / 5
            return dict(angle=225 + 20 * u, e=ease(u / 0.85), alpha=0.85 * ease((t - 3) / 0.5),
                        cap=('Совмещение скана и модели', 'синий — скан, серый — модель'), capfade=min(1, (t - 3) / 0.5))
        if t < 13:     # облёт, скан полупрозрачный поверх модели
            u = (t - 8) / 5
            return dict(angle=245 + 300 * ease(u), e=1.0, alpha=0.85 - 0.30 * ease((t - 8) / 0.5),
                        cap=('Проверка совпадения', a.deviation), capfade=min(1, (t - 8) / 0.5))
        u = (t - 13) / 2.5   # скан растворяется
        return dict(angle=545 + 15 * u, e=1.0, alpha=0.55 * (1 - ease(u)), cap=('Готово к 3D-печати', a.final), capfade=min(1, (t - 13) / 0.5))
    return 15.5, p


def scan_pose(pts, nrm, e, sc):
    # e: 0 — скан в стороне и повёрнут, 1 — точно на модели
    k = 1 - e
    if k <= 1e-6:
        return pts, nrm
    R = rot_matrix([0.3, 0.5, 0.8], math.radians(35) * k)
    off = np.array([0.55, -0.2, 0.18]) * sc.diag * k
    return (pts - sc.center) @ R.T + sc.center + off, nrm @ R.T


def frame(t, params, model, scan, sc, fonts, a):
    P = params(t)
    cam = camera(sc, P['angle'])
    mb = render_mesh(model[0], model[1], MODEL_COL, cam)
    sb = None
    if scan is not None and P['alpha'] > 0:
        sp, sn = scan_pose(scan[0], scan[1], P['e'], sc)
        sb = render_points(sp, sn, SCAN_COL, cam)
    img = compose(mb, sb, P['alpha'], a.tol)
    cap = P['cap'] if not a.no_captions else (None, None)
    return caption(img, fonts, cap[0], cap[1], P['capfade'])


def main():
    p = argparse.ArgumentParser(description='Видео-презентация модели (и совмещения со сканом).')
    p.add_argument('--stl', required=True, help='двоичный STL модели (мм)')
    p.add_argument('--out', required=True, help='путь к .mp4')
    p.add_argument('--scan', help='папка с pts.f32/nrm.f32 (мм, выровнены как модель)')
    p.add_argument('--test', action='store_true', help='только 5 пробных кадров PNG')
    p.add_argument('--title', default='CAD-модель')
    p.add_argument('--deviation', default='', help='подпись к сцене проверки, например «отклонение ≈ 0,2 мм»')
    p.add_argument('--final', default='STL + STEP', help='подпись последней сцены')
    p.add_argument('--no-captions', action='store_true')
    p.add_argument('--tol', type=float, default=0.8, help='мм: скан глубже поверхности модели на столько ещё виден')
    a = p.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)

    model = load_model(a.stl)
    scan = load_scan(a.scan) if a.scan else None
    sc = Scene(model[0])
    fonts = load_fonts()
    dur, params = timeline(a, scan is not None)
    total = int(dur * FPS)
    if a.test:
        base = os.path.splitext(a.out)[0]
        for fr in np.linspace(0.1, 0.95, 5) * total:
            path = '%s_test_%03d.png' % (base, int(fr))
            Image.fromarray(frame(fr / FPS, params, model, scan, sc, fonts, a)).save(path)
            print(path, flush=True)
        return
    import imageio.v2 as imageio
    wr = imageio.get_writer(a.out, fps=FPS, codec='libx264', quality=8, macro_block_size=8)
    for fr in range(total):
        wr.append_data(frame(fr / FPS, params, model, scan, sc, fonts, a))
        if fr % FPS == 0:
            print('кадр', fr, '/', total, flush=True)
    wr.close()
    print('готово:', a.out, os.path.getsize(a.out), 'байт')


if __name__ == '__main__':
    # Перехваченный вывод в Windows идёт в cp1251, где нет «≈» (есть в --help) — заменяем, а не падаем.
    if hasattr(sys.stdout, 'reconfigure'):  # нет консоли (pythonw) — stdout может быть None
        sys.stdout.reconfigure(errors='replace')
    main()

# Анализ 3D-скана ВНЕ Fusion (обычный Python + numpy): Fusion медленно считает сетки в миллионы
# треугольников, а numpy делает то же за секунды.
#
# Входные данные — папка с файлами, которые пишет сниппет «Выгрузка сетки» (references/snippets.md):
#   pts.f32 — координаты узлов, float32, x y z подряд, В МИЛЛИМЕТРАХ
#   nrm.f32 — нормали узлов, float32 (для команд planes/info)
#
# Команды:
#   py scan_tools.py info    <папка>                     габариты, главные оси, преобладающие направления граней
#   py scan_tools.py matrix  <папка> --x=ax,ay,az --y=bx,by,bz
#                                                        матрица выравнивания для сниппета «Выровненная копия скана»
#                                                        (пишите через «=»: так работают и оси с минусом в начале)
#   py scan_tools.py section <папка> z=30 x=0 y=-12.5    сечения в PNG с миллиметровой сеткой (можно и z30)
#   py scan_tools.py planes  <папка>                     плоские грани скана -> planes.json
#   py scan_tools.py compare <папка> <model_sections.json> [z30 x0 ...]
#                                                        наложение сечений модели на скан + отклонения
import argparse, json, math, os, sys

import numpy as np
from PIL import Image, ImageDraw


def load(folder, need_normals=False):
    pts = np.fromfile(os.path.join(folder, 'pts.f32'), dtype=np.float32).reshape(-1, 3).astype(np.float64)
    nrm = None
    p = os.path.join(folder, 'nrm.f32')
    if os.path.exists(p):
        nrm = np.fromfile(p, dtype=np.float32).reshape(-1, 3).astype(np.float64)
        L = np.linalg.norm(nrm, axis=1)
        ok = L > 1e-9
        pts, nrm = pts[ok], nrm[ok] / L[ok, None]
    elif need_normals:
        sys.exit('Нет файла nrm.f32 — выгрузите нормали вместе с точками.')
    return pts, nrm


def normal_peaks(nrm, cell=0.035, min_share=0.005, merge_deg=6.0, max_n=12, n_cand=300, cone_deg=4.0):
    """Преобладающие направления нормалей (плоские грани скана).
    1) Кандидаты: гистограмма по кубикам компонент нормали (одинаковый размер во всех направлениях;
       сетка «широта/долгота» у полюсов мельчит и теряет горизонтальные грани).
    2) Вес кандидата — доля ВСЕХ нормалей в конусе cone_deg вокруг него. Так шумная грань, чьи
       точки размазаны по нескольким соседним ячейкам, всё равно набирает свой настоящий вес.
    3) Лучшие кандидаты уточняются средним по конусу, повторы отсеиваются."""
    q = np.floor(nrm / cell).astype(np.int64) + 64            # компоненты в диапазоне 0..~121
    key = (q[:, 0] * 256 + q[:, 1]) * 256 + q[:, 2]
    uniq, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    top = np.argsort(-cnt)[:n_cand]
    sums = np.stack([np.bincount(inv, weights=nrm[:, k], minlength=len(uniq)) for k in range(3)], axis=1)
    cand = sums[top] / (np.linalg.norm(sums[top], axis=1, keepdims=True) + 1e-12)   # средняя нормаль ячейки
    ccone = math.cos(math.radians(cone_deg))
    sub = nrm[:: max(1, len(nrm) // 500000)].astype(np.float32)   # для оценки веса хватит 500 тыс. точек
    share = np.concatenate([(sub @ cand[i:i + 25].T.astype(np.float32) > ccone).mean(axis=0)
                            for i in range(0, len(cand), 25)])
    peaks = []
    cmerge = math.cos(math.radians(merge_deg))
    for i in np.argsort(-share):
        if share[i] < min_share or len(peaks) >= max_n:
            break
        d = cand[i]
        if any(d @ e > cmerge for e, _ in peaks):
            continue
        for _ in range(3):  # уточняем направление средним по конусу
            s = nrm[nrm @ d > ccone].sum(axis=0)
            d = s / np.linalg.norm(s)
        if any(d @ e > cmerge for e, _ in peaks):   # после уточнения соседи сходятся к одному направлению
            continue
        peaks.append((d, float((nrm @ d > ccone).mean())))
    return peaks


def cmd_info(a):
    pts, nrm = load(a.folder)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    size = hi - lo
    print('узлов: %d' % len(pts))
    print('габарит по осям документа, мм: %.1f x %.1f x %.1f' % tuple(size))
    print('min (%.1f %.1f %.1f)  max (%.1f %.1f %.1f)' % (*lo, *hi))
    if size.max() > 500:
        print('!! Больше 0.5 м: проверьте единицы при импорте (частая ошибка — масштаб x10).')
    # Главные оси (PCA): направления наибольшего разброса точек
    sample = pts[:: max(1, len(pts) // 200000)]
    c = sample.mean(axis=0)
    w, v = np.linalg.eigh(np.cov((sample - c).T))
    print('\nГлавные оси (PCA), от самой длинной:')
    for k in np.argsort(-w):
        ax = v[:, k]
        pr = (pts - c) @ ax
        print('  (%+.4f %+.4f %+.4f)  протяжённость %.1f мм' % (*ax, pr.max() - pr.min()))
    if nrm is not None:
        print('\nПреобладающие направления граней (нормали), доля точек:')
        for d, share in normal_peaks(nrm):
            print('  (%+.4f %+.4f %+.4f)  %.1f%%' % (*d, 100 * share))
        print('Для корпусных деталей оси выравнивания лучше брать отсюда (пары противоположных граней),')
        print('а не из PCA: грани точнее. Затем: scan_tools.py matrix --x ... --y ...')


def cmd_matrix(a):
    pts, _ = load(a.folder)
    X = np.array([float(t) for t in a.x.split(',')])
    Y = np.array([float(t) for t in a.y.split(',')])
    X /= np.linalg.norm(X)
    cosang = min(1.0, abs(float(X @ Y)) / np.linalg.norm(Y))
    if cosang > 0.87:            # меньше ~30° — оси почти параллельны (например, передали пару противоположных граней)
        sys.exit('Оси X и Y почти параллельны — выберите два разных направления граней.')
    ang = math.degrees(math.acos(cosang))
    Y = Y - (Y @ X) * X          # делаем Y строго перпендикулярным X
    Y /= np.linalg.norm(Y)
    Z = np.cross(X, Y)
    loc = pts @ np.vstack([X, Y, Z]).T
    lo, hi = loc.min(axis=0), loc.max(axis=0)
    # Новое начало: центр по X и Y, низ детали на Z = 0
    o_loc = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    R = np.vstack([X, Y, Z])       # строки — новые оси: p_new = R @ p - o_loc
    t_mm = -o_loc
    print('отклонение заданных осей от перпендикулярности: %.2f°' % (90 - ang))
    print('габарит после выравнивания, мм: %.1f x %.1f x %.1f' % tuple(hi - lo))
    print('Ось Z = X × Y. Если деталь после выравнивания окажется вверх ногами — поменяйте знак у --y.')
    cells = [R[0, 0], R[0, 1], R[0, 2], t_mm[0] / 10,
             R[1, 0], R[1, 1], R[1, 2], t_mm[1] / 10,
             R[2, 0], R[2, 1], R[2, 2], t_mm[2] / 10, 0, 0, 0, 1]
    print('\n# Матрица «мир -> выровненные оси», сдвиг в САНТИМЕТРАХ (как во Fusion API):')
    print('CELLS = [' + ','.join('%.9f' % float(v) for v in cells) + ']')


def parse_cut(s):
    # Принимаем обе записи: 'z=30' и 'z30' (как ключи в model_sections.json)
    ax, val = s.split('=') if '=' in s else (s[0], s[1:])
    return 'xyz'.index(ax.strip().lower()), float(val)


def draw_canvas(u_rng, v_rng, ppm, labels):
    umin, umax = u_rng
    vmin, vmax = v_rng
    # Защита от гигантской картинки (скан в метрах/с ошибкой масштаба): не больше ~4000 px по стороне
    ppm = min(ppm, 4000 / max(umax - umin, vmax - vmin))
    W = int((umax - umin) * ppm) + 1
    H = int((vmax - vmin) * ppm) + 1
    im = Image.new('RGB', (W, H), 'white')
    dr = ImageDraw.Draw(im)
    X = lambda u: (u - umin) * ppm
    Y = lambda v: (vmax - v) * ppm
    # Сетка: светлая каждые 5 мм, заметнее каждые 10 мм, оси — красные
    for g in range(int(math.floor(umin / 5)) * 5, int(umax) + 1, 5):
        col = (255, 150, 150) if g == 0 else ((200, 200, 230) if g % 10 == 0 else (236, 236, 246))
        dr.line([(X(g), 0), (X(g), H)], fill=col)
        if g % 10 == 0:
            dr.text((X(g) + 2, H - 12), str(g), fill=(120, 120, 160))
    for g in range(int(math.floor(vmin / 5)) * 5, int(vmax) + 1, 5):
        col = (255, 150, 150) if g == 0 else ((200, 200, 230) if g % 10 == 0 else (236, 236, 246))
        dr.line([(0, Y(g)), (W, Y(g))], fill=col)
        if g % 10 == 0:
            dr.text((2, Y(g) + 1), str(g), fill=(120, 120, 160))
    # Встроенный шрифт Pillow знает только латиницу, поэтому подпись осей — ASCII
    dr.text((W - 110, 4), 'right: %s   up: %s' % labels, fill=(120, 120, 160))
    return im, dr, X, Y


# Для сечения по оси ax рисуем две другие оси: (горизонталь, вертикаль)
UV = {0: (1, 2), 1: (0, 2), 2: (0, 1)}


def cmd_section(a):
    pts, _ = load(a.folder)
    out = a.out or a.folder
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    for s in a.cuts:
        ax, lvl = parse_cut(s)
        sl = pts[np.abs(pts[:, ax] - lvl) < a.tol]
        ui, vi = UV[ax]
        im, dr, X, Y = draw_canvas((lo[ui] - 5, hi[ui] + 5), (lo[vi] - 5, hi[vi] + 5), a.ppm, ('xyz'[ui], 'xyz'[vi]))
        px = im.load()
        for u, v in zip(X(sl[:, ui]).astype(int), Y(sl[:, vi]).astype(int)):
            if 0 <= u < im.width and 0 <= v < im.height:
                px[u, v] = (0, 0, 0)
        name = 'sec_%s%s.png' % ('xyz'[ax], ('%g' % lvl).replace('-', 'm'))
        im.save(os.path.join(out, name))
        print(os.path.join(out, name), 'точек в слое:', len(sl))


def cmd_planes(a):
    pts, nrm = load(a.folder, need_normals=True)
    c3 = math.cos(math.radians(3))
    planes = []
    for d, _ in normal_peaks(nrm, min_share=0.002, max_n=40):
        m = nrm @ d > c3
        off = pts[m] @ d
        g = pts[m][np.argsort(off)]
        off = np.sort(off)
        # Внутри одного направления разбиваем на отдельные плоскости по смещению (разрыв > 0.4 мм)
        cuts = np.where(np.diff(off) > 0.4)[0] + 1
        for idx in np.split(np.arange(len(off)), cuts):
            if len(idx) < a.min_points:
                continue
            q = g[idx]
            p2, p98 = np.percentile(q, 2, axis=0), np.percentile(q, 98, axis=0)
            planes.append({'n': [round(float(v), 4) for v in d], 'd': round(float(np.median(off[idx])), 2),
                           'points': int(len(idx)),
                           'x': [round(float(p2[0]), 1), round(float(p98[0]), 1)],
                           'y': [round(float(p2[1]), 1), round(float(p98[1]), 1)],
                           'z': [round(float(p2[2]), 1), round(float(p98[2]), 1)]})
    planes.sort(key=lambda q: -q['points'])
    path = os.path.join(a.out or a.folder, 'planes.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(planes, f, indent=1)
    print('Плоскость: n·p = d (n — единичная нормаль, d в мм). Область — 2..98 перцентиль точек.')
    print('У сканов нормали часто не согласованы: внутренняя стенка может прийти с нормалью «наружу»')
    print('и отрицательным d. Сверяйте по координатам x/y/z, где лежит грань.')
    for q in planes:
        print('n=(%+.3f %+.3f %+.3f) d=%8.2f  точек %7d  x[%6.1f %6.1f] y[%6.1f %6.1f] z[%6.1f %6.1f]' % (
            *q['n'], q['d'], q['points'], *q['x'], *q['y'], *q['z']))
    print('->', path)


def nearest_dist(a2, b2):
    """Для каждой точки a2 — расстояние до ближайшей из b2 (2D, перебором по кускам)."""
    out = np.empty(len(a2))
    b2 = b2.astype(np.float32)
    # Размер куска — от числа точек скана: временный массив chunk × len(b2) × 2 держим ~40 МБ
    chunk = max(1, int(5e6 // max(1, len(b2))))
    for i in range(0, len(a2), chunk):
        d = a2[i:i + chunk, None, :].astype(np.float32) - b2[None, :, :]
        out[i:i + chunk] = np.sqrt((d * d).sum(axis=2)).min(axis=1)
    return out


def cmd_compare(a):
    pts, _ = load(a.folder)
    with open(a.model_json, encoding='utf-8') as f:
        model = json.load(f)
    keys = a.keys or list(model.keys())
    out = a.out or a.folder
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    for k in keys:
        ax, lvl = parse_cut(k)
        ui, vi = UV[ax]
        sl = pts[np.abs(pts[:, ax] - lvl) < a.tol]
        mp = np.asarray(model[k], dtype=np.float64).reshape(-1, 3)
        im, dr, X, Y = draw_canvas((lo[ui] - 5, hi[ui] + 5), (lo[vi] - 5, hi[vi] + 5), a.ppm, ('xyz'[ui], 'xyz'[vi]))
        px = im.load()
        for u, v in zip(X(sl[:, ui]).astype(int), Y(sl[:, vi]).astype(int)):
            if 0 <= u < im.width and 0 <= v < im.height:
                px[u, v] = (0, 0, 0)
        for u, v in zip(X(mp[:, ui]).astype(int), Y(mp[:, vi]).astype(int)):
            dr.rectangle([u, v, u + 1, v + 1], fill=(230, 30, 30))
        name = 'cmp_%s.png' % k.replace('-', 'm')
        im.save(os.path.join(out, name))
        if len(sl) == 0 or len(mp) == 0:
            print(k, 'пусто: скан %d точек, модель %d' % (len(sl), len(mp)))
            continue
        dist = nearest_dist(mp[:, [ui, vi]], sl[:, [ui, vi]])
        print('%-6s модель %5d т.  отклонение от скана: медиана %.2f  90%% %.2f мм  <0.5мм %3.0f%%  >2мм %3.0f%%  -> %s' % (
            k, len(mp), np.median(dist), np.percentile(dist, 90), 100 * (dist < 0.5).mean(), 100 * (dist > 2).mean(), name))
    print('Чёрное — скан, красное — модель. Большие отклонения ищите на картинках.')


def main():
    p = argparse.ArgumentParser(description='Анализ 3D-скана, выгруженного из Fusion (мм).')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('info'); s.add_argument('folder'); s.set_defaults(fn=cmd_info)
    s = sub.add_parser('matrix'); s.add_argument('folder'); s.add_argument('--x', required=True); s.add_argument('--y', required=True); s.set_defaults(fn=cmd_matrix)
    s = sub.add_parser('section'); s.add_argument('folder'); s.add_argument('cuts', nargs='+')
    s.add_argument('--tol', type=float, default=0.3); s.add_argument('--ppm', type=float, default=6); s.add_argument('--out'); s.set_defaults(fn=cmd_section)
    s = sub.add_parser('planes'); s.add_argument('folder'); s.add_argument('--min-points', type=int, default=300); s.add_argument('--out'); s.set_defaults(fn=cmd_planes)
    s = sub.add_parser('compare'); s.add_argument('folder'); s.add_argument('model_json'); s.add_argument('keys', nargs='*')
    s.add_argument('--tol', type=float, default=0.15); s.add_argument('--ppm', type=float, default=6); s.add_argument('--out'); s.set_defaults(fn=cmd_compare)
    a = p.parse_args()
    if getattr(a, 'out', None):
        os.makedirs(a.out, exist_ok=True)
    a.fn(a)


if __name__ == '__main__':
    # Перехваченный вывод в Windows идёт в cp1251, где нет «×» и т.п. — заменяем, а не падаем.
    if hasattr(sys.stdout, 'reconfigure'):  # нет консоли (pythonw) — stdout может быть None
        sys.stdout.reconfigure(errors='replace')
    main()

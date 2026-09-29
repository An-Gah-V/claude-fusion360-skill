# Проверка STL перед 3D-печатью: замкнутость сетки, габариты, объём.
# Запуск вне Fusion:  py check_stl.py деталь.stl [ещё.stl ...]
# Понимает двоичный (binary) и текстовый (ASCII) STL. Fusion по умолчанию пишет двоичный, в мм.
import struct, sys

import numpy as np


def read_stl(path):
    data = open(path, 'rb').read()
    if len(data) >= 84:
        n = struct.unpack_from('<I', data, 80)[0]
        if 84 + 50 * n == len(data):          # размер совпал — это двоичный STL
            rec = np.frombuffer(data, dtype=np.dtype([('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')]),
                                count=n, offset=84)
            return rec['v'].astype(np.float64)
    # Иначе разбираем текстовый: строки "vertex x y z"
    vs = [list(map(float, line.split()[1:4])) for line in data.decode('utf-8', 'replace').splitlines()
          if line.strip().startswith('vertex')]
    if len(vs) % 3:
        sys.exit('%s: число вершин не кратно 3 — файл повреждён' % path)
    return np.array(vs, dtype=np.float64).reshape(-1, 3, 3)


def check(path):
    tri = read_stl(path)
    n = len(tri)
    if n == 0:
        print(path, ': треугольников нет — файл пустой или повреждён')
        return False
    # Склеиваем совпадающие вершины (с точностью 1e-4 единицы) и считаем, сколько треугольников у каждого ребра
    key = np.round(tri.reshape(-1, 3), 4)
    _, vid = np.unique(key, axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    e = np.concatenate([vid[:, [0, 1]], vid[:, [1, 2]], vid[:, [2, 0]]])
    e.sort(axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    bad = int((cnt != 2).sum())               # у замкнутой сетки каждое ребро ровно у двух треугольников
    lo, hi = tri.reshape(-1, 3).min(axis=0), tri.reshape(-1, 3).max(axis=0)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    vol = float(np.einsum('ij,ij->i', a, np.cross(b, c)).sum() / 6)   # объём через смешанное произведение
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    print(path)
    print('  треугольников: %d, вырожденных (площадь≈0): %d' % (n, int((area < 1e-9).sum())))
    print('  открытых или разветвлённых (non-manifold) рёбер: %d  %s' % (bad, '— сетка замкнута, OK' if bad == 0 else '— ЕСТЬ ДЫРЫ, слайсер может ошибиться'))
    print('  габарит: %.2f x %.2f x %.2f (единицы файла, обычно мм)' % tuple(hi - lo))
    print('  объём: %.2f (куб. единиц; в мм³ -> /1000 = см³)%s' % (abs(vol), '' if vol > 0 else '  [нормали смотрят внутрь]'))
    if (hi - lo).max() < 10:
        print('  !! Очень маленькая деталь: возможно, файл в сантиметрах, а не в мм.')
    return bad == 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Использование: py check_stl.py файл.stl [ещё.stl ...]')
    ok = all([check(p) for p in sys.argv[1:]])
    sys.exit(0 if ok else 1)

# Готовые куски кода для скриптов Fusion

Все сниппеты выполняются **внутри Fusion** через `fusion_mcp_execute` (`featureType: "script"`).
Координаты в коде — см, в выводе — мм. Все сниппеты проверены вживую (сентябрь 2026).

**Как собирать скрипт.** Берёшь шаблон из раздела 1 и вставляешь нужные куски **внутрь
`run()`**. Вспомогательные функции (`report`, `halfspace` и т.п.) можно оставлять на верхнем
уровне — это только определения. Переменные `comp` и `body` задаёшь сам, например:
`comp = comp_by_name('Cover')`, `body = comp.bRepBodies.itemByName('Cover')`.

## Содержание
1. Шаблон скрипта (проверка документа + помощники)
2. Отчёт о состоянии модели
3. Параметр: создать или взять существующий
4. Эскиз на грани и вырез насквозь
5. Рёбра по типу кривой (для скругления, фаски)
6. «Брусок-срез»: обрезать тело плоскостью n·p = d
7. Поиск микрограней (перед экспортом)
8. Сечения модели в JSON (для сравнения со сканом)
9. Выгрузка сетки скана в файлы (для scan_tools.py и render_video.py)
10. Выровненная копия скана
11. Экспорт STL и STEP
12. Кадр вида в PNG
13. Импорт сетки (STL / OBJ / 3MF) в компонент Scan

## 1. Шаблон скрипта

Почему именно так:
- **Весь рабочий код — внутри `def run(_context):`.** Коннектор хранит функции между запусками:
  если в скрипте нет своей `run`, после твоего кода вызовется `run` из **предыдущего** скрипта
  (возможно, из другого чата), и она сделает что-то своё с активным документом. Своя `run`
  её перекрывает.
- Если скрипт падает с ошибкой, Fusion **откатывает все его изменения**. Поэтому большой скрипт
  с ошибкой в конце не оставит «половину» — но и сделанное до ошибки пропадёт.
- **Печатай латиницей.** Кириллицу в выводе коннектор возвращает «кракозябрами» (UTF-8,
  прочитанный как Latin-1). Сообщения пиши по-английски, а имена, которые могут быть
  русскими (документ, компоненты), печатай через `ascii(...)` — получатся коды `\u0417...`,
  их легко прочитать. Комментарии в коде можно по-русски: они не печатаются.
- Имя у несохранённых документов — `Untitled`, таких вкладок может быть несколько, поэтому
  сверяй ещё и содержимое (компоненты, длину истории) с тем, что видел в прошлый раз.

```python
import adsk.core, adsk.fusion, math, os, tempfile

app = adsk.core.Application.get()
design = adsk.fusion.Design.cast(app.activeProduct)
root = design.rootComponent if design else None
MM = 0.1                                           # 1 мм = 0.1 см (внутренние единицы)
def P(x, y, z=0.0):                                # точка по координатам в мм
    return adsk.core.Point3D.create(x * MM, y * MM, z * MM)
def V(expr):                                       # размер строкой с единицами: V('5 mm'), V('wall*2')
    return adsk.core.ValueInput.createByString(expr)
def bb_mm(bb):
    return [round(v * 10, 2) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z,
                                        bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)]
def comp_by_name(name):
    for o in root.occurrences:
        if o.component.name == name:
            return o.component
    return None
WORK = os.path.join(tempfile.gettempdir(), 'fusion_work')   # папка обмена: её видят и Fusion, и Claude

def run(_context: str):
    if design is None:
        raise RuntimeError('Active product is not a 3D design (drawing? CAM?) - stop and ask the user')
    # Печатаем латиницей: кириллицу коннектор возвращает «кракозябрами»; имена — через ascii()
    print('doc:', ascii(app.activeDocument.name), '| open docs:', app.documents.count,
          '| timeline:', design.timeline.count if design.designType == 1 else 'none (direct modeling)',
          '| components:', ascii([o.component.name for o in root.occurrences]))
    # Ожидаемое содержимое (заполни по прошлому выводу). Не совпало — не продолжаем.
    EXPECT_COMPONENT = None                        # например 'Cover'
    if EXPECT_COMPONENT and comp_by_name(EXPECT_COMPONENT) is None:
        raise RuntimeError('No component %s - wrong active document?' % EXPECT_COMPONENT)
    os.makedirs(WORK, exist_ok=True)

    # ... здесь рабочий код (сниппеты ниже) ...
```

## 2. Отчёт о состоянии модели

Объём печатается в см³ намеренно: 1 см³ = 1 мл, по нему удобно прикидывать массу пластика.
```python
def report(comp=None):
    comps = [comp] if comp else [root] + [o.component for o in root.allOccurrences]
    for c in comps:
        for b in c.bRepBodies:
            print('  %s / %s: %s, shells %d, faces %d, vol %.3f cm3, bbox mm %s' % (
                c.name, b.name, 'solid' if b.isSolid else 'SURFACE', b.shells.count,
                b.faces.count, b.volume, bb_mm(b.boundingBox)))
    if design.designType == 1:
        tl = design.timeline
        bad = [(tl.item(i).name, tl.item(i).errorOrWarningMessage) for i in range(tl.count)
               if tl.item(i).healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState]
        print('  timeline steps:', tl.count, '| unhealthy:', ascii(bad) if bad else 'none')
# внутри run():  report()
```
Ожидай: тело `solid`, `shells 1` (иначе внутри пустоты или оторванные куски), нет проблемных шагов.

## 3. Параметр: создать или взять существующий

```python
def param(name, expr, comment=''):
    p = design.userParameters.itemByName(name)
    if p is None:
        p = design.userParameters.add(name, V(expr), 'mm', comment)
    return p
# внутри run():  param('wall', '2.9 mm', 'толщина стенки')
```
Повторный вызов с тем же именем вернёт существующий параметр и **не** изменит его значение.

## 4. Эскиз на грани и вырез насквозь

```python
body = comp.bRepBodies.itemByName('Plate')
top = max(body.faces, key=lambda f: f.centroid.z)          # верхняя грань — по геометрии, не по номеру
sk = comp.sketches.add(top); sk.name = 'Hole sketch'
c = sk.modelToSketchSpace(P(0, 0, top.centroid.z * 10))    # центр отверстия в мировых мм -> эскиз
sk.sketchCurves.sketchCircles.addByCenterRadius(c, 4 * MM)  # радиус 4 мм
prof = min(sk.profiles, key=lambda p: p.areaProperties().area)   # круг — самый маленький профиль
ei = comp.features.extrudeFeatures.createInput(prof, adsk.fusion.FeatureOperations.CutFeatureOperation)
ei.setAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)  # вглубь тела
ei.participantBodies = [body]
f = comp.features.extrudeFeatures.add(ei); f.name = 'Hole'
```
Направление (`Negative` / `Positive`) зависит от того, куда смотрит нормаль эскиза. Проверь объём
до и после — он должен уменьшиться на объём отверстия.

## 5. Рёбра по типу кривой

```python
def vertical_line_edges(body, tol=1e-6):
    """Прямые вертикальные рёбра. Проверка типа обязательна: у окружности начало == конец,
    и без неё в выборку попадают круглые кромки отверстий."""
    col = adsk.core.ObjectCollection.create()
    for e in body.edges:
        if e.geometry.curveType != adsk.core.Curve3DTypes.Line3DCurveType:
            continue
        a, b = e.startVertex.geometry, e.endVertex.geometry
        if abs(a.x - b.x) < tol and abs(a.y - b.y) < tol:
            col.add(e)
    return col

# внутри run():
edges = vertical_line_edges(body)
fi = comp.features.filletFeatures.createInput()
fi.edgeSetInputs.addConstantRadiusEdgeSet(edges, V('3 mm'), True)
comp.features.filletFeatures.add(fi).name = 'Corner fillets'
```

## 6. «Брусок-срез»: обрезать тело плоскостью

Для наклонных граней, снятых со скана: каждая грань задана как `n·p = d` (мм), всё, где
`n·p > d`, срезается. Бруски-инструменты живут в базовом элементе, поэтому потом их можно
**заменить на месте** (`bf.updateBody`) — и вся история пересчитается.
```python
def norm(v):
    L = math.sqrt(sum(c * c for c in v)); return [c / L for c in v]
def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

def halfspace(n, d, H=80.0, size=300.0, near=(0, 0, 100.0)):
    """Временный брусок толщиной H мм за плоскостью n·p = d (в сторону n). near — точка возле детали, мм."""
    L = math.sqrt(sum(c * c for c in n)); n = [c / L for c in n]; d = d / L
    a = norm(cross(n, [0, 0, 1])) if abs(n[2]) < 0.9 else norm(cross(n, [1, 0, 0]))
    b = cross(n, a)
    t = d - sum(n[k] * near[k] for k in range(3))
    c = [near[k] + t * n[k] + n[k] * H / 2 for k in range(3)]
    obb = adsk.core.OrientedBoundingBox3D.create(P(*c), adsk.core.Vector3D.create(*a),
                                                 adsk.core.Vector3D.create(*b), size * MM, size * MM, H * MM)
    return adsk.fusion.TemporaryBRepManager.get().createBox(obb)

CUTS = {'Right slope': ((0.926, 0.0, 0.377), 68.44)}      # имя: (нормаль, d в мм)

# внутри run():
target = comp.bRepBodies.itemByName('Cover')
bf = comp.features.baseFeatures.add(); bf.name = 'Slope tools'
bf.startEdit()
for name, (n, d) in CUTS.items():
    comp.bRepBodies.add(halfspace(n, d), bf).name = name
bf.finishEdit()
tools = adsk.core.ObjectCollection.create()
for name in CUTS:
    tools.add(comp.bRepBodies.itemByName(name))
ci = comp.features.combineFeatures.createInput(target, tools)
ci.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
ci.isKeepToolBodies = False
comp.features.combineFeatures.add(ci).name = 'Slopes'

# Позже — поправить плоскости на месте (например, сделать парные грани симметричными):
# bf = comp.features.baseFeatures.itemByName('Slope tools'); bf.startEdit()
# for b in list(bf.bodies): bf.updateBody(b, halfspace(*CUTS[b.name]))
# bf.finishEdit()
```
Брусок должен перекрывать всё, что надо срезать: `size` (300 мм) — по ширине и длине, `H`
(80 мм) — по глубине за плоскостью. Деталь крупнее — увеличь оба.

## 7. Поиск микрограней

Грани шириной в сотые доли мм — следы неточно совпавших плоскостей. Слайсер их обычно не
видит, но они признак ошибки в построении и мешают дальнейшим операциям.
```python
faces = sorted(body.faces, key=lambda f: f.area)
for f in faces[:10]:
    p = f.pointOnFace
    per = sum(e.length for e in f.edges) * 10           # периметр, мм
    a = f.area * 100                                     # площадь, мм²
    print('face %.3f mm2, width ~%.2f mm at (%.1f %.1f %.1f)' % (a, 2 * a / per, p.x*10, p.y*10, p.z*10))
```
Ширина < 0.1 мм — повод разобраться: обычно две поверхности почти, но не точно совпали.
Лечится построением «по собственным граням» (одна и та же плоскость для обеих операций).

## 8. Сечения модели в JSON

Для `scan_tools.py compare`. Ключи: `z30` — плоскость Z = 30 мм, `x-9` — X = −9 мм и т.д.
```python
import json
def sample_edge(e, step_mm=0.1):
    n = max(2, int(e.length * 10 / step_mm))
    if e.geometry.curveType == adsk.core.Curve3DTypes.Line3DCurveType and e.startVertex and e.endVertex:
        a, b = e.startVertex.geometry, e.endVertex.geometry
        return [(a.x + (b.x-a.x)*s/n, a.y + (b.y-a.y)*s/n, a.z + (b.z-a.z)*s/n) for s in range(n + 1)]
    ev = e.evaluator
    ok, t0, t1 = ev.getParameterExtents()
    eps = (t1 - t0) * 1e-6                     # ровно на краю getPointAtParameter падает
    out = []
    for s in range(n + 1):
        ok, p = ev.getPointAtParameter(t0 + eps + (t1 - t0 - 2*eps) * s / n)
        if ok:
            out.append((p.x, p.y, p.z))
    return out

# внутри run():
tbm = adsk.fusion.TemporaryBRepManager.get()
res = {}
for key in ['z30', 'z60', 'x0', 'y0']:
    ax, lvl = key[0], float(key[1:]) * MM
    o = adsk.core.Point3D.create(lvl if ax == 'x' else 0, lvl if ax == 'y' else 0, lvl if ax == 'z' else 0)
    nrm = adsk.core.Vector3D.create(float(ax == 'x'), float(ax == 'y'), float(ax == 'z'))
    wire = tbm.planeIntersection(body, adsk.core.Plane.create(o, nrm))
    pts = []
    if wire:
        for e in wire.edges:
            pts += [[round(c * 10, 3) for c in p] for p in sample_edge(e)]
    res[key] = pts
with open(os.path.join(WORK, 'model_sections.json'), 'w') as f:
    json.dump(res, f)
print({k: len(v) for k, v in res.items()}, '->', WORK)
```

## 9. Выгрузка сетки скана в файлы

Пишет `pts.f32` и `nrm.f32` (float32; координаты в **мм**) для `scripts/scan_tools.py` и
`render_video.py`. 2 млн узлов — ~48 МБ и несколько секунд. Координаты берутся в системе своего
компонента, поэтому вхождение компонента `Scan` держи в начале координат (не двигай его).
```python
import array
def mesh_by_name(comp, name):
    for m in comp.meshBodies:              # у MeshBodies нет itemByName
        if m.name == name:
            return m
    return None

# внутри run():
c = comp_by_name('Scan') or root           # скан в компоненте Scan (сниппет 13), иначе — в корне
mb = mesh_by_name(c, 'Scan aligned') or c.meshBodies.item(0)   # выровненная копия, а до неё — исходник
if mb is None:
    raise RuntimeError('Mesh not found')
mesh = mb.mesh
OUT = os.path.join(WORK, 'scan')
os.makedirs(OUT, exist_ok=True)
for name, arr in (('pts.f32', array.array('f', (v * 10 for v in mesh.nodeCoordinatesAsDouble))),
                  ('nrm.f32', array.array('f', mesh.normalVectorsAsDouble))):
    with open(os.path.join(OUT, name), 'wb') as f:
        arr.tofile(f)
print(ascii(mb.name), 'nodes', mesh.nodeCount, 'triangles', mesh.triangleCount, 'bbox mm', bb_mm(mb.boundingBox), '->', OUT)
```

## 10. Выровненная копия скана

Импортированную сетку сдвинуть не удалось, поэтому создаём **копию** в новых осях.
`CELLS` — из `scan_tools.py matrix` (16 чисел по строкам, сдвиг в см).
```python
CELLS = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]      # подставь матрицу из scan_tools.py matrix

# внутри run():
comp = comp_by_name('Scan') or root
src = comp.meshBodies.item(0)
mesh = src.mesh
xyz, nrm, idx = mesh.nodeCoordinatesAsDouble, mesh.normalVectorsAsDouble, mesh.triangleNodeIndices
r = CELLS
n = len(xyz) // 3
out, outn = [0.0] * (3 * n), [0.0] * (3 * n)
for i in range(n):                                  # точки: поворот + сдвиг; нормали: только поворот
    x, y, z = xyz[3*i], xyz[3*i+1], xyz[3*i+2]
    out[3*i], out[3*i+1], out[3*i+2] = (r[0]*x + r[1]*y + r[2]*z + r[3],
                                         r[4]*x + r[5]*y + r[6]*z + r[7],
                                         r[8]*x + r[9]*y + r[10]*z + r[11])
    x, y, z = nrm[3*i], nrm[3*i+1], nrm[3*i+2]
    outn[3*i], outn[3*i+1], outn[3*i+2] = (r[0]*x + r[1]*y + r[2]*z,
                                            r[4]*x + r[5]*y + r[6]*z,
                                            r[8]*x + r[9]*y + r[10]*z)
bf = comp.features.baseFeatures.add()
bf.startEdit()
comp.meshBodies.addByTriangleMeshData(out, idx, outn, idx)
bf.finishEdit()
bf.name = 'Aligned scan'
src.name = 'Scan original'; src.isLightBulbOn = False           # оригинал прячем, не удаляем
# Новое тело ищем заново: ссылка, полученная внутри startEdit/finishEdit, после finishEdit
# может указывать на объект внутри базового элемента, а не на тело в компоненте.
new = [m for m in comp.meshBodies if m.name != 'Scan original'][-1]
new.name = 'Scan aligned'
print('aligned scan bbox mm:', bb_mm(new.boundingBox))    # ждём: центр по X/Y, низ на Z = 0
```
После — `screenshot`: деталь стоит как надо, не вверх ногами? Если перевёрнута — поменяй знак
у `--y` в `scan_tools.py matrix` и повтори (лишнюю копию убери через `undo`).

## 11. Экспорт STL и STEP

```python
# внутри run():
DIR = r'C:\Projects\имя-проекта'          # папка проекта пользователя (пример); не AppData\Roaming\Claude
os.makedirs(DIR, exist_ok=True)
em = design.exportManager
so = em.createSTLExportOptions(body, os.path.join(DIR, 'part.stl'))
so.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh   # для печати; для видео — Low/Medium отдельным файлом
so.isBinaryFormat = True
print('stl', em.execute(so))
print('step', em.execute(em.createSTEPExportOptions(os.path.join(DIR, 'part.step'), comp)))
```
После экспорта — снаружи: `py <scripts>\check_stl.py C:\Projects\имя-проекта\part.stl`.

## 12. Кадр вида в PNG

Для картинок с нужного ракурса и размера (обычный `screenshot` коннектора проще, если его хватает).
Масштаб задавай явно (`viewExtents`, в см — примерно 1.2–1.5 габарита детали): иначе камера
унаследует масштаб прошлого вида, и деталь может выйти крошечной точкой. Альтернатива —
`cam.isFitView = True` (Fusion сам впишет модель, но впритык к краям).
```python
# внутри run():
vp = app.activeViewport
old_cam = vp.camera                          # копия, чтобы вернуть
cam = vp.camera
cam.cameraType = adsk.core.CameraTypes.PerspectiveCameraType
cam.target = P(0, 0, 5)                      # центр детали, мм
cam.eye = P(-120, -160, 130)                 # откуда смотрим, мм
cam.upVector = adsk.core.Vector3D.create(0, 0, 1)
cam.isFitView = False
cam.viewExtents = 8.0                        # см; для детали 60 мм — с запасом
cam.isSmoothTransition = False
vp.camera = cam                              # присвоить обратно обязательно
vp.refresh(); adsk.doEvents()
print(vp.saveAsImageFile(os.path.join(WORK, 'view.png'), 1280, 720))
vp.camera = old_cam
print('pending snapshot:', design.snapshots.hasPendingSnapshot)   # должно быть False
```

## 13. Импорт сетки в компонент Scan

Когда пользователь даёт файл скана (STL, OBJ, 3MF). В параметрическом документе сетка
добавляется только внутри базового элемента.
```python
# внутри run():
PATH = r'C:\Projects\имя-проекта\scan.stl'
UNITS = adsk.fusion.MeshUnits.MillimeterMeshUnit    # единицы файла; ошибся — габарит будет в 10 раз не тот
occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())   # вхождение в начале координат
sc = occ.component; sc.name = 'Scan'
bf = sc.features.baseFeatures.add()
bf.startEdit()
lst = sc.meshBodies.add(PATH, UNITS, bf)            # возвращает список сеток (у OBJ их может быть несколько)
bf.finishEdit()
bf.name = 'Scan import'
mb = sc.meshBodies.item(0)
print('meshes:', lst.count if lst else None, '| nodes', mb.mesh.nodeCount, 'triangles', mb.mesh.triangleCount,
      '| bbox mm', bb_mm(mb.boundingBox))
```
Сверь габарит с реальной деталью (см. `reverse-engineering.md`, шаг 0).

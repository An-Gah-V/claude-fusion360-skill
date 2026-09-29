# Ловушки Fusion API

Всё ниже получено на практике: ошибки, которые реально случились, и проверенный правильный
вариант. Если нужного здесь нет — `fusion_mcp_read` → `apiDocumentation` с `searchPattern`.

## Содержание
0. Запуск скриптов через коннектор
1. Общее
2. Сетки (mesh) — сканы, импортированные STL/OBJ
3. История (timeline)
4. Эскизы, профили, выбор граней и рёбер
5. Операции (features)
6. Кривые и сечения
7. Экспорт
8. Вид, камера, внешний вид

## 0. Запуск скриптов через коннектор

Проверено вживую, это самое важное:
- **Весь рабочий код — внутри `def run(_context: str):`.** Коннектор хранит функции между
  запусками и после кода скрипта вызывает `run`. Если своей `run` нет, вызовется **чужая**,
  оставшаяся от предыдущего скрипта (в том числе из другого чата), и выполнит свои действия над
  активным документом. Симптомы: в выводе чужие строки (например `ok`), или ошибка вида
  `File "<string>", line 34, in run ... IndexError`, хотя в твоём скрипте нет строки 34.
- **Ошибка откатывает весь скрипт.** Если скрипт завершился исключением (твоим или чужой `run`),
  Fusion отменяет все его изменения. Вывод `print()` при этом приходит — не принимай его за
  успех: смотри на `success`.
- **Вывод — латиницей.** Кириллицу коннектор возвращает «кракозябрами» (UTF-8, прочитанный как
  Latin-1), и в успешном ответе, и в ошибке. Сообщения печатай по-английски, имена, которые
  могут быть русскими, — через `ascii(name)` (получатся коды `\u0417...`).
- `readOnly: true` — для скриптов, которые только читают; попытка что-то изменить в таком
  скрипте завершится ошибкой.
- Создание и закрытие документа не откатываются: документ, созданный в упавшем скрипте, остаётся
  открытым. Закрыть — `fusion_mcp_execute` с `featureType: "document"`,
  `object: {"operation": "close", "userConfirmedCloseWithoutSave": true}` (закрывает активный
  документ; флаг — только с согласия пользователя).

## 1. Общее

- `adsk.fusion.Design.cast(app.activeProduct)` вернёт `None`, если активна не модель
  (например, чертёж или рабочая среда CAM). Проверяй.
- `design.designType`: `1` — параметрический (с историей), `0` — прямой (без истории, timeline
  недоступен).
- Многие `add(...)` при неудаче возвращают `None` **без исключения**. Проверяй результат, прежде
  чем писать `feature.name = ...` (иначе `'NoneType' object has no attribute 'name'`).
- Коллекции можно перебирать `for b in comp.bRepBodies:`, а можно `item(i)` / `count`.
- Длины в см, углы в радианах. `ValueInput.createByReal(x)` — в см; `createByString('5 mm')` —
  с единицами.

## 2. Сетки (mesh)

| Неправильно | Правильно |
|---|---|
| `mesh.nodeIndices` | `mesh.triangleNodeIndices` (плоский список, по 3 индекса на треугольник) |
| `comp.meshBodies.itemByName(n)` — такого метода нет | перебор: `[m for m in comp.meshBodies if m.name == n]` |
| `lst = meshBodies.addByTriangleMeshData(...)`, затем `lst.count` | метод возвращает **одно** `MeshBody` |
| `occurrence.opacity` — нет такого свойства | прозрачность — у тела: `mesh_body.opacity = 0.5` |
| `mesh_body.visibleOpacity` у тела внутри компонента → RuntimeError | нужен «прокси» с контекстом сборки: `mesh_body.createForAssemblyContext(occ).visibleOpacity` |

- Импорт файла сетки: `comp.meshBodies.add(путь, adsk.fusion.MeshUnits.MillimeterMeshUnit, base_feature)`
  между `bf.startEdit()` и `bf.finishEdit()`; возвращает **список** (`MeshBodyList`) — у OBJ сеток
  может быть несколько. Сниппет 13.
- Данные сетки: `mb.mesh.nodeCoordinatesAsDouble` (x, y, z подряд, **см**),
  `normalVectorsAsDouble`, `triangleNodeIndices`, `triangleCount`, `nodeCount`.
- Новая сетка в параметрическом документе создаётся внутри базового элемента:
  `bf = comp.features.baseFeatures.add(); bf.startEdit(); comp.meshBodies.addByTriangleMeshData(coords, idx, normals, idx); bf.finishEdit()`.
- **Импортированную сетку не удалось сдвинуть** ни `moveFeatures` (вернул `None`), ни поворотом
  компонента (положение сбрасывалось). Рабочий путь — создать выровненную **копию**: пересчитать
  координаты и нормали матрицей и добавить новой сеткой (сниппет «Выровненная копия скана»).
  Оригинал спрятать (`isLightBulbOn = False`), не удалять.
- `mesh_body.baseOrFormFeature` для сетки после переноса в компонент вернул `None` — не полагайся.
- Сетка в миллионы треугольников: перебор в Python внутри Fusion — десятки секунд. Считай
  снаружи: выгрузи точки в файл и анализируй `scripts/scan_tools.py`.
- Нормали узлов у скана могут быть **не согласованы** (часть смотрит внутрь). Не делай выводов
  «наружу/внутрь» по знаку нормали без проверки по положению точки.

## 3. История (timeline)

| Неправильно | Правильно |
|---|---|
| `timeline.item(i).deleteMe()` → нет такого метода | `timeline.item(i).entity.deleteMe()` |

- Здоровье шагов: `tl.item(i).healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState`
  — это проблемный шаг; текст ошибки — `tl.item(i).errorOrWarningMessage`.
- Изменение `occurrence.transform2` в параметрическом документе создаёт отложенный «снимок
  положения» (`design.snapshots.hasPendingSnapshot == True`), а при фиксации — шаг «Position» в
  истории. Для временных сдвигов (кадры для видео) верни матрицу обратно и проверь, что снимка
  нет. Лишние шаги Position удаляются через `.entity.deleteMe()`.
- Правка существующего шага пересчитывает всё после него. Пример: у выдавливания
  `adsk.fusion.DistanceExtentDefinition.cast(f.extentOne).distance.expression = 'recess_top - recess_z'`.
- Базовый элемент (base feature) можно отредактировать и заменить тела-инструменты на месте:
  `bf.startEdit(); bf.updateBody(старое_тело, новое_временное_тело); bf.finishEdit()` — все
  Combine, использующие эти тела, пересчитаются. Так одним скриптом правились 33 места истории.

## 4. Эскизы, профили, выбор граней и рёбер

- Оси эскиза на XZ и YZ перевёрнуты по Z — см. `coordinates.md`. Надёжно:
  `sk.modelToSketchSpace(Point3D_мира)`.
- Порядок `sketch.profiles` не гарантирован. Нужный профиль выбирай по площади
  (`p.areaProperties().area`) или по числу петель (`p.profileLoops.count`: кольцо = 2 петли).
- Грань по геометрии: верхняя — `max(body.faces, key=lambda f: f.centroid.z)`; нормаль —
  `f.evaluator.getNormalAtPoint(f.pointOnFace)` → `(ok, vector)`.
- **Рёбра по типу кривой.** У окружности начальная и конечная вершины совпадают, поэтому
  проверка «x и y начала равны x и y конца» ловит и круглые кромки отверстий — так скругление
  легло не туда. Сначала `e.geometry.curveType == adsk.core.Curve3DTypes.Line3DCurveType`, потом
  направление.

## 5. Операции (features)

- Быстрое выдавливание: `extrudeFeatures.addSimple(profile, ValueInput, FeatureOperations.NewBodyFeatureOperation)`.
- Вырез насквозь: `ei = extrudeFeatures.createInput(profile, CutFeatureOperation)`,
  `ei.setAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)` (направление — от
  плоскости эскиза), `ei.participantBodies = [body]`, затем `add(ei)`.
- Скругление: `fi = filletFeatures.createInput()`,
  `fi.edgeSetInputs.addConstantRadiusEdgeSet(edges, ValueInput.createByString('3 mm'), True)`.
- Булевы операции: `ci = combineFeatures.createInput(цель, ObjectCollection_инструментов)`,
  `ci.operation = CutFeatureOperation` / `JoinFeatureOperation`, `ci.isKeepToolBodies = False`.
- Тело из временной геометрии: `tbm = adsk.fusion.TemporaryBRepManager.get()`,
  `tbm.createBox(OrientedBoundingBox3D)`, `tbm.createCylinderOrCone(p1, r1, p2, r2)`; в документ —
  `comp.bRepBodies.add(temp_body, base_feature)` между `bf.startEdit()` и `bf.finishEdit()`.
- Сдвиг тел: `mi = moveFeatures.createInput2(collection); mi.defineAsFreeMove(matrix)`.
- Параметр: `design.userParameters.add('wall', ValueInput.createByString('2.9 mm'), 'mm', 'комментарий')`;
  если уже есть — `itemByName('wall')` вернёт его (при повторном add будет ошибка).

## 6. Кривые и сечения

| Неправильно | Правильно |
|---|---|
| `evaluator.getStrokes(0.002)` | `getStrokes(fromParameter, toParameter, tolerance)` — три аргумента |
| `getPointAtParameter(t0)` ровно на краю диапазона → `invalid argument parameter` | отступить на ε: `t0 + (t1-t0)*1e-6`; для отрезков брать вершины |

- Сечение тела плоскостью: `TemporaryBRepManager.get().planeIntersection(body, adsk.core.Plane.create(точка, нормаль))`
  → временное тело из рёбер (`wire.edges`, `wire.vertices`). Сниппет «Сечения модели в JSON».

## 7. Экспорт

- `em = design.exportManager`
- STL: `so = em.createSTLExportOptions(body_или_компонент, путь)`;
  `so.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh` (Medium/Low для
  лёгких файлов); `so.isBinaryFormat = True`; `em.execute(so)` → `True`.
- STEP: `em.execute(em.createSTEPExportOptions(путь, component))`.
- Путь — в папку, которую видит Fusion (правило 8 в SKILL.md).

## 8. Вид, камера, внешний вид

- Кадр в файл: `vp = app.activeViewport; vp.refresh(); adsk.doEvents(); vp.saveAsImageFile(путь, 1280, 720)`.
- Камера: `cam = vp.camera` (копия!), поменять `eye`, `target`, `upVector`, `cameraType`,
  `cam.isSmoothTransition = False`, затем **присвоить обратно** `vp.camera = cam`.
- **Масштаб задавай явно**: `cam.isFitView = False; cam.viewExtents = <см>` (≈1.2–1.5 габарита
  детали) или `cam.isFitView = True` (впишет впритык). Без этого камера наследует масштаб
  прошлого вида — в новом документе деталь вышла крошечной точкой в центре кадра.
- Внешний вид из библиотеки: сначала скопировать в документ —
  `design.appearances.addByCopy(lib.appearances.itemByName(имя), имя)`, потом `body.appearance = ap`.
  Библиотека: `[l for l in app.materialLibraries if 'Appearance' in l.name][0]`.
- Сетку без текстуры Fusion рисует бледной, почти прозрачной — для презентаций со сканом
  используй `scripts/render_video.py` (см. `presentation.md`).

# Ловушки Fusion API

Всё ниже получено на практике: ошибки, которые реально случились, и проверенный правильный
вариант. Если нужного здесь нет — `fusion_mcp_read` → `apiDocumentation` с `searchPattern`.

Исключение — пункты с пометкой **(чужой опыт)**: они взяты из открытых проектов
[fusion-agent-kit](https://github.com/Chocksy/fusion-agent-kit) (`references/gotchas.md`) и
[fusion-cad-mcp](https://github.com/Mfrostbutter/fusion-cad-mcp) (оба MIT) и у нас вживую ещё
не проверены. Доверяй им как подсказке; подтвердился — поменяй пометку на «проверено <дата>»,
не подтвердился — исправь или удали пункт. Пункты с пометкой **(проверено 12.10.2026)** пришли оттуда же и подтверждены у нас
(Fusion 2705.1.25, несохранённый пробный документ), часто с уточнениями. Пункты с другими
датами (**проверено 25.10.2026** и позже) — наш собственный опыт на реальных проектах.

## Содержание
0. Запуск скриптов через коннектор
1. Общее
2. Сетки (mesh) — сканы, импортированные STL/OBJ
3. История (timeline), сборка из компонентов, копии тел
4. Эскизы, профили, выбор граней и рёбер
5. Операции (features)
6. Кривые и сечения
7. Экспорт
8. Вид, камера, внешний вид

## 0. Запуск скриптов через коннектор

Самое важное (пункты без пометки проверены вживую):
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
- **(чужой опыт)** `document.save()` и `saveAs()` из скрипта через MCP не срабатывают. Сохранить
  попроси пользователя (Ctrl+S); если нужен файл модели — экспорт `.f3d`
  (`em.createFusionArchiveExportOptions(путь)`).
- **(чужой опыт)** Речь о файлах на диске, не о тексте скрипта, который передаёшь коннектору
  (в нём русские комментарии можно). Свои модули-помощники, которые скрипт импортирует, держи
  только латиницей; файлы данных открывай с `open(..., encoding='utf-8')` — иначе Python внутри
  Fusion может читать их как ASCII и падать на кириллице.
- **(проверено 25.10.2026) Кириллица в строках самого скрипта тоже портится** — комментарии
  безвредны, а строковые литералы нет. Путь `r'D:\Модели\...'` → `FileNotFoundError` с
  кракозябрами; `comp.name = 'Сборка'` дал имя-кракозябру. Даже запись `'\u0421...'` (одна
  латиница!) дала кракозябру — видимо, коннектор раскрывает `\u` ещё до Python; надёжен
  только hex. Что делать:
  - большой скрипт держи **файлом на диске** (в папке проекта, в git) и запускай коротким
    скриптом: `g = {'__name__': 'x'}; exec(open(r'<папка проекта>\scripts\имя\имя.py', encoding='utf-8').read(), g); g['run']('')`.
    Путь в этой строке — тоже литерал: только латиницей (или hex). Сам файл читается
    без коннектора, кириллица внутри него безопасна. Чтобы файл запускался ещё и из меню
    Fusion (Utilities → Scripts and Add-Ins), он должен лежать в своей папке с тем же именем:
    `scripts\имя\имя.py`;
  - русские имена в коде — UTF-8 hex: `bytes.fromhex('d0a1d0b1...').decode('utf-8')`
    (hex получить: `py -c "print('Сборка'.encode().hex())"`);
  - уже испорченное имя чинится: `s.encode('latin-1').decode('utf-8')`.
  Ищи имена компонентов и тел по `name ==`, только если имя пришло из модели, а не из текста
  скрипта.

## 1. Общее

- `adsk.fusion.Design.cast(app.activeProduct)` вернёт `None`, если активна не модель
  (например, чертёж или рабочая среда CAM). Проверяй.
- `design.designType`: `1` — параметрический (с историей), `0` — прямой (без истории, timeline
  недоступен).
- Многие `add(...)` при неудаче возвращают `None` **без исключения**. Проверяй результат, прежде
  чем писать `feature.name = ...` (иначе `'NoneType' object has no attribute 'name'`).
- Коллекции можно перебирать `for b in comp.bRepBodies:`, а можно `item(i)` / `count`.
- **(проверено 12.10.2026) `deleteMe()` тела.** Проверяли один случай: удаляли **исходное** тело
  массива (то, из которого массив построен). Итог: исключения нет, но и тело не удалилось —
  ни шага в истории, число тел то же. При этом ссылки, полученные до вызова, на это тело и на все
  копии массива стали недействительными (`isValid == False`); ссылка на несвязанное тело
  осталась рабочей. Что вернул сам `deleteMe()`, не смотрели. Поэтому: перед каждым удалением
  заново собирай список из `comp.bRepBodies`, проверяй, что вернул `deleteMe()`, а после —
  сверяй `comp.bRepBodies.count`.
- **(проверено 12.10.2026)** В несохранённом документе корневой компонент не переименовывается:
  `root.name = ...` → `root component name cannot be changed`. Сработает ли после сохранения —
  не проверяли (по данным fusion-agent-kit — да).
- **(проверено 12.10.2026)** `importManager.importToTarget2(...)` в несохранённом документе
  падает (`InternalValidationError : pResult`). По данным fusion-agent-kit работает
  `importToNewDocument(...)` — но он создаёт **новый документ** (вкладку): только с согласия
  пользователя, и после него проверь, какой документ активен (правило 2 в SKILL.md).
- **(проверено 25.10.2026)** В **сохранённом** документе `importToTarget2(createSTEPImportOptions(путь), root)`
  работает: каждый STEP становится новым компонентом с именем файла. Та же ошибка
  `InternalValidationError : pResult` была у одного файла — с **«+» в имени**
  (вида «деталь + крышка.step»). Обход: скопировать файлы во временную папку под
  латинскими именами (`part0.step`…), импортировать оттуда и переименовать новые компоненты
  обратно (новые вхождения — те, чьих `entityToken` не было до импорта). Ошибка откатывает весь
  скрипт, поэтому импортируй всё одним скриптом только после пробы.
- Длины в см, углы в радианах. `ValueInput.createByReal(x)` — в см; `createByString('5 mm')` —
  с единицами.
- **(проверено 25.10.2026) Пересечения:** `ii = design.createInterferenceInput(тела)`,
  `ii.areCoincidentFacesIncluded = False`, `design.analyzeInterference(ii).count`. С `False`
  касание «впритык» (общая грань, зазор 0) **не считается** пересечением — так прошёл
  незамеченным упор торца штыря в дно гнезда, и байонет у напечатанных деталей не
  поворачивался. С `True` поймаешь зазор ровно 0, но не зазор 0.1 мм там, где нужен 1 мм.
  Зазоры у посадок проверяй отдельно — `print-export.md`, «Проверка посадок» (сниппет 16).

## 2. Сетки (mesh)

| Неправильно | Правильно |
|---|---|
| сетка-скан (`mesh_body.mesh`, `PolygonMesh`): `.nodeIndices` | `.triangleNodeIndices` (плоский список, по 3 индекса на треугольник) |
| сетка из тела (`body.meshManager.createMeshCalculator().calculate()`, `TriangleMesh`): `.triangleNodeIndices` | здесь наоборот `.nodeIndices` — сниппет 15 |
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
- Операции сетки (face groups, convert, separate) — **preview API**, могут измениться. Подробности и
  статус проверки — `reverse-engineering.md`, раздел 6.
- Нормали узлов у скана могут быть **не согласованы** (часть смотрит внутрь). Не делай выводов
  «наружу/внутрь» по знаку нормали без проверки по положению точки.

## 3. История (timeline), сборка из компонентов, копии тел

| Неправильно | Правильно |
|---|---|
| `timeline.item(i).deleteMe()` → нет такого метода | `timeline.item(i).entity.deleteMe()` |

- Здоровье шагов: `tl.item(i).healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState`
  — это проблемный шаг; текст ошибки — `tl.item(i).errorOrWarningMessage`.
- Изменение `occurrence.transform2` в параметрическом документе создаёт отложенный «снимок
  положения» (`design.snapshots.hasPendingSnapshot == True`), а при фиксации — шаг «Position» в
  истории. Для временных сдвигов (кадры для видео) верни матрицу обратно и проверь, что снимка
  нет. Лишние шаги Position удаляются через `.entity.deleteMe()`.
- **(проверено 25.10.2026) Компонент внутри компонента (сборка).**
  - `parent_comp.occurrences.addNewComponent(матрица)` — положение **относительно родителя**.
  - Менять положение уже вложенного вхождения: `occ.transform2 = m` у «родного» вхождения →
    `transform overrides can only be set on Occurrence proxy from root component`. Нужен прокси:
    `p = occ.createForAssemblyContext(parent_occ); p.transform2 = m` — и тогда матрица
    **в мировых координатах**, а не от родителя (деталь встала внахлёст с соседней: сдвиг на 200 мм от
    начала мира вместо 200 мм от сборки). После — `design.snapshots.add()`, если
    `hasPendingSnapshot`.
  - Видимость у прокси и у «родного» вхождения своя: `p.isLightBulbOn` может быть `True`
    (на экране видно), а `occ.isLightBulbOn` — `False`. Экспорт компонента смотрит на «родную»
    (см. раздел 7).
  - `addExistingComponent(comp, матрица)` — ещё одно вхождение того же компонента: правка
    компонента видна во всех вхождениях (три одинаковые секции — один компонент).
- **(проверено 25.10.2026) Копия тела из другого компонента:** `comp.features.copyPasteBodies.add(тело_или_прокси)`
  (это коллекция, `copyPasteBodies(...)` → `object is not callable`). Копия связана с исходником
  (правки исходного тела приходят в копию), но встаёт **в мировом положении исходника**: в
  компоненте, вложенном со сдвигом, она оказалась сдвинута на минус этот сдвиг. Сразу после
  `add` проверь `boundingBox` копии и при нужде сдвинь `moveFeatures` (`defineAsFreeMove`).
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
- **(проверено 12.10.2026) Массив тел (pattern).** Новые тела называются `Имя (1)`, `Имя (2)`…;
  бери их из `pattern_feature.bodies`, а не ищи по имени. Учти: в `pattern_feature.bodies`
  входит и **исходное** тело (оно было последним). И ещё: вызов
  `rectangularPatternFeatures.createInput(тела, ось, V('3'), V('15 mm'), SpacingPatternDistanceType)`
  (`V` = `ValueInput.createByString`) дал **9** тел вместе с исходным (3×3), а не 3 — второе
  направление включилось само. Нужен ряд в одну сторону — задай второе количество явно
  (`pi.quantityTwo = V('1')`, не проверяли) и сверь число тел.
- **(чужой опыт)** Combine с большим числом тел-инструментов — частями, примерно по 20 тел.
- **(чужой опыт)** Рёбра жёсткости (Rib) из скрипта не создаются — в API они только для чтения.
  Делай ребро тонким выдавливанием с `JoinFeatureOperation`.
- **(проверено 12.10.2026) Резьба настоящей геометрией** (для печати; без `isModeled` она только
  «нарисована» на цилиндре). `tf = comp.features.threadFeatures`:
  1. Размеры — только стандартные, строками из справочника: `q = tf.threadDataQuery`;
     `q.allThreadTypes` (метрическая — `'ISO Metric profile'`), `q.allSizes(тип)` — размеры вида
     **`'10.0'`** (не `'10'`: с ним `allDesignations` падает `cannot get all the designations`),
     `q.allDesignations(тип, '10.0')` → `'M10x1.5'`, `'M10x1.25'`…,
     `q.allClasses(внутренняя?, тип, обозначение)` → `'6g'` (наружная) и т.п.
  2. `info = tf.createThreadInfo(внутренняя?, тип, обозначение, класс)` — ровно **четыре**
     аргумента (с тремя — `missing 1 required positional argument: 'threadClass'`).
  3. `faces = ObjectCollection` с цилиндрической гранью, `ti = tf.createInput(faces, info)`,
     `ti.isModeled = True`, `tf.add(ti)`. Проверка: объём тела уменьшился (цилиндр Ø10×20 мм:
     1570.8 → 1270.5 мм³).
  - **(чужой опыт)** Внутренняя резьба сужает отверстие до внутреннего диаметра резьбы: если
    сквозь деталь что-то должно проходить, считай зазор от внутреннего диаметра резьбы.
  - **(чужой опыт)** Для печати: V-образная (метрическая) резьба печатается надёжнее
    трапецеидальной, деталь лучше ставить вертикально (ось резьбы — вверх). Нижняя сторона
    витков при этом наклонена ~60° от вертикали — формально «нависание», но у мелкой резьбы
    (шаг до ~2 мм) это обычно печатается без поддержек; не считай это ошибкой.

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
- **(проверено 12.10.2026) Скрытое тело (выключена «лампочка») в STL не выгружается**, а
  `em.execute(so)` всё равно возвращает `True`. У нас файл **не появился вовсе** (по данным
  fusion-agent-kit бывает и файл в 0 байт); так же — при выгрузке корневого компонента, где
  единственное тело скрыто. Перед экспортом включи видимость (`isLightBulbOn = True`), после —
  верни как было, и проверяй результат:
  `os.path.exists(путь) and os.path.getsize(путь) > 0`.
- **(проверено 25.10.2026) То же с STEP компонента, вложенного в сборку:** его «родное»
  вхождение было скрыто (хотя на экране через прокси видно, см. раздел 3) — STEP вышел
  **на 4.5 КБ без единого тела**, `execute` вернул `True`. Размер > 0 тут не спасает. Проверка
  STEP: число тел в файле —
  `(Select-String -Path файл.step -Pattern MANIFOLD_SOLID_BREP).Count` (PowerShell) должно
  совпадать с числом тел; для сборки — с суммой тел по **разным** компонентам (одинаковые
  вхождения записываются один раз).
- **STL и STEP пишутся в системе координат компонента.** Если деталь построена с осью Y вверх
  (как часто в Fusion с «Y up»), штатный STL ляжет в слайсере на бок. STL с осью Z вверх и низом
  на столе — своим кодом, сниппет 15.

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

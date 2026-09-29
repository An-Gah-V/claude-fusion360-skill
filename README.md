# claude-fusion360-skill

Скилл для [Claude Code](https://claude.com/claude-code): Claude сам моделирует в **Autodesk
Fusion** — от простой детали до реверс-инжиниринга 3D-скана и подготовки к 3D-печати.

*Скилл* — это папка с инструкциями и программами, которую Claude Code подгружает сам, когда
тема разговора подходит (здесь — Fusion, 3D-модели, сканы, 3D-печать).

> **English summary.** A Claude Code skill for driving Autodesk Fusion through Autodesk's
> official Fusion MCP server (Python scripts via the Fusion API): parametric modeling,
> scan-to-CAD reverse engineering, 3D-print checks and STL/STEP export, plus a video renderer
> for model/scan presentations. The skill text is in **Russian**; Claude follows it regardless
> of the language you chat in. Every pitfall and snippet was verified live (Windows 10,
> Fusion 2705.1.15). Requirements: Fusion running on the same machine with *Preferences →
> General → API → Fusion MCP Server* enabled, the server added to Claude Code
> (`claude mcp add --scope user --transport http fusion http://127.0.0.1:27182/mcp`),
> Python 3.7+ with numpy and Pillow (imageio + imageio-ffmpeg for video).
> Install — Git Bash / macOS: `git clone https://github.com/An-Gah-V/claude-fusion360-skill ~/.claude/skills/fusion360-modeling`;
> PowerShell: `git clone https://github.com/An-Gah-V/claude-fusion360-skill "$HOME\.claude\skills\fusion360-modeling"`.
> License: MIT.

## Что умеет

- **Моделирование через Fusion API**: эскизы, выдавливание, вырезы, скругления, параметры,
  компоненты — со строгими правилами, которые спасают от типичных ошибок (единицы в см,
  перевёрнутые оси эскизов на XZ/YZ, выбор граней по геометрии, а не по номеру).
- **Реверс-инжиниринг скана**: выравнивание сетки по осям, сечения, поиск плоских граней,
  построение чистой модели и сравнение её со сканом (отклонения в мм и картинки наложения).
- **Подготовка к 3D-печати**: правила проектирования под FDM, поиск микрограней, экспорт
  STL/STEP и проверка STL на замкнутость.
- **Презентации**: кадры из Fusion и видео «облёт модели» / «скан садится на модель» в MP4.

Всё, что описано в скилле, проверено вживую. Отдельный справочник собирает ловушки Fusion API и
коннектора с правильными вариантами — например, почему скрипт обязательно оформлять функцией
`run()` и почему кириллица в выводе приходит «кракозябрами».

## Что нужно

| Что | Зачем |
|---|---|
| Claude Code (CLI или вкладка Code в приложении Claude) | скиллы — функция Claude Code |
| Autodesk Fusion, запущенный на том же компьютере | в нём строится модель |
| Встроенный MCP-сервер Fusion, подключённый к Claude Code под именем `fusion` | через него Claude выполняет скрипты во Fusion (см. ниже) |
| Python 3.7+ с `numpy` и `pillow` | программы анализа скана и проверки STL |
| + `imageio` и `imageio-ffmpeg` | только для видео |

### Подключить Fusion к Claude Code

1. Во Fusion: **Preferences → General → API** → поставьте галочку
   **«Fusion MCP Server (runs locally on this device)»**. Сервер заработает на вашем компьютере
   по адресу `http://127.0.0.1:27182/mcp` (подробнее — в
   [блоге разработчиков Autodesk](https://blog.autodesk.io/fusion-mcp-server/), статья на японском).
2. В терминале добавьте сервер в Claude Code (имя `fusion` важно — на него рассчитан скилл):
   ```
   claude mcp add --scope user --transport http fusion http://127.0.0.1:27182/mcp
   ```
3. Проверка: `claude mcp list` должен показать `fusion: ... ✓ Connected` (при запущенном Fusion).

### Установить библиотеки Python

```
py -m pip install numpy pillow imageio imageio-ffmpeg
```
(на macOS — `python3 -m pip install ...`)

**Платформа.** Скилл написан и проверен под **Windows 10** (Fusion 2705.1.15, Python 3.14):
в примерах пути вида `C:\...` и команда `py`. На macOS должен работать, но не проверялся.

## Установка скилла

**Git Bash или macOS:**
```
git clone https://github.com/An-Gah-V/claude-fusion360-skill ~/.claude/skills/fusion360-modeling
```

**PowerShell** (там `~` для git не раскрывается):
```
git clone https://github.com/An-Gah-V/claude-fusion360-skill "$HOME\.claude\skills\fusion360-modeling"
```

**Без git — ZIP.** Code → Download ZIP. В архиве всё лежит в папке
`claude-fusion360-skill-main`: распакуйте её, переименуйте в `fusion360-modeling` и положите в
`C:\Users\<имя>\.claude\skills\` (на macOS — `~/.claude/skills/`; папка `.claude` в Finder скрыта,
показать — Cmd+Shift+.). Проверьте, что `SKILL.md` лежит прямо в `fusion360-modeling`, а не
во вложенной папке.

Начните новую сессию Claude Code — скилл подхватится сам, когда речь пойдёт о Fusion, 3D-модели,
скане или 3D-печати. Пример запроса: «Сделай во Fusion кронштейн 40×30 мм с двумя отверстиями под M4».

## Что внутри

```
SKILL.md                        главные правила и порядок работы
references/
  api-pitfalls.md               ловушки Fusion API и коннектора
  coordinates.md                единицы, оси эскизов (таблица проверена), матрицы
  snippets.md                   13 проверенных кусков кода («сниппетов») для скриптов Fusion
  reverse-engineering.md        процесс «скан → чистая CAD-модель»
  print-export.md               проектирование под печать, экспорт, проверка STL
  presentation.md               картинки и видео
scripts/                        запускаются вне Fusion, обычным Python
  scan_tools.py                 анализ скана: info, matrix, section, planes, compare
  check_stl.py                  проверка STL перед печатью
  render_video.py               видео-презентация модели (и совмещения со сканом)
```

## Благодарности

Идеи частично взяты из открытых проектов (код оттуда не копировался, правила перепроверены
вживую):
- [fusion360-expert](https://github.com/theneoai/awesome-skills/tree/main/skills/tool/cad/fusion360-expert)
  (theneoai/awesome-skills) — порядок построения элементов, советы по печати;
- [ClaudeFusion360MCP](https://github.com/rahayesj/ClaudeFusion360MCP) (rahayesj) —
  внимание к пространственной ориентации и перевёрнутой оси Z на плоскостях XZ/YZ.

Основной опыт — из реального проекта реверс-инжиниринга корпуса по 3D-скану.

## Лицензия

[MIT](LICENSE) — можно свободно использовать, менять и распространять, сохраняя текст лицензии
с указанием автора.

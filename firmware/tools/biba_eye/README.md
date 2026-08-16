# BIBA Eye

FPV-инструмент для камеры **V380 Q8** (и аналогичных): веб-страница с живым
видео и управлением поворотом камеры (PTZ) с клавиатуры или кнопок.

## Возможности
- 🎥 Видео в браузере (RTSP → MJPEG через ffmpeg, ~20 к/с)
- 🕹 PTZ: **WASD / стрелки** (держать — движение, отпустить — стоп), кнопки на экране
- ⚙️ **Первый запуск**: страница спрашивает IP камеры или сама находит камеры в сети
- 📶 **Профили качества**: Ultra (макс. скорость) / Fast / Balanced / Quality (720p) — выбор в шапке, переключение на лету
- 💾 Всё сохраняется в `config.json`, повторный запуск — без ввода

## Установка одной строкой
Скопируйте и выполните в PowerShell (скачает всё с GitHub и настроит ПК):
```powershell
irm https://raw.githubusercontent.com/GOODWORKRINKZ/biba/main/firmware/tools/biba_eye/install.ps1 | iex
```
Локальный вариант (если папка тулзы уже есть рядом):
```powershell
powershell -ExecutionPolicy Bypass -File tools\biba_eye\setup.ps1
```
Скрипт сам:
- установит **Python 3.12** и **ffmpeg**, если их нет (через winget);
- создаст виртуальное окружение **`biba_venv`** и поставит все пакеты
  из `requirements.txt`;
- спросит IP камеры (можно пропустить — потом ввести на странице);
- создаст `run.cmd` и ярлыки **«BIBA Eye»** с иконкой на рабочем столе и в меню Пуск.

## Запуск
- Ярлык **BIBA Eye** на рабочем столе / в меню Пуск, или
- `tools\biba_eye\run.cmd`, или вручную:
```powershell
tools\biba_eye\biba_venv\Scripts\python.exe tools\biba_eye\server.py
```
Страница откроется сама: **http://127.0.0.1:8081/**

## Настройки
Файл `tools/biba_eye/config.json` (создаётся автоматически):
```json
{
  "camera_ip": "192.168.1.107",
  "camera_user": "admin",
  "camera_pass": "888888",
  "rtsp_port": 554,
  "onvif_port": 8899,
  "profile": "balanced",
  "web_port": 8081,
  "ptz_speed": 0.5,
  "flip_x": 0,
  "flip_y": 0
}
```
- `profile`: `ultra` | `fast` | `balanced` | `quality`
- `ptz_speed`: скорость поворота (0.1–1.0)
- `flip_x` / `flip_y`: инверсия осей, если направления перепутаны
- Переменные окружения-переопределения: `BIBA_CAM_IP`, `BIBA_CAM_PASS`, `BIBA_WEB_PORT`

## API
- `GET /stream` — MJPEG-поток
- `GET /api/config` — конфигурация
- `POST /api/config` — сохранить IP/пароль (с проверкой ONVIF)
- `GET /api/discover` — скан подсети, поиск камер (порты 8899/554 + ONVIF)
- `POST /api/profile` — сменить профиль качества
- `POST /api/ptz` — `{"action":"up|down|left|right|stop"}`
- `GET /api/status` — состояние потока

## Требования
Устанавливаются автоматически `setup.ps1`:
- Python 3.8+ (winget `Python.Python.3.12`)
- ffmpeg (winget `Gyan.FFmpeg`)
- виртуальное окружение `biba_venv` + пакеты из `requirements.txt`
  (сам сервер использует только стандартную библиотеку)
- камера с включённым RTSP/ONVIF (V380 Pro → настройки камеры)

## Файлы
- `server.py` — сервер (видео + PTZ + поиск)
- `index.html` — страница оператора
- `setup.ps1` — установка одной строкой (Python/ffmpeg/venv/ярлыки)
- `requirements.txt` — пакеты для venv (сейчас пусто: сервер на stdlib)
- `biba_eye.ico` — иконка «глаз BIBA» для ярлыков
- `run.cmd` — запуск через `biba_venv` (создаётся setup.ps1)
- `biba_venv/` — виртуальное окружение BIBA (создаётся setup.ps1)
- `config.json` — настройки (создаётся при первом подключении)

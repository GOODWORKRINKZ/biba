# FPV: картинка с OpenIPC-камеры по радио через RTL8812AU + wfb-ng

Статус: **работает** (проверено 2026-10-13 на ноутбуке `test-Katana-GF66-11UD`).

Инструкция для следующих сессий: как поднять приём видео с OpenIPC-камеры (Air unit)
на ноутбуке через USB-адаптер RTL8812AU и `wfb-ng` (wifibroadcast-ng), и как это
диагностировать. Про V380-камеру (сторонний проект, RTSP/BIBA Eye) — см.
[`fpv_camera.md`](fpv_camera.md); это отдельная история.

## Схема

```
OpenIPC (Air unit) ──H.264 RTP──► wfb_tx ──[ 802.11 monitor/injection, ch161 5805 МГц ]──► RTL8812AU
       ▲                                                                                        │
       │ UART (ttyS2) → полётник                                                      wfb_rx (gs.key)
                                                                                                │
                                                              RTP → UDP 127.0.0.1:5600 ────────┘
                                                                                                │
                                                                            gstreamer → окно / JPEG
```

## Железо и софт

- **Камера:** OpenIPC, hostname `openipc-gk7205v200`, SoC **Goke GK7205V200**.
  Есть USB Wi-Fi **RTL8812AU** и Ethernet (100 Мбит).
- **Ground station:** ноутбук `test-Katana-GF66-11UD` + USB **RTL8812AU**
  (`0bda:8812`), интерфейс `wlxfc221c20077d`.
- **Драйвер:** `svpcom/rtl8812au` ветка `v5.2.20` → модуль **`88XXau_wfb`**
  (умеет monitor + injection). Обычный `morrownr/8812au` **не подходит** —
  в его README прямо: «Monitor mode is not supported», а без монитора wfb-ng не работает.

## Параметры линка (видео)

Подтверждено на камере (2026-10-13, `openipc-gk7205v200`). Файл конфига —
`/etc/wfb.conf` (в новых образах OpenIPC он же `/etc/wfb.yaml`).

| Параметр | Значение |
|---|---|
| channel | **161** (5805 МГц) |
| bandwidth | 20 |
| mcs_index | 1 |
| fec_k / fec_n | 8 / 12 |
| stbc / ldpc | 0 / 0 |
| guard_interval | long |
| stream (radio_port) | 0 |
| link_id | 7669206 |
| udp_port | 5600 |
| video | **H.264** (RTP pt=96, FU-A) |

Ключи — **дефолтные OpenIPC** (публичные, совпадают у air и ground):
`https://github.com/OpenIPC/firmware/tree/master/general/package/legacy/wifibroadcast/files/`
(`gs.key`, `drone.key`). На камере лежит `drone.key`, нам нужен `gs.key`.

## Подготовка (один раз)

### 1. Драйвер RTL8812AU с monitor + injection

```bash
git clone -b v5.2.20 https://github.com/svpcom/rtl8812au.git
sudo rm -rf /usr/src/rtl8812au-5.2.20.2
sudo cp -r rtl8812au /usr/src/rtl8812au-5.2.20.2
sudo dkms add     -m rtl8812au -v 5.2.20.2
sudo dkms build   -m rtl8812au -v 5.2.20.2
sudo dkms install -m rtl8812au -v 5.2.20.2

# если до этого стоял morrownr/8812au (без монитора) — убрать:
sudo dkms remove -m rtl8812au -v 5.13.6-23 --all
sudo rmmod 8812au 2>/dev/null || true
```

> Их `./dkms-install.sh` **не запускать**: он дописывает в `/etc/sysctl.conf` и
> отключает IPv6 на всей машине.

### 2. Secure Boot (Ubuntu) — подпись DKMS-модулей

При включённом Secure Boot неподписанный модуль не загрузится. Ключ — штатный MOK:

```bash
printf '%s\n' '#!/bin/sh' \
  '/lib/modules/"$1"/build/scripts/sign-file sha512 /var/lib/shim-signed/mok/MOK.priv /var/lib/shim-signed/mok/MOK.der "$2"' \
  | sudo tee /etc/dkms/sign_helper.sh >/dev/null
sudo chmod +x /etc/dkms/sign_helper.sh
sudo sed -i 's|^# *sign_tool=|sign_tool=|' /etc/dkms/framework.conf

sudo mokutil --import /var/lib/shim-signed/mok/MOK.der   # задать пароль (8–16 симв.)
sudo reboot   # при загрузке: синий MOK Manager → Enroll MOK → Continue → Yes → пароль
```

Проверка подписи:
`modinfo -F signer /lib/modules/$(uname -r)/updates/dkms/88XXau_wfb.ko`
→ `ubuntu Secure Boot Module Signature key`.

> Нюанс: `dkms` после сборки подписанного модуля сам вызывает
> `update-secureboot-policy --enroll-key`, который поднимает **интерактивный
> диалог** (whiptail). Если MOK ещё не зачислен — установка «висит» с 0% CPU.
> Лечится зачислением MOK (шаг выше).

### 3. wfb-ng (только приёмник) и ключи

```bash
sudo apt install -y iw libsodium-dev libpcap-dev
git clone https://github.com/svpcom/wfb-ng && cd wfb-ng && make wfb_rx

mkdir -p keys
curl -o keys/gs.key \
  https://raw.githubusercontent.com/OpenIPC/firmware/master/general/package/legacy/wifibroadcast/files/gs.key
```

### 4. Декодер видео

```bash
sudo apt install -y gstreamer1.0-plugins-bad gstreamer1.0-libav
# даёт h264parse (plugins-bad) и avdec_h264 (libav)
```

## Запуск (каждый раз)

**1) Монитор + канал.** Важно: канал переключать через `iwconfig` (nl80211
отказывает: «Channel is disabled» из-за regdomain):

```bash
IF=wlxfc221c20077d
sudo nmcli dev set $IF managed no
sudo ip link set $IF down
sudo iw dev $IF set type monitor
sudo ip link set $IF up
sudo iwconfig $IF channel 161
```

**2) Приём** (декодирует радио, форвардит RTP на UDP `127.0.0.1:5600`):

```bash
sudo wfb_rx -K keys/gs.key -c 127.0.0.1 -u 5600 -p 0 -i 7669206 $IF
```

**3) Просмотр** (живое окно):

```bash
gst-launch-1.0 udpsrc port=5600 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=H264,payload=96" \
  ! rtph264depay ! h264parse ! avdec_h264 ! videoflip method=rotate-180 ! videoconvert ! autovideosink sync=false
```

Без экрана (снять кадры в файлы): заменить хвост на
`! videoconvert ! jpegenc ! multifilesink location=/tmp/cam_%03d.jpg`.
Ориентацию подобрать в `videoflip` (`rotate-90` / `rotate-180` / `rotate-270`).

## Диагностика

- Камера **не видна как Wi-Fi AP** — она в monitor/injection, обычного SSID нет.
- Поиск канала пассивно: включить монитор, `iwconfig $IF channel <CH>` и считать
  дельту `/sys/class/net/$IF/statistics/rx_packets`. На рабочем 161 — ~1100–1700 пакетов/с.
  (Альтернатива — `tcpdump`: кадры с высокой энтропией = шифрованный wfb.)
- «Серая/плоская» картинка на первых кадрах — это декод **до IDR**; через 1–2 с
  приходит нормальный кадр. Если серо постоянно — смотреть настройки камеры.
- Полезный признак живого линка в `wfb_rx`: строка `SESSION 0:1:8:12`
  и `RX_ANT 5805:1:20 …` (канал 5805, ширина 20).

### Доступ к камере по Ethernet

Камера отдаёт IPv6 link-local **`fe80::200:23ff:fe34:4566`** (MAC `00:00:23:34:45:66`):

```bash
ping -6 -I enp2s0 fe80::200:23ff:fe34:4566
ssh root@fe80::200:23ff:fe34:4566%enp2s0     # порты 22/80/554 открыты
```

> Если `ssh`/`ping` отвечают «Network is unreachable», а у `enp2s0` вообще нет
> адреса — значит у интерфейса `addr_gen_mode=1` (ядро не создаёт link-local),
> часто в паре с тем, что портом рулит NetworkManager и сносит адрес. Лечится:
>
> ```bash
> sudo nmcli dev set enp2s0 managed no
> sudo sysctl -w net.ipv6.conf.enp2s0.addr_gen_mode=0
> sudo ip link set enp2s0 down; sudo ip link set enp2s0 up
> ip -6 addr show dev enp2s0      # должен появиться fe80::…
> ```

### UART-консоль камеры

**115200 8N1.** Логина нет (OpenIPC его отключает), консоль периодически пишет
`N packets dropped`. Полезно для просмотра логов загрузки, но не для shell.

## MAVLink (телеметрия) поверх wfb-ng

Телеметрия — **отдельный сервис** OpenIPC `/usr/bin/telemetry` (включается
`telemetry=true` в `/etc/datalink.conf`). Идёт **своими radio-port** рядом с видео,
через те же бинари (``telemetry_rx``/`telemetry_tx` — симлинки на `wfb_rx`/`wfb_tx`).
Источник — UART камеры, подключённый к UART полётника; если полётник не подключён,
телеметрии, естественно, не будет.

Подтверждено на камере (2026-10-13, `openipc-gk7205v200`).

`/etc/datalink.conf`: `daemon=1`, **`telemetry=true`**, `tunnel=false`.

`/etc/telemetry.conf` (drone):

```
serial=/dev/ttyAMA0    baud=115200
router=0               # 0=mavfwd, 1=mavlink-routerd, 2=msposd (OSD)
stream_rx=144          # radio-port: приём от наземки
stream_tx=16           # radio-port: передача на наземку
port_rx=14551          # UDP: mavfwd пишет сюда вход (--in)
port_tx=14550          # UDP: mavfwd пишет сюда выход (--out)
link_id=7669206
bandwidth=20  mcs_index=1  stbc=1  ldpc=1  fec_k=1  fec_n=2  guard_interval=long
one_way=false  frame_type=data
```

`/usr/bin/telemetry` на камере фактически запускает:

```sh
telemetry_rx -p 144 -u 14551 -K /etc/drone.key -i 7669206 wlan0      # наземка → камера
telemetry_tx -p  16 -u 14550 -K /etc/drone.key -B 20 -M 1 -S 1 -L 1 \
             -G long -k 1 -n 2 wlan0                                 # камера → наземка
mavfwd --master /dev/ttyAMA0 --baudrate 115200 -p 100 -t -a 15 \
       --out 127.0.0.1:14550 --in 127.0.0.1:14551
```

Наземке, значит, нужно **симметрично**: принимать radio-port **16** → отдавать в
UDP **14550**, и передавать radio-port **144**, читая UDP **14551**.

### Наземка (ноутбук)

```bash
cd ~/wfb-ng && make wfb_rx wfb_tx

# камера → GS: radio 16 → UDP 14550 (это «видит» QGroundControl / MAVProxy)
sudo wfb_rx -K keys/gs.key -c 127.0.0.1 -u 14550 -p 16 -i 7669206 $IF

# GS → камера: UDP 14551 → radio 144 (параметры должны совпадать с телеметрией камеры)
sudo wfb_tx -K keys/gs.key -p 144 -u 14551 -B 20 -M 1 -S 1 -L 1 \
            -G long -k 1 -n 2 -f data -i 7669206 $IF
```

QGroundControl / MAVProxy: вход `udp://127.0.0.1:14550`, выход (для команд/RC)
`udp://127.0.0.1:14551`.

> Параметры передачи телеметрии (`-B/-M/-S/-L/-G/-k/-n/-f`) отличаются от
> видео-линка: тут `stbc/ldpc=1` и `fec 1/2`, у видео `stbc/ldpc=0` и `fec 8/12`.

### Куда паять MAVLink (UART камеры)

- На камере (`openipc-gk7205v200`) телеметрия сидит на **`/dev/ttyAMA0`** — это
  **второй UART (UART2)** SoC; pinmux включается автоматически
  (`devmem 0x120C0010 32 0x1E04` в `/usr/bin/wifibroadcast`).
- По таблице OpenIPC
  [gpio-settings](https://github.com/OpenIPC/wiki/blob/master/en/gpio-settings.md)
  для GK7205V200: **UART2_RXD = GPIO12**, **UART2_TXD = GPIO13**, UART2_RTS = GPIO54.
  Но **конкретные пятачки на плате зависят от модели** (в таблице — платы
  2M-M2103 / 2G-M3072), поэтому смотреть маркировку/пятачки своей платы.
- Уровни **3.3 В** (5 В подавать нельзя), GND общий, соединение перекрёстное:
  `FC TX → камера RX`, `FC RX → камера TX`.
- На полётнике: MAVLink (ArduPilot `SERIALx_PROTOCOL=2`), 115200.
- ⚠️ U-Boot камеры **останавливается**, если при загрузке на UART приходят байты —
  полётник должен начинать телеметрию с задержкой (ArduPilot `TELEM_DELAY`) либо
  линию на время загрузки разрывать.

## Артефакты на ноутбуке

- `~/rtl8812au-wfb` — исходники патченного драйвера;
- `~/wfb-ng/` (+ `keys/gs.key`) — приёмник и ключ;
- `~/8812au-20210820` — старый драйвер без монитора (можно удалить).

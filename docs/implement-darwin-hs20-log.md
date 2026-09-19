# Журнал внедрения Darwin HS20-генератора

## 2026-09-19

- Прочитан `README.md`.
- Изучены `mkdarwin.py`, `mkandroid.py`, `pub-darwin.py` и `pub-android.py`.
- Подтверждено: обычный Darwin-генератор уже использует
  `com.apple.wifi.managed` и EAP-TLS payloads.
- Подтверждено: Android HS20 PoC использует friendly name, FQDN и realm.
- По документации Apple выбраны HS20-ключи `DisplayedOperatorName`,
  `DomainName` и `NAIRealmNames`.
- Добавлен `mkdarwin-hs20.py` с отдельным CLI и HS20 Wi-Fi payload.
- В `README.md` добавлен пример запуска.
- Проверен Python-синтаксис нового скрипта.
- Проверен CLI без аргументов: выводится usage с четырьмя аргументами.
- `git diff --check` не выявил ошибок форматирования.
- Полная генерация на `rutest-rsa.pfx` не выполнена: пароль PFX неизвестен.
- В README добавлен полный пример запуска с параметрами Android PoC:
  `./mkdarwin-hs20.py NETAMS wifi.netams.com netams.com rutest-rsa.pfx`.
- Запуск генератора остановлен на запросе пароля PFX без создания профиля.
- После ввода пароля PFX создан `NETAMS-hs20.mobileconfig`.
- Проверены payload-типы: PKCS#12, root CA и `com.apple.wifi.managed`.
- Проверены значения: `NETAMS`, `wifi.netams.com`, `netams.com`, EAP-TLS (13).
- После ошибки импорта добавлены обязательные Apple HS20-поля с тестовыми
  значениями: `RoamingConsortiumOIs=["112233"]` и `MCCAndMNCs=["25001"]`.
- Тестовые значения подходят для проверки импорта, но не гарантируют выбор
  конкретной реальной HS20-сети.
- По macOS unified log отказ локализован в `wifiPayloadPlugin`, код `-307`;
  PKCS#12 при этом успешно декодируется.
- Исправлен Darwin payload: добавлен `IsHotspot=true`, удалён
  `MCCAndMNCs`, который Apple не поддерживает на macOS.
- Пересоздан `NETAMS-hs20.mobileconfig` с исправленным payload.
- Проверен статус Wi-Fi на MacBook: `system_profiler` показывает подключение к
  `gost-eap-tls` с защитой WPA2 Enterprise; к `NETAMS`/Passpoint-профилю Mac не
  подключён.
- `networksetup -getairportnetwork en0` в текущем окружении вернул
  `You are not associated with an AirPort network`, поэтому для статуса принят
  подробный результат `system_profiler SPAirPortDataType`.

Команды и вывод проверки:

```sh
networksetup -getairportnetwork en0
```

```text
You are not associated with an AirPort network.
```

```sh
system_profiler SPAirPortDataType
```

```text
Interfaces:
  en0:
    Status: Connected
    Current Network Information:
      gost-eap-tls:
        Network Type: Infrastructure
        Security: WPA2 Enterprise
```

Итог: MacBook подключён к `gost-eap-tls` по обычному WPA2 Enterprise, а не к
сети Passpoint/HS20 `NETAMS`.

## 2026-09-19 — переписывание генератора на C

- Зафиксировано решение добавить C-программу рядом с существующим
  `mkdarwin-hs20.py`.
- XML plist, base64 и UUID будут формироваться напрямую в C без plist-библиотек.
- Для разбора зашифрованного PFX сохранён вызов внешнего `openssl`; собственный
  ASN.1/PKCS#12 стек не добавляется из-за лишней сложности.
- Добавлен `mkdarwin-hs20.c`; существующий Python-генератор сохранён.
- C-программа собрана командой `cc -std=c11 -Wall -Wextra -O2` без предупреждений.
- Проверен usage без аргументов.
- На `rutest-rsa.pfx` создан `NETAMS-hs20.mobileconfig` с payload-типами
  PKCS#12, root CA и Wi-Fi HS20; plist распарсирован успешно.
- Python-генератор `mkdarwin-hs20.py` не удалён и сохранён рядом.
- Дополнительно выполнено `plutil -lint NETAMS-hs20.mobileconfig`: `OK`.

## 2026-09-19 — удаление тестового Roaming Consortium OI

- Удалён тестовый `RoamingConsortiumOIs=["112233"]` из Python- и C-генераторов.
- Причина: значение было случайным и отсутствует в конфигурации текущей HS20-сети
  OpenWrt; оно могло мешать macOS сопоставить профиль `NETAMS` с Passpoint-сетью.
- README обновлён: генераторы больше не добавляют `RoamingConsortiumOIs` и
  `MCCAndMNCs`.
- Проверки после изменения:
  - `python3 -m py_compile mkdarwin-hs20.py` — успешно.
  - `cc -std=c11 -O2 -Wall -Wextra -o mkdarwin-hs20 mkdarwin-hs20.c` — успешно,
    без предупреждений.
  - Оба генератора создали профиль с `NETAMS`, `wifi.netams.com` и
    `netams.com`; проверка plist подтвердила отсутствие `RoamingConsortiumOIs`
    и `MCCAndMNCs`.
  - `plutil -lint NETAMS-hs20.mobileconfig` — `OK`.
  - `git diff --check` — успешно.
  - `make test` — не выполнен: в репозитории нет `Makefile` и цели `test`;
    команда завершилась с кодом 2.
- C-генератор и документация закоммичены в commit `3f38211`.

## 2026-09-19 — pcap и hostapd во время попытки Darwin HS20

- Захват выполнен на AP `root@10.11.11.101`, SSID `gost-eap-tls`, интерфейсы
  `awlan0_118` и `awlan1_118`.
- Запущена команда захвата:

  ```sh
  tcpdump -i any -s 0 -U -w /tmp/darwin-hs20-20260919-152714.pcap \
    '(ether proto 0x888e) or (udp port 1812) or (udp port 1813)'
  ```

- Команда снятия hostapd-лога:

  ```sh
  logread | grep hostapd | tail -300
  ```

- Получено `50 packets captured`, `0 packets dropped by kernel`.
- В hostapd подтверждён HS20/ANQP-запрос Mac:
  `GAS Initial Request`, запрошены `Domain Name`, `NAI Realm` и `HS 2.0 Query
  List`; `Roaming Consortium not available` и `Operator Friendly Name not
  available`.
- В RADIUS-трафике виден Passpoint realm: `User-Name: null@wifi.netams.com`.
- RADIUS отправляет `Access-Challenge`, после чего AP отправляет EAP-TLS
  фрагмент с клиентским сертификатом:
  `Access-Request id=0x71`, `EAP Response`, `Type TLS`, EAP length `1181`.
- После этого RADIUS не отвечает: пакет `id=0x71` повторён примерно через 3,
  6 и 12 секунд. Нет ни `Access-Accept`, ни `Access-Reject`.
- Это объясняет macOS timeout: проблема происходит после HS20 discovery и во
  время проверки/обработки клиентского EAP-TLS сертификата на стороне RADIUS;
  окно выбора сертификата появляется уже после fallback на обычный EAP-TLS.
- Файлы захвата на AP:
  `/tmp/darwin-hs20-20260919-152714.pcap`,
  `/tmp/darwin-hs20-20260919-152714-hostapd.log`.

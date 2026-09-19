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

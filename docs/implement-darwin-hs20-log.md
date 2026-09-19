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

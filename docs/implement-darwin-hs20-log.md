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

# План внедрения Darwin HS20-генератора

## Цель

Добавить рядом с `mkdarwin.py` отдельный генератор Apple `mobileconfig` для
Hotspot 2.0 / Passpoint с EAP-TLS.

## Исходное состояние

- `mkdarwin.py` уже создаёт рабочий обычный Wi-Fi EAP-TLS профиль.
- `mkandroid.py` уже создаёт рабочий Android HS20-профиль.
- Параметры HS20 в текущем PoC: friendly name, FQDN и NAI realm.
- Клиентская identity и CA chain передаются внутри PFX.

## Решение

Добавить отдельный скрипт `mkdarwin-hs20.py`, не изменяя рабочий
`mkdarwin.py`.

Скрипт будет:

1. Принимать `FRIENDLY_NAME FQDN REALM client.pfx`.
2. Извлекать из PFX клиентский сертификат, закрытый ключ и CA-сертификаты.
3. Находить self-signed root CA и добавлять его как
   `com.apple.security.root` payload.
4. Добавлять PFX как `com.apple.security.pkcs12` payload.
5. Создавать `com.apple.wifi.managed` payload с:
   - `DisplayedOperatorName`;
   - `DomainName`;
   - `NAIRealmNames`;
   - EAP-TLS configuration.
6. Записывать XML plist в файл с суффиксом `-hs20.mobileconfig`.

## Границы

- Не менять обычный Darwin-генератор.
- Не добавлять RADIUS proxy, DNS discovery, realm routing и roaming logic.
- Не выдумывать `RoamingConsortiumOIs`, `MCCAndMNCs` и другие параметры,
  которых нет в текущем PoC.
- Не добавлять архитектурные слои или общий framework для двух скриптов.

## Проверка

- Проверить синтаксис нового Python-скрипта.
- На тестовом PFX сгенерировать `mobileconfig`.
- Распарсить plist и проверить наличие трёх payload-типов.
- Проверить значения HS20-полей и EAP-TLS payload.
- Убедиться, что обычный `mkdarwin.py` не изменился.

## Документация

После реализации добавить в `README.md` пример запуска нового генератора и
описать формат его аргументов.

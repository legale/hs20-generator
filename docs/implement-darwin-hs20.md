# План внедрения Darwin HS20-генератора

## Цель

Переписать Darwin-генератор Apple `mobileconfig` для Hotspot 2.0 / Passpoint с
EAP-TLS на простой C без plist-библиотек и OpenSSL API.

## Исходное состояние

- `mkdarwin.py` уже создаёт рабочий обычный Wi-Fi EAP-TLS профиль.
- `mkandroid.py` уже создаёт рабочий Android HS20-профиль.
- Параметры HS20 в текущем PoC: friendly name, FQDN и NAI realm.
- Клиентская identity и CA chain передаются внутри PFX.

## Решение

Добавить `mkdarwin-hs20.c` рядом с существующим `mkdarwin-hs20.py`, не изменяя
рабочие генераторы.

Программа будет:

1. Принимать `FRIENDLY_NAME FQDN REALM client.pfx`.
2. Вызывать установленный `openssl` для извлечения CA-сертификатов из PFX.
3. Находить self-signed root CA и добавлять его как
   `com.apple.security.root` payload.
4. Добавлять исходный PFX как `com.apple.security.pkcs12` payload.
5. Самостоятельно формировать XML plist и base64 без plist-библиотеки.
6. Создавать `com.apple.wifi.managed` payload с:
   - `DisplayedOperatorName`;
   - `DomainName`;
   - `NAIRealmNames`;
   - EAP-TLS configuration.
7. Записывать XML plist в файл с суффиксом `-hs20.mobileconfig`.

## Границы

- Не менять обычный Darwin-генератор.
- Не добавлять RADIUS proxy, DNS discovery, realm routing и roaming logic.
- Не выдумывать `RoamingConsortiumOIs`, `MCCAndMNCs` и другие параметры,
  которых нет в текущем PoC.
- Не добавлять архитектурные слои или общий framework для двух скриптов.
- Не реализовывать собственный ASN.1/PKCS#12/PBES стек.

## Проверка

- Собрать C-программу системным C-компилятором.
- Проверить usage программы без аргументов.
- На тестовом PFX сгенерировать `mobileconfig`.
- Распарсить plist и проверить наличие трёх payload-типов.
- Проверить значения HS20-полей и EAP-TLS payload.
- Убедиться, что обычный `mkdarwin.py` не изменился.

## Документация

После реализации добавить в `README.md` команды сборки и запуска нового
генератора, а также описать зависимость от `openssl` для PFX-разбора.

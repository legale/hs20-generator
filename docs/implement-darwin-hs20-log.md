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

## 2026-09-19 — повторный параллельный захват AP и RADIUS

- Предыдущий захват остановлен; новый захват запущен одновременно на AP и
  RADIUS перед повторной попыткой Passpoint.
- AP `10.11.11.101`:

  ```sh
  tcpdump -ni any -s0 -U \
    -w /tmp/ap-radius-20260919-155010.pcap \
    "udp port 1812 and host 172.16.133.254"
  ```

- RADIUS `172.16.133.254`:

  ```sh
  sudo systemd-run --unit=radius-capture-20260919-155010 --collect --quiet \
    /usr/sbin/tcpdump -ni any -s0 -U \
    -w /tmp/radius-20260919-155010.pcap "udp port 1812"
  ```

- После попытки на AP выполнено ровно:

  ```sh
  logread | grep hostapd | tail -500
  ```

  Сохранено 500 строк в `/tmp/ap-radius-20260919-155010-hostapd.log`.
- Статистика захвата: AP — `50 packets captured`, `0 packets dropped`; RADIUS —
  `25 packets captured`, `0 packets dropped`.
- В корень репозитория скопированы артефакты:
  `capture-20260919-155010-ap.pcap`,
  `capture-20260919-155010-radius.pcap`,
  `capture-20260919-155010-hostapd.log`,
  `capture-20260919-155010-ap-tcpdump.log` и
  `capture-20260919-155010-radius-journal.log`.

Сопоставление `tshark` по AP pcap и RADIUS pcap:

| Время AP TX | RADIUS Identifier | State | EAP Identifier | EAP length | RADIUS length | Message-Authenticator | Результат |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| 15:50:24.822348 | `0x7d` | `8594b8472211afa605102df3b399952b` | 103 | 1181 | 1456 | `87d2ee1790f393de689475f6ab243fb5` | AP TX и server RX есть; server TX и AP RX отсутствуют |
| 15:50:54.499230 | `0x83` | `3321b938d733165b729f6df0c3b0a3ac` | 201 | 1181 | 1456 | `2977532ea71157d5bfdee2bbd333176a` | AP TX и server RX есть; server TX и AP RX отсутствуют |

- Для первого финального фрагмента `id=0x7d` RADIUS pcap содержит server RX в
  `15:50:24.824079`; тот же пакет повторён через 3, 6 и 12 секунд. Ответов на
  эти повторы нет.
- Для второго финального фрагмента `id=0x83` RADIUS pcap содержит server RX в
  `15:50:54.500330`; ответа также нет.
- Предыдущие EAP-TLS фрагменты получают ответы `Access-Challenge`, поэтому
  маршрут AP—RADIUS, начальная EAP-TLS фаза и обратный путь работают.
- В серверном `journalctl --since "10 min ago"` перед финальным фрагментом
  повторяется ошибка:

  ```text
  AbstractPacketHandler:340 - Index 3 out of bounds for length 3
  java.lang.ArrayIndexOutOfBoundsException
  at AbstractPacketHandler.parseTLV(AbstractPacketHandler.java:193)
  at AbstractPacketHandler.parseVendorSpecific(AbstractPacketHandler.java:135)
  ```

  Перед ошибкой сервер печатает `parseTLV name=dhcp-option, raw='00000076'`.
  Этот VSA соответствует настроенному на AP атрибуту
  `radius_auth_req_attr='26:x:00005a3b050600000076'`.
- Для пакета с финальным EAP-TLS fragment (`EAP id=103`/`201`) серверный pcap
  подтверждает прием UDP, но в application log нет обработки этого пакета и
  нет `Access-Challenge`, `Access-Accept` или `Access-Reject`. Это исключает
  потерю пакета между AP и сервером и локализует проблему в обработке RADIUS
  packet на сервере; ошибка парсинга NeTAMS VSA — основной подозреваемый.
- В последних 500 строках `hostapd` полезных EAP-строк нет: хвост занят
  повторным выводом beacon/nl80211-конфигурации. Это не меняет результат pcap.

## 2026-09-19 — журнал RADIUS за последние 5 минут

- Выполнена команда на сервере `172.16.133.254`:

  ```sh
  sudo journalctl --since "5 min ago" --no-pager -o short-iso
  ```

- Лог сохранён в корне репозитория:
  `capture-20260919-164705-radius-journal-5min.log`.
- В свежем окне видна попытка от AP `10.11.11.101`, realm —
  `null@wifi.netams.com`.
- В `16:45:56` сервер принял финальный крупный EAP-TLS fragment:

  ```text
  RADIUS-DIAG A source=10.11.11.101 id=146 datagram_length=1553 declared_length=1553
  RADIUS-DIAG C ... eap=code=2,id=235,type=13,length=1276,data_length=1276
  RADIUS-DIAG L eap_tls entry input_length=1266 more_fragments=true length_included=true
  RADIUS-DIAG N source=10.11.11.101 id=146 response_type=Access-Challenge
  ```

  То есть в этой попытке серверный RADIUS packet и EAP-TLS fragment были
  разобраны, после чего сервер отправил следующий `Access-Challenge`.
- В `16:46:41` сервер завершил сессию отказом:

  ```text
  AccessHandler:617 - reactor.core.Exceptions$RetryExhaustedException: Retries exhausted: 3/3
  Response state: FAIL
  handleRadiusPacket AUTH as=10.11.11.101, return=FAIL Retries exhausted: 3/3
  RADIUS-DIAG N ... id=148 response_type=Access-Reject
  ```

- Одновременно сервер не может получить токен для внутренних запросов:

  ```text
  AccessException: The token was not received
  No servers available for service: w2config
  Error status: 503 SERVICE_UNAVAILABLE
  Can't start RadiusService Next attempt in 3 sec
  ```

- Важное уточнение предыдущего вывода: VSA-поля действительно имеют
  некорректный размер (`vendor_type=3 declared_length=5 actual_data_length=3`),
  и сервер пишет `parseTLV unsafe index=3`, но в этой попытке парсер доходит до
  `parse_done` и сам по себе не блокирует EAP-TLS. Непосредственная причина
  текущего отказа — недоступность `w2config`/токена и последующее исчерпание
  внутренних повторов RADIUS.

## 2026-09-19 — повторная попытка после изменений на сервере

- Перед попыткой запущен сбор журнала сервера:

  ```sh
  ssh sysadmin@172.16.133.254 \
    'sudo -n journalctl --since "5 min ago" -f --no-pager -o short-iso' \
    > capture-20260919-220000-radius-journal-live.log
  ```

- После сообщения о завершении попытки сбор остановлен. Получено 8047 строк.
- В этом окне нет строк с `10.11.11.101`, `RADIUS-DIAG` или
  `handleRadiusPacket AUTH`; новая попытка с AP до обработчика RADIUS не дошла.
- На сервере в это же время повторяются конкретные ошибки:

  ```text
  No servers available for service: w2config
  The token was not received
  503 Service Unavailable from UNKNOWN
  ```

- Проверка Eureka показала, что экземпляр `W2CONFIG` зарегистрирован, но имеет
  статус `STARTING` и `overriddenstatus=UNKNOWN`:

  ```text
  instanceId=172.16.133.254:w2config:13208adca5397302951f10caeb37f402
  status=STARTING
  overriddenstatus=UNKNOWN
  port=8080
  ```

- Процесс `w2config` запущен, порт `8080` слушается, а
  `GET http://127.0.0.1:8080/actuator/health` возвращает `200` и `{"status":"UP"}`.
  Следовательно, проблема не в падении процесса или порта: сервис не переводится
  в состояние `UP` в Eureka, и Spring LoadBalancer исключает его из маршрутизации.
- Время попытки совпало только с сообщениями о недоступном `w2config`; в журнале
  `w2config` нет новой RADIUS-сессии. Диагноз: сначала нужно восстановить
  регистрацию/readiness `w2config` в Eureka, затем повторять проверку профиля.

## 2026-09-19 — повторная проверка журнала за последние 5 минут

- Повторно выполнена команда:

  ```sh
  ssh sysadmin@172.16.133.254 \
    'sudo -n journalctl --since "5 min ago" --no-pager -o short-iso' \
    > capture-20260919-220414-radius-journal-5min.log
  ```

- Получено 8317 строк. В свежем окне снова нет `10.11.11.101`,
  `RADIUS-DIAG`, `handleRadiusPacket AUTH` и `Access-Request`/`Access-*`.
  Нового RADIUS-запроса от AP не было.
- Ошибка сервиса сохраняется:

  ```text
  No servers available for service: w2config
  LoadBalancer does not contain an instance for the service w2config
  503 Service Unavailable from UNKNOWN
  The token was not received
  ```

- Состояние не изменилось: прежде чем повторять попытку на Mac, нужно перевести
  `w2config` из `STARTING` в `UP` в Eureka либо исправить его регистрацию.

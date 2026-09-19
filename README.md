# HS20 Profile Generator

Standalone-генератор клиентских профилей Hotspot 2.0 / Passpoint.

Текущая цель: вынести уже работающий PoC в отдельную небольшую утилиту, которая генерирует корректные HS20-профили без зависимости от основного кода WNAM.

## Текущее состояние

PoC генерации профиля для Android работает и проверен на реальном устройстве.

Тестовая схема:

Android-клиент
-> OpenWrt AP с включённым Hotspot 2.0
-> RADIUS
-> EAP-TLS аутентификация

Сгенерированный профиль успешно импортируется в Android. Passpoint-сеть определяется автоматически, подключение и EAP-TLS аутентификация проходят успешно.

## Конфигурация OpenWrt

Для проверки использовались две WLAN-конфигурации, рекламирующие одного HS20-провайдера:

```sh
uci set wireless.profile0_118.iw_enabled='1'
uci set wireless.profile0_118.iw_internet='1'
uci set wireless.profile0_118.iw_access_network_type='0'

uci add_list wireless.profile0_118.iw_domain_name='wifi.netams.com'
uci add_list wireless.profile0_118.iw_nai_realm='0,netams.com,13[5:6]'

uci set wireless.profile0_118.hs20='1'
uci add_list wireless.profile0_118.hs20_oper_friendly_name='eng:NETAMS'

uci set wireless.profile1_118.iw_enabled='1'
uci set wireless.profile1_118.iw_internet='1'
uci set wireless.profile1_118.iw_access_network_type='0'

uci add_list wireless.profile1_118.iw_domain_name='wifi.netams.com'
uci add_list wireless.profile1_118.iw_nai_realm='0,netams.com,13[5:6]'

uci set wireless.profile1_118.hs20='1'
uci add_list wireless.profile1_118.hs20_oper_friendly_name='eng:NETAMS'

uci commit wireless
wifi reload
```

Параметры провайдера в рабочем PoC:

```text
FQDN: wifi.netams.com
Realm: netams.com
Friendly Name: NETAMS
EAP: EAP-TLS
```

## Текущая задача

Превратить рабочий Android PoC в standalone-генератор HS20-профилей.

Требования:

* сохранить уже проверенный формат Android-профиля;
* не зависеть от реализации WNAM и RADIUS;
* принимать параметры HS20-провайдера и клиентские сертификаты/ключи;
* генерировать готовый к импорту профиль;
* реализация должна быть минимальной и детерминированной;
* не добавлять пока RADIUS proxy, realm routing, DNS discovery и другую функциональность.

Существующий рабочий PoC является эталоном поведения.

При рефакторинге сначала необходимо полностью сохранить его текущую семантику и совместимость с Android. Новую функциональность добавлять только после этого.

## Darwin HS20

Для Apple-профиля Passpoint/HS20 используется отдельный генератор:

```sh
./mkdarwin-hs20.py FRIENDLY_NAME FQDN REALM client.pfx
```

Он создаёт `mobileconfig` с HS20-полями `DisplayedOperatorName`, `DomainName`
и `NAIRealmNames`, а EAP-TLS identity и доверенный корневой сертификат берёт из
PFX так же, как обычный Darwin-генератор.

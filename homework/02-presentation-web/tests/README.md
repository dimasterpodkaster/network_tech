# Тестовый стенд домашнего задания

Полностью локальный, без внешней сети. Обе фикстуры независимы — TLS-стенд
не нужен для этапов A/B/D.

## `fixture_server.py` (этапы A, B, D)

```bash
python3 fixture_server.py --port 8090
```

Только стандартная библиотека. Эндпоинты:

| Путь | Для чего | Ожидаемый класс у корректного клиента |
|---|---|---|
| `/plain` | базовый happy path | `http_ok` |
| `/status/<code>` | произвольный HTTP-статус (например `/status/404`, `/status/503`) | `http_ok` — код статуса не равен сбою клиента |
| `/chunked` | `Transfer-Encoding: chunked`, 3 чанка | `http_ok` |
| `/broken-length` | `Content-Length` больше реально переданного, соединение закрывается | `framing_error` |
| `/timeout` | принимает соединение и ничего не отвечает 30 секунд | `timeout` (используйте `--timeout` заметно меньше 30) |
| `/repr?case=utf8` | текст в utf-8 | `http_ok` |
| `/repr?case=cp1251` | тот же текст в cp1251, корректно заявлен | `http_ok` |
| `/repr?case=charset-mismatch` | заявлен utf-8, реально cp1251 | `decode_error` |
| `/repr?case=gzip-ok` | `Content-Encoding: gzip`, корректный поток | `http_ok` |
| `/repr?case=bad-gzip` | заявлен gzip, тело не gzip | `decode_error` |
| `/repr?case=json-ok` | `Content-Type: application/json`, валидный JSON | `http_ok` |
| `/repr?case=json-bad` | текст восстанавливается, JSON синтаксически невалиден | `parse_error` |
| `/repr?case=gzip-json-ok` | gzip → UTF-8 с кириллицей → валидный JSON | `http_ok` |
| `/repr?case=gzip-json-bad` | gzip → корректный UTF-8 → JSON с лишней запятой | `parse_error` |
| `/multipart` | `multipart/mixed`, 2 части (текст + «бинарная») | этап D: обе части разобраны |
| `/multipart-broken-boundary` | тот же ответ, но ни одна граница в теле не совпадает с заявленной в заголовке | этап D: `multipart_error`, не падение |

`dns_error` и `connect_error` фикстура не производит специально — они
проверяются обращением к несуществующему имени (`nosuchhost.invalid`) и
к заведомо закрытому локальному порту.

## `tls_fixture/` (этап C)

После обновления генератора повторно выполните `make_certs.py` и
перезапустите TLS-сервер. Генератор заменяет учебные ключи и сертификаты;
клиенту передайте новый `out/ca.crt`. Сертификаты включают расширения
для строгой X.509-проверки; отключать `VERIFY_X509_STRICT` не требуется.

```bash
pip install cryptography       # разово, только для подготовки стенда
python3 tls_fixture/make_certs.py
python3 tls_fixture/tls_server.py
```

`make_certs.py` кладёт сертификаты в `tls_fixture/out/`. Клиенту нужен
только `out/ca.crt` как доверенный корень.

`tls_server.py` поднимает 4 порта — 8543, 8544, 8545, 8546. При каждом
запуске сценарий (валидный / просроченный / чужое имя / чужой CA) заново
случайно перемешивается между портами и нигде не печатается и не
сохраняется. Определить, какой порт что нарушает, — часть задания
(`assignment.md`, раздел 5.3): проверяющий делает это тем же способом —
запускает свежий `tls_server.py` и смотрит на вывод чужого клиента.

Перезапуск `tls_server.py` даёт новую случайную раскладку — так задание
не решается один раз и не передаётся по цепочке между потоками группы.

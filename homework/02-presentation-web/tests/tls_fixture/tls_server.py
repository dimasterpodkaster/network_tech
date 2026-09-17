"""4 HTTPS-порта с намеренно разными сертификатами (этап C задания).

Требует заранее выполненный `make_certs.py` (каталог out/ рядом со
скриптом). Сам сервер использует только стандартную библиотеку.

Запуск:

    python3 tls_server.py

Порты фиксированы (см. PORTS ниже), но сопоставление порт → сертификат
перемешивается заново при каждом запуске: списывать у одногруппника
таблицу портов бессмысленно, определять комбинацию нужно собственным
клиентом. Сервер не печатает и нигде не сохраняет это сопоставление.
"""

from __future__ import annotations

import random
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

OUT = Path(__file__).parent / "out"
PORTS = (8543, 8544, 8545, 8546)
CERT_NAMES = ("valid", "expired", "wrong-host", "untrusted")


class Handler(BaseHTTPRequestHandler):
    server_version = "homework-tls-fixture/1.0"

    def log_message(self, fmt, *args):  # noqa: D401 - quiet by default
        pass

    def do_GET(self):
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TLSHTTPServer(HTTPServer):
    def __init__(self, addr, handler_cls, ssl_context: ssl.SSLContext):
        super().__init__(addr, handler_cls)
        self._ssl_context = ssl_context

    def get_request(self):
        sock, addr = self.socket.accept()
        wrapped = self._ssl_context.wrap_socket(sock, server_side=True)
        return wrapped, addr


def _serve(port: int, cert_name: str):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(
        certfile=str(OUT / f"{cert_name}.crt"),
        keyfile=str(OUT / f"{cert_name}.key"),
    )
    server = TLSHTTPServer(("127.0.0.1", port), Handler, context)
    server.serve_forever()


def main():
    missing = [name for name in CERT_NAMES if not (OUT / f"{name}.crt").exists()]
    if missing:
        raise SystemExit(
            f"Не найдены сертификаты {missing} в {OUT}. Сначала запустите make_certs.py."
        )

    assignment = list(CERT_NAMES)
    random.shuffle(assignment)

    threads = []
    for port, cert_name in zip(PORTS, assignment):
        t = threading.Thread(target=_serve, args=(port, cert_name), daemon=True)
        t.start()
        threads.append(t)

    print(f"tls_server: слушаю {list(PORTS)} (Ctrl+C для остановки)")
    print("Соответствие порт -> сертификат перемешано и не публикуется.")
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

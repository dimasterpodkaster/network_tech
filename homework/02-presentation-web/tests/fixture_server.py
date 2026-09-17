"""Тестовый стенд для домашнего задания «Диагностический HTTP/HTTPS-клиент».

Только стандартная библиотека. Запуск:

    python3 fixture_server.py --port 8090

Эндпоинты описаны в README.md рядом с этим файлом.
Сервер сознательно не проверяет входные данные строго: это фикстура для
диагностики, а не образец production-кода.
"""

from __future__ import annotations

import argparse
import gzip
import json
import socketserver
import time
from http.server import BaseHTTPRequestHandler

PLAIN_BODY = b"Stage A: plain response\n"

REPR_TEXT = "Значение: сорок два\n"


def _gzip_case(charset: str) -> tuple[bytes, dict[str, str]]:
    body = REPR_TEXT.encode(charset)
    headers = {
        "Content-Type": f"text/plain; charset={charset}",
        "Content-Encoding": "gzip",
    }
    return gzip.compress(body), headers


def _json_case(valid: bool) -> tuple[bytes, dict[str, str]]:
    if valid:
        body = json.dumps({"answer": 42, "ok": True}).encode("utf-8")
    else:
        body = b'{"answer": 42, "ok": True,}'  # trailing comma, unquoted True
    return body, {"Content-Type": "application/json; charset=utf-8"}


def _gzip_json_case(valid: bool) -> tuple[bytes, dict[str, str]]:
    text = json.dumps({"answer": 42, "text": "сорок два"}, ensure_ascii=False)
    if not valid:
        text = text[:-1] + ",}"  # Валидный UTF-8, невалидная JSON-грамматика.
    return gzip.compress(text.encode("utf-8")), {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Encoding": "gzip",
    }


def _charset_mismatch_case() -> tuple[bytes, dict[str, str]]:
    body = REPR_TEXT.encode("cp1251")
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    return body, headers


REPR_CASES = {
    "utf8": lambda: (REPR_TEXT.encode("utf-8"), {"Content-Type": "text/plain; charset=utf-8"}),
    "cp1251": lambda: (REPR_TEXT.encode("cp1251"), {"Content-Type": "text/plain; charset=cp1251"}),
    "charset-mismatch": _charset_mismatch_case,
    "gzip-ok": lambda: _gzip_case("utf-8"),
    "bad-gzip": lambda: (b"not actually gzip data", {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Encoding": "gzip",
    }),
    "json-ok": lambda: _json_case(True),
    "json-bad": lambda: _json_case(False),
    "gzip-json-ok": lambda: _gzip_json_case(True),
    "gzip-json-bad": lambda: _gzip_json_case(False),
}

MULTIPART_BOUNDARY = "homework-boundary-9f2c"


def _multipart_body() -> bytes:
    parts = [
        f"--{MULTIPART_BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="note"\r\n'
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "первая часть\r\n",
        f"--{MULTIPART_BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="payload"; filename="data.bin"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
        + "\x00\x01\x02binary-ish\r\n",
        f"--{MULTIPART_BOUNDARY}--\r\n",
    ]
    return "".join(parts).encode("utf-8", errors="surrogateescape")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "homework-fixture/1.0"

    def log_message(self, fmt, *args):  # noqa: D401 - quiet by default
        pass

    def _send_simple(self, status: int, body: bytes, headers: dict[str, str]):
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path

        if path == "/" or path == "/plain":
            self._send_simple(200, PLAIN_BODY, {"Content-Type": "text/plain; charset=utf-8"})
            return

        if path.startswith("/status/"):
            code = int(path.rsplit("/", 1)[-1])
            body = f"status {code}\n".encode("utf-8")
            self._send_simple(code, body, {"Content-Type": "text/plain; charset=utf-8"})
            return

        if path == "/chunked":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in (b"first-", b"second-", b"third\n"):
                self.wfile.write(f"{len(chunk):x}\r\n".encode("ascii"))
                self.wfile.write(chunk + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            return

        if path == "/broken-length":
            full_body = b"this body is declared longer than it really is"
            sent = full_body[: len(full_body) // 2]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(full_body)))
            self.end_headers()
            self.wfile.write(sent)
            self.close_connection = True
            return

        if path == "/timeout":
            time.sleep(30)
            return

        if path.startswith("/repr"):
            query = path.split("?", 1)[1] if "?" in path else ""
            params = dict(pair.split("=", 1) for pair in query.split("&") if "=" in pair)
            case = params.get("case", "")
            factory = REPR_CASES.get(case)
            if factory is None:
                self._send_simple(400, f"unknown case: {case}\n".encode(), {
                    "Content-Type": "text/plain; charset=utf-8",
                })
                return
            body, headers = factory()
            self._send_simple(200, body, headers)
            return

        if path == "/multipart":
            body = _multipart_body()
            self._send_simple(200, body, {
                "Content-Type": f'multipart/mixed; boundary="{MULTIPART_BOUNDARY}"',
            })
            return

        if path == "/multipart-broken-boundary":
            # Ни один delimiter в теле не соответствует boundary из заголовка.
            # Так парсер не может принять вторую часть за корректный multipart,
            # проигнорировав только первый испорченный delimiter как preamble.
            body = _multipart_body().replace(MULTIPART_BOUNDARY.encode(), b"wrong-boundary")
            self._send_simple(200, body, {
                "Content-Type": f'multipart/mixed; boundary="{MULTIPART_BOUNDARY}"',
            })
            return

        self._send_simple(404, b"not found\n", {"Content-Type": "text/plain; charset=utf-8"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    with socketserver.ThreadingTCPServer((args.host, args.port), Handler) as server:
        print(f"fixture_server: http://{args.host}:{args.port}/  (Ctrl+C для остановки)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

"""Готовит 4 TLS-фикстуры для этапа C домашнего задания.

Разовый скрипт подготовки стенда, не часть netdiag.py. Требует пакет
`cryptography` (pip install cryptography) — это не нарушает требование
«без внешних зависимостей» из assignment.md, потому что зависимость нужна
только здесь, для генерации сертификатов, а не в самом клиенте.

Запуск:

    python3 make_certs.py

Результат — каталог out/ рядом со скриптом:

    out/ca.crt                  — корень, которому должен доверять клиент
    out/valid.crt / valid.key   — обычный корректный сертификат
    out/expired.crt / .key     — валидное имя, срок истёк
    out/wrong-host.crt / .key  — валидный срок, неверный SAN
    out/untrusted.crt / .key   — валиден и по имени, и по сроку, но подписан
                                 ДРУГИМ корнем (не ca.crt)

Соответствие «файл → порт» намеренно не публикуется в README стенда:
студент определяет его по поведению собственного клиента (assignment.md,
раздел 5.3).
"""

from __future__ import annotations

import datetime
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

OUT = Path(__file__).parent / "out"


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write(name: str, key, cert: x509.Certificate):
    (OUT / f"{name}.key").write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (OUT / f"{name}.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _make_ca(name: str, common_name: str):
    key = _key()
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write(name, key, cert)
    return key, cert


def _make_leaf(
    name: str,
    ca_key,
    ca_cert: x509.Certificate,
    *,
    hostnames: list[str],
    not_before: datetime.datetime,
    not_after: datetime.datetime,
):
    key = _key()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0])])
    san_entries = []
    for host in hostnames:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            san_entries.append(x509.DNSName(host))
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=True,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write(name, key, cert)


def main():
    OUT.mkdir(exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)

    trusted_ca_key, trusted_ca_cert = _make_ca("ca", "Homework Trusted CA")
    other_ca_key, other_ca_cert = _make_ca("_other-ca", "Homework Other CA (not trusted by client)")

    _make_leaf(
        "valid",
        trusted_ca_key,
        trusted_ca_cert,
        hostnames=["localhost", "127.0.0.1"],
        not_before=now - datetime.timedelta(days=1),
        not_after=now + datetime.timedelta(days=365),
    )

    _make_leaf(
        "expired",
        trusted_ca_key,
        trusted_ca_cert,
        hostnames=["localhost", "127.0.0.1"],
        not_before=now - datetime.timedelta(days=400),
        not_after=now - datetime.timedelta(days=30),
    )

    _make_leaf(
        "wrong-host",
        trusted_ca_key,
        trusted_ca_cert,
        hostnames=["totally-different-name.invalid"],
        not_before=now - datetime.timedelta(days=1),
        not_after=now + datetime.timedelta(days=365),
    )

    _make_leaf(
        "untrusted",
        other_ca_key,
        other_ca_cert,
        hostnames=["localhost", "127.0.0.1"],
        not_before=now - datetime.timedelta(days=1),
        not_after=now + datetime.timedelta(days=365),
    )

    print(f"Готово: {OUT}")
    print("Клиенту нужен только out/ca.crt как доверенный корень.")
    print("out/_other-ca.* — вспомогательный файл для untrusted, клиенту не выдаётся.")


if __name__ == "__main__":
    main()

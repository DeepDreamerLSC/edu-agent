"""partner 侧测试模拟器(02 §6 tests/fixtures 同类):RSA 密钥对、断言签名、PKCE。

与 scripts/dev_auth_fixture.py 的 CLI 同语义;这里供 tests/contracts 导入。
RSA-1024 现场生成,联调/测试专用非生产凭据。
"""

from __future__ import annotations

import base64
import hashlib
import secrets


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _der_len(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    raw = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _der_int(value: int) -> bytes:
    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return bytes([0x02]) + _der_len(len(raw)) + raw


def _der_seq(*parts: bytes) -> bytes:
    body = b"".join(parts)
    return bytes([0x30]) + _der_len(len(body)) + body


def _is_prime(candidate: int) -> bool:
    if candidate < 2:
        return False
    for witness in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if candidate % witness == 0:
            return candidate == witness
    d, rounds = candidate - 1, 0
    while d % 2 == 0:
        d, rounds = d // 2, rounds + 1
    for _ in range(16):
        x = pow(secrets.randbelow(candidate - 3) + 2, d, candidate)
        if x in (1, candidate - 1):
            continue
        for _ in range(rounds - 1):
            x = pow(x, 2, candidate)
            if x == candidate - 1:
                break
        else:
            return False
    return True


def _prime(bits_count: int) -> int:
    while True:
        candidate = secrets.randbits(bits_count) | (1 << (bits_count - 1)) | 1
        if _is_prime(candidate):
            return candidate


def generate_rsa_key(bits: int = 1024) -> tuple[int, int, int]:
    """返回 (n, e, d)。Miller-Rabin 现场生成。"""
    half = bits // 2
    p = _prime(half)
    q = _prime(bits - half)
    while q == p:
        q = _prime(bits - half)
    e = 65537
    return p * q, e, pow(e, -1, (p - 1) * (q - 1))


def public_pem(n: int, e: int) -> str:
    """SubjectPublicKeyInfo PEM(与 identity._rsa_public_numbers 对偶;标准 base64 字母表)。"""
    rsa_key = _der_seq(_der_int(n), _der_int(e))
    algorithm = bytes.fromhex("300d06092a864886f70d0101010500")  # rsaEncryption
    spki = _der_seq(algorithm, bytes([0x03]) + _der_len(len(rsa_key) + 1) + b"\x00" + rsa_key)
    body = base64.b64encode(spki).decode()
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----\n"


def sign_rs256(header: dict, payload: dict, n: int, d: int) -> str:
    signing = (_b64url(json_encode(header)) + "." + _b64url(json_encode(payload)))
    digest = hashlib.sha256(signing.encode()).digest()
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + digest
    k = (n.bit_length() + 7) // 8
    padded = b"\x00\x01" + b"\xff" * (k - len(digest_info) - 3) + b"\x00" + digest_info
    return signing + "." + _b64url(pow(int.from_bytes(padded, "big"), d, n).to_bytes(k, "big"))


def json_encode(payload: dict) -> bytes:
    return json_dumps(payload)


def json_dumps(payload: dict) -> bytes:
    import json
    return json.dumps(payload, separators=(",", ":")).encode()


def pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode()).digest())

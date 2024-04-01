import base64
import hashlib
import hmac
import json
import logging
import pathlib
import re
import time
import urllib3

from raspi_remoteid_receiver.healthcheck.exceptions import *


def get_hs256_signature_bytes(*args, key: bytes, msg: bytes) -> bytes:
    """Generates an HMAC SHA-256 (HS256) signature in byte form given a key
    and message in bytes."""
    return hmac.new(key, msg, hashlib.sha256).digest()


def get_hs256_signature_str_from_bytes(*args, key: bytes, msg: bytes) -> str:
    """Generates an HMAC SHA-256 (HS256) signature as a string with padding
    removed.

    :param args: None
    :param key: Bytes-like object
    :param msg: Bytes-like object
    :return: string object in form 'header.payload'
    """
    return base64.urlsafe_b64encode(
        get_hs256_signature_bytes(
            key=key,
            msg=msg,
        ),
    ).rstrip(b"=").decode("utf-8")


def get_hs256_signature_str(*args, key: str, msg: str) -> str:
    """Generates an HMAC SHA-256 (HS256) signature as a string with padding
    removed."""
    return get_hs256_signature_str_from_bytes(
        key=key.encode("utf-8"),
        msg=msg.encode("utf-8"),
    )


def get_hs256_message_str_from_bytes(
        *args,
        header: bytes,
        payload: bytes,
) -> str:
    """Generates a string representation of the base64 URL safe encoded
    header and payload combined with a period.
    Example:
                                non-escaped characters
        Header:                    v            v
            b'\xb6\x18\xac"\xc0\x01j\xc7\xba\xe0I\xdc\xa1\xd8\xa7\x80\xe7\xc1\xca\xd7\xac'
                          ^
                note this must be escaped if delimited with double quotes
                                                    this must be escaped if delimited with single quotes
        Payload:                                                                           v
            b"\xad\xeakz\xc7\xa7\xb5\xe7A\xc8\x04\xad\xae)\xe0\x02wH\xb1DKI\xa7\xde\xfb\xf0't\xf6\x9du\xe7"
                      ^^                ^                ^        ^^    ^^^                 ^        ^
                    non-escaped characters              more non-escaped characters         some more!

        Output:
            "thisIsABase64EncodingOfBytes.representedByAStringAndIsURLSafe-_AndPadded="

    :param args: None
    :param header: bytes-like object generated from encoding header string characters using UTF-8
    :param payload: bytes-like object generated from encoding payload string characters using UTF-8
    :return: concatenation of string representation of base64 URL safe encoded header and payload
    """  # noqa

    # Encode bytes in base64
    header_base64 = base64.urlsafe_b64encode(header).rstrip(b"=")
    payload_base64 = base64.urlsafe_b64encode(payload).rstrip(b"=")
    # Convert base64URL string representation characters to UTF-8 characters
    header_base64_str = header_base64.decode("utf-8")
    payload_base64_str = payload_base64.decode("utf-8")
    # Create message string
    message_str = header_base64_str + "." + payload_base64_str
    return message_str


def get_hs256_message_str(*args, header: str, payload: str) -> str:
    # Convert strings to UTF-8 bytes
    header_bytes = header.encode("utf-8")
    payload_bytes = payload.encode("utf-8")
    return get_hs256_message_str_from_bytes(
        header=header_bytes,
        payload=payload_bytes,
    )


def validate_jws_protected_header(
        *args,
        header: str,
        payload: str,
) -> tuple[str, str]:
    """Converts all single quotes to double quotes and removes all delimiting
    whitespace. Raises JSONValueError if invalid JSON.

    :param header: header in string JSON representation
    :param payload: payload in string JSON representation
    :return: validated header and payload.
    """

    header = header.strip()
    payload = payload.strip()
    # Remove whitespace characters by converting to JSON object and back
    # to string
    try:
        header_json = json.loads(header)
    except json.JSONDecodeError as exc:
        raise JSONValueError(f"Invalid JSON format for JWT header: {exc}")
    try:
        alg = header_json["alg"]
    except KeyError:
        raise JSONValueError(
            'JWS Protected Header must contain the "alg" field',
        )
    if alg != "HS256":
        raise JSONValueError(f'JWT algorithm must be "HS256" not "{alg}"')
    try:
        typ = header_json["typ"]
    except KeyError:
        raise JSONValueError(
            'JWS Protected header must contain the "JWT" field',
        )
    if typ != "JWT":
        raise JSONValueError(
            f'JWS protected header field "typ" must be "JWT" not "{typ}"',
        )
    header = json.dumps(header_json, separators=(",", ":"))

    if payload != "":
        try:
            payload_json = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise JSONValueError(f"Invalid JSON format for JWT payload: {exc}")
        payload = json.dumps(payload_json, separators=(",", ":"))

    return header, payload


def get_JWT_str_with_byte_key(
        *args, header: str, payload: str, key: bytes) -> str:
    header, payload = validate_jws_protected_header(
        header=header,
        payload=payload,
    )
    # Convert message to bytes
    message_str = get_hs256_message_str(header=header, payload=payload)
    signature_str = get_hs256_signature_str_from_bytes(
        key=key, msg=message_str.encode("utf-8"))
    return message_str + "." + signature_str


def get_JWT_str(*args, header: str, payload: str, key: str) -> str:
    """Generates a JSON Web Token (JWT) encoded as a base64 URL safe (RFC 4648)
    UTF-8 string according to RFC 7519 with base64 padding stripped. Converts
    all single quotes to double quotes.

    :param header: JWS Protected Header in string JSON representation
    :param payload: JSON string representation
    :param key: plaintext UTF-8 string, recommended at least 256 bytes long
    :return: the generated JWT as a UTF-8 string
    """

    header, payload = validate_jws_protected_header(
        header=header,
        payload=payload,
    )

    # Convert message to bytes
    message_str = get_hs256_message_str(header=header, payload=payload)
    signature_str = get_hs256_signature_str(key=key, msg=message_str)
    return message_str + "." + signature_str


class Healthcheck:
    """Class to simplify the sending of a healthcheck."""

    def __init__(
            self,
            key_file_name: pathlib.Path,
            url: str,
            logger: logging.Logger,
    ):

        self._key_file_name = key_file_name
        self._url = url
        self._logger = logger
        self._key_str, self._id_str = self._read_key_file()
        print("DEBUG: key str:", self._key_str)

    def _read_key_file(self) -> tuple[bytes, str]:
        """Reads the key and ID from a PEM file as strings. Raises FileNotFound
        error the if file doesn't exist. Raises ValueError if the key or ID
        are invalid.
        """

        self._logger.info("Opening file '%s'", self._key_file_name)
        try:
            with open(self._key_file_name, 'rt') as file:
                in_key = False
                base64_key_str = ""
                in_id = False
                id_str = ""
                for line in file:
                    line = line.strip()
                    if line == "-----BEGIN KEY-----":
                        in_key = True
                    elif line == "-----END KEY-----":
                        in_key = False
                    elif line == "-----BEGIN ID-----":
                        in_id = True
                    elif line == "-----END ID-----":
                        in_id = False
                    elif in_key:
                        base64_key_str += line
                    elif in_id:
                        id_str += line
        except FileNotFoundError as exc:
            self._logger.error(
                "Failed to open file '%s'",
                self._key_file_name,
            )
            raise FileNotFoundError from exc
        except UnicodeDecodeError as exc:
            self._logger.error(
                "Failed to parse file '%' containing non-unicode characters.",
                self._key_file_name,
            )
            raise ValueError from exc
        if in_key:
            msg = "No -----END KEY----- detected in file."
            self._logger.error(msg)
            raise ValueError(msg)
        if in_id:
            msg = "No -----END ID----- detected in file."
            self._logger.error(msg)
            raise ValueError(msg)
        if not re.match(
            r"^[A-Za-z0-9+/]*={0,2}$",
                base64_key_str):  # not URL safe characters
            self._logger.error("Invalid base64 key: '%s'", base64_key_str)
            raise ValueError(f"Invalid base64 key in file: '{file}'")
        print(base64_key_str, flush=True)
        key_bytes = base64.b64decode(base64_key_str)

        return key_bytes, id_str

    def _get_JWT(self, exp_time):
        header = '{"alg":"HS256","typ":"JWT"}'
        now = time.time()
        exp = now + exp_time
        iat = int(now)
        exp = int(exp)
        payload = f'{{"iat":{iat},"exp":{exp}}}'
        return get_JWT_str_with_byte_key(
            header=header, payload=payload, key=self._key_str)

    def send_healthcheck(
            self,
            status: str = "Healthy",
            pkt_count: int = 3,
            exp_time: int | float = 30,
    ) -> bool:
        """Attempts to send a healthcheck to the url. Returns True on success,
        returns False otherwise"""

        headers = {
            "Authorization": f"Bearer {self._get_JWT(exp_time)}",
            "Content-Type": "application/json",
        }

        fields = {
            "Status": status,
            "Received-Packets": pkt_count,
            "ID": "pi1",
        }

        print(headers)
        print(fields)
        print(json.dumps(fields))

        try:
            response = urllib3.request(
                "POST",
                self._url,
                preload_content=True,  # response should be small
                headers=headers,
                body=json.dumps(fields, separators=(",", ":")),
            )
        except urllib3.exceptions.HTTPError as exc:
            self._logger.error("urllib3 HTTP Error: %s", exc)
            return False

        print(response.data)

        return response.status == 200


if __name__ == "__main__":

    header = '{"alg":"HS256","typ":"JWT"}'
    payload = '{"exp":"2147483647"}'
    key = (b"0" * 32).decode("utf-8")
    print(key)
    print(get_JWT_str(key=key, header=header, payload=payload))

    logging.getLogger().setLevel(logging.DEBUG)
    logger = logging.getLogger("test")
    logger.setLevel(logging.DEBUG)
    healthchecker = Healthcheck(
        key_file_name=pathlib.Path.home() / ".remoteid" / "website_key.pem",
        url="https://cursedindustries.com/wp-json/healthcheck/v1/healthcheck",
        logger=logger,
    )
    print(healthchecker.send_healthcheck(exp_time=3600))

import base64
import unittest

import raspi_remoteid_receiver.healthcheck.healthcheck as uut
import raspi_remoteid_receiver.healthcheck.exceptions as uut_exceptions


class GetHS256SignatureStrTestCase(unittest.TestCase):
    """Tests method get_hs256_signature_str()"""

    def test_key_is_str_of_zeros(self):
        key = "00000000000000000000000000000000"
        tests = [
            {
                "msg": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOiIyMTQ3NDgzNjQ3In0",
                "sig": "Oz_lnbf2cpaM9RNPgyGISkb-OaK26An5UqaH2eR0LyQ",
            },
            {
                "msg": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3MTE5NDEwODMsImV4cCI6MTcxMTk0MTA4NH0",
                "sig": "16R28mBW8B_S-4TKSoztae9Nhp5XNE_Ph1XMosQ4Aww",
            },
        ]
        for test in tests:
            with self.subTest(msg=test):
                self.assertEqual(
                    test["sig"],
                    uut.get_hs256_signature_str(
                        key=key,
                        msg=test["msg"],
                    ),
                )


class GetJWTStrWithByteKey(unittest.TestCase):
    """Tests method get_hs256_signature_str_with_byte_key()"""

    def test_start_open_ssh_key(self):
        key = b"openssh-key-v1\x00\x00\x00\x00\x00none\x00\x00\x00\x00none\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00ssh-rsa\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        header = '{"alg":"HS256","typ":"JWT"}'
        payload = '{"exp":"2147483647"}'
        self.assertEqual(
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOiIyMTQ3NDgzNjQ3In0.IEXUEfUGBMyJ-gCvmzVgWJtjlxNjjiQHDon8HudRSvA",
            uut.get_JWT_str_with_byte_key(
                header=header,
                payload=payload,
                key=key,
            ),
        )


class GetHS256SignatureStringTestCase(unittest.TestCase):
    """Tests method get_hs256_signature_str()"""

    def setUp(self) -> None:
        self.key_256_bits_zeros = (b"0" * 32).decode("utf-8")

    def test_unittest_setup(self):
        self.assertEqual(
            "00000000000000000000000000000000",
            self.key_256_bits_zeros,
        )

    def test_empty_header_raises_error(self):
        """Verifies that using an empty JSON header raises an error."""
        header = "{}"
        payload = "{}"
        key = self.key_256_bits_zeros
        self.assertRaises(
            uut_exceptions.JSONValueError,
            uut.get_JWT_str,
            **{"key": key, "header": header, "payload": payload},
        )

    def test_alg_none_raises_error(self):
        """Verifies that using no JSON Web Signature (JWS) for the JSON Web
        Token (JWT) raises an error."""

        header = '{"alg":"none"}'
        payload = "{}"
        key = self.key_256_bits_zeros
        self.assertRaises(
            uut_exceptions.JSONValueError,
            uut.get_JWT_str,
            **{"key": key, "header": header, "payload": payload},
        )

    def test_alg_rs256_raises_error(self):
        """Verifies that using the RS256 algorithm to generate a JSON Web
        Signature raises an error."""

        header = '{"alg":"RS256"}'
        payload = "{}"
        key = self.key_256_bits_zeros
        self.assertRaises(
            uut_exceptions.JSONValueError,
            uut.get_JWT_str,
            **{"key": key, "header": header, "payload": payload},
        )

    def test_missing_typ_raises_error(self):
        """Verifies that missing the type attribute raises an error."""

        header = '{"alg":"HS256"}'
        payload = "{}"
        key = self.key_256_bits_zeros
        self.assertRaises(
            uut_exceptions.JSONValueError,
            uut.get_JWT_str,
            **{"key": key, "header": header, "payload": payload},
        )

    def test_typ_JWE_raises_error(self):
        """Verifies that using JWE for the type field raises an error."""

        header = '{"alg":"HS256","typ":"JWE"}'
        payload = "{}"
        key = self.key_256_bits_zeros
        self.assertRaisesRegex(
            uut_exceptions.JSONValueError,
            r'"JWT" not "JWE"',
            uut.get_JWT_str,
            **{"key": key, "header": header, "payload": payload},
        )

    def test_spaces_are_removed(self):
        """Verifies that spaces are removed from the JSON input."""

        header = ' { "alg" : "HS256" , "typ" : "JWT" }'
        payload = "{}"
        key = self.key_256_bits_zeros
        self.assertEqual(
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.i_Ip9qvXLD9wBkTC4h0y6YzYGgt9j0KgPU4afAqN11c",
            uut.get_JWT_str(key=key, header=header, payload=payload),
        )

    def test_whitespace_is_removed(self):
        """Verifies that whitespace is removed from the JSON input."""

        header = '\n\t\r { \r\t\n "alg" \n\r\t : \t\r\n "HS256" \t\n\r , \t\t "typ" : \n\r\n\t "JWT" \t }\r\n'
        payload = "{}"
        key = self.key_256_bits_zeros
        self.assertEqual(
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.i_Ip9qvXLD9wBkTC4h0y6YzYGgt9j0KgPU4afAqN11c",
            uut.get_JWT_str(key=key, header=header, payload=payload),
        )

    def test_padding_is_removed(self):
        """Verifies that padding characters '=' are removed from the JSON
        input"""

        header = '{"alg":"HS256","typ":"JWT","crit":["exp"]}'
        payload = '{"exp":"2147483647"}'
        key = self.key_256_bits_zeros
        self.assertEqual(
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImNyaXQiOlsiZXhwIl19.eyJleHAiOiIyMTQ3NDgzNjQ3In0.qkAb0eWeUfyZdO_afbLKKfl2lzin3zAaoKvbK4idgXs",
            uut.get_JWT_str(key=key, header=header, payload=payload),
        )
        #     THIS: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImNyaXQiOlsiZXhwIl19.eyJleHAiOiIyMTQ3NDgzNjQ3In0.qkAb0eWeUfyZdO_afbLKKfl2lzin3zAaoKvbK4idgXs
        # NOT THIS:
        # eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImNyaXQiOlsiZXhwIl19.eyJleHAiOiIyMTQ3NDgzNjQ3In0=.Ag725j5TyIaCSc_EhaBVN4I0OT5N6gbaUzSAEJKRn4s=


class HealthcheckExceptionsTestCase(unittest.TestCase):
    """Tests exceptions defined by 'healthcheck.exceptions'"""

    def test_healthcheck_error_is_jwt_error_ancestor(self):
        """Verifies JWTError is a subclass of HealthcheckError"""
        self.assertTrue(
            issubclass(
                uut_exceptions.JWTError,
                uut_exceptions.HealthcheckError,
            ),
        )

    def test_healthcheck_error_is_json_value_error_ancestor(self):
        """Verifies JSONValueError is a subclass of HealthcheckError"""
        self.assertTrue(
            issubclass(
                uut_exceptions.JSONValueError,
                uut_exceptions.HealthcheckError,
            ),
        )


if __name__ == "__main__":
    unittest.main()

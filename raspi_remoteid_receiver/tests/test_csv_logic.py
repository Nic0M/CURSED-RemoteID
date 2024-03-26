import unittest

import raspi_remoteid_receiver.core.csv_creator as csv_module_under_test


class IsValidSrcAddrTestCase(unittest.TestCase):
    """Tests method is_valid_src_addr()"""

    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass

    def test_is_valid_src_addr_empty(self):
        """Verifying empty string is not a valid source address"""
        self.assertFalse(csv_module_under_test.is_valid_src_addr(""))

    def test_is_valid_src_addr_non_hex(self):
        """Verifying that non-hex letters are invalid"""
        invalid_names = [
            "MAC-GG:GG:GG:GG:GG:GG",
            "BDA-GH:IJ:KL:MN:OP:QR",
            "MAC-ST:UV:WX:YZ:AB:CD",
        ]
        for src_addr in invalid_names:
            with self.subTest(msg=src_addr):
                self.assertFalse(
                    csv_module_under_test.is_valid_src_addr(src_addr),
                )

    def test_is_valid_src_addr_invalid_prefix(self):
        """Tests prefixes besides 'MAC-' and 'BDA-'"""
        invalid_names = [
            "BLE-00:00:00:00:00:00",  # invalid prefix
            "MCA-00:00:00:00:00:00",  # scrambled letters
            "ABD-FF:FF:FF:FF:FF:FF",
        ]
        for src_addr in invalid_names:
            with self.subTest(msg=src_addr):
                self.assertFalse(
                    csv_module_under_test.is_valid_src_addr(src_addr),
                )

    def test_is_valid_src_addr_lower_case(self):
        """Verifying that partially lowercase source addresses are invalid"""
        # All correctly formatted, but have at least one lower case character
        invalid_names = [
            "mac-00:00:00:00:00:00",
            "bda-00:00:00:00:00:00",
            "MaC-99:99:99:99:99:99",
            "MAC-aa:bb:cc:dd:ee:ff",
            "BDA-ff:ee:dd:cc:bb:aa",
        ]
        for src_addr in invalid_names:
            with self.subTest(msg=src_addr):
                self.assertFalse(
                    csv_module_under_test.is_valid_src_addr(src_addr),
                )

    def test_is_valid_src_addr_invalid_format(self):
        """Verifying invalid formats are invalid"""
        invalid_names = [
            "MAC-000000000000",  # no colons
            "00:00:00:00:00:00",  # no prefix
            "999999999999",  # no colons or prefix
            "AA:BB:CC:DD:EE:FF",  # no prefix
            "BDA-AA:BB:CC:DD:EE:FF:00",  # has 14 hex digits
            "MACAA:BB:CC:DD:EE:FF",  # missing dash
        ]
        for src_addr in invalid_names:
            with self.subTest(msg=src_addr):
                self.assertFalse(
                    csv_module_under_test.is_valid_src_addr(src_addr),
                )

    def test_is_valid_src_addr_whitespace(self):
        """Verifying names with whitespace are invalid"""
        invalid_names = [
            "MAC-00 00 00 00 00 00",  # separated by space instead of colon
            " MAC-FF:FF:FF:FF:FF:FF",  # has leading whitespace
            "\nMAC-AA:AA:AA:AA:AA:AA",
            "\tBDA-11:23:57:64:99:11",
            "MAC-BB:BB:BB:BB:BB:BB ",  # has trailing white space
            "MAC-B1:B9:B7:5B:B3:22\n",
            "BDA-31:41:59:26:53:58\t",
            "BDA 00:00:00:00:00:00",  # whitespace instead of dash
        ]
        for src_addr in invalid_names:
            with self.subTest(msg=src_addr):
                self.assertFalse(
                    csv_module_under_test.is_valid_src_addr(src_addr),
                )

    def test_is_valid_src_addr_valid_names(self):
        """Verifying valid source address names"""
        valid_names = [
            "MAC-01:AA:BB:CC:DD:EE",
            "BDA-FF:FF:EE:EE:CC:00",
            "MAC-21:82:81:82:85:90",
            "BDA-98:76:45:23:10:FF",
        ]
        for src_addr in valid_names:
            with self.subTest(msg=src_addr):
                self.assertTrue(
                    csv_module_under_test.is_valid_src_addr(src_addr),
                )


class CreateRowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.header_row = csv_module_under_test.header_row

    def tearDown(self) -> None:
        pass

    @staticmethod
    def generate_default_packet(
            src_addr="MAC-00:00:00:00:00:00",
            unique_id="",
            timestamp="1970-01-01 00:00:00.0",
            heading=181,
            gnd_speed=0.0,
            vert_speed=0.0,
            lat=0.0,
            lon=0.0,
    ) -> list:
        packet = [
            src_addr, unique_id, timestamp, heading,
            gnd_speed, vert_speed, lat, lon,
        ]
        return packet

    def test_create_header_row(self):
        """Checks if list of elements for header row is created properly."""
        self.assertEqual(
            self.header_row,
            [
                "Source Address", "Unique ID", "Timestamp", "Heading",
                "Ground Speed", "Vertical Speed", "Latitude", "Longitude",
            ],
            "header row does not match",
        )

    def test_create_data_row_missing_src_addr(self):
        """Verifies that error is thrown for missing"""
        self.assertRaisesRegex(
            csv_module_under_test.MissingPacketFieldError,
            "Missing Source Address",
            csv_module_under_test.create_row,
            self.generate_default_packet(),  # TODO: fix packet generation
        )

    def test_create_data_row_invalid_src_addr(self):
        """Verifies that error is thrown for missing"""
        # TODO: packet generation is not right

        # self.assertRaisesRegex(
        #     csv_module_under_test.InvalidPacketFieldError,
        #     "Invalid Source Address",
        #     csv_module_under_test.create_row,
        #     self.generate_default_packet(src_addr="abracadabra")
        # )


if __name__ == "__main__":
    unittest.main()

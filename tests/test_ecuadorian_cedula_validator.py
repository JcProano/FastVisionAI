import unittest

from src.core.person_database import EcuadorianCedulaValidator, PersonDataValidationError


class EcuadorianCedulaValidatorTests(unittest.TestCase):
    def test_valid_cedula_only_confirms_structure_and_checksum(self):
        self.assertEqual(EcuadorianCedulaValidator.validate("1710034065"), "1710034065")
        self.assertTrue(EcuadorianCedulaValidator.is_valid("0926687856"))

    def test_length_and_non_numeric_characters(self):
        for value in ("171003406", "17100340655", "17100A4065", "１７１００３４０６５"):
            with self.subTest(value=value), self.assertRaises(PersonDataValidationError):
                EcuadorianCedulaValidator.validate(value)

    def test_province_third_digit_and_checksum(self):
        for value in ("0010034065", "2510034065", "1760034065", "1710034064"):
            with self.subTest(value=value), self.assertRaises(PersonDataValidationError):
                EcuadorianCedulaValidator.validate(value)


if __name__ == "__main__": unittest.main()

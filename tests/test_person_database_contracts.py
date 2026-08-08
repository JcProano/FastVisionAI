import dataclasses
import unittest
import uuid

import numpy as np

from src.core.person_database import (
    PersonCreateRequest, PersonDataValidationError, PersonDatabaseStats,
    PersonRecord, PersonSearchQuery, PersonUpdateRequest,
)


class PersonDatabaseContractTests(unittest.TestCase):
    def test_create_normalizes_safe_fields(self):
        request = PersonCreateRequest(
            str(uuid.uuid4()), "1710034065", "  Ana   María ", " Pérez ",
            phone="+593 (99) 123-4567", email="USER@Example.COM", birth_date="2000-01-02",
        )
        self.assertEqual(request.first_name, "Ana María")
        self.assertEqual(request.phone, "+593991234567")
        self.assertEqual(request.email, "USER@example.com")

    def test_invalid_administrative_fields(self):
        identity = str(uuid.uuid4())
        invalid = (
            {"first_name": ""}, {"last_name": "bad\x00name"},
            {"email": "invalid"}, {"phone": "12"}, {"birth_date": "2999-01-01"},
        )
        for changes in invalid:
            values = dict(person_id=identity, cedula="1710034065",
                          first_name="Temporary", last_name="Person")
            values.update(changes)
            with self.subTest(changes=changes), self.assertRaises(PersonDataValidationError):
                PersonCreateRequest(**values)

    def test_public_contracts_have_no_biometric_payloads(self):
        types = (PersonCreateRequest, PersonUpdateRequest, PersonRecord,
                 PersonSearchQuery, PersonDatabaseStats)
        forbidden = {"embedding", "template", "image", "model", "frame", "thumbnail"}
        for contract in types:
            fields = dataclasses.fields(contract)
            self.assertTrue({field.name.casefold() for field in fields}.isdisjoint(forbidden))
            self.assertTrue(all("ndarray" not in str(field.type).casefold() for field in fields))
        self.assertNotIn(np.ndarray, [field.type for contract in types
                                     for field in dataclasses.fields(contract)])


if __name__ == "__main__": unittest.main()

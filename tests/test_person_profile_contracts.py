import dataclasses
import unittest

from src.ui.person_profile import PersonProfileDTO, PersonProfileOperationDTO


class PersonProfileContractTests(unittest.TestCase):
    def test_public_contracts_exclude_biometric_internals(self):
        forbidden = {
            "embedding", "embeddings", "template", "templates", "landmarks",
            "weights_sha256", "model", "path", "service", "gallery",
        }
        for contract in (PersonProfileDTO, PersonProfileOperationDTO):
            names = {field.name.casefold() for field in dataclasses.fields(contract)}
            self.assertFalse(names & forbidden)


if __name__ == "__main__":
    unittest.main()

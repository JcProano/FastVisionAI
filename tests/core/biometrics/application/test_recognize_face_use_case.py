import unittest

from src.core.biometrics.application import RecognizeFaceUseCase
from src.core.biometrics.domain import RecognitionPolicy, RecognitionState
from tests.core.biometrics.fakes import (
    FakeEmbedding,
    FakeIdentity,
    FakeIndexedTemplate,
    FakeMatchCandidate,
    FakeMatcher,
    FakeTemplate,
    InMemoryBiometricGallery,
)


class RecognizeFaceUseCaseTests(unittest.TestCase):
    def gallery_with_identity(self) -> tuple[InMemoryBiometricGallery, FakeIdentity]:
        gallery = InMemoryBiometricGallery()
        identity = FakeIdentity("person-1", "Ada Lovelace")
        gallery.identities[identity.person_id] = identity
        gallery.items.append(
            FakeIndexedTemplate(
                0,
                FakeTemplate(identity, 3, "fake-model", "1", "a" * 64),
                "template-1",
            )
        )
        return gallery, identity

    def test_empty_gallery_is_a_structural_outcome(self) -> None:
        matcher = FakeMatcher()
        result = RecognizeFaceUseCase(
            InMemoryBiometricGallery(), matcher
        ).execute(FakeEmbedding())

        self.assertIs(result.state, RecognitionState.NO_GALLERY)
        self.assertEqual(matcher.calls, 0)

    def test_default_policy_keeps_candidates_informational(self) -> None:
        gallery, identity = self.gallery_with_identity()
        matcher = FakeMatcher((FakeMatchCandidate(identity, 0.92, 1),))

        result = RecognizeFaceUseCase(gallery, matcher).execute(FakeEmbedding())

        self.assertIs(result.state, RecognitionState.NOT_EVALUATED)
        self.assertFalse(result.evaluated)
        self.assertEqual(result.person_id, "person-1")

    def test_explicit_policy_can_produce_a_match(self) -> None:
        gallery, identity = self.gallery_with_identity()
        matcher = FakeMatcher((FakeMatchCandidate(identity, 0.92, 1),))
        policy = RecognitionPolicy(
            automatic_decision_enabled=True,
            match_threshold=0.8,
            policy_name="unit-test",
        )

        result = RecognizeFaceUseCase(gallery, matcher, policy).execute(
            FakeEmbedding()
        )

        self.assertIs(result.state, RecognitionState.MATCH)
        self.assertTrue(result.evaluated)


if __name__ == "__main__":
    unittest.main()

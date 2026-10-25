import tempfile
import unittest
from pathlib import Path

from app.models.user import UserProfile
from app.services.wardrobe_store import create_store


class ProfilePersistenceTests(unittest.TestCase):
    def test_profile_survives_store_recreation_and_can_be_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "aura.sqlite3")
            first = create_store(path)
            profile = UserProfile(
                shopping_fit="mens", preferred_styles=["minimalist", "smart casual"],
                preferred_colors=["neutral"], usual_size="M", default_budget_per_outfit=50,
            )
            first.save_profile("profile-user", profile)
            reloaded = create_store(path).get_profile("profile-user")
            self.assertEqual(reloaded.shopping_fit, "mens")
            self.assertEqual(reloaded.preferred_styles, ["minimalist", "smart casual"])
            self.assertEqual(reloaded.default_budget_per_outfit, 50)
            self.assertTrue(create_store(path).delete_profile("profile-user"))
            self.assertIsNone(create_store(path).get_profile("profile-user").shopping_fit)


if __name__ == "__main__":
    unittest.main()

import unittest

from agents.core.planner import TripPlanner
from agents.products.client import make_search_request


class ProfilePlanningTests(unittest.TestCase):
    def test_profile_changes_search_constraints(self):
        planner = TripPlanner(
            "profile-session",
            {"styles": [], "preferred_colors": [], "occasions": [], "per_outfit_budget": None},
            {"shopping_fit": "mens", "preferred_styles": ["minimalist", "smart casual"],
             "preferred_colors": ["neutral"], "default_budget_per_outfit": 50},
            [], None, [],
        )
        request = planner._base_search("shirt", "top")
        self.assertIn("men's", request["query"])
        self.assertIn("minimalist", request["query"])
        self.assertEqual(request["max_price"], 50)
        self.assertEqual(request["colors"], [])
        self.assertIn("smart casual", request["tags"])


if __name__ == "__main__":
    unittest.main()

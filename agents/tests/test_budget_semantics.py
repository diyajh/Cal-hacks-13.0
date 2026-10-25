"""Regression coverage for total outfit budgets and conservative style filtering."""
import asyncio
import unittest
from unittest.mock import patch

from agents.core.engine import plan_shopping


def _product(pid, name, category, price, tags=None):
    return {
        "id": pid, "name": name, "category": category, "subcategory": None,
        "price": price, "currency": "USD", "retailer": "Test retailer",
        "image_url": "https://images.example.test/" + pid + ".jpg",
        "product_url": "https://retailer.example.test/" + pid,
        "description": name, "colors": ["black"], "tags": tags or [],
        "available": True, "source": "apify", "source_id": pid,
    }


def _run(text, products, profile=None):
    def search(req):
        return [p for p in products if not req.get("category") or p["category"] == req["category"]], "product_service", {"received": len(products), "kept": len(products)}

    with patch("agents.core.agent_logic.search_products", side_effect=search):
        return asyncio.run(plan_shopping(text, "budget-test-user", "budget-test-session", profile=profile))["final_recommendation"]


class TestBudgetSemantics(unittest.TestCase):
    def test_explicit_top_bottom_shoes_are_complete_and_within_budget(self):
        rec = _run("One date night outfit under $100 with a top, bottom, and shoes", [
            _product("top-40", "Smart Casual Shirt", "top", 40),
            _product("bottom-30", "Tailored Trousers", "bottom", 30),
            _product("shoe-25", "Leather Loafers", "shoes", 25),
        ], {"shopping_fit": "mens", "preferred_styles": ["smart casual"]})
        self.assertTrue(rec["all_constraints_satisfied"])
        self.assertEqual(len(rec["outfits"]), 1)
        self.assertEqual({item["product"]["category"] for item in rec["outfits"][0]["items"]}, {"top", "bottom", "shoes"})
        self.assertLessEqual(rec["planned_spend"], 100)
        self.assertNotIn("heel", " ".join(item["product"]["name"].lower() for item in rec["outfits"][0]["items"]))

    def test_two_products_totaling_157_95_are_rejected(self):
        rec = _run("One date night outfit under $100", [
            _product("dress-60", "Smart Evening Shirt", "dress", 60),
            _product("shoe-97", "Classic Evening Shoe", "shoes", 97.95),
        ])
        self.assertFalse(rec["all_constraints_satisfied"])
        self.assertEqual(rec["status"], "needs_user_input")
        self.assertEqual(rec["outfits"], [])
        self.assertTrue(any(v["constraint"] == "complete_outfit" for v in rec["constraint_violations"]))

    def test_sixty_plus_thirty_passes_as_one_hundred_total(self):
        rec = _run("One date night outfit under $100", [
            _product("dress-60", "Smart Evening Shirt", "dress", 60),
            _product("shoe-30", "Classic Evening Shoe", "shoes", 30),
        ])
        self.assertTrue(rec["all_constraints_satisfied"])
        self.assertEqual(rec["planned_spend"], 90.0)
        self.assertEqual(rec["requested_budget"], 100.0)
        self.assertEqual(rec["remaining_budget"], 10.0)

    def test_smart_casual_mens_rejects_platform_heel(self):
        rec = _run("One date night outfit under $200", [
            _product("dress-80", "Men's Smart Casual Shirt Dress", "dress", 80),
            _product("heel-70", "Cuban Heel Platform Shoe", "shoes", 70, ["high heel", "platform heel"]),
        ], {"shopping_fit": "mens", "preferred_styles": ["smart casual"]})
        self.assertFalse(rec["all_constraints_satisfied"])
        self.assertEqual(rec["outfits"], [])
        self.assertNotIn("Cuban Heel", rec["message"])


if __name__ == "__main__":
    unittest.main()

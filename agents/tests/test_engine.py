"""Run from repo root:  python -m unittest agents.tests.test_engine -v
Uses the local bus + fallback/mock catalog, so no network, keys or uagents install needed."""
import asyncio
import os
import unittest

os.environ.pop("PRODUCT_SEARCH_URL", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from agents import config  # noqa: E402

config.PRODUCT_SEARCH_URL = ""
config.OPENAI_API_KEY = config.ANTHROPIC_API_KEY = ""

from agents.core.contract import SHOPPING_REQUEST_KEYS  # noqa: E402
from agents.core.engine import modify_shopping, plan_shopping  # noqa: E402
from agents.core.parser import parse_request  # noqa: E402

CANONICAL = ("I'm going to San Diego for five days. I need five outfits. Each outfit should be under $50 and my "
             "total budget is $500. I want a beachy neutral aesthetic. One outfit needs a crochet top and skirt. "
             "I like beige and white. I don't like neon colors. I already own white sneakers. Remember that I own them.")

REC_KEYS = {"session_id", "status", "parsed_request", "outfits", "total_new_purchase_cost", "total_budget",
            "owned_items_used", "reused_items", "agent_events", "constraint_violations",
            "all_constraints_satisfied", "message", "wardrobe_reused_count", "unique_purchase_count",
            "purchases_avoided", "outfits_unlocked", "wardrobe_value_avoided", "candidate_reused_count"}
OUTFIT_KEYS = {"id", "title", "day", "occasion", "match_score", "score_breakdown", "items", "total_value",
               "new_purchase_cost", "why_it_works", "constraints_satisfied"}
ITEM_KEYS = {"id", "source_type", "source", "product", "wardrobe_item", "purchase_required", "reused", "used_in_outfits"}
EVENT_KEYS = {"id", "session_id", "agent", "type", "status", "message", "outfit_id", "timestamp"}


def run(coro):
    return asyncio.run(coro)


class TestParser(unittest.TestCase):
    def test_currency_never_becomes_look_count(self):
        cases = [
            ("five days under $50 per outfit", 5, 50),
            ("5 days under $50 each", 5, 50),
            ("create 3 looks under $75", 3, 75),
            ("create 5 outfits under fifty dollars", 5, 50),
            ("I need 10 looks for a 5-day trip under $40 each", 10, 40),
        ]
        for text, looks, budget in cases:
            request = parse_request(text, "s", "u", use_llm=False)["request"]
            self.assertEqual(request["number_of_outfits"], looks, text)
            self.assertEqual(request["per_outfit_budget"], budget, text)

    def test_canonical(self):
        r = parse_request(CANONICAL, "s", "u", use_llm=False)["request"]
        self.assertEqual(list(r.keys()), SHOPPING_REQUEST_KEYS)
        self.assertEqual(r["location"], "San Diego")
        self.assertEqual((r["duration_days"], r["number_of_outfits"]), (5, 5))
        self.assertEqual((r["per_outfit_budget"], r["total_budget"]), (50, 500))
        self.assertIn("beachy", r["styles"])
        self.assertIn("coastal", r["styles"])
        self.assertTrue({"beige", "white"} <= set(r["preferred_colors"]))
        self.assertEqual(r["avoid"], ["neon"])
        self.assertEqual([i["item"] for i in r["required_items"]], ["crochet top", "skirt"])
        self.assertEqual(r["owned_item_references"], ["wardrobe_white_sneakers"])

    def test_one_long_comma_sentence(self):
        r = parse_request("5 days in San Diego, five outfits under $50 each, $500 total, beachy neutral, "
                          "one outfit needs a crochet top and skirt, I own white sneakers", "s", "u", use_llm=False)["request"]
        self.assertEqual([i["item"] for i in r["required_items"]], ["crochet top", "skirt"])
        self.assertEqual(r["owned_item_references"], ["wardrobe_white_sneakers"])
        self.assertEqual((r["per_outfit_budget"], r["total_budget"]), (50, 500))

    def test_casual_phrasings(self):
        cases = {
            "I want to go to San diego for 5 days, select 5 outfits under 50$ total outfit budget  is 500$.":
                ("San Diego", 5, 5, 50, 500),
            "trip to new york for a week, 4 outfits, max 60 dollars per outfit, 300 total": ("New York", 7, 4, 60, 300),
            "Paris trip 4 days, 4 outfits, $80 per outfit, total $300": ("Paris", 4, 4, 80, 300),
        }
        for text, exp in cases.items():
            r = parse_request(text, "s", "u", use_llm=False)["request"]
            got = (r["location"], r["duration_days"], r["number_of_outfits"], r["per_outfit_budget"], r["total_budget"])
            self.assertEqual(got, exp, text)

    def test_required_item_phrasings(self):
        for text in ["One outfit should have a crochet top and skirt.",
                     "One outfit needs a crochet top and skirt.",
                     "I'd like one outfit with a crochet top and skirt.",
                     "One outfit must include a crochet top and skirt.",
                     "One look has to have a crochet top and skirt.",
                     "Please include a crochet top and skirt in one outfit."]:
            r = parse_request("5 outfits under $50 each. " + text + " I own white sneakers.", "s", "u",
                              use_llm=False)["request"]
            self.assertEqual([i["item"] for i in r["required_items"]], ["crochet top", "skirt"], text)
            self.assertIn("required_items", r["hard_constraints"], text)
            self.assertEqual(r["owned_item_references"], ["wardrobe_white_sneakers"], text)

    def test_memory_rule(self):
        remembered = parse_request(CANONICAL, "s", "u", use_llm=False)["new_wardrobe_items"][0]
        self.assertEqual(remembered["memory_type"], "remembered")
        self.assertIsNone(remembered["expires_at"])
        temp = parse_request("I have black sandals. 2 outfits for brunch.", "s", "u", use_llm=False)["new_wardrobe_items"][0]
        self.assertEqual(temp["memory_type"], "temporary")
        self.assertIsNotNone(temp["expires_at"])


class TestPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run(plan_shopping(CANONICAL, "user_123", "session_unittest"))
        cls.rec = cls.result["final_recommendation"]

    def test_contract_shape(self):
        self.assertEqual(set(self.rec), REC_KEYS)
        for o in self.rec["outfits"]:
            self.assertEqual(set(o), OUTFIT_KEYS)
            self.assertTrue(1 <= o["match_score"] <= 100)
            for it in o["items"]:
                self.assertEqual(set(it), ITEM_KEYS)
                self.assertTrue((it["product"] is None) != (it["wardrobe_item"] is None))
        for e in self.rec["agent_events"]:
            self.assertEqual(set(e), EVENT_KEYS)
            self.assertIn(e["status"], {"working", "completed", "failed"})

    def test_hard_constraints(self):
        rec = self.rec
        self.assertEqual(rec["status"], "completed")
        self.assertTrue(rec["all_constraints_satisfied"])
        self.assertEqual(rec["constraint_violations"], [])
        self.assertEqual(len(rec["outfits"]), 5)
        for o in rec["outfits"]:
            self.assertLessEqual(o["new_purchase_cost"], 50)
        self.assertLessEqual(rec["total_new_purchase_cost"], 500)

    def test_unique_purchase_cost(self):
        unique = {}
        for o in self.rec["outfits"]:
            for it in o["items"]:
                if it["source_type"] == "product":
                    unique[it["product"]["id"]] = it["product"]["price"]
        self.assertAlmostEqual(self.rec["total_new_purchase_cost"], round(sum(unique.values()), 2))

    def test_required_items_and_wardrobe(self):
        names = [(it["product"] or it["wardrobe_item"])["name"].lower()
                 for o in self.rec["outfits"] for it in o["items"]]
        self.assertTrue(any("crochet" in n for n in names))
        self.assertTrue(any("skirt" in n for n in names))
        self.assertTrue(any(it["wardrobe_item"]["id"] == "wardrobe_white_sneakers" for it in self.rec["owned_items_used"]))

    def test_replanning_happened(self):
        types = [e["type"] for e in self.rec["agent_events"]]
        self.assertIn("constraint_violation", types)
        self.assertIn("replanning", types)
        self.assertIn("replacement_found", types)
        self.assertNotIn("neon", " ".join(str(o["items"]) for o in self.rec["outfits"]).lower())

    def test_vision_wardrobe_is_reused_and_excluded_from_purchases(self):
        result = run(plan_shopping(
            "One casual outfit for San Diego under $120", "wardrobe_user", "vision-wardrobe",
            wardrobe=[
                {"id": "w-pants", "name": "Beige pants", "category": "pants", "color": "beige", "style": "casual", "confidence": 0.94},
                {"id": "w-jacket", "name": "Beige jacket", "category": "jacket", "color": "beige", "style": "casual", "confidence": 0.92},
                {"id": "w-shoes", "name": "White shoes", "category": "shoes", "color": "white", "style": "casual", "confidence": 0.97},
            ]))
        rec = result["final_recommendation"]
        items = [item for outfit in rec["outfits"] for item in outfit["items"]]
        names = {(item["source"], (item["wardrobe_item"] or item["product"])["name"]) for item in items}
        self.assertIn(("wardrobe", "Beige pants"), names)
        self.assertIn(("wardrobe", "White shoes"), names)
        self.assertEqual(rec["wardrobe_reused_count"], 2)
        self.assertEqual(rec["unique_purchase_count"], 1)

    def test_modify_only_target(self):
        before = {o["id"]: [i["id"] for i in o["items"]] for o in self.rec["outfits"]}
        top_before = [i for i in self.rec["outfits"][2]["items"] if (i["product"] or i["wardrobe_item"])["category"] == "top"]
        r = run(modify_shopping({"session_id": "session_unittest", "user_id": "user_123",
                                 "message": "Keep the top in outfit three but replace the skirt and make it more elegant.",
                                 "target_outfit_id": None}))["final_recommendation"]
        after = {o["id"]: [i["id"] for i in o["items"]] for o in r["outfits"]}
        for oid in ("outfit_1", "outfit_2", "outfit_4", "outfit_5"):
            self.assertEqual(before[oid], after[oid])
        top_after = [i for i in r["outfits"][2]["items"] if (i["product"] or i["wardrobe_item"])["category"] == "top"]
        self.assertEqual(top_before[0]["id"], top_after[0]["id"])
        self.assertNotEqual(before["outfit_3"], after["outfit_3"])
        self.assertTrue(r["all_constraints_satisfied"])

    def test_targeted_replacement_budget_is_enforced(self):
        r = run(modify_shopping({"session_id": "session_unittest", "user_id": "user_123",
                                 "message": "Replace the top in outfit 2 with something under $20.",
                                 "target_outfit_id": None}))
        rec = r["final_recommendation"]
        outfit = next(o for o in rec["outfits"] if o["id"] == "outfit_2")
        top = next(i for i in outfit["items"] if (i["product"] or i["wardrobe_item"])["category"] == "top")
        self.assertLessEqual((top["product"] or top["wardrobe_item"]).get("price", 0), 20)


class TestWardrobe(unittest.TestCase):
    """Stored wardrobe items (Person 2's DB) are candidates with an advantage, never forced."""
    W = [
        {"id": "w_heels", "user_id": "u", "name": "Black Strappy Heels", "category": "Shoes", "colors": ["Black"],
         "tags": ["Evening"], "memory_type": "remembered", "created_at": "2026-10-01T00:00:00Z", "expires_at": None},
        {"id": "w_coat", "user_id": "u", "name": "Winter Wool Coat", "category": None, "colors": ["grey"], "tags": [],
         "memory_type": "remembered", "created_at": "2026-10-01T00:00:00Z", "expires_at": None},
        {"id": "w_neon", "user_id": "u", "name": "Neon Running Shoes", "category": "shoes", "colors": ["neon green"],
         "tags": ["athletic"], "memory_type": "remembered", "created_at": "2026-10-01T00:00:00Z", "expires_at": None},
        {"id": "w_expired", "user_id": "u", "name": "Old Temp Tee", "category": "top", "colors": [], "tags": [],
         "memory_type": "temporary", "created_at": "2020-01-01T00:00:00Z", "expires_at": "2020-01-31T00:00:00Z"},
    ]

    def test_wardrobe_candidates(self):
        res = run(plan_shopping("4 days in San Diego, 4 outfits under $50 each, beachy, I hate neon", "u", "s_ward",
                                wardrobe=self.W))
        rec = res["final_recommendation"]
        selected = {i["wardrobe_item"]["id"] for o in rec["outfits"] for i in o["items"] if i["wardrobe_item"]}
        used = {i["wardrobe_item"]["id"]: i["used_in_outfits"] for i in rec["owned_items_used"]}
        self.assertEqual(set(used), selected)                       # only pieces actually selected
        self.assertIn("w_heels", used)                              # "Shoes" category normalized and used
        occ = {o["id"]: o["occasion"] for o in rec["outfits"]}
        self.assertTrue(all(occ[oid] == "dinner" for oid in used["w_heels"]))  # only where they fit
        self.assertNotIn("w_neon", selected)                        # avoided color never used
        self.assertNotIn("w_expired", selected)                     # expired temporary memory ignored
        self.assertNotIn("w_coat", selected)                        # not forced into an outfit
        self.assertTrue(rec["all_constraints_satisfied"])


class TestConflict(unittest.TestCase):
    def test_impossible_budget_asks_user(self):
        res = run(plan_shopping("2 outfits for brunch, each outfit under $15, must include a satin dress", "u", "s_conf"))
        rec = res["final_recommendation"]
        self.assertEqual(rec["status"], "needs_user_input")
        self.assertFalse(rec["all_constraints_satisfied"])
        self.assertTrue(rec["constraint_violations"])
        self.assertEqual(res["conflict"]["status"], "needs_user_input")
        self.assertTrue(res["conflict"]["options"])


if __name__ == "__main__":
    unittest.main()

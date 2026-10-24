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
            "all_constraints_satisfied", "message"}
OUTFIT_KEYS = {"id", "title", "day", "occasion", "match_score", "score_breakdown", "items", "total_value",
               "new_purchase_cost", "why_it_works", "constraints_satisfied"}
ITEM_KEYS = {"id", "source_type", "product", "wardrobe_item", "purchase_required", "reused", "used_in_outfits"}
EVENT_KEYS = {"id", "session_id", "agent", "type", "status", "message", "outfit_id", "timestamp"}


def run(coro):
    return asyncio.run(coro)


class TestParser(unittest.TestCase):
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

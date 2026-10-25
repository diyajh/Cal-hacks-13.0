import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

from app.services.vision import VisionAnalysisError, _json_object, normalize_items
from app.services.wardrobe_decision import compare_product
from app.models.user import WardrobeItem
from app.routes import users
from app.services.wardrobe_store import create_store


def item(category="shirt", subcategory="button-up", color="beige", confidence=0.91):
    return {
        "category": category,
        "subcategory": subcategory,
        "color": color,
        "pattern": "solid",
        "material": "unknown",
        "style": "casual",
        "formality": "casual",
        "confidence": confidence,
    }


class WardrobeAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        users.configure_wardrobe_store(str(Path(self.temp_dir.name) / "aura.sqlite3"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_temporary_item_expires_in_thirty_days(self):
        saved = users.add_item("memory-test", WardrobeItem(name="Beige pants", category="pants"))
        self.assertEqual(saved.memory_type, "temporary")
        self.assertIsNotNone(saved.expires_at)
        self.assertGreater(saved.expires_at, datetime.now(timezone.utc))

    def test_sqlite_survives_store_recreation_and_expires_temporary_items(self):
        database = str(Path(self.temp_dir.name) / "restart.sqlite3")
        first = create_store(database)
        temporary = first.create("durable-user", WardrobeItem(name="Temporary tee", category="shirt"))
        remembered = first.create("durable-user", WardrobeItem(name="Saved sneakers", category="shoes", memory_type="remembered"))
        with first._connect() as connection:
            connection.execute("UPDATE wardrobe_items SET expires_at=? WHERE item_id=?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), temporary.id))
        second = create_store(database)
        loaded = second.list("durable-user")
        self.assertEqual([item.name for item in loaded], [remembered.name])
        self.assertEqual(loaded[0].memory_type, "remembered")

    def test_sqlite_edit_delete_and_clear_are_durable(self):
        database = str(Path(self.temp_dir.name) / "operations.sqlite3")
        store = create_store(database)
        saved = store.create("durable-user", WardrobeItem(name="Old name", category="shirt"))
        saved.name = "Edited name"
        saved.memory_type = "remembered"
        updated = store.update("durable-user", saved.id, saved)
        reloaded = create_store(database).list("durable-user")
        self.assertEqual(reloaded[0].name, "Edited name")
        self.assertIsNone(reloaded[0].expires_at)
        self.assertTrue(store.delete("durable-user", saved.id))
        store.create("durable-user", WardrobeItem(name="One", category="shirt"))
        self.assertEqual(store.clear("durable-user"), 1)
        self.assertEqual(create_store(database).list("durable-user"), [])

    def test_remembered_item_reloads_until_deleted(self):
        saved = users.add_item("memory-test", WardrobeItem(name="White sneakers", category="shoes", memory_type="remembered"))
        self.assertIsNone(saved.expires_at)
        loaded = users.get_wardrobe("memory-test")
        self.assertEqual(loaded[0].id, saved.id)
        self.assertEqual(loaded[0].memory_type, "remembered")
        self.assertEqual(users.delete_item("memory-test", saved.id)["deleted"], True)
        self.assertEqual(users.get_wardrobe("memory-test"), [])

    def test_clear_all_wardrobe_memory(self):
        users.add_item("memory-test", WardrobeItem(name="Beige pants", category="pants"))
        users.add_item("memory-test", WardrobeItem(name="Beige jacket", category="jacket"))
        self.assertEqual(users.clear_wardrobe("memory-test")["deleted"], 2)
        self.assertEqual(users.get_wardrobe("memory-test"), [])

    def test_valid_wardrobe_json_is_normalized(self):
        result = normalize_items(_json_object('{"items":[{"category":"shirt","subcategory":"button-up","color":"beige","confidence":0.91}]}'))
        self.assertEqual(result[0]["category"], "shirt")
        self.assertEqual(result[0]["color"], "beige")
        self.assertEqual(result[0]["confidence"], 0.91)

    def test_footwear_subtype_is_normalized(self):
        result = normalize_items(_json_object('{"items":[{"category":"shoes","subcategory":"unknown","color":"white","style":"sneaker","confidence":0.95}]}'))
        self.assertEqual(result[0]["subcategory"], "sneaker")
        self.assertEqual(result[0]["subtype"], "sneaker")

    def test_malformed_vision_response_is_rejected(self):
        with self.assertRaises(VisionAnalysisError):
            _json_object("not json")

    def test_empty_wardrobe_needs_data(self):
        result = compare_product({"name": "Navy overshirt", "price": 34.99, "category": "outerwear"}, [])
        self.assertEqual(result["verdict"], "INSUFFICIENT_WARDROBE_DATA")
        self.assertIn("wardrobe photo", result["missing_information"])

    def test_low_confidence_item_needs_confirmation(self):
        result = compare_product({"name": "Navy overshirt", "price": 34.99, "category": "outerwear"}, [item(confidence=0.4)])
        self.assertEqual(result["verdict"], "INSUFFICIENT_WARDROBE_DATA")
        self.assertIn("confirm low-confidence wardrobe items", result["missing_information"])

    def test_duplicate_product_is_skip(self):
        result = compare_product(
            {"name": "White leather sneakers", "price": 54.99, "category": "sneakers", "color": "white"},
            [item(category="sneakers", subcategory="running shoes", color="white")],
        )
        self.assertEqual(result["verdict"], "SKIP")
        self.assertEqual(result["budget_impact"], 54.99)
        self.assertTrue(result["matched_items"])

    def test_nike_white_sneaker_duplicates_white_wardrobe_shoes(self):
        result = compare_product(
            {"name": "Nike Air Force 1 ’07 Men's Shoes", "price": 115,
             "currency": "USD", "category": "shoes", "color": "White/White",
             "description": "Classic leather construction for style on court or on the go.",
             "image_url": "https://static.nike.com/air-force-1.jpg",
             "product_url": "https://www.nike.com/t/air-force-1/CW2288-111"},
            [item(category="shoes", subcategory="sneakers", color="white")],
        )
        self.assertEqual(result["verdict"], "SKIP")
        self.assertGreaterEqual(result["duplication_score"], 0.8)
        self.assertEqual(result["outfits_unlocked"], 0)
        self.assertIn("Duplicates your white sneaker", result["reason"])
        self.assertIn("$115.00 avoided", result["reason"])
        self.assertTrue(result["matched_items"])

    def test_white_sandal_is_not_automatic_duplicate_of_white_sneaker(self):
        result = compare_product(
            {"name": "White leather sandal", "price": 45, "category": "shoes", "subcategory": "sandal", "color": "white"},
            [item(category="shoes", subcategory="sneaker", color="white")],
        )
        self.assertEqual(result["verdict"], "BUY")

    def test_black_sneaker_can_add_coverage(self):
        result = compare_product(
            {"name": "Black court sneaker", "price": 85, "category": "shoes", "subcategory": "sneaker", "color": "black"},
            [item(category="shoes", subcategory="sneaker", color="white")],
        )
        self.assertIn(result["verdict"], {"BUY", "INSUFFICIENT_WARDROBE_DATA"})

    def test_new_white_sneaker_buys_when_no_comparable_sneaker_exists(self):
        result = compare_product(
            {"name": "White court sneaker", "price": 85, "category": "shoes", "subcategory": "sneaker", "color": "white"},
            [item(category="pants", subcategory="trousers", color="beige"), item(category="outerwear", subcategory="jacket", color="beige")],
        )
        self.assertEqual(result["verdict"], "BUY")

    def test_unknown_footwear_subtype_requires_confirmation(self):
        result = compare_product(
            {"name": "White footwear", "price": 85, "category": "shoes", "color": "white"},
            [item(category="shoes", subcategory="unknown", color="white")],
        )
        self.assertEqual(result["verdict"], "INSUFFICIENT_WARDROBE_DATA")
        self.assertIn("confirm footwear subtype", result["missing_information"])

    def test_novel_product_is_buy(self):
        result = compare_product(
            {"name": "Navy overshirt", "price": 34.99, "category": "outerwear", "color": "navy"},
            [item(category="shirt", subcategory="button-up", color="beige")],
        )
        self.assertEqual(result["verdict"], "BUY")
        self.assertEqual(result["budget_impact"], 34.99)
        self.assertGreaterEqual(result["outfits_unlocked"], 1)

    def test_missing_product_price_is_not_invented(self):
        result = compare_product({"name": "Navy overshirt", "category": "outerwear"}, [item()])
        self.assertEqual(result["verdict"], "INSUFFICIENT_WARDROBE_DATA")
        self.assertIsNone(result["budget_impact"])
        self.assertIn("product price", result["missing_information"])

    def test_budget_change_can_turn_buy_into_skip(self):
        product = {"name": "Navy overshirt", "price": 34.99, "category": "outerwear", "color": "navy"}
        wardrobe = [item(category="shirt", subcategory="button-up", color="beige")]
        affordable = compare_product(product, wardrobe, budget_remaining=40)
        over_budget = compare_product(product, wardrobe, budget_remaining=20)
        self.assertEqual(affordable["verdict"], "BUY")
        self.assertEqual(over_budget["verdict"], "SKIP")
        self.assertIn("remaining budget", over_budget["reason"])


if __name__ == "__main__":
    unittest.main()

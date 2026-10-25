from fastapi import APIRouter, HTTPException
from app.models.user import UserProfile, WardrobeItem
from app.services.wardrobe_store import WardrobeStore, create_store

router = APIRouter(prefix="/users")

wardrobe_store: WardrobeStore = create_store()


def configure_wardrobe_store(database_url: str) -> None:
    """Replace the store for isolated tests or an explicit local database URL."""
    global wardrobe_store
    wardrobe_store = create_store(database_url)


@router.put("/{user_id}/profile")
def save_profile(user_id: str, profile: UserProfile):
    return wardrobe_store.save_profile(user_id, profile)


@router.get("/{user_id}/profile")
def get_profile(user_id: str):
    return wardrobe_store.get_profile(user_id)


@router.delete("/{user_id}/profile")
def delete_profile(user_id: str):
    return {"deleted": wardrobe_store.delete_profile(user_id)}


@router.post("/{user_id}/wardrobe")
def add_item(user_id: str, item: WardrobeItem):
    return wardrobe_store.create(user_id, item)


@router.put("/{user_id}/wardrobe/{item_id}")
def update_item(user_id: str, item_id: str, item: WardrobeItem):
    updated = wardrobe_store.update(user_id, item_id, item)
    if updated is None:
        raise HTTPException(status_code=404, detail="Wardrobe item not found")
    return updated


@router.get("/{user_id}/wardrobe")
def get_wardrobe(user_id: str):
    return wardrobe_store.list(user_id)


@router.delete("/{user_id}/wardrobe/{item_id}")
def delete_item(user_id: str, item_id: str):
    if not wardrobe_store.delete(user_id, item_id):
        raise HTTPException(status_code=404, detail="Wardrobe item not found")
    return {"deleted": True}


@router.delete("/{user_id}/wardrobe")
def clear_wardrobe(user_id: str):
    return {"deleted": wardrobe_store.clear(user_id)}

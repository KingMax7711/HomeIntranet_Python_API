from sqlalchemy.orm import Session

from models import ShoppingList


def increment_current_list_version(
    db: Session,
    house_id: int | None = None,
    shopping_list_id: int | None = None,
) -> None:
    """
    Increment the version of the current shopping list(s).

    If `shopping_list_id` is provided, only that list is updated (if active).
    Else if `house_id` is provided, all active lists for that house are updated.
    Otherwise, all active lists are updated.

    This helper intentionally does not commit; callers are responsible for
    committing within their own transaction scope.
    """
    query = db.query(ShoppingList).filter(
        ShoppingList.status.in_(["preparation", "in_progress"])
    )
    if shopping_list_id is not None:
        query = query.filter(ShoppingList.id == shopping_list_id)
    elif house_id is not None:
        query = query.filter(ShoppingList.house_id == house_id)

    current_lists = query.all()
    for current_list in current_lists:
        current_list.version = (current_list.version or 0) + 1  # type: ignore

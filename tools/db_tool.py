from fastmcp import tool
from db.database import SessionLocal
from sqlalchemy import text

@tool
def query_orders_by_user(user_id: int) -> str:
    """
    Query recent orders by a given user from the database.
    """
    session = SessionLocal()
    try:
        query = text("SELECT * FROM orders WHERE user_id = :user_id ORDER BY order_date DESC LIMIT 5")
        result = session.execute(query, {"user_id": user_id})
        orders = result.fetchall()
        if not orders:
            return f"No recent orders found for user {user_id}."
        return "\n".join([str(dict(row)) for row in orders])
    finally:
        session.close()

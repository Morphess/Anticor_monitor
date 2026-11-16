from fastapi import APIRouter
from app.schemas.orders import OrderCreate


router = APIRouter(
    prefix="/orders",
    tags=["API Orders"],
)


@router.post("/")
def create_order(order: OrderCreate):
    return {
        "message": "Наказ отримано",
        "number": order.number,
        "title": order.title,
    }


@router.get("/")
def get_orders():
    return {
        "orders": [],
    }

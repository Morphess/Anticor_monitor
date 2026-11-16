from pydantic import BaseModel


class OrderCreate(BaseModel):
    number: str
    title: str

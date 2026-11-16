from fastapi import APIRouter
from app.schemas.programs import ProgramsCreate

router = APIRouter(
    prefix="/programs",
    tags=["API Programs"],
)


@router.post("/")
def create_program(program: ProgramsCreate):
    return {
        "message": "Програма отримана",
        "number": program.number,
        "title": program.title,
    }


@router.get("/")
def get_orders():
    return {
        "program": [],
    }

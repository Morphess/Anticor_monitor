from pydantic import BaseModel


class ProgramsCreate(BaseModel):
    number: str
    title: str

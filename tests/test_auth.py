import unittest

from pwdlib import PasswordHash
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.auth_user import AuthUser
from app.repositories.auth import SqlAlchemyAuthRepository
from app.services.auth_service import authenticate_user


class AuthFlowTests(unittest.TestCase):
    def test_credentials_against_database(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)

        try:
            with Session(engine) as db:
                db.add(
                    AuthUser(
                        login="demo-user",
                        password_hash=PasswordHash.recommended().hash("demo-password"),
                    )
                )
                db.commit()

                repository = SqlAlchemyAuthRepository(db)

                self.assertTrue(
                    authenticate_user("demo-user", "demo-password", repository)
                )
                self.assertFalse(
                    authenticate_user("demo-user", "wrong", repository)
                )
                self.assertFalse(
                    authenticate_user("unknown", "demo-password", repository)
                )
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()

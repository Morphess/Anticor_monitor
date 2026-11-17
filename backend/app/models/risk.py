from __future__ import annotations
from datetime import date
from decimal import Decimal
from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Корупційний ризик, його оцінка, індикатори й відповідальний підрозділ.
class Risk(Base):
    # Ім’я таблиці в PostgreSQL, з якою працює ця модель.
    __tablename__ = "risks"
    # Правила цілісності БД: унікальність і перевірки значень.
    __table_args__ = (
        # Імовірність ризику повинна бути в межах 1–4.
        CheckConstraint(
            "probability_score BETWEEN 1 AND 4", name="ck_risk_probability"
        ),
        # Наслідки ризику повинні бути в межах 1–4.
        CheckConstraint("impact_score BETWEEN 1 AND 4", name="ck_risk_impact"),
        # Бал повинен дорівнювати добутку імовірності та наслідків.
        CheckConstraint(
            "score = probability_score * impact_score", name="ck_risk_score"
        ),
        # Дозволені лише чотири технічні рівні ризику.
        CheckConstraint(
            "level IN ('low', 'medium', 'high', 'critical')", name="ck_risk_level"
        ),
        # Показник має збільшуватися або зменшуватися.
        CheckConstraint(
            "indicator_direction IN ('increase', 'decrease')", name="ck_risk_direction"
        ),
    )

    # Код ризику з Excel, наприклад KR01.
    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # KR01
    # Функція або процес, у якому виникає ризик.
    process_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Коротка назва ризику.
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Детальний зміст ризику.
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Джерела та чинники ризику.
    risk_sources: Mapped[str] = mapped_column(Text, nullable=False)
    # Контрольні заходи, які вже застосовують.
    existing_controls: Mapped[str] = mapped_column(Text, nullable=False)
    # Оцінка ймовірності: ціле число від 1 до 4.
    probability_score: Mapped[int] = mapped_column(Integer, nullable=False)
    # Оцінка наслідків: ціле число від 1 до 4.
    impact_score: Mapped[int] = mapped_column(Integer, nullable=False)
    # Загальний бал ризику: probability_score × impact_score.
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    # Рівень ризику (low/medium/high/critical).
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    # Підрозділ-власник, відповідальний за цей ризик.
    owner_department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )
    # Показник, за яким можна визначити зміну ризику.
    indicator_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Одиниця вимірювання показника (% або шт.).
    indicator_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # Кращий напрям зміни: increase або decrease.
    indicator_direction: Mapped[str] = mapped_column(String(12), nullable=False)
    # Базове значення показника (наприклад, на 31.12.2025).
    indicator_baseline_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False
    )
    # Цільове значення, якого прагнемо досягнути.
    indicator_target_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False
    )
    # Дата, до якої потрібно досягнути цілі.
    target_date: Mapped[date] = mapped_column(Date, nullable=False)

    # ORM-доступ до підрозділу-власника ризику.
    owner_department: Mapped["Department"] = relationship("Department")
    # Усі значення індикатора за різні дати.
    measurements: Mapped[list["RiskMeasurement"]] = relationship(
        "RiskMeasurement", back_populates="risk"
    )
    # Усі заходи, пов’язані з цим ризиком.
    measures: Mapped[list["Measure"]] = relationship("Measure", back_populates="risk")

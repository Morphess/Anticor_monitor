"""Таблиці PostgreSQL. Структура повторює синтетичний набір організаторів (data/nabir-orhanizatoriv,
словник — dictionary.md), тому ідентифікатори довідників — рядкові, як у наборі (Z-01, KR01, P03, U-002).

  program 1─* sections 1─* measures *─1 risks          (захід другого розділу → корупційний ризик)
  units 1─* measures, users                            (відповідальний підрозділ, виконавець)
  measures 1─* executions                              (що вніс виконавець за півріччя + погодження)
  measures 1─* evidence                                (підтвердні матеріали, незмінні, з SHA-256)
  measures 1─* deadline_changes                        (внутрішні рішення про перенесення строку)
  risks 1─* risk_measurements                          (динаміка індикатора стану ризику)
  journal                                              (журнал дій: хто, коли, що змінив; лише додавання)
"""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")
TS = DateTime(timezone=True)


class Setting(Base):
    """Налаштування: звітний період і дата зрізу даних."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType)


class Program(Base):
    """Паспорт антикорупційної програми."""
    __tablename__ = "program"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(400))
    organ: Mapped[str] = mapped_column(String(300))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    approved_by: Mapped[str] = mapped_column(String(300), default="")
    nazk_status: Mapped[str] = mapped_column(String(300), default="")
    restricted: Mapped[bool] = mapped_column(Boolean, default=False)   # містить інформацію з обмеженим доступом
    authorized_unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"))
    goals: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")


class Section(Base):
    """Розділ програми — назва дослівно як вкладка на Порталі доброчесності."""
    __tablename__ = "sections"
    code: Mapped[str] = mapped_column(String(4), primary_key=True)     # R1 / R2 / R3
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(400))


class Unit(Base):
    __tablename__ = "units"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)      # P01
    name: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(50), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class User(Base):
    """Користувач: роль і посада. Імен немає — як у наборі (жодних персональних даних)."""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)      # U-001 — він же логін
    role: Mapped[str] = mapped_column(String(10))                      # ADMIN / KOORD / VYK / KER / ANAL
    unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"))
    position: Mapped[str] = mapped_column(String(300))
    password_hash: Mapped[str | None] = mapped_column(String(200))     # лише коли DEMO_MODE=0
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    unit: Mapped[Unit | None] = relationship()


class Risk(Base):
    """Корупційний ризик (Методологія НАЗК № 830/21) з індикатором СТАНУ ризику."""
    __tablename__ = "risks"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)      # KR01
    function: Mapped[str] = mapped_column(String(300))
    name: Mapped[str] = mapped_column(String(400))
    content: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[str] = mapped_column(Text, default="")
    existing_controls: Mapped[str] = mapped_column(Text, default="")
    probability: Mapped[int] = mapped_column(Integer)                  # 1–4
    impact: Mapped[int] = mapped_column(Integer)                       # 1–4
    owner_unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"))
    indicator_name: Mapped[str] = mapped_column(String(400))
    indicator_unit: Mapped[str] = mapped_column(String(20), default="")
    direction: Mapped[str] = mapped_column(String(10))                 # менше / більше
    indicator_base: Mapped[float] = mapped_column(Float)
    indicator_target: Mapped[float] = mapped_column(Float)
    target_date: Mapped[date | None] = mapped_column(Date)

    owner_unit: Mapped[Unit | None] = relationship()
    measurements: Mapped[list["RiskMeasurement"]] = relationship(order_by="RiskMeasurement.date")
    measures: Mapped[list["Measure"]] = relationship(back_populates="risk", order_by="Measure.id")


class RiskMeasurement(Base):
    __tablename__ = "risk_measurements"
    __table_args__ = (UniqueConstraint("risk_id", "date", name="uq_risk_measurement"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    risk_id: Mapped[str] = mapped_column(ForeignKey("risks.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(300), default="")
    entered_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Measure(Base):
    """Захід програми. Зміст і строк за програмою після затвердження не змінюються."""
    __tablename__ = "measures"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)      # Z-01
    section_code: Mapped[str] = mapped_column(ForeignKey("sections.code"), index=True)
    number: Mapped[int] = mapped_column(Integer)                       # № у розділі
    content: Mapped[str] = mapped_column(Text)                         # «Опис заходу» на Порталі
    risk_id: Mapped[str | None] = mapped_column(ForeignKey("risks.id"), index=True)  # обов'язково для R2
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"), index=True)
    co_units: Mapped[list] = mapped_column(JSONType, default=list)     # id співвиконавців
    executor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    deadline_text: Mapped[str] = mapped_column(String(200))            # як записано в програмі
    deadline_type: Mapped[str] = mapped_column(String(15))             # data / postiino / periodychno
    deadline_date: Mapped[date | None] = mapped_column(Date)
    indicator_name: Mapped[str] = mapped_column(String(400), default="")
    indicator_unit: Mapped[str] = mapped_column(String(30), default="")
    indicator_target: Mapped[float | None] = mapped_column(Float)
    required_evidence: Mapped[str] = mapped_column(String(400), default="")  # підказка виконавцю
    resources: Mapped[str] = mapped_column(String(300), default="")

    section: Mapped[Section] = relationship(lazy="joined")
    unit: Mapped[Unit] = relationship(lazy="joined")
    risk: Mapped[Risk | None] = relationship(back_populates="measures")
    executions: Mapped[list["Execution"]] = relationship(back_populates="measure", order_by="Execution.period")
    evidence: Mapped[list["Evidence"]] = relationship(order_by="Evidence.id")
    deadline_changes: Mapped[list["DeadlineChange"]] = relationship(order_by="DeadlineChange.decision_date")


class Execution(Base):
    """Що вніс виконавець щодо заходу за півріччя. Два незалежні виміри:
    status — стан виконання, який заявляє виконавець; review_state — етап погодження координатором."""
    __tablename__ = "executions"
    __table_args__ = (UniqueConstraint("measure_id", "period", name="uq_execution"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), index=True)
    period: Mapped[str] = mapped_column(String(8))                     # 2026-H1
    status: Mapped[str] = mapped_column(String(15), default="ne_rozpochato")
    actual_date: Mapped[date | None] = mapped_column(Date)
    result_text: Mapped[str] = mapped_column(Text, default="")
    indicator_fact: Mapped[float | None] = mapped_column(Float)
    entered_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    entered_at: Mapped[datetime | None] = mapped_column(TS)
    review_state: Mapped[str] = mapped_column(String(12), default="draft")  # draft / submitted / returned / approved
    review_comment: Mapped[str] = mapped_column(Text, default="")
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)

    measure: Mapped[Measure] = relationship(back_populates="executions")


class Evidence(Base):
    """Підтвердний матеріал. Після додавання не змінюється й не видаляється; SHA-256 фіксує вміст."""
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)      # E-001
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(500))
    doc_date: Mapped[date] = mapped_column(Date)
    link: Mapped[str] = mapped_column(String(500), default="")
    uploaded_at: Mapped[datetime] = mapped_column(TS)
    uploaded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    stored_name: Mapped[str | None] = mapped_column(String(200))       # файл у сховищі (у наборі файлів немає)
    original_name: Mapped[str | None] = mapped_column(String(300))
    size: Mapped[int | None] = mapped_column(Integer)


class DeadlineChange(Base):
    """Внутрішнє рішення про перенесення строку. Строк у затвердженій програмі не змінюється."""
    __tablename__ = "deadline_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), index=True)
    decision_date: Mapped[date] = mapped_column(Date)
    old_date: Mapped[date] = mapped_column(Date)
    new_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class JournalEntry(Base):
    """Журнал дій: хто, коли, що і з якого значення на яке змінив. Записи лише додаються."""
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(TS, index=True)
    user_id: Mapped[str | None] = mapped_column(String(10), index=True)
    action: Mapped[str] = mapped_column(String(100))
    object: Mapped[str] = mapped_column(String(30), index=True)        # zakhid / vykonannia / pidtverdzhennia / ...
    object_id: Mapped[str] = mapped_column(String(40), index=True)
    field: Mapped[str] = mapped_column(String(60), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    device: Mapped[str] = mapped_column(String(100), default="")

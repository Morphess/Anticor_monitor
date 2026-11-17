"""Shared sections and program measures

Revision ID: dfd4fb0168b9
Revises: 1669ad801a8e
Create Date: 2026-11-17 09:19:40.234751

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Ідентифікатори міграції Alembic.
revision: str = "dfd4fb0168b9"

down_revision: Union[str, Sequence[str], None] = "1669ad801a8e"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Перехід до спільних розділів R1, R2, R3.

    Нова структура:

    programs
        |
        | program_id
        v
    measures
        ^
        | section_id
        |
    sections

    Кожен захід належить одній програмі
    та одному зі спільних розділів.
    """

    conn = op.get_bind()

    # ==========================================
    # 1. ПЕРЕВІРКА РОЗДІЛІВ
    # ==========================================

    # Не допускаємо однакових номерів розділів.
    duplicates = conn.execute(
        sa.text(
            """
            SELECT number, COUNT(*)
            FROM sections
            GROUP BY number
            HAVING COUNT(*) > 1
        """
        )
    ).fetchall()

    if duplicates:
        raise RuntimeError(
            "Знайдено повторення номерів розділів: "
            f"{duplicates}. "
            "Спочатку потрібно об'єднати розділи."
        )

    # Перевіряємо допустимі номери.
    invalid_sections = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM sections
            WHERE number IS NULL
               OR number NOT BETWEEN 1 AND 3
        """
        )
    ).scalar()

    if invalid_sections:
        raise RuntimeError(
            "У таблиці sections є розділи " "з номерами поза діапазоном 1–3."
        )

    # ==========================================
    # 2. ДОДАЄМО PROGRAM_ID ДО MEASURES
    # ==========================================

    # Спочатку nullable=True для перенесення даних.
    op.add_column(
        "measures",
        sa.Column(
            "program_id",
            sa.String(length=50),
            nullable=True,
        ),
    )

    # ==========================================
    # 3. ПЕРЕНОСИМО ЗВ'ЯЗКИ
    # ==========================================

    # Беремо program_id зі старої таблиці sections.
    conn.execute(
        sa.text(
            """
            UPDATE measures AS m
            SET program_id = s.program_id
            FROM sections AS s
            WHERE m.section_id = s.id
        """
        )
    )

    # Перевіряємо, що немає заходів без програми.
    missing_programs = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM measures
            WHERE program_id IS NULL
        """
        )
    ).scalar()

    if missing_programs:
        raise RuntimeError(
            f"Знайдено {missing_programs} заходів " "без програми. Міграцію зупинено."
        )

    # ==========================================
    # 4. PROGRAM_ID СТАЄ ОБОВ'ЯЗКОВИМ
    # ==========================================

    op.alter_column(
        "measures",
        "program_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )

    # ==========================================
    # 5. ЗОВНІШНІЙ КЛЮЧ ДО PROGRAMS
    # ==========================================

    op.create_foreign_key(
        "fk_measures_program_id_programs",
        "measures",
        "programs",
        ["program_id"],
        ["id"],
    )

    # ==========================================
    # 6. УНІКАЛЬНІСТЬ ЗАХОДІВ
    # ==========================================

    # Прибираємо старе обмеження:
    # section_id + sequence_number.
    op.drop_constraint(
        "uq_measure_number_in_section",
        "measures",
        type_="unique",
    )

    # Нове:
    # program_id + section_id + sequence_number.
    op.create_unique_constraint(
        "uq_measure_number_in_program_section",
        "measures",
        [
            "program_id",
            "section_id",
            "sequence_number",
        ],
    )

    # ==========================================
    # 7. ЗМІНЮЄМО ТАБЛИЦЮ SECTIONS
    # ==========================================

    # Прибираємо стару унікальність у межах програми.
    op.drop_constraint(
        "uq_section_number_per_program",
        "sections",
        type_="unique",
    )

    # Прибираємо FK sections -> programs.
    op.drop_constraint(
        "sections_program_id_fkey",
        "sections",
        type_="foreignkey",
    )

    # Видаляємо program_id із sections.
    op.drop_column(
        "sections",
        "program_id",
    )

    # ==========================================
    # 8. ТРИ СПІЛЬНІ РОЗДІЛИ
    # ==========================================

    # Кожен номер розділу унікальний.
    op.create_unique_constraint(
        "uq_sections_number",
        "sections",
        ["number"],
    )

    # Допустимі тільки номери 1, 2, 3.
    op.create_check_constraint(
        "ck_sections_number_1_3",
        "sections",
        "number BETWEEN 1 AND 3",
    )


def downgrade() -> None:
    """
    Автоматичний відкат заборонений.

    Після переходу до спільних розділів
    один розділ може використовуватися
    декількома програмами.

    Для повернення старої структури
    потрібно відновити окремі розділи
    для кожної програми та їхні зв'язки.
    """

    raise NotImplementedError(
        "Автоматичний downgrade неможливий. "
        "Потрібна окрема зворотна міграція "
        "або відновлення резервної копії."
    )

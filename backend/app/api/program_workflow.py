"""HTTP-шар: програми до підрозділів -> підрозділи -> конкретні виконавці."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.programs import ProgramRead
from app.schemas.program_workflow import (
    AssignMeasureIn,
    AssignmentResult,
    CoordinatorRead,
    DepartmentDispatchRead,
    DepartmentScopeRead,
    DispatchDepartmentsIn,
    DispatchDepartmentsOut,
    MeasureAssignmentRead,
    MeasureBriefRead,
    ProgramAccessRead,
    SectionBriefRead,
)
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError

# Стандартні помилки наших маршрутів. Вони також з'являються у Swagger UI.
# Під час валідації тіла запиту FastAPI сам може повертати 422.
WORKFLOW_ERROR_RESPONSES = {
    401: {"description": "Немає токена або JWT недійсний."},
    403: {"description": "Недостатньо прав або підрозділ за межами дозволеної гілки."},
    404: {
        "description": "Програму, захід, підрозділ, користувача чи призначення не знайдено."
    },
    409: {"description": "Конфлікт бізнес-правил або некоректна ієрархія підрозділів."},
    422: {"description": "Помилка валідації даних запиту."},
}

router = APIRouter(
    prefix="/program-routing",
    tags=["Program Routing"],
    responses=WORKFLOW_ERROR_RESPONSES,
)


def handle(action):
    try:
        return action()
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/programs/{program_id}/available-departments",
    response_model=list[DepartmentScopeRead],
    summary="Отримати доступні підрозділи",
    description="""Повертає підрозділи, які користувач може бачити у списку вибору для вказаної програми.

**Права:** `ADMIN` і головний координатор — усі підрозділи; координатор, якому програму **безпосередньо** направлено, — власний підрозділ та всі нижчі рівні. Іншим ролям — `403`.

**Важливо:** цей список потрібен інтерфейсу. Кожен POST/DELETE окремо перевіряє підпорядкування на сервері.

Поля відповіді: `id`, `name`, `parent_id`.""",
    response_description="Список підрозділів, доступних для вибору.",
)
def available_departments(
    program_id: Annotated[
        str, Path(description="Ідентифікатор антикорупційної програми")
    ],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Повернути доступні підрозділи для селектора в кабінеті координатора."""
    return handle(
        lambda: ProgramWorkflowService(db).available_departments(program_id, user)
    )


@router.post(
    "/programs/{program_id}/departments",
    response_model=DispatchDepartmentsOut,
    summary="Направити програму підрозділам",
    description="""Передає наявну програму одному або кільком підрозділам. Для кожного підрозділу обовʼязково має існувати користувач із роллю `KOORD`; інакше — `409`.

**Права:** `ADMIN` або головний координатор-власник програми можуть направляти її до будь-якого підрозділу. Координатор-одержувач, якому програму вже **безпосередньо** направлено, може передати її тільки **строго підлеглим** підрозділам, не собі чи сусідній гілці.

**Тіло запиту:** `department_ids` — список кодів підрозділів. Дублікати кодів прибираються. Усі підрозділи перевіряються **до** запису в базу. Повторне направлення повертає `already_sent: true`, не створюючи дубліката.""",
    response_description="Результат направлення по кожному підрозділу та знайдені координатори.",
)
def send_program(
    program_id: Annotated[
        str, Path(description="Ідентифікатор антикорупційної програми")
    ],
    data: DispatchDepartmentsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Направити програму до підрозділів, у яких є KOORD."""
    return handle(
        lambda: ProgramWorkflowService(db).send_to_departments(
            program_id, data.department_ids, user
        )
    )


@router.get(
    "/my/programs",
    response_model=list[ProgramAccessRead],
    summary="Отримати мої програми",
    description="""Повертає лише програми, доступні поточному користувачу за його JWT-токеном. ID користувача у запиті не передається.

**Права:** `ADMIN` — усі програми; `KOORD` — створені ним або направлені **безпосередньо** його підрозділу; `VYK` — програми з чинними персональними призначеннями. Для інших ролей цей сервіс наразі повертає порожній список.

`access_type`: `admin`, `owner`, `department_coordinator` або `executor`.""",
    response_description="Список програм із видом доступу.",
)
def my_programs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отримати програми, дозволені користувачеві за роллю й направленнями."""
    return handle(lambda: ProgramWorkflowService(db).my_programs(user))


@router.get(
    "/programs/{program_id}",
    response_model=ProgramRead,
    summary="Переглянути доступну програму",
    description="""Повертає паспорт програми (`ProgramRead`) **тільки якщо** поточний користувач має доступ до неї за правилами `GET /my/programs`.

**Помилки:** `404` — програми немає; `403` — існує, але користувач не має прав на перегляд.""",
    response_description="Повна інформація про доступну програму.",
)
def read_visible_program(
    program_id: Annotated[
        str, Path(description="Ідентифікатор антикорупційної програми")
    ],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отримати паспорт програми лише після перевірки доступу."""
    return handle(lambda: ProgramWorkflowService(db).visible_program(program_id, user))


@router.get(
    "/programs/{program_id}/sections",
    response_model=list[SectionBriefRead],
    summary="Переглянути розділи програми",
    description="""Після перевірки доступу до програми повертає розділи з довідника `sections`: код, номер і назву.

**Нюанс поточної реалізації:** розділи в БД є спільними; сервіс повертає **весь довідник розділів**, а не лише ті, у яких є заходи цієї програми.""",
    response_description="Довідник розділів із кодами, номерами й назвами.",
)
def program_sections(
    program_id: Annotated[
        str, Path(description="Ідентифікатор антикорупційної програми")
    ],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отримати спільний довідник розділів після перевірки програми."""
    return handle(lambda: ProgramWorkflowService(db).program_sections(program_id, user))


@router.get(
    "/programs/{program_id}/measures",
    response_model=list[MeasureBriefRead],
    summary="Переглянути доступні заходи програми",
    description="""Повертає короткі відомості про заходи вказаної програми з урахуванням прав користувача.

**Права:** `ADMIN` і головний координатор-власник бачать усі заходи програми; `KOORD` із прямим направленням — заходи, що стосуються його гілки, з урахуванням батьківських/дочірніх підрозділів; `VYK` — лише свої **дійсні персональні призначення**.

Виконавець без призначених заходів цієї програми отримає `403`. Для інших сторонніх користувачів доступ заборонено.""",
    response_description="Список доступних заходів у скороченому вигляді.",
)
def program_measures(
    program_id: Annotated[
        str, Path(description="Ідентифікатор антикорупційної програми")
    ],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отримати заходи програми відповідно до прав користувача."""
    return handle(lambda: ProgramWorkflowService(db).program_measures(program_id, user))


@router.get(
    "/my/measures",
    response_model=list[MeasureBriefRead],
    summary="Переглянути мої призначені заходи",
    description="""Повертає всі доступні особисто призначені заходи поточного користувача.

**Права:** тільки користувач із роллю `VYK`, якому визначено `department_id`. Необхідні чинне призначення в `measure_assignments`, направлення програми до його підрозділу або предка і відповідність заходу цій гілці.

Якщо виконавець ще не має заходів, повертається порожній список (`200`), а не помилка.""",
    response_description="Список особисто призначених заходів виконавця.",
)
def my_measures(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отримати чинні персонально призначені заходи ролі VYK."""
    return handle(lambda: ProgramWorkflowService(db).my_measures(user))


@router.get(
    "/programs/{program_id}/departments/{department_id}/coordinators",
    response_model=list[CoordinatorRead],
    summary="Знайти координаторів підрозділу",
    description="""Повертає користувачів вибраного підрозділу з роллю `KOORD`. Це потрібно перед направленням програми: одержати її може тільки підрозділ, у якому є координатор.

**Права:** `ADMIN` і головний координатор-власник можуть переглядати координаторів будь-якого наявного підрозділу; звичайний `KOORD` — лише підрозділів власної гілки, якщо програму безпосередньо направлено його підрозділу.

Повертаються: `id`, `login`, `role_id`, `department_id`.""",
    response_description="Координатори вибраного підрозділу.",
)
def get_coordinators(
    program_id: Annotated[
        str, Path(description="Ідентифікатор антикорупційної програми")
    ],
    department_id: Annotated[str, Path(description="Код підрозділу в ієрархії")],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Знайти користувачів KOORD у доступному підрозділі."""
    return handle(
        lambda: ProgramWorkflowService(db).department_coordinators(
            program_id, department_id, user
        )
    )


@router.get(
    "/programs/{program_id}/departments/{department_id}/executors",
    response_model=list[CoordinatorRead],
    summary="Знайти виконавців підрозділу",
    description="""Повертає користувачів підрозділу з роллю `VYK`, яких можна вибрати для призначення на захід.

**Права:** координатор із безпосереднім направленням може переглядати виконавців свого підрозділу й нащадків; `ADMIN` — виконавців гілки, до якої програму направлено. Головний координатор без прямого направлення до власного підрозділу в поточній реалізації не має окремого винятку для цього методу.

**Примітка:** використовується схема відповіді `CoordinatorRead`, але самі записи мають роль `VYK`.""",
    response_description="Виконавці обраного підрозділу.",
)
def get_executors(
    program_id: Annotated[
        str, Path(description="Ідентифікатор антикорупційної програми")
    ],
    department_id: Annotated[str, Path(description="Код підрозділу в ієрархії")],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Знайти користувачів VYK у дозволеному підрозділі."""
    return handle(
        lambda: ProgramWorkflowService(db).department_executors(
            program_id, department_id, user
        )
    )


@router.post(
    "/measures/{measure_id}/assign",
    response_model=AssignmentResult,
    summary="Призначити виконавця на захід",
    description="""Створює персональний доступ користувача до конкретного заходу. Передай `department_id` та `user_id` у JSON.

Сервер перевіряє: **(1)** право керувати цією гілкою; **(2)** відповідність заходу відповідальному підрозділу/співвиконавцю або їхнім нащадкам; **(3)** існування користувача з роллю `VYK` саме у вибраному підрозділі.

**Результат:** `assignment` і `already_assigned`. Якщо призначення вже існує, новий запис не створюється.

**Помилки:** `403` — чужа гілка/програма; `404` — відсутній захід, підрозділ або користувач; `409` — захід не стосується вибраної гілки; `422` — користувач не відповідає ролі чи підрозділу.""",
    response_description="Створене або вже існуюче призначення.",
)
def assign_measure(
    measure_id: Annotated[str, Path(description="Ідентифікатор заходу")],
    data: AssignMeasureIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Призначити виконавця на захід із перевіркою ієрархії."""
    return handle(
        lambda: ProgramWorkflowService(db).assign(
            measure_id, data.department_id, data.user_id, user
        )
    )


@router.get(
    "/measures/{measure_id}/assignments",
    response_model=list[MeasureAssignmentRead],
    summary="Переглянути призначення на захід",
    description="""Повертає перелік персональних призначень на конкретний захід.

**Права:** `ADMIN` і головний координатор-власник — усі призначення; координатор з прямим направленням — **лише призначення у власному підрозділі та підлеглих**, якщо сам захід належить до сфери його видимості.

Виконавці та сторонні координатори не можуть переглядати цей список. Відповідь містить користувача, підрозділ, автора й час призначення.""",
    response_description="Список призначень, доступних координатору.",
)
def measure_assignments(
    measure_id: Annotated[str, Path(description="Ідентифікатор заходу")],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Переглянути дозволені призначення конкретного заходу."""
    return handle(lambda: ProgramWorkflowService(db).list_assignments(measure_id, user))


@router.delete(
    "/measures/{measure_id}/assign/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Скасувати призначення виконавця",
    description="""Видаляє персональне призначення конкретного виконавця до заходу. Не видаляє ані самого користувача, ані захід.

**Права:** координатор може скасувати призначення тільки у своєму підрозділі або підлеглих, до яких має право керування за направленням програми. `ADMIN` — в гілках, до яких програму направлено.

**Успіх:** `204 No Content` — без JSON-тіла. **Якщо запису призначення немає:** `404`.""",
    response_description="Призначення видалено; тіло відповіді відсутнє.",
)
def unassign_measure(
    measure_id: Annotated[str, Path(description="Ідентифікатор заходу")],
    user_id: Annotated[
        int,
        Path(ge=1, description="Числовий ID виконавця, якому скасовують призначення"),
    ],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Відкликати особисте призначення виконавця; успіх — 204."""
    handle(lambda: ProgramWorkflowService(db).revoke(measure_id, user_id, user))

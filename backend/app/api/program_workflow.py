"""HTTP-шар: програми до підрозділів -> підрозділи -> конкретні виконавці."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User
from app.models.program_workflow import ProgramDepartment, MeasureAssignment
from app.models.department import Department
from app.models.measure import Measure
from app.models.execution import Execution
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
    404: {"description": "Програму, захід, підрозділ, користувача чи призначення не знайдено."},
    409: {"description": "Конфлікт бізнес-правил або некоректна ієрархія підрозділів."},
    422: {"description": "Помилка валідації даних запиту."},
}

def require_workflow_user(user: User = Depends(get_current_user)) -> User:
    """ADMIN та інші сторонні ролі не мають доступу до жодного маршруту."""
    if user.role_id not in {"MAIN_KOORD", "KOORD", "VYK"}:
        raise HTTPException(status_code=403, detail="Ця роль не має доступу до маршрутизації програм")
    return user


router = APIRouter(
    prefix="/program-routing",
    tags=["Program Routing"],
    dependencies=[Depends(require_workflow_user)],
    responses=WORKFLOW_ERROR_RESPONSES,
)


def handle(action):
    try:
        return action()
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/programs/{program_id}/dispatches", summary="MAIN_KOORD: поточні направлення програми")
def list_program_dispatches(
    program_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Read-only; never disclose another owner's program dispatches."""
    if user.role_id != "MAIN_KOORD":
        raise HTTPException(status_code=403, detail="Доступно лише власнику програми")
    program = handle(lambda: ProgramWorkflowService(db).visible_program(program_id, user))
    if program.created_by_user_id != user.id:
        raise HTTPException(status_code=403, detail="Це не твоя програма")
    rows = db.execute(
        select(ProgramDepartment.department_id, Department.name, ProgramDepartment.sent_at)
        .join(Department, Department.id == ProgramDepartment.department_id)
        .where(ProgramDepartment.program_id == program_id)
        .order_by(ProgramDepartment.sent_at)
    ).all()
    return [{"department_id": dept_id, "department_name": name, "sent_at": sent_at}
            for dept_id, name, sent_at in rows]


@router.get(
    "/programs/{program_id}/available-departments",
    response_model=list[DepartmentScopeRead],
    summary='Отримати доступні підрозділи',
    description="""Повертає підрозділи, які користувач може бачити у списку вибору для вказаної програми.

**Права:** `MAIN_KOORD` — підрозділи, де є `KOORD` (для направлення власної програми); `KOORD`, якому програму **безпосередньо** направлено, — власний підрозділ та всі нижчі рівні (для вибору виконавців, координатор у дочірньому підрозділі не потрібен). `ADMIN`, `VYK` та іншим ролям — `403`.

**Важливо:** цей список потрібен інтерфейсу. Кожен POST/DELETE окремо перевіряє підпорядкування на сервері.

Поля відповіді: `id`, `name`, `parent_id`.""",
    response_description='Список підрозділів, доступних для вибору.',
)
def available_departments(
    program_id: Annotated[str, Path(description='Ідентифікатор антикорупційної програми')],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Повернути доступні підрозділи для селектора в кабінеті координатора."""
    return handle(lambda: ProgramWorkflowService(db).available_departments(program_id, user))


@router.post(
    "/programs/{program_id}/departments",
    response_model=DispatchDepartmentsOut,
    summary='Направити програму підрозділам',
    description="""Передає наявну програму одному або кільком підрозділам. Для кожного підрозділу обовʼязково має існувати користувач із роллю `KOORD`; інакше — `409`.

**Права:** лише `MAIN_KOORD`, який створив програму, направляє її підрозділам із користувачем `KOORD`. Підрозділовий `KOORD` не перенаправляє програму; він самостійно призначає `VYK` у власному та підлеглих підрозділах. `ADMIN`, `VYK` також не мають права направляти програми.

**Тіло запиту:** `department_ids` — список кодів підрозділів. Дублікати кодів прибираються. Усі підрозділи перевіряються **до** запису в базу. Повторне направлення повертає `already_sent: true`, не створюючи дубліката.""",
    response_description='Результат направлення по кожному підрозділу та знайдені координатори.',
)
def send_program(
    program_id: Annotated[str, Path(description='Ідентифікатор антикорупційної програми')],
    data: DispatchDepartmentsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Направити програму до підрозділів, у яких є KOORD."""
    return handle(lambda: ProgramWorkflowService(db).send_to_departments(
        program_id, data.department_ids, user
    ))


@router.get(
    "/my/programs",
    response_model=list[ProgramAccessRead],
    summary='Отримати мої програми',
    description="""Повертає лише програми, доступні поточному користувачу за його JWT-токеном. ID користувача у запиті не передається.

**Права:** `MAIN_KOORD` — лише програми, які він створив; `KOORD` — програми, безпосередньо направлені його підрозділу; `VYK` — програми з чинними персональними призначеннями. `ADMIN` та інші ролі отримують `403`.

`access_type`: `owner`, `department_coordinator` або `executor`.""",
    response_description='Список програм із видом доступу.',
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
    summary='Переглянути доступну програму',
    description="""Повертає паспорт програми (`ProgramRead`) **тільки якщо** поточний користувач має доступ до неї за правилами `GET /my/programs`.

**Помилки:** `404` — програми немає; `403` — існує, але користувач не має прав на перегляд.""",
    response_description='Повна інформація про доступну програму.',
)
def read_visible_program(
    program_id: Annotated[str, Path(description='Ідентифікатор антикорупційної програми')],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отримати паспорт програми лише після перевірки доступу."""
    return handle(lambda: ProgramWorkflowService(db).visible_program(program_id, user))


@router.get(
    "/programs/{program_id}/sections",
    response_model=list[SectionBriefRead],
    summary='Переглянути розділи програми',
    description="""Після перевірки доступу до програми повертає розділи з довідника `sections`: код, номер і назву.

**Важливо:** довідник `sections` спільний для всіх програм, але цей ендпоінт повертає **тільки розділи, що містять доступні користувачу заходи** вказаної програми.""",
    response_description='Довідник розділів із кодами, номерами й назвами.',
)
def program_sections(
    program_id: Annotated[str, Path(description='Ідентифікатор антикорупційної програми')],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отримати розділи з доступними користувачу заходами програми."""
    return handle(lambda: ProgramWorkflowService(db).program_sections(program_id, user))


@router.get(
    "/programs/{program_id}/measures",
    response_model=list[MeasureBriefRead],
    summary='Переглянути доступні заходи програми',
    description="""Повертає короткі відомості про заходи вказаної програми з урахуванням прав користувача.

**Права:** `MAIN_KOORD` бачить усі заходи **власної** програми; `KOORD` із прямим направленням — **усі заходи цієї програми**, щоб призначати виконавців зі своєї гілки; `VYK` — лише свої **дійсні персональні призначення**. `ADMIN` доступу не має.

Виконавець без призначених заходів цієї програми отримає `403`. Для інших сторонніх користувачів доступ заборонено.""",
    response_description='Список доступних заходів у скороченому вигляді.',
)
def program_measures(
    program_id: Annotated[str, Path(description='Ідентифікатор антикорупційної програми')],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отримати заходи програми відповідно до прав користувача."""
    return handle(lambda: ProgramWorkflowService(db).program_measures(program_id, user))


@router.get(
    "/my/measures",
    response_model=list[MeasureBriefRead],
    summary='Переглянути мої призначені заходи',
    description="""Повертає всі доступні особисто призначені заходи поточного користувача.

**Права:** тільки користувач із роллю `VYK`, якому визначено `department_id`. Необхідні чинне призначення в `measure_assignments` і направлення програми до його підрозділу або предка. `responsible_department_id` не блокує персональне призначення.

Якщо виконавець ще не має заходів, повертається порожній список (`200`), а не помилка.""",
    response_description='Список особисто призначених заходів виконавця.',
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
    summary='Знайти координаторів підрозділу',
    description="""Повертає користувачів вибраного підрозділу з роллю `KOORD`. Це потрібно перед направленням програми: одержати її може тільки підрозділ, у якому є координатор.

**Права:** `MAIN_KOORD`-власник може переглядати координаторів будь-якого підрозділу для своєї програми; `KOORD` — лише власного підрозділу та нащадків, якщо програму безпосередньо направлено його підрозділу. `ADMIN` і `VYK` не мають доступу.

Повертаються: `id`, `login`, `role_id`, `department_id`.""",
    response_description='Координатори вибраного підрозділу.',
)
def get_coordinators(
    program_id: Annotated[str, Path(description='Ідентифікатор антикорупційної програми')],
    department_id: Annotated[str, Path(description='Код підрозділу в ієрархії')],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Знайти користувачів KOORD у доступному підрозділі."""
    return handle(lambda: ProgramWorkflowService(db).department_coordinators(
        program_id, department_id, user
    ))


@router.get(
    "/programs/{program_id}/departments/{department_id}/executors",
    response_model=list[CoordinatorRead],
    summary='Знайти виконавців підрозділу',
    description="""Повертає користувачів підрозділу з роллю `VYK`, яких можна вибрати для призначення на захід.

**Права:** тільки `KOORD`, який безпосередньо отримав програму, може переглядати виконавців свого підрозділу та нащадків. `MAIN_KOORD`, `VYK` та `ADMIN` у цьому ендпоінті не мають доступу.

**Примітка:** використовується схема відповіді `CoordinatorRead`, але самі записи мають роль `VYK`.""",
    response_description='Виконавці обраного підрозділу.',
)
def get_executors(
    program_id: Annotated[str, Path(description='Ідентифікатор антикорупційної програми')],
    department_id: Annotated[str, Path(description='Код підрозділу в ієрархії')],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Знайти користувачів VYK у дозволеному підрозділі."""
    return handle(lambda: ProgramWorkflowService(db).department_executors(
        program_id, department_id, user
    ))


@router.post(
    "/measures/{measure_id}/assign",
    response_model=AssignmentResult,
    summary='Призначити виконавця на захід',
    description="""Створює персональний доступ користувача до конкретного заходу. Передай `department_id` та `user_id` у JSON.

**Права:** призначати може тільки `KOORD`, який безпосередньо отримав програму. `ADMIN`, `MAIN_KOORD` і `VYK` не можуть призначати виконавців.

Сервер перевіряє: **(1)** програма безпосередньо направлена підрозділу `KOORD`; **(2)** вибраний підрозділ є власним або нащадком підрозділу `KOORD`; **(3)** користувач має роль `VYK` і належить обраному підрозділу. `responsible_department_id` заходу не обмежує призначення.

**Результат:** `assignment` і `already_assigned`. Якщо призначення вже існує, новий запис не створюється.

**Помилки:** `403` — чужа гілка/програма; `404` — відсутній захід, підрозділ або користувач; `409` — попереднє призначення цього користувача в іншому підрозділі; `422` — користувач не відповідає ролі чи підрозділу.""",
    response_description='Створене або вже існуюче призначення.',
)
def assign_measure(
    measure_id: Annotated[str, Path(description='Ідентифікатор заходу')],
    data: AssignMeasureIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Призначити виконавця на захід із перевіркою ієрархії."""
    return handle(lambda: ProgramWorkflowService(db).assign(
        measure_id, data.department_id, data.user_id, user
    ))


@router.get(
    "/measures/{measure_id}/assignments",
    response_model=list[MeasureAssignmentRead],
    summary='Переглянути призначення на захід',
    description="""Повертає перелік персональних призначень на конкретний захід.

**Права:** `MAIN_KOORD`-власник — усі призначення в межах власної програми; `KOORD` із прямим направленням — **лише призначення у власному підрозділі та підлеглих** для заходів отриманої програми. `ADMIN` доступу не має.

Виконавці та сторонні координатори не можуть переглядати цей список. Відповідь містить користувача, підрозділ, автора й час призначення.""",
    response_description='Список призначень, доступних координатору.',
)
def measure_assignments(
    measure_id: Annotated[str, Path(description='Ідентифікатор заходу')],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Переглянути дозволені призначення конкретного заходу."""
    return handle(lambda: ProgramWorkflowService(db).list_assignments(measure_id, user))


@router.delete(
    "/measures/{measure_id}/assign/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Скасувати призначення виконавця',
    description="""Видаляє персональне призначення конкретного виконавця до заходу. Не видаляє ані самого користувача, ані захід.

**Права:** тільки `KOORD` може скасувати призначення у власному підрозділі або підлеглих, якщо програму безпосередньо направлено його підрозділу. `ADMIN`, `MAIN_KOORD` і `VYK` не можуть скасовувати призначення.

**Успіх:** `204 No Content` — без JSON-тіла. **Якщо запису призначення немає:** `404`.""",
    response_description='Призначення видалено; тіло відповіді відсутнє.',
)
def unassign_measure(
    measure_id: Annotated[str, Path(description='Ідентифікатор заходу')],
    user_id: Annotated[int, Path(ge=1, description='Числовий ID виконавця, якому скасовують призначення')],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Відкликати особисте призначення виконавця; успіх — 204."""
    handle(lambda: ProgramWorkflowService(db).revoke(measure_id, user_id, user))


@router.get("/measures/{measure_id}/assignment-people",
            summary="Призначені виконавці з логінами; only visible KOORD/MAIN_KOORD")
def assignment_people(
    measure_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role_id not in {"KOORD", "MAIN_KOORD"}:
        raise HTTPException(status_code=403, detail="Недостатньо прав")
    assignments = handle(lambda: ProgramWorkflowService(db).list_assignments(measure_id, user))
    output = []
    for assignment in assignments:
        executor = db.get(User, assignment.user_id)
        output.append({
            "user_id": assignment.user_id,
            "login": executor.login if executor else f"#{assignment.user_id}",
            "department_id": assignment.department_id,
        })
    return output


@router.get('/programs/{program_id}/progress', summary='MAIN_KOORD: прогрес подань за направленими підрозділами')
def program_progress(
    program_id: str,
    period: str = Query(..., pattern=r'^\d{4}-H[12]$'),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Read-only. One executor is counted in the nearest dispatched department.

    An assignment counts only while the user is an executor of that department.
    No assignments => no fictitious approved progress.
    """
    if user.role_id != 'MAIN_KOORD':
        raise HTTPException(status_code=403, detail='Тільки головний координатор')
    workflow = ProgramWorkflowService(db)
    program = handle(lambda: workflow.visible_program(program_id, user))
    if program.created_by_user_id != user.id:
        raise HTTPException(status_code=403, detail='Не ваша програма')

    sent_rows = db.execute(
        select(ProgramDepartment.department_id, Department.name)
        .join(Department, Department.id == ProgramDepartment.department_id)
        .where(ProgramDepartment.program_id == program_id)
        .order_by(Department.name, ProgramDepartment.department_id)
    ).all()
    measure_ids = set(db.scalars(select(Measure.id).where(Measure.program_id == program_id)))
    result = {
        'program_id': program_id,
        'period': period,
        'measures_total': len(measure_ids),
        'unassigned_measures': len(measure_ids),
        'departments': [],
    }
    if not sent_rows or not measure_ids:
        result['departments'] = [
            {'department_id': dep_id, 'department_name': name,
             'assigned': 0, 'approved': 0, 'pending': 0,
             'rejected': 0, 'not_submitted': 0,
             'measures_total': 0, 'measures_approved': 0, 'measures': []}
            for dep_id, name in sent_rows
        ]
        return result

    # The router already verifies ownership; the tree is used ONLY to group
    # assignments within explicitly dispatched departments, including descendants.
    tree = workflow.tree
    recipients = {dep_id: name for dep_id, name in sent_rows}
    grouped = {dep_id: {} for dep_id in recipients}
    assigned_measures = set()
    assignments = db.execute(
        select(MeasureAssignment.measure_id, MeasureAssignment.user_id, MeasureAssignment.department_id)
        .join(User, User.id == MeasureAssignment.user_id)
        .where(
            MeasureAssignment.measure_id.in_(measure_ids),
            User.role_id == 'VYK',
            User.department_id == MeasureAssignment.department_id,
        )
    ).all()
    submissions = {
        (entry.measure_id, entry.submitted_by_user_id): entry
        for entry in db.scalars(select(Execution).where(
            Execution.measure_id.in_(measure_ids), Execution.period == period
        ))
    }
    for measure_id, executor_id, assigned_dept in assignments:
        ancestors = tree.ancestors(assigned_dept)
        candidates = [d for d in recipients if d in ancestors]
        if not candidates:
            continue
        # A nested dispatch must not double-count the same executor.
        recipient = max(candidates, key=lambda d: len(tree.ancestors(d)))
        stats = grouped[recipient].setdefault(measure_id, {
            'measure_id': measure_id, 'assigned': 0, 'approved': 0,
            'pending': 0, 'rejected': 0, 'not_submitted': 0,
        })
        assigned_measures.add(measure_id)
        stats['assigned'] += 1
        entry = submissions.get((measure_id, executor_id))
        if entry is None:
            stats['not_submitted'] += 1
        elif (entry.status == 'approved' and not entry.document_changed
              and entry.order_version_id is not None and entry.submitted_sha256):
            stats['approved'] += 1
        elif entry.status == 'rejected' and not entry.document_changed:
            stats['rejected'] += 1
        else:
            # Pending, stale documents and inconsistent approved submissions.
            stats['pending'] += 1

    result['unassigned_measures'] = len(measure_ids - assigned_measures)
    for dep_id, name in sent_rows:
        per_measure = sorted(grouped[dep_id].values(), key=lambda row: row['measure_id'])
        result['departments'].append({
            'department_id': dep_id, 'department_name': name,
            'assigned': sum(row['assigned'] for row in per_measure),
            'approved': sum(row['approved'] for row in per_measure),
            'pending': sum(row['pending'] for row in per_measure),
            'rejected': sum(row['rejected'] for row in per_measure),
            'not_submitted': sum(row['not_submitted'] for row in per_measure),
            'measures_total': len(per_measure),
            'measures_approved': sum(row['assigned'] > 0 and row['approved'] == row['assigned'] for row in per_measure),
            'measures': per_measure,
        })
    return result

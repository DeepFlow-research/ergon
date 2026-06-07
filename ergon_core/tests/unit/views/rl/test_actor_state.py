from datetime import UTC, datetime, timedelta
from uuid import UUID

from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.samples.models import SampleWorkerEventRow
from ergon_core.core.persistence.shared.enums import SampleStatus
from ergon_core.core.persistence.telemetry.models import SampleRecord
from ergon_core.core.views.rl.actor_state import SampleActorReadService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


SAMPLE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ROOT_TASK_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
CHILD_TASK_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
SAME_SLUG_CHILD_TASK_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
T0 = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=1)
T2 = T0 + timedelta(minutes=2)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_actor_fixture(session: Session) -> None:
    session.add(
        SampleRecord(
            id=SAMPLE_ID,
            benchmark_type="unit",
            instance_key="actor-fixture",
            status=SampleStatus.EXECUTING,
        )
    )
    session.add_all(
        [
            SampleGraphNode(
                sample_id=SAMPLE_ID,
                task_id=ROOT_TASK_ID,
                instance_key="actor-fixture",
                task_slug="root",
                description="Root",
                status="running",
                assigned_worker_slug="planner",
                level=0,
                created_at=T0,
                updated_at=T0,
            ),
            SampleGraphNode(
                sample_id=SAMPLE_ID,
                task_id=CHILD_TASK_ID,
                instance_key="actor-fixture",
                task_slug="child",
                description="Child",
                status="pending",
                assigned_worker_slug="researcher",
                parent_task_id=ROOT_TASK_ID,
                level=1,
                created_at=T1,
                updated_at=T1,
            ),
            SampleGraphNode(
                sample_id=SAMPLE_ID,
                task_id=SAME_SLUG_CHILD_TASK_ID,
                instance_key="actor-fixture",
                task_slug="same-slug-child",
                description="Same slug child",
                status="pending",
                assigned_worker_slug="planner",
                parent_task_id=ROOT_TASK_ID,
                level=1,
                created_at=T1,
                updated_at=T1,
            ),
        ]
    )
    session.add_all(
        [
            SampleWorkerEventRow(
                sample_id=SAMPLE_ID,
                task_id=ROOT_TASK_ID,
                worker_slug="planner",
                event_timestamp=T0,
                event_type="worker.added",
            ),
            SampleWorkerEventRow(
                sample_id=SAMPLE_ID,
                task_id=CHILD_TASK_ID,
                worker_slug="researcher",
                event_timestamp=T1,
                event_type="worker.added",
            ),
            SampleWorkerEventRow(
                sample_id=SAMPLE_ID,
                task_id=CHILD_TASK_ID,
                worker_slug="researcher",
                event_timestamp=T2,
                event_type="worker.removed",
            ),
        ]
    )
    session.commit()


def test_root_task_with_worker_produces_root_actor() -> None:
    session = _session()
    _seed_actor_fixture(session)

    state = SampleActorReadService(session).get_actor_state(SAMPLE_ID, at_time=T1)

    root_actor = next(actor for actor in state.actors if actor.task_id == ROOT_TASK_ID)
    assert root_actor.actor_slug == "planner"
    assert root_actor.parent_actor_slug is None
    assert [root.actor.task_id for root in state.roots] == [ROOT_TASK_ID]


def test_child_task_derives_parent_actor_slug_from_parent_task() -> None:
    session = _session()
    _seed_actor_fixture(session)

    state = SampleActorReadService(session).get_actor_state(SAMPLE_ID, at_time=T1)

    child_actor = next(actor for actor in state.actors if actor.task_id == CHILD_TASK_ID)
    assert child_actor.actor_slug == "researcher"
    assert child_actor.parent_actor_slug == "planner"


def test_same_worker_slug_parent_and_child_remain_separate_task_linked_actors() -> None:
    session = _session()
    _seed_actor_fixture(session)

    state = SampleActorReadService(session).get_actor_state(SAMPLE_ID, at_time=T1)

    planner_records = [actor for actor in state.actors if actor.actor_slug == "planner"]
    assert {actor.task_id for actor in planner_records} == {ROOT_TASK_ID, SAME_SLUG_CHILD_TASK_ID}
    same_slug_child = next(actor for actor in planner_records if actor.task_id != ROOT_TASK_ID)
    assert same_slug_child.parent_task_id == ROOT_TASK_ID
    assert same_slug_child.parent_actor_slug == "planner"


def test_availability_replays_worker_added_and_removed_events_at_time() -> None:
    session = _session()
    _seed_actor_fixture(session)

    before_removal = SampleActorReadService(session).get_actor_state(SAMPLE_ID, at_time=T1)
    after_removal = SampleActorReadService(session).get_actor_state(SAMPLE_ID, at_time=T2)

    assert next(
        actor for actor in before_removal.actors if actor.actor_slug == "researcher"
    ).is_available
    assert not next(
        actor for actor in after_removal.actors if actor.actor_slug == "researcher"
    ).is_available


def test_include_events_false_omits_per_actor_events() -> None:
    session = _session()
    _seed_actor_fixture(session)

    without_events = SampleActorReadService(session).get_actor_state(SAMPLE_ID)
    with_events = SampleActorReadService(session).get_actor_state(SAMPLE_ID, include_events=True)

    assert all(actor.events == [] for actor in without_events.actors)
    assert any(actor.events for actor in with_events.actors)

import pytest
from unittest import mock

from rendercontroller.controller import RenderQueue
from rendercontroller.job import WAITING, FINISHED, RENDERING, STOPPED, FAILED


class DummyJob(object):
    def __init__(self, id, status):
        self.id = id
        self.status = status


queue_jobs = [
    DummyJob("job1", WAITING),
    DummyJob("job2", FINISHED),
    DummyJob("job3", RENDERING),
    DummyJob("job4", STOPPED),
    DummyJob("job5", FINISHED),
    DummyJob("job6", WAITING),
]
orig_keys = ["job1", "job2", "job3", "job4", "job5", "job6"]


@pytest.fixture(scope="function")
def queue():
    q = RenderQueue()
    for i in queue_jobs:
        q.append(i)
    return q


# Test the dunder/magic methods first
@mock.patch("rendercontroller.controller.OrderedDict")
def test_queue_init(od):
    od.assert_not_called()
    q = RenderQueue()
    od.assert_called_once()
    assert q.jobs is od.return_value
    assert q.index == 0


def test_queue_iterates(queue):
    i = 0
    for job in queue:
        assert job.id == queue_jobs[i].id
        i += 1


def test_queue_len(queue):
    assert len(queue) == len(queue_jobs)


def test_queue_str(queue):
    # Not going to try to test an exact match b/c memory addresses str(RenderJob)
    # Just make sure it returns a string without blowing up.
    assert str(queue).startswith("RenderQueue(")

def test_queue_getitem(queue):
    assert queue[0] is queue_jobs[0]
    assert queue[3] is queue_jobs[3]
    assert queue[5] is queue_jobs[5]
    assert queue[-1] is queue_jobs[5]
    with pytest.raises(IndexError):
        queue[99]


def test_queue_contains(queue):
    assert "job1" in queue
    assert "job99" not in queue


def test_queue_slice(queue):
    assert queue_jobs[2] == queue[2]
    assert queue_jobs[1:3] == [j for j in queue[1:3]]
    assert queue_jobs[-1] == queue[-1]
    assert queue_jobs[2:-3] == [j for j in queue[2:-3]]


# Now test public methods and other functionality
def test_queue_order(queue):
    """Make sure queue is in the expected order."""
    assert queue.keys() == orig_keys


def test_queue_append(queue):
    for i in queue_jobs:
        queue.append(i)
    assert queue.keys() == orig_keys
    queue.append(DummyJob("job7", RENDERING))
    assert queue.keys() == orig_keys + [
        "job7",
    ]


def test_queue_pop(queue):
    for i in queue_jobs:
        queue.append(i)
    assert queue.keys() == orig_keys
    job = queue.pop("job4")
    assert job == queue_jobs[3]
    assert job not in queue
    with pytest.raises(KeyError):
        queue.pop("badkey")


def test_queue_get_by_id(queue):
    for i in range(len(queue_jobs)):
        job = queue_jobs[i]
        assert job == queue.get_by_id(job.id)
    with pytest.raises(KeyError):
        queue.get_by_id("badkey")


def test_queue_get_by_position(queue):
    for i in range(len(queue_jobs)):
        assert queue_jobs[i].id == queue.get_by_position(i).id
    with pytest.raises(IndexError):
        queue.get_by_position(999)


def test_queue_insert(queue):
    for i in queue_jobs:
        queue.append(i)
    assert queue.keys() == orig_keys
    queue.insert(DummyJob("job7", RENDERING), 3)
    assert queue.keys() == ["job1", "job2", "job3", "job7", "job4", "job5", "job6"]


def test_queue_keys(queue):
    assert queue.keys() == [job.id for job in queue_jobs]


def test_queue_values(queue):
    assert queue.values() == queue_jobs


def test_queue_move(queue):
    for i in queue_jobs:
        queue.append(i)
    assert queue.keys() == orig_keys
    queue.move("job2", 4)
    assert queue.keys() == ["job1", "job3", "job4", "job5", "job2", "job6"]


def test_queue_sort_by_status(queue):
    for i in queue_jobs:
        queue.append(i)
    assert queue.keys() == orig_keys
    queue.sort_by_status()
    assert queue.keys() == ["job1", "job3", "job4", "job6", "job2", "job5"]


def test_queue_get_next_waiting(queue):
    for i in queue_jobs:
        queue.append(i)
    assert queue.keys() == orig_keys
    next = queue.get_next_waiting()
    assert next == queue_jobs[0]
    # Simulate starting render
    queue[0].status = RENDERING
    again = queue.get_next_waiting()
    assert again == queue_jobs[5]
    # Simulate starting again
    queue[5].status = RENDERING
    # Should be none left
    assert queue.get_next_waiting() is None


def test_queue_count_status(queue):
    assert queue.count_status(FINISHED) == 2
    assert queue.count_status(STOPPED) == 1
    assert queue.count_status(FAILED) == 0


def test_queue_get_position(queue):
    for i in queue_jobs:
        queue.append(i)
    assert queue.get_position("job1") == 0
    assert queue.get_position("job4") == 3

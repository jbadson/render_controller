import pytest
import time
from unittest import mock
from rendercontroller.job import RenderJob
from rendercontroller.constants import WAITING, RENDERING, FINISHED, STOPPED, FAILED
from rendercontroller.exceptions import JobStatusError, NodeNotFoundError


class LoopStopper(object):
    """Mocks a boolean object, but changes value after it's been accessed a set number of times.

    Allows a while loop to be stopped after a set number of iterations for testing purposes."""

    def __init__(self, max_count=1):
        self.max_count = max_count
        self.call_count = 0

    def __bool__(self):
        if self.call_count >= self.max_count:
            return True
        self.call_count += 1
        return False

    def reset(self):
        self.call_count = 0


@pytest.fixture(scope="function")
def testjob1():
    """Minimum set of kwargs.  Mimics creating a new job.

    Note: Must be in fixture to pass-by-reference induced confusion if tests change values."""
    return {
        "id": "job01",
        "path": "/tmp/job1.blend",
        "start_frame": 0,
        "end_frame": 100,
        "render_nodes": ["node1", "node2"],
    }


@pytest.fixture(scope="function")
def testjob2():
    """Complete kwargs. Mimics restoring from db."""
    return {
        "id": "job02",
        "status": RENDERING,
        "path": "/tmp/job2.blend",
        "start_frame": 0,
        "end_frame": 25,
        "render_nodes": ["node1", "node2", "node3"],
        "time_start": 1643945770.027214,
        "time_stop": 1643945813.785717,
        "time_offset": 300,
        "frames_completed": [0, 1, 2, 3, 4, 5, 6, 7, 8],
    }


# Do not share mutable types in tests
render_nodes = (
    "node1",
    "node2",
    "node3",
    "node4",
)


@pytest.fixture(scope="function")
def job1(testjob1):
    """RenderJob fixture representing a newly enqueued job with default values."""
    conf = mock.MagicMock(name="Config")
    conf.render_nodes = render_nodes
    db = mock.MagicMock(name="StateDatabase")
    mt = mock.MagicMock(name="RenderJob.master_thread")
    job = RenderJob(conf, db, **testjob1)
    job.master_thread = mt
    return job


@pytest.fixture(scope="function")
@mock.patch("rendercontroller.job.BlenderRenderThread")
@mock.patch("rendercontroller.job.RenderJob._mainloop")
def job2(ml, rt, testjob2):
    """RenderJob fixture representing a job that is currently rendering."""
    conf = mock.MagicMock(name="Config")
    rt.return_value = None
    conf.render_nodes = render_nodes
    db = mock.MagicMock(name="StateDatabase")
    job = RenderJob(conf, db, **testjob2)
    job.time_stop = 0.0
    return job


@mock.patch("rendercontroller.job.Executor")
@mock.patch("rendercontroller.controller.Config")
def test_job_init_new(conf, ex, testjob1):
    """Tests creating a new job."""
    conf.render_nodes = render_nodes
    db = mock.MagicMock(name="StateDatabase")
    j = RenderJob(conf, db, **testjob1)
    # Check passed params
    assert j.config is conf
    assert j.db is db
    assert j.id == testjob1["id"]
    assert j.path == testjob1["path"]
    assert j.start_frame == testjob1["start_frame"]
    assert j.end_frame == testjob1["end_frame"]
    assert j.nodes_enabled == testjob1["render_nodes"]
    # Check generated params
    assert j.status == WAITING
    assert j.time_start == 0.0
    assert j.time_stop == 0.0
    assert j.time_offset == 0.0
    assert j.frames_completed == set()
    queue_expected = list(range(0, 100 + 1))
    queue_actual = []
    while not j.queue.empty():
        queue_actual.append(j.queue.get())
    assert queue_actual == queue_expected
    assert j.skip_list == []
    node_status_expected = {
        "node1": ex.return_value,
        "node2": ex.return_value,
        "node3": ex.return_value,
        "node4": ex.return_value,
    }
    assert j.node_status == node_status_expected
    # Test start frame > end frame
    with pytest.raises(ValueError):
        j = RenderJob(conf, db, "failjob", "/tmp/failjob", 10, 5, render_nodes)


@mock.patch("rendercontroller.job.Executor")
@mock.patch("rendercontroller.controller.Config")
@mock.patch("rendercontroller.job.RenderJob.render")
def test_job_init_restore(render, conf, ex, testjob2):
    """Tests restoring a job from disk."""
    conf.render_nodes = render_nodes
    db = mock.MagicMock(name="StateDatabase")
    j = RenderJob(conf, db, **testjob2)
    # Check passed params
    assert j.config is conf
    assert j.db is db
    assert j.id == testjob2["id"]
    assert j.path == testjob2["path"]
    assert j.start_frame == testjob2["start_frame"]
    assert j.end_frame == testjob2["end_frame"]
    assert j.nodes_enabled == testjob2["render_nodes"]
    # Status is reset to WAITING before render() is called
    assert j.status == WAITING
    assert j.time_start == testjob2["time_start"]
    assert j.time_stop == testjob2["time_stop"]
    assert j.time_offset == testjob2["time_offset"]
    assert j.frames_completed == set(testjob2["frames_completed"])
    # Check generated params
    queue_expected = list(range(9, 25 + 1))
    queue_actual = []
    while not j.queue.empty():
        queue_actual.append(j.queue.get())
    assert queue_actual == queue_expected
    assert j.skip_list == []
    render.assert_called_once()
    node_status_expected = {
        "node1": ex.return_value,
        "node2": ex.return_value,
        "node3": ex.return_value,
        "node4": ex.return_value,
    }
    assert j.node_status == node_status_expected


def test_job_set_status(job1, testjob1):
    assert job1.status == WAITING
    job1.db.update_job_status.assert_not_called()
    job1._set_status(STOPPED)
    assert job1.status == STOPPED
    job1.db.update_job_status.assert_called_with(testjob1["id"], STOPPED)


@mock.patch("rendercontroller.job.RenderJob._start_timer")
def test_job_render(timer, job1):
    timer.assert_not_called()
    job1.master_thread.start.assert_not_called()
    assert job1.status == WAITING
    job1.render()
    assert job1.status == RENDERING
    timer.assert_called_once()
    job1.master_thread.start.assert_called_once()
    # Make sure it won't render a job that's already rendering
    with pytest.raises(JobStatusError):
        job1.render()


def test_job_stop(job1):
    assert job1._stop is False
    job1.stop()
    assert job1._stop is True


def test_job_enable_node(job1, testjob1):
    # Should throw exception if node not in Config.render_nodes
    with pytest.raises(NodeNotFoundError):
        job1.enable_node("fakenode")
    # Now try good node
    newnode = "node3"
    nodes_expected = [*testjob1["render_nodes"], newnode]
    assert newnode not in job1.nodes_enabled
    job1.enable_node(newnode)
    assert newnode in job1.nodes_enabled
    assert len(job1.nodes_enabled) == 3
    job1.db.update_nodes.assert_called_with(testjob1["id"], nodes_expected)
    job1.db.update_nodes.reset_mock()
    # Should quietly do nothing if node is already enabled
    job1.enable_node(newnode)
    assert newnode in job1.nodes_enabled
    assert job1.nodes_enabled == nodes_expected
    job1.db.update_nodes.assert_not_called()


def test_job_disable_node(job1, testjob1):
    # Should throw exception if node not in Config.render_nodes
    with pytest.raises(NodeNotFoundError):
        job1.disable_node("fakenode")
    # Now try good node
    newnode = "node1"
    assert newnode in job1.nodes_enabled
    job1.disable_node(newnode)
    assert newnode not in job1.nodes_enabled
    assert len(job1.nodes_enabled) == 1
    nodes_expected = ["node2"]
    job1.db.update_nodes.assert_called_with(testjob1["id"], nodes_expected)
    job1.db.update_nodes.reset_mock()
    # Should quietly do nothing if node is already disabled
    job1.disable_node(newnode)
    assert newnode not in job1.nodes_enabled
    assert job1.nodes_enabled == nodes_expected
    job1.db.update_nodes.assert_not_called()


def test_job_get_progress(job1):
    assert job1.status == WAITING
    assert job1.frames_completed == set()
    assert job1.get_progress() == 0.0
    job1.frames_completed = set(range(25))
    assert job1.get_progress() == pytest.approx(24.75, rel=1e-3)
    job1.frames_completed = set(range(75))
    assert job1.get_progress() == pytest.approx(74.26, rel=1e-3)
    job1.frames_completed = set(range(job1.start_frame, job1.end_frame + 1))
    assert job1.get_progress() == 100.0
    # Make sure we don't divide by zero if start_frame == end_frame
    job1.end_frame = 0
    assert job1.start_frame == job1.end_frame
    job1.frames_completed = set()
    assert job1.get_progress() == 0.0


def test_job_get_times(job1):
    # Case 1: New job waiting in queue (time_start not set)
    assert job1.time_start == 0.0
    assert job1.get_times() == (0.0, 0.0, 0.0)

    # Case 2: Job finished or restored from disk (time_stop has been set)
    # Case 2a: Job was started then stopped but never rendered a frame.
    job1.time_stop = time.time()
    job1.time_start = job1.time_stop - 100
    elapsed, avg, rem = job1.get_times()
    assert elapsed == 100.0
    assert avg == 0.0
    assert rem == 0.0
    # Case 2b: Job rendered some frames before it was stopped.
    job1.frames_completed = [i for i in range(25)]
    elapsed, avg, rem = job1.get_times()
    # 100 seconds to render 25 frames => 4 sec/frame and 304s remaining
    assert elapsed == 100.0
    assert avg == 4.0
    assert rem == 304.0

    # Case 3: Job currently rendering (time_start has been set, time_stop has not)
    job1.time_stop = 0.0
    # Case 3a: Job just started, no frames finished yet
    job1.frames_completed = []
    assert job1.time_start > 0.0
    elapsed, avg, rem = job1.get_times()
    # RenderThread is mocked, so elapsed will increase but no frames will ever finish
    assert elapsed > 0.0
    assert avg == 0.0
    assert rem == 0.0
    # Case 3b: Job has been rendering for a while, some frames finished
    job1.frames_completed = [i for i in range(25)]
    assert job1.time_stop == 0.0
    job1.time_start = time.time() - 100
    elapsed, avg, rem = job1.get_times()
    # A little lag between subsequent calls to time.time(), so use approx.
    assert elapsed == pytest.approx(100.0)
    assert avg == pytest.approx(4.0)
    assert rem == pytest.approx(304.0)


def test_job_dump(job1, job2, testjob1, testjob2):
    # New job, nothing rendered yet. Most fields will be default values
    assert job1.dump() == {
        "id": testjob1["id"],
        "path": testjob1["path"],
        "start_frame": testjob1["start_frame"],
        "end_frame": testjob1["end_frame"],
        "nodes_enabled": testjob1["render_nodes"],
        "status": WAITING,
        "time_start": 0.0,
        "time_stop": 0.0,
        "time_elapsed": 0.0,
        "time_avg_per_frame": 0.0,
        "time_remaining": 0.0,
        "frames_completed": [],
        "progress": 0.0,
        "node_status": {
            node: {
                "frame": None,
                "progress": 0.0,
                "enabled": True if node in job1.nodes_enabled else False,
                "rendering": False,
            }
            for node in render_nodes
        },
    }
    # Job that has been rendering
    elapsed, avg, rem = job2.get_times()
    dump = job2.dump()
    # Have to do this one at a time because of approx times.
    assert dump["id"] == testjob2["id"]
    assert dump["path"] == testjob2["path"]
    assert dump["start_frame"] == testjob2["start_frame"]
    assert dump["end_frame"] == testjob2["end_frame"]
    assert dump["nodes_enabled"] == testjob2["render_nodes"]
    assert dump["status"] == RENDERING
    assert dump["time_start"] == job2.time_start
    assert dump["time_stop"] == 0.0
    assert dump["time_elapsed"] == pytest.approx(elapsed)
    assert dump["time_avg_per_frame"] == pytest.approx(avg)
    assert dump["time_remaining"] == pytest.approx(rem)
    assert dump["frames_completed"] == testjob2["frames_completed"]
    assert dump["progress"] == job2.get_progress()
    # Master thread is mocked, so node status should be defaults
    assert dump["node_status"] == {
        node: {
            "frame": None,
            "progress": 0.0,
            "enabled": True if node in testjob2["render_nodes"] else False,
            "rendering": False,
        }
        for node in render_nodes
    }


@mock.patch("rendercontroller.job.Executor")
def test_job_frames_rendering(ex, job1):
    assert job1.frames_rendering() is False
    job1.node_status["node2"] = mock.MagicMock(name="Executor")
    job1.node_status["node2"].is_idle.return_value = False
    assert job1.frames_rendering() is True


@mock.patch("rendercontroller.job.Executor")
def test_job_get_nodes_status(ex, job1):
    expected = {
        "node1": {"frame": None, "progress": 0.0, "enabled": True, "rendering": False},
        "node2": {"frame": None, "progress": 0.0, "enabled": True, "rendering": False},
        "node3": {"frame": None, "progress": 0.0, "enabled": False, "rendering": False},
        "node4": {"frame": None, "progress": 0.0, "enabled": False, "rendering": False},
    }
    # Case 1: Defaults & node enabled but idle
    assert job1.get_nodes_status() == expected
    # Case 2: Node enabled and rendering
    job1.node_status["node2"] = mock.MagicMock(name="Executor")
    job1.node_status["node2"].frame = 1
    job1.node_status["node2"].is_idle.return_value = False
    job1.node_status["node2"].progress = 15.0
    expected["node2"] = {
        "frame": 1,
        "progress": 15.0,
        "enabled": True,
        "rendering": True,
    }
    assert job1.get_nodes_status() == expected


@mock.patch("time.time")
def test_job_start_timer1(timer, job1):
    """Case 1: New job, status waiting (i.e. time_start not set), no offset.

    Correction factor should be 0.0
    """
    t = 123.456
    timer.return_value = t
    assert job1.time_start == 0.0
    assert job1.time_offset == 0.0
    job1.db.update_job_time_start.assert_not_called()
    job1._start_timer()
    assert job1.time_start == t
    assert job1.time_offset == 0.0
    job1.db.update_job_time_start.assert_called_with(job1.id, t)


@mock.patch("time.time")
def test_job_start_timer2(timer, job1):
    """Case 2: New or restored job, status waiting, offset.

    Offset should be ignored, correction factor should be 0.0
    """
    t = 123.456
    timer.return_value = t
    job1.time_offset = 10.2
    job1.db.update_job_time_start.assert_not_called()
    assert not job1.time_start
    assert not job1.time_stop
    job1._start_timer()
    assert job1.time_start == t
    assert job1.time_offset == 0.0
    job1.db.update_job_time_start.assert_called_with(job1.id, t)


@mock.patch("time.time")
def test_job_start_timer3(timer, job1):
    """Case 3: Stopped or finished job (time_start and time_stop both set), no offset.

    Correction factor should be time_stop - time_start
    """
    t = 123.456
    timer.return_value = t
    start = 51.5
    stop = 100.0
    job1.time_start = start
    job1.time_stop = stop
    assert job1.time_offset == 0.0
    job1.db.update_job_time_start.assert_not_called()
    job1._start_timer()
    expected = t - (stop - start)
    assert job1.time_start == expected
    assert job1.time_stop == 0.0
    assert job1.time_offset == 0.0
    job1.db.update_job_time_start.assert_called_with(job1.id, expected)


@mock.patch("time.time")
def test_job_start_timer4(timer, job1):
    """Case 4: Stopped or finished job with offset.

    Offset should be ignored, correction factor should be time_stop - time_start
    """
    t = 123.456
    timer.return_value = t
    start = 51.5
    stop = 100.0
    job1.time_start = start
    job1.time_stop = stop
    job1.time_offset = 10.2
    job1.db.update_job_time_start.assert_not_called()
    job1._start_timer()
    expected = t - (stop - start)
    assert job1.time_start == expected
    assert job1.time_stop == 0.0
    assert job1.time_offset == 0.0
    job1.db.update_job_time_start.assert_called_with(job1.id, expected)


@mock.patch("time.time")
def test_job_start_timer5(timer, job1):
    """Case 5: Restoring job from disk, status rendering (time_start is set, time_stop is not), offset.

    Correction factor should == offset
    """
    t = 123.456
    timer.return_value = t
    start = 51.5
    offset = 10.2
    job1.time_start = start
    job1.time_offset = offset
    assert job1.time_stop == 0.0
    job1.db.update_job_time_start.assert_not_called()
    job1._start_timer()
    expected = t - offset
    assert job1.time_start == expected
    assert job1.time_stop == 0.0
    assert job1.time_offset == 0.0
    job1.db.update_job_time_start.assert_called_with(job1.id, expected)


@mock.patch("time.time")
def test_job_stop_timer(timer, job1):
    timer.return_value = 123.456
    assert job1.time_stop == 0.0
    job1.db.update_job_time_stop.assert_not_called()
    job1._stop_timer()
    assert job1.time_stop == 123.456
    job1.db.update_job_time_stop.assert_called_with(job1.id, 123.456)


@mock.patch("rendercontroller.job.RenderJob.get_times")
@mock.patch("rendercontroller.job.RenderJob._stop_timer")
def test_job_render_finished(timer, times, job2):
    timer.assert_not_called()
    times.assert_not_called()
    times.return_value = (3.0, 2.0, 1.0)  # Not using in test, but needed in method.
    job2.db.update_job_status.reset_mock()  # Gets called twice in __init__
    assert job2.status == RENDERING
    job2._render_finished()
    assert job2.status == FINISHED
    job2.db.update_job_status.assert_called_with(job2.id, FINISHED)
    timer.assert_called_once()
    times.assert_called_once()


@mock.patch("rendercontroller.job.RenderJob._pop_skipped_node")
def test_job_frame_finished(pop, job1):
    frame = 5
    queue = mock.MagicMock(name="queue.LiFoQueue")
    job1.queue = queue
    job1.queue.task_done.assert_not_called()
    ex = mock.MagicMock(name="Executor")
    job1.node_status["node1"] = ex
    ex.ack_done.assert_not_called()
    pop.assert_not_called()
    assert frame not in job1.frames_completed
    ex.frame = frame
    ex.elapsed_time.return_value = 123.456
    job1._frame_finished("node1")
    job1.queue.task_done.assert_called_once()
    ex.ack_done.assert_called_once()
    assert frame in job1.frames_completed
    job1.db.update_job_frames_completed.assert_called_with(job1.id, {5})
    pop.assert_called_once()


def test_job_frame_failed(job1):
    frame = 5
    node = "node1"
    q = mock.MagicMock(name="queue.LiFoQueue")
    job1.queue = q
    ex = mock.MagicMock(name="Executor")
    ex.frame = frame
    job1.node_status[node] = ex
    assert node not in job1.skip_list
    q.put.assert_not_called()
    ex.ack_done.assert_not_called()
    job1._frame_failed(node)
    q.put.assert_called_with(frame)
    assert node in job1.skip_list
    ex.ack_done.assert_called_once()
    assert frame not in job1.frames_completed


def test_job_pop_skipped_node(job1):
    # Case 1: skip list empty
    assert len(job1.skip_list) == 0
    job1._pop_skipped_node()  # Nothing should happen
    assert len(job1.skip_list) == 0
    # Case 2: Something in skip list
    job1.skip_list.append("node2")
    job1._pop_skipped_node()
    assert "node2" not in job1.skip_list


@mock.patch("rendercontroller.job.RenderJob._render_finished")
def test_job_mainloop_1(rfin, job1):
    """Tests first block of mainloop: checking if job is finished."""
    job1._stop = LoopStopper(1)
    # Case 1: Queue empty and no threads running -> _render_finished
    q = mock.MagicMock(name="queue.LiFoQueue")
    q.empty.return_value = True
    job1.queue = q
    rfin.assert_not_called()
    assert not job1.frames_rendering()
    job1._mainloop()
    rfin.assert_called_once()
    # Corollary: If queue empty but threads *are* running, do not call finished
    rfin.reset_mock()
    ex = mock.MagicMock(name="Executor")
    ex.is_idle.return_value = False
    job1.node_status["node1"] = ex
    ex.is_idle.assert_not_called()
    assert job1.frames_rendering()
    job1._mainloop()
    rfin.assert_not_called()
    ex.is_idle.assert_called_once()


@mock.patch("rendercontroller.job.RenderJob._pop_skipped_node")
def test_job_mainloop_2(pop, job1, testjob1):
    """Tests second block of mainloop: all nodes in skip list"""
    stop = LoopStopper(1)
    job1._stop = stop
    pop.assert_not_called()
    job1.skip_list = testjob1["render_nodes"]
    assert len(job1.skip_list) == 2
    job1._mainloop()
    pop.assert_called_once()
    # Edge case: skip list longer than enabled nodes
    pop.reset_mock()
    pop.assert_not_called()
    job1.skip_list = render_nodes
    assert len(job1.skip_list) > len(job1.nodes_enabled)
    stop.reset()
    job1._mainloop()
    pop.assert_called_once()


@mock.patch("rendercontroller.job.RenderJob._frame_failed")
@mock.patch("rendercontroller.job.RenderJob._frame_finished")
def test_job_mainloop_3(ffin, ffail, job1):
    """Tests first unit of inner (node) loop: node has thread assigned -> check status."""
    stop = LoopStopper(2)
    job1._stop = stop
    mock_node_status = {}
    for node in job1.config.render_nodes:
        mock_node_status[node] = mock.MagicMock(name=f"Executor_{node}")
    job1.node_status = mock_node_status

    # Case 1: FINISHED or FAILED, but mainloop has already ack'd -> do nothing
    # 1a: FINISHED and idle (ack'd)
    job1.node_status["node1"].is_idle.return_value = True
    job1.node_status["node1"].status = FINISHED
    job1._mainloop()
    ffin.assert_not_called()
    ffail.assert_not_called()
    # 1b: FAILED and idle (ack'd)
    stop.reset()
    job1.node_status["node1"].status = FINISHED
    job1._mainloop()
    ffin.assert_not_called()
    ffail.assert_not_called()

    # Case 2: FINISHED but not ack'd -> _frame_finished
    stop.reset()
    job1.node_status["node1"].is_idle.return_value = False
    job1.node_status["node1"].status = FINISHED
    job1._mainloop()
    ffin.assert_called_with("node1")
    ffail.assert_not_called()

    # Case 3: FAILED but not ack'd -> _frame_failed
    stop.reset()
    ffin.reset_mock()
    job1.node_status["node1"].status = FAILED
    job1.node_status["node1"].is_idle.return_value = False
    job1._mainloop()
    ffail.assert_called_with("node1")
    ffin.assert_not_called()


def test_job_mainloop_5(job1):
    """Tests second unit of inner (node) loop: node is idle -> assign frame."""
    stop = LoopStopper(2)
    job1._stop = stop
    q = mock.MagicMock(name="queue.LiFoQueue")
    q.get.return_value = 2
    q.empty.return_value = False
    job1.queue = q
    mock_node_status = {}
    for node in job1.config.render_nodes:
        mock_node_status[node] = mock.MagicMock(name=f"Executor_{node}")
    job1.node_status = mock_node_status
    # Case 1: Node is in skiplist -> do not assign frame
    job1.skip_list = [
        "node1",
    ]
    q.get.assert_not_called()
    job1.node_status["node1"].render.assert_not_called()
    assert "node1" in job1.nodes_enabled
    job1._mainloop()
    q.get.assert_not_called()
    job1.node_status["node1"].render.assert_not_called()

    # Case 2: Node not in skiplist -> assign frame
    stop.reset()
    job1.skip_list = []
    job1.node_status["node1"].reset_mock()
    q.get.assert_not_called()
    job1.node_status["node1"].render.assert_not_called()
    assert "node1" in job1.nodes_enabled
    job1._mainloop()
    q.get.assert_called_once()
    job1.node_status["node1"].render.assert_called_with(2)

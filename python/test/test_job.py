import pytest
import time
from unittest import mock

import rendercontroller.job
from rendercontroller.job import RenderJob
from rendercontroller.constants import WAITING, RENDERING, FINISHED, STOPPED, FAILED
from rendercontroller.exceptions import JobStatusError, NodeNotFoundError
from rendercontroller.util import MagicBool


@pytest.fixture(scope="function")
def testjob1():
    """Minimum set of kwargs.  Mimics creating a new job.

    Note: Must be in fixture to pass-by-reference induced confusion if tests change values."""
    return {
        "id": "job01",
        "path": "/tmp/job1.blend",
        "start_frame": 0,
        "end_frame": 100,
        "render_nodes": ("node1", "node2"),
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
        "render_nodes": ("node1", "node2", "node3"),
        "time_start": 1643945770.027214,
        "time_stop": 1643945813.785717,
        "time_offset": 300,
        "frames_completed": {0, 1, 2, 3, 4, 5, 6, 7, 8},
    }


@pytest.fixture(scope="function")
def render_nodes():
    return ["node1", "node2", "node3", "node4"]


@pytest.fixture(scope="function")
@mock.patch("rendercontroller.job.StateDatabase")
def job1(db, render_nodes, testjob1):
    """RenderJob fixture representing a newly enqueued job with default values."""
    conf = mock.MagicMock(name="Config")
    conf.render_nodes = render_nodes
    job = RenderJob(
        config=conf,
        id=testjob1["id"],
        path=testjob1["path"],
        start_frame=testjob1["start_frame"],
        end_frame=testjob1["end_frame"],
        render_nodes=testjob1["render_nodes"],
    )
    job.master_thread = mock.MagicMock(name="RenderJob.master_thread")
    return job


@pytest.fixture(scope="function")
@mock.patch("rendercontroller.job.StateDatabase")
@mock.patch("rendercontroller.job.BlenderRenderThread")
@mock.patch("rendercontroller.job.RenderJob._mainloop")
def job2(ml, rt, db, render_nodes, testjob2):
    """RenderJob fixture representing a job that is currently rendering.

    Mainloop is mocked to prevent render from starting automatically."""
    conf = mock.MagicMock(name="Config")
    rt.return_value = None
    conf.render_nodes = render_nodes
    job = RenderJob(
        config=conf,
        id=testjob2["id"],
        path=testjob2["path"],
        start_frame=testjob2["start_frame"],
        end_frame=testjob2["end_frame"],
        render_nodes=testjob2["render_nodes"],
        status=testjob2["status"],
        time_start=testjob2["time_start"],
        time_stop=testjob2["time_stop"],
        time_offset=testjob2["time_offset"],
        frames_completed=testjob2["frames_completed"],
    )
    job.time_stop = 0.0
    return job


@mock.patch("rendercontroller.job.StateDatabase")
@mock.patch("rendercontroller.job.RenderJob.render")
@mock.patch("rendercontroller.controller.Config")
def test_job_init_new(conf, render, db, render_nodes, testjob1):
    """Tests creating a new job with the minimum required parameters."""
    conf.render_nodes = render_nodes
    j = RenderJob(
        config=conf,
        id=testjob1["id"],
        path=testjob1["path"],
        start_frame=testjob1["start_frame"],
        end_frame=testjob1["end_frame"],
        render_nodes=testjob1["render_nodes"],
    )

    # Check passed params
    assert j.config is conf
    assert j.id == testjob1["id"]
    assert j.path == testjob1["path"]
    assert j.start_frame == testjob1["start_frame"]
    assert j.end_frame == testjob1["end_frame"]
    assert j.get_enabled_nodes() == testjob1["render_nodes"]

    # Check generated values
    assert j.status == WAITING
    assert j.time_start == 0.0
    assert j.time_stop == 0.0
    assert j.time_offset == 0.0
    assert j._stop is False
    assert j.db is db.return_value
    assert j.frames_completed == set()
    assert j.skip_list == []

    # Check queue by emptying it and comparing contents
    queue_expected = list(range(0, 100 + 1))
    queue_actual = []
    while not j.queue.empty():
        queue_actual.append(j.queue.get())
    assert queue_actual == queue_expected

    # Test startup tasks
    assert sorted(list(j.executors.keys())) == sorted(render_nodes)
    for name, ex in j.executors.items():
        assert isinstance(ex, rendercontroller.job.Executor)
        assert ex.node == name
        if name in testjob1["render_nodes"]:
            assert ex.is_enabled()
        else:
            assert not ex.is_enabled()
    render.assert_not_called()

    # Test special cases
    # Case 1: start frame > end frame
    with pytest.raises(ValueError):
        RenderJob(
            config=conf,
            id="failjob",
            path="/tmp/failjob",
            start_frame=10,
            end_frame=5,
            render_nodes=render_nodes,
        )
    # Case 2: unknown render node
    with pytest.raises(NodeNotFoundError):
        RenderJob(
            config=conf,
            id="failjob",
            path="/tmp/failjob",
            start_frame=1,
            end_frame=5,
            render_nodes=("node1", "bogusnode"),
        )


@mock.patch("rendercontroller.job.StateDatabase")
@mock.patch("rendercontroller.controller.Config")
@mock.patch("rendercontroller.job.RenderJob.render")
def test_job_init_restore(render, conf, db, render_nodes, testjob2):
    """Tests restoring a job from disk."""
    conf.render_nodes = render_nodes
    j = RenderJob(
        config=conf,
        id=testjob2["id"],
        path=testjob2["path"],
        start_frame=testjob2["start_frame"],
        end_frame=testjob2["end_frame"],
        render_nodes=testjob2["render_nodes"],
        status=testjob2["status"],
        time_start=testjob2["time_start"],
        time_stop=testjob2["time_stop"],
        time_offset=testjob2["time_offset"],
        frames_completed=testjob2["frames_completed"],
    )

    # Check passed params
    assert j.config is conf
    assert j.id == testjob2["id"]
    assert j.path == testjob2["path"]
    assert j.start_frame == testjob2["start_frame"]
    assert j.end_frame == testjob2["end_frame"]
    assert j.get_enabled_nodes() == testjob2["render_nodes"]
    assert j.status == WAITING  # Status is reset to waiting until render starts.
    assert j.time_start == testjob2["time_start"]
    assert j.time_stop == testjob2["time_stop"]
    assert j.time_offset == testjob2["time_offset"]
    assert j.frames_completed == testjob2["frames_completed"]

    # Check generated values
    queue_expected = list(range(9, 25 + 1))
    queue_actual = []
    while not j.queue.empty():
        queue_actual.append(j.queue.get())
    assert queue_actual == queue_expected
    assert j.db is db.return_value
    assert j.skip_list == []

    # Test startup tasks
    assert sorted(list(j.executors.keys())) == sorted(render_nodes)
    for node, ex in j.executors.items():
        assert isinstance(ex, rendercontroller.job.Executor)
        assert ex.node == node
        if node in testjob2["render_nodes"]:
            assert ex.is_enabled()
        else:
            assert not ex.is_enabled()
    render.assert_called_once()

    # Test special cases
    # Case 1: Unknown render node
    with pytest.raises(NodeNotFoundError):
        RenderJob(
            config=conf,
            id=testjob2["id"],
            path=testjob2["path"],
            start_frame=testjob2["start_frame"],
            end_frame=testjob2["end_frame"],
            render_nodes=[*testjob2["render_nodes"], "bogusnode"],
            status=testjob2["status"],
            time_start=testjob2["time_start"],
            time_stop=testjob2["time_stop"],
            time_offset=testjob2["time_offset"],
            frames_completed=testjob2["frames_completed"],
        )


def test_job_set_status(job1, testjob1):
    assert job1.status == WAITING
    job1.db.update_job_status.assert_not_called()
    job1._set_status(STOPPED)
    assert job1.status == STOPPED
    job1.db.update_job_status.assert_called_with(testjob1["id"], STOPPED)


@mock.patch("rendercontroller.job.RenderJob._reset_render_state")
@mock.patch("rendercontroller.job.RenderJob._start_timer")
def test_job_render_new(timer, reset_state, job1):
    """Tests render() on a job that has never been rendered."""
    timer.assert_not_called()
    job1.master_thread.start.assert_not_called()
    assert job1.status == WAITING

    job1.render()
    assert job1.status == RENDERING
    timer.assert_called_once()
    job1.master_thread.start.assert_called_once()
    reset_state.assert_not_called()

    # Should not render a job that's already rendering
    with pytest.raises(JobStatusError):
        job1.render()


@mock.patch("rendercontroller.job.RenderJob._reset_render_state")
@mock.patch("rendercontroller.job.RenderJob._start_timer")
def test_job_render_resume(timer, reset_state, job1):
    """Tests render() on a job that has been previously started then stopped."""
    job1.status = STOPPED
    job1.time_start = 100.0
    job1.time_stop = 200.0
    timer.assert_not_called()  # Artificial, but it should not have been called yet in this test.
    reset_state.assert_not_called()

    job1.render()
    reset_state.assert_called_once()
    timer.assert_called_once()
    assert job1.status == RENDERING


@mock.patch("rendercontroller.job.RenderJob._stop_timer")
def test_job_stop(timer, job1):
    thread = mock.MagicMock(name="threading.Thread")
    job1.master_thread = thread
    executors = {
        node: mock.MagicMock(name=f"Executor.{node}")
        for node in job1.config.render_nodes
    }
    job1.executors = executors
    job1.render()
    assert job1._stop is False
    assert job1.status == RENDERING
    for ex in executors.values():
        ex.stop.assert_not_called()
    timer.assert_not_called()
    thread.join.assert_not_called()

    # Case 1: master thread is still running
    thread.is_alive.return_value = True
    job1.stop()
    assert job1._stop is True
    assert job1.status == STOPPED
    for ex in executors.values():
        ex.stop.assert_called_once()
    thread.join.assert_called_once()
    timer.assert_called_once()

    # Case 2: master thread has already exited
    thread.reset_mock()
    thread.is_alive.return_value = False
    job1.status = RENDERING
    job1.stop()
    thread.join.assert_not_called()
    assert job1.status == STOPPED

    # Raise exception if job is already stopped
    with pytest.raises(JobStatusError):
        job1.stop()


def test_job_enable_waiting(job1):
    with pytest.raises(JobStatusError):
        job1.reset_waiting()
    job1.status = STOPPED
    job1.reset_waiting()
    assert job1.status == WAITING


def test_job_enable_node(job1, testjob1):
    # Throw exception if node not in Config.render_nodes
    with pytest.raises(NodeNotFoundError):
        job1.enable_node("fakenode")

    # Now try valid node
    newnode = "node3"
    nodes_expected = (*testjob1["render_nodes"], newnode)
    assert newnode not in job1.get_enabled_nodes()
    job1.enable_node(newnode)
    assert newnode in job1.get_enabled_nodes()
    assert len(job1.get_enabled_nodes()) == 3
    job1.db.update_nodes.assert_called_with(testjob1["id"], nodes_expected)
    job1.db.update_nodes.reset_mock()

    # Should quietly do nothing if node is already enabled
    job1.enable_node(newnode)
    assert newnode in job1.get_enabled_nodes()
    assert job1.get_enabled_nodes() == nodes_expected
    job1.db.update_nodes.assert_not_called()


def test_job_disable_node(job1, testjob1):
    # Throw exception if node not in Config.render_nodes
    with pytest.raises(NodeNotFoundError):
        job1.disable_node("fakenode")

    # Now try valid node
    newnode = "node1"
    assert newnode in job1.get_enabled_nodes()
    job1.disable_node(newnode)
    assert newnode not in job1.get_enabled_nodes()
    assert len(job1.get_enabled_nodes()) == 1
    nodes_expected = ("node2", )
    job1.db.update_nodes.assert_called_with(testjob1["id"], nodes_expected)
    job1.db.update_nodes.reset_mock()

    # Should quietly do nothing if node is already disabled
    job1.disable_node(newnode)
    assert newnode not in job1.get_enabled_nodes()
    assert job1.get_enabled_nodes() == nodes_expected
    job1.db.update_nodes.assert_not_called()


def test_job_get_progress(job1):
    # Case 1: No frames have been rendered yet
    assert job1.frames_completed == set()
    assert job1.get_progress() == 0.0

    # Case 2: Some, but not all frames have been rendered
    job1.frames_completed = set(range(25))
    assert job1.get_progress() == pytest.approx(24.75, rel=1e-3)
    job1.frames_completed = set(range(75))
    assert job1.get_progress() == pytest.approx(74.26, rel=1e-3)

    # Case 3: All frames rendered
    job1.frames_completed = set(range(job1.start_frame, job1.end_frame + 1))
    assert job1.get_progress() == 100.0

    # Edge case: start_frame == end frame. Make sure we don't divide by zero.
    job1.end_frame = 0
    assert job1.start_frame == job1.end_frame
    job1.frames_completed = set()
    assert job1.get_progress() == 0.0


def test_job_get_times(job1):
    # Case 1: New job waiting in queue (time_start not set)
    assert job1.time_start == 0.0
    assert job1.get_times() == (0.0, 0.0, 0.0)

    # Case 2: Job finished or restored from disk (time_start and time_stop both set)
    # 2a: Job was started then stopped but never rendered a frame.
    job1.time_stop = time.time()
    job1.time_start = job1.time_stop - 100
    elapsed, avg, rem = job1.get_times()
    assert elapsed == 100.0
    assert avg == 0.0
    assert rem == 0.0
    # 2b: Job rendered some frames before it was stopped.
    job1.frames_completed = set(i for i in range(25))
    elapsed, avg, rem = job1.get_times()
    # 100 seconds to render 25 frames => 4 sec/frame and 304s remaining
    assert elapsed == 100.0
    assert avg == 4.0
    assert rem == 304.0

    # Case 3: Job currently rendering (time_start has been set, time_stop has not)
    job1.time_stop = 0.0
    # 3a: Job just started, no frames finished yet
    job1.frames_completed = set()
    assert job1.time_start > 0.0
    elapsed, avg, rem = job1.get_times()
    # RenderThread is mocked, so elapsed will increase but no frames will ever finish
    assert elapsed > 0.0
    assert avg == 0.0
    assert rem == 0.0
    # 3b: Job has been rendering for a while, some frames finished
    job1.frames_completed = set(i for i in range(25))
    assert job1.time_stop == 0.0
    job1.time_start = time.time() - 100
    elapsed, avg, rem = job1.get_times()
    # A little lag between subsequent calls to time.time(), so use approx.
    assert elapsed == pytest.approx(100.0)
    assert avg == pytest.approx(4.0)
    assert rem == pytest.approx(304.0)


def test_job_dump(job1, job2, render_nodes, testjob1, testjob2):
    # Case 1: New job, nothing rendered yet. Most fields will be default values
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
        "frames_completed": set(),
        "progress": 0.0,
        "node_status": {
            node: {
                "frame": None,
                "progress": 0.0,
                "enabled": True if node in job1.get_enabled_nodes() else False,
                "rendering": False,
            }
            for node in render_nodes
        },
    }
    # Case 2: Job that has been rendering
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
def test_job_executors_active(ex, job1):
    assert job1.executors_active() is False
    job1.executors["node2"] = mock.MagicMock(name="Executor")
    job1.executors["node2"].is_idle.return_value = False
    assert job1.executors_active() is True


def test_job_get_enabled_nodes(job1, testjob1):
    assert sorted(job1.get_enabled_nodes()) == sorted(testjob1["render_nodes"])


def test_job_get_nodes_status(job1):
    expected = {
        "node1": {"frame": None, "progress": 0.0, "enabled": True, "rendering": False},
        "node2": {"frame": None, "progress": 0.0, "enabled": True, "rendering": False},
        "node3": {"frame": None, "progress": 0.0, "enabled": False, "rendering": False},
        "node4": {"frame": None, "progress": 0.0, "enabled": False, "rendering": False},
    }
    # Case 1: Defaults & node enabled but idle
    assert job1.get_nodes_status() == expected
    # Case 2: Node enabled and rendering
    job1.executors["node2"] = mock.MagicMock(name="Executor")
    job1.executors["node2"].frame = 1
    job1.executors["node2"].is_idle.return_value = False
    job1.executors["node2"].is_enabled.return_value = True
    job1.executors["node2"].progress = 15.0
    expected["node2"] = {
        "frame": 1,
        "progress": 15.0,
        "enabled": True,
        "rendering": True,
    }
    assert job1.get_nodes_status() == expected


@mock.patch("time.time")
def test_job_start_timer_1(timer, job1):
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
def test_job_start_timer_2(timer, job1):
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
def test_job_start_timer_3(timer, job1):
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
def test_job_start_timer_4(timer, job1):
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
def test_job_start_timer_5(timer, job1):
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


@mock.patch("rendercontroller.job.RenderJob._stop_timer")
def test_job_finished(timer, job2):
    timer.assert_not_called()
    job2.db.update_job_status.reset_mock()  # Gets called twice in __init__
    assert job2.status == RENDERING

    job2._render_finished()
    assert job2.status == FINISHED
    job2.db.update_job_status.assert_called_with(job2.id, FINISHED)
    timer.assert_called_once()


@mock.patch("rendercontroller.job.RenderJob._pop_skipped_node")
def test_job_frame_finished(pop, job1):
    frame = 5
    job1.queue = mock.MagicMock(name="queue.LiFoQueue")
    job1.queue.task_done.assert_not_called()
    ex = mock.MagicMock(name="Executor")
    ex.ack_done.assert_not_called()
    ex.frame = frame
    ex.node = "node1"
    ex.elapsed_time.return_value = 123.456
    pop.assert_not_called()
    assert frame not in job1.frames_completed

    job1._frame_finished(ex)
    job1.queue.task_done.assert_called_once()
    ex.ack_done.assert_called_once()
    assert frame in job1.frames_completed
    job1.db.update_job_frames_completed.assert_called_with(job1.id, {5})
    pop.assert_called_once()


def test_job_frame_failed(job1):
    frame = 5
    node = "node1"
    job1.queue = mock.MagicMock(name="queue.LiFoQueue")
    ex = mock.MagicMock(name="Executor")
    ex.frame = frame
    ex.node = node
    ex.ack_done.assert_not_called()
    assert node not in job1.skip_list
    assert frame not in job1.frames_completed
    job1.queue.put.assert_not_called()

    # Case 1: frame failed while job is rendering
    job1._frame_failed(ex)
    job1.queue.put.assert_called_with(frame)
    assert node in job1.skip_list
    ex.ack_done.assert_called_once()
    assert frame not in job1.frames_completed

    # Case 2: frame failed because job is being stopped
    job1.queue.reset_mock()
    ex.ack_done.reset_mock()
    job1.skip_list = []
    job1._stop = True
    job1._frame_failed(ex)
    job1.queue.put.assert_called_with(frame)
    assert node not in job1.skip_list
    ex.ack_done.assert_called_once()


def test_job_pop_skipped_node(job1):
    # Case 1: skip list empty
    assert len(job1.skip_list) == 0
    job1._pop_skipped_node()  # Nothing should happen
    assert len(job1.skip_list) == 0

    # Case 2: Something in skip list
    job1.skip_list.append("node2")
    job1._pop_skipped_node()
    assert "node2" not in job1.skip_list


def test_job_reset_render_state(job1):
    job1._stop = True
    thread_before = id(job1.master_thread)
    executors_before = {}
    for name, ex in job1.executors.items():
        executors_before[name] = id(ex)
    new_enabled = ("node2", "node4")

    job1._reset_render_state(new_enabled)
    assert not job1._stop
    for name, ex in job1.executors.items():
        assert id(ex) != executors_before[name]

    assert id(job1.master_thread) != thread_before
    assert sorted(job1.get_enabled_nodes()) == sorted(new_enabled)


@mock.patch("rendercontroller.job.RenderJob._frame_failed")
@mock.patch("rendercontroller.job.RenderJob._frame_finished")
def test_job_executor_is_ready(ffin, ffail, job1):
    ex = mock.MagicMock(name="Executor")
    ex.is_enabled.return_value = True
    ex.node = "node1"

    # Case 1: Executor is not idle
    ex.is_idle.return_value = False

    # 1a: but finished => call _frame_finished()
    ex.status = FINISHED
    assert job1._executor_is_ready(ex)
    ffin.assert_called_with(ex)
    ffail.assert_not_called()

    # 1b: but failed => call _frame_failed()
    ex.status = FAILED
    ffail.reset_mock()
    ffin.reset_mock()
    assert not job1._executor_is_ready(ex)
    ffail.assert_called_with(ex)
    ffin.assert_not_called()

    # 1c: still rendering
    ex.status = RENDERING
    ffail.reset_mock()
    ffin.reset_mock()
    assert not job1._executor_is_ready(ex)
    ffail.assert_not_called()
    ffin.assert_not_called()

    # Case 2: Executor is idle but still should not get a frame
    ex.is_idle.return_value = True
    ex.status = WAITING

    # 2a: but not enabled
    ex.is_enabled.return_value = False
    assert not job1._executor_is_ready(ex)

    # 2b: but in skip_list
    ex.is_enabled.return_value = True
    job1.skip_list.append("node1")
    assert not job1._executor_is_ready(ex)
    job1.skip_list = []

    # 2c: but stop has been requested
    job1._stop = True
    assert not job1._executor_is_ready(ex)

    # Case 3: Executor is idle and ready for a frame
    job1._stop = False
    assert job1._executor_is_ready(ex)


@mock.patch("rendercontroller.job.RenderJob.executors_active")
@mock.patch("rendercontroller.job.RenderJob._render_finished")
def test_job_mainloop_1(rfin, execs_active, job1):
    """Tests first block of mainloop: loop exit conditions."""
    job1.test = True  # Enable loop counters
    job1.queue = mock.MagicMock(name="threading.LiFoQueue")
    job1.queue.empty.return_value = False

    # Case 1: Stop requested, executors done => break loop (NOT render finished!)
    job1._stop = True
    execs_active.return_value = False
    job1._mainloop()
    rfin.assert_not_called()
    assert job1.outer_count == 1
    assert job1.inner_count == 0

    # Case 2: Stop requested, executors still running => loop until executors done
    execs_active.return_value = MagicBool(True, 1)  # Loop won't exit unless _stop = True and executors_active() = False
    job1._mainloop()
    rfin.assert_not_called()
    assert job1.outer_count == 2
    assert job1.inner_count == 4

    # Case 3: Stop not requested, queue empty, executors done => render finished
    job1._stop = MagicBool(False, 1)
    job1.queue.empty.return_value = True
    execs_active.return_value = False
    job1._mainloop()
    rfin.assert_called_once()
    assert job1.outer_count == 1
    assert job1.inner_count == 0

    # Case 4: Stop not requested, queue empty, executors still running => loop until executors done
    job1._stop.reset()
    rfin.reset_mock()
    execs_active.return_value = MagicBool(True, 1)
    job1._mainloop()
    rfin.assert_not_called()
    assert job1.outer_count == 2
    assert job1.inner_count == 4


@mock.patch("rendercontroller.job.RenderJob._pop_skipped_node")
def test_job_mainloop_2(pop, job1, render_nodes, testjob1):
    """Tests second block of mainloop: all nodes in skip list"""
    stop = MagicBool(False, 1)
    job1._stop = stop
    job1.test = True
    pop.assert_not_called()
    job1.skip_list = testjob1["render_nodes"]
    assert len(job1.skip_list) == 2

    job1._mainloop()
    pop.assert_called_once()
    assert job1.outer_count == 2

    # Edge case: skip list longer than enabled nodes
    pop.reset_mock()
    pop.assert_not_called()
    job1.skip_list = render_nodes
    assert len(job1.skip_list) > len(job1.get_enabled_nodes())
    stop.reset()
    job1._mainloop()
    pop.assert_called_once()
    assert job1.outer_count == 2


@mock.patch("rendercontroller.job.RenderJob._executor_is_ready")
@mock.patch("rendercontroller.job.RenderJob.executors_active")
def test_job_mainloop_3(execs_active, exec_ready, render_nodes, job1):
    """Tests first unit of inner (node) loop: node has thread assigned -> check status."""
    stop = MagicBool(False, 1)
    job1._stop = stop
    job1.test = True  # Enable loop counters
    execs_active.return_value = False
    job1.queue = mock.MagicMock(name="threading.LiFoQueue")
    job1.queue.empty.return_value = False
    for name in job1.executors:
        job1.executors[name] = mock.MagicMock(name=f"Executor.{name}")

    # Case 1: Executor is not ready => do nothing
    exec_ready.return_value = False
    job1._mainloop()
    # Loop counters to make sure we're really hitting both loops.
    assert job1.outer_count == 2
    assert job1.inner_count == 4
    assert job1.queue.empty.call_count == 1  # Not called in inner loop if not _executor_is_ready()

    job1.queue.get.assert_not_called()
    for ex in job1.executors.values():
        ex.render.assert_not_called()

    # Case 2: Executor is ready and queue is empty => do nothing
    stop.reset()
    job1.queue.reset_mock()
    job1.queue.empty.return_value = MagicBool(False, 1)  # Otherwise it will exit with _render_finished()
    exec_ready.return_value = True

    job1._mainloop()
    assert job1.outer_count == 2
    assert job1.inner_count == 4
    assert job1.queue.empty.call_count == 5  # Once in outer loop, then once for each node.
    job1.queue.get.assert_not_called()
    for ex in job1.executors.values():
        ex.render.assert_not_called()

    # Case 3: Executor is ready and queue is not empty => assign frame
    stop.reset()
    job1.queue.reset_mock()
    job1.queue.empty.return_value = False
    exec_ready.return_value = MagicBool(True, 1)  # Only want to try to start first node
    job1.queue.get.return_value = 5

    job1._mainloop()
    assert job1.outer_count == 2
    assert job1.inner_count == 4
    assert job1.queue.empty.call_count == 2  # Once in outer loop, then once for the one ready executor
    job1.queue.get.assert_called_once()
    for name, ex in job1.executors.items():
        if name == "node1":
            ex.render.assert_called_with(5)
        else:
            ex.render.assert_not_called()
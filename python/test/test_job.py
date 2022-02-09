import pytest
import time
from unittest import mock
from rendercontroller.job import RenderJob
from rendercontroller.status import WAITING, RENDERING, FINISHED, STOPPED, FAILED
from rendercontroller.exceptions import JobStatusError, NodeNotFoundError
import rendercontroller.job


testjob1 = {  # Minimum set of kwargs. Mimics creating new job.
    "id": "job01",
    "path": "/tmp/job1",
    "start_frame": 0,
    "end_frame": 100,
    "render_nodes": ["node1", "node2"],
}

testjob2 = {  # Complete kwargs. Mimics restoring from db.
    "id": "job02",
    "status": RENDERING,
    "path": "/tmp/job2",
    "start_frame": 0,
    "end_frame": 25,
    "render_nodes": ["node1", "node2", "node3"],
    "time_start": 1643945770.027214,
    "time_stop": 1643945813.785717,
    "time_offset": 300,
    "frames_completed": [0, 1, 2, 3, 4, 5, 6, 7, 8],
}

conf_render_nodes = ["node1", "node2", "node3", "node4"]


@pytest.fixture(scope="function")
@mock.patch("rendercontroller.job.BlenderRenderThread")
def job1(rt):
    """RenderJob fixture representing a newly enqueued job with default values."""
    conf = mock.Mock(name="Config")
    conf.render_nodes = conf_render_nodes
    db = mock.Mock(name="StateDatabase")
    mt = mock.Mock(name="RenderJob.master_thread")
    job = RenderJob(conf, db, **testjob1)
    job.master_thread = mt
    return job


@pytest.fixture(scope="function")
@mock.patch("rendercontroller.job.BlenderRenderThread")
@mock.patch("rendercontroller.job.RenderJob._thread")
def job_with_renderthread(mt, rt):
    """RenderJob fixture representing a job that is currently rendering."""
    conf = mock.Mock(name="Config")
    rt.return_value = None
    #FIXME For some reason, this is still not patching BlenderRenderThread.
    # Is okay for now because we're mocking master thread, but will be a problem for testing that...
    conf.render_nodes = conf_render_nodes
    db = mock.Mock(name="StateDatabase")
    #mt = mock.Mock(name="RenderJob.master_thread")
    #job.master_thread = mt
    #brt = mock.Mock(name="BlenderRenderThread")
    #with mock.patch.object(rendercontroller.job, "BlenderRenderThread", brt):
    #    brt.return_value = None
    job = RenderJob(conf, db, **testjob2)
    job.time_stop = 0.0
    return job, rt


@mock.patch("rendercontroller.controller.Config")
def test_job_init_new(conf):
    """Tests creating a new job."""
    conf.render_nodes = conf_render_nodes
    db = mock.Mock(name="StateDatabase")
    j = RenderJob(conf, db, **testjob1)
    # Check passed params
    assert j.config is conf
    assert j.db is db
    assert j.id == testjob1["id"]
    assert j.path == testjob1["path"]
    assert j.start_frame == testjob1["start_frame"]
    assert j.end_frame == testjob1["end_frame"]
    assert j.nodes_enabled == set(testjob1["render_nodes"])
    # Check generated params
    assert j.status == WAITING
    assert j.time_start == 0.0
    assert j.time_stop == 0.0
    assert j.time_offset == 0.0
    assert j.frames_completed == []
    queue_expected = list(range(0, 100 + 1))
    queue_actual = []
    while not j.queue.empty():
        queue_actual.append(j.queue.get())
    assert queue_actual == queue_expected
    assert j.skip_list == []
    node_status_expected = {
        "node1": {"frame": None, "thread": None, "progress": 0.0},
        "node2": {"frame": None, "thread": None, "progress": 0.0},
        "node3": {"frame": None, "thread": None, "progress": 0.0},
        "node4": {"frame": None, "thread": None, "progress": 0.0},
    }
    assert j.node_status == node_status_expected
    # Test start frame > end frame
    with pytest.raises(ValueError):
        j = RenderJob(conf, db, "failjob", "/tmp/failjob", 10, 5, conf_render_nodes)


@mock.patch("rendercontroller.controller.Config")
@mock.patch("rendercontroller.job.RenderJob.render")
def test_job_init_restore(render, conf):
    """Tests restoring a job from disk."""
    conf.render_nodes = conf_render_nodes
    db = mock.Mock(name="StateDatabase")
    j = RenderJob(conf, db, **testjob2)
    # Check passed params
    assert j.config is conf
    assert j.db is db
    assert j.id == testjob2["id"]
    assert j.path == testjob2["path"]
    assert j.start_frame == testjob2["start_frame"]
    assert j.end_frame == testjob2["end_frame"]
    assert j.nodes_enabled == set(testjob2["render_nodes"])
    # Status is reset to WAITING before render() is called
    assert j.status == WAITING
    assert j.time_start == testjob2["time_start"]
    assert j.time_stop == testjob2["time_stop"]
    assert j.time_offset == testjob2["time_offset"]
    assert j.frames_completed == testjob2["frames_completed"]
    # Check generated params
    queue_expected = list(range(9, 25 + 1))
    queue_actual = []
    while not j.queue.empty():
        queue_actual.append(j.queue.get())
    assert queue_actual == queue_expected
    assert j.skip_list == []
    render.assert_called_once()
    node_status_expected = {
        "node1": {"frame": None, "thread": None, "progress": 0.0},
        "node2": {"frame": None, "thread": None, "progress": 0.0},
        "node3": {"frame": None, "thread": None, "progress": 0.0},
        "node4": {"frame": None, "thread": None, "progress": 0.0},
    }
    assert j.node_status == node_status_expected


def test_job_set_status(job1):
    assert job1.status == WAITING
    job1.db.update_job_status.assert_not_called()
    job1.set_status(STOPPED)
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


def test_job_enable_node(job1):
    # Should throw exception if node not in Config.render_nodes
    with pytest.raises(NodeNotFoundError):
        job1.enable_node("fakenode")
    # Now try good node
    newnode = "node3"
    assert newnode not in job1.nodes_enabled
    job1.enable_node(newnode)
    assert newnode in job1.nodes_enabled
    assert len(job1.nodes_enabled) == 3
    nodes_expected = {*testjob1["render_nodes"], newnode}
    job1.db.update_nodes.assert_called_with(testjob1["id"], tuple(nodes_expected))
    job1.db.update_nodes.reset_mock()
    # Should quietly do nothing if node is already enabled
    job1.enable_node(newnode)
    assert newnode in job1.nodes_enabled
    assert job1.nodes_enabled == nodes_expected
    job1.db.update_nodes.assert_not_called()


def test_job_disable_node(job1):
    # Should throw exception if node not in Config.render_nodes
    with pytest.raises(NodeNotFoundError):
        job1.disable_node("fakenode")
    # Now try good node
    newnode = "node1"
    assert newnode in job1.nodes_enabled
    job1.disable_node(newnode)
    assert newnode not in job1.nodes_enabled
    assert len(job1.nodes_enabled) == 1
    nodes_expected = {
        "node2",
    }
    job1.db.update_nodes.assert_called_with(testjob1["id"], tuple(nodes_expected))
    job1.db.update_nodes.reset_mock()
    # Should quietly do nothing if node is already disabled
    job1.disable_node(newnode)
    assert newnode not in job1.nodes_enabled
    assert job1.nodes_enabled == nodes_expected
    job1.db.update_nodes.assert_not_called()


def test_job_get_progress(job1):
    assert job1.status == WAITING
    assert job1.frames_completed == []
    assert job1.get_progress() == 0.0
    job1.frames_completed = list(range(25))
    assert job1.get_progress() == pytest.approx(24.75, rel=1e-3)
    job1.frames_completed = list(range(75))
    assert job1.get_progress() == pytest.approx(74.26, rel=1e-3)
    job1.frames_completed = list(range(job1.start_frame, job1.end_frame + 1))
    assert job1.get_progress() == 100.0
    # Make sure we don't divide by zero if start_frame == end_frame
    job1.end_frame = 0
    assert job1.start_frame == job1.end_frame
    job1.frames_completed = []
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
    job1.frames_completed = set([i for i in range(25)])
    elapsed, avg, rem = job1.get_times()
    # 100 seconds to render 25 frames => 4 sec/frame and 300s remaining
    assert elapsed == 100.0
    assert avg == 4.0
    assert rem == 300.0

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
    job1.frames_completed = set([i for i in range(25)])
    assert job1.time_stop == 0.0
    job1.time_start = time.time() - 100
    elapsed, avg, rem = job1.get_times()
    # A little lag between subsequent calls to time.time(), so use approx.
    assert elapsed == pytest.approx(100.0)
    assert avg == pytest.approx(4.0)
    assert rem == pytest.approx(300.0)


def test_job_dump(job1, job_with_renderthread):
    # New job, nothing rendered yet. Most fields will be default values
    assert job1.dump() == {
        "id": testjob1["id"],
        "path": testjob1["path"],
        "start_frame": testjob1["start_frame"],
        "end_frame": testjob1["end_frame"],
        "render_nodes": testjob1["render_nodes"],
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
            for node in conf_render_nodes
        },
    }
    # Job that has been rendering
    job2, rt = job_with_renderthread
    elapsed, avg, rem = job2.get_times()
    dump = job2.dump()
    # Have to do this one at a time because of approx times.
    assert dump["id"] == testjob2["id"]
    assert dump["path"] == testjob2["path"]
    assert dump["start_frame"] == testjob2["start_frame"]
    assert dump["end_frame"] == testjob2["end_frame"]
    assert dump["render_nodes"] == testjob2["render_nodes"]
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
            for node in conf_render_nodes
        }


def test_job_render_threads_active(job1):
    assert job1.render_threads_active() is False
    job1.node_status["node2"]["thread"] = mock.Mock(name="RenderThread")
    assert job1.render_threads_active() is True


def test_job_get_node_status():
    # Case 1: Defaults
    # Case 2: Node enabled but idle
    # Case 3: Node enabled and rendering
    pass


def test_job_set_node_status():
    # Case 1: Reset to defaults (no params passed)
    # Case 2: Set frame only
    # Case 3: Set thread only
    # Case 4: Set progress only
    # Case 5: Set everything
    pass


def test_job_start_timer():
    # Case 1: No offset
    # Case 2: Offset
    pass


def test_job_stop_timer():
    pass


def test_job_thread():
    # May need to split thread functionality up into more methods to make testing not a total mess
    pass

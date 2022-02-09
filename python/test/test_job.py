import pytest
from unittest import mock
from rendercontroller.job import RenderJob
from rendercontroller.status import WAITING, RENDERING, FINISHED, STOPPED, FAILED
from rendercontroller.exceptions import JobStatusError, NodeNotFoundError


testjob1 = {  # Minimum set of kwargs
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
@mock.patch("rendercontroller.renderthread.BlenderRenderThread")
@mock.patch("rendercontroller.util.Config")
def job1(conf, rt):
    conf.render_nodes = conf_render_nodes
    db = mock.Mock(name="StateDatabase")
    mt = mock.Mock(name="RenderJob.master_thread")
    job = RenderJob(conf, db, **testjob1)
    job.master_thread = mt
    return job


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


def test_enable_node(job1):
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


def test_disable_node(job1):
    # Should throw exception if node not in Config.render_nodes
    with pytest.raises(NodeNotFoundError):
        job1.disable_node("fakenode")
    # Now try good node
    newnode = "node1"
    assert newnode in job1.nodes_enabled
    job1.disable_node(newnode)
    assert newnode not in job1.nodes_enabled
    assert len(job1.nodes_enabled) == 1
    nodes_expected = {"node2", }
    job1.db.update_nodes.assert_called_with(testjob1["id"], tuple(nodes_expected))
    job1.db.update_nodes.reset_mock()
    # Should quietly do nothing if node is already disabled
    job1.disable_node(newnode)
    assert newnode not in job1.nodes_enabled
    assert job1.nodes_enabled == nodes_expected
    job1.db.update_nodes.assert_not_called()

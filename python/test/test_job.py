import pytest
from unittest import mock
from rendercontroller.job import RenderJob, WAITING, RENDERING, FINISHED, STOPPED, FAILED

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


@mock.patch("rendercontroller.controller.Config")
def test_renderjob_init_new(conf):
    """Tests creating a new job."""
    conf.render_nodes = conf_render_nodes
    db = mock.MagicMock()
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
def test_renderjob_init_restore(render, conf):
    """Tests restoring a job from disk."""
    conf.render_nodes = conf_render_nodes
    db = mock.MagicMock()
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

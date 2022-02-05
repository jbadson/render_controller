import pytest
from unittest import mock
from rendercontroller import job

testjob1 = {  # Minimum set of kwargs
    "id": "job01",
    "path": "/tmp/job1",
    "start_frame": 0,
    "end_frame": 100,
    "render_nodes": ["node1", "node2"],
}

testjob2 = {  # Complete kwargs. Mimics restoring from db.
    "id": "job02",
    "status": "Rendering",
    "path": "/tmp/job2",
    "start_frame": 0,
    "end_frame": 25,
    "render_nodes": ["node1", "node2", "node3"],
    "time_start": 1643945770.027214,
    "time_stop": 1643945813.785717,
    "frames_completed": [0, 1, 2, 3, 4, 5, 6, 7, 8],
}


@mock.patch("rendercontroller.controller.Config")
@mock.patch("time.time")
def test_renderjob_init_new(time, conf):
    """Tests creating a new job."""
    mock_start_time = 1644030316.228603
    time.return_value = mock_start_time
    j = job.RenderJob(conf, **testjob1)
    # Check passed params
    assert j.config is conf
    assert j.id == testjob1["id"]
    assert j.path == testjob1["path"]
    assert j.start_frame == testjob1["start_frame"]
    assert j.end_frame == testjob1["end_frame"]
    assert j.nodes_enabled == testjob1["render_nodes"]
    # Check generated params
    assert j.status == job.WAITING
    assert j.time_start == mock_start_time
    assert j.time_stop is None
    assert j.frames_completed == []
    queue_expected = list(range(0, 100 + 1))
    queue_actual = []
    while not j.queue.empty():
        queue_actual.append(j.queue.get())
    assert queue_actual == queue_expected


@mock.patch("rendercontroller.controller.Config")
@mock.patch("rendercontroller.job.RenderJob.render")
def test_renderjob_init_restore(render, conf):
    """Tests restoring a job from disk."""
    j = job.RenderJob(conf, **testjob2)
    assert j.config is conf
    assert j.id == testjob2["id"]
    assert j.path == testjob2["path"]
    assert j.start_frame == testjob2["start_frame"]
    assert j.end_frame == testjob2["end_frame"]
    assert j.nodes_enabled == testjob2["render_nodes"]
    assert j.status == job.RENDERING
    assert j.time_start == testjob2["time_start"]
    assert j.time_stop == testjob2["time_stop"]
    assert j.frames_completed == testjob2["frames_completed"]
    queue_expected = list(range(9, 25 + 1))
    queue_actual = []
    while not j.queue.empty():
        queue_actual.append(j.queue.get())
    assert queue_actual == queue_expected
    render.assert_called_once()

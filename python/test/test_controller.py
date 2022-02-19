#!/usr/bin/env python3

import pytest
from unittest import mock

from rendercontroller.controller import RenderController, RenderQueue
from rendercontroller.constants import WAITING, RENDERING, STOPPED, FAILED, FINISHED
from rendercontroller.exceptions import (
    JobNotFoundError,
    JobStatusError,
    NodeNotFoundError,
)


test_nodes = ["node1", "node2", "node3", "node4"]

summary = [
    {
        "file_path": "/tmp/render1.blend",
        "id": "9003067201194900903b257115df33bd",
        "progress": 0.0,
        "status": STOPPED,
        "time_elapsed": 32.200013160705566,
        "time_remaining": 0,
        "time_created": 1544985625.618685,
    },
    {
        "file_path": "/tmp/render2.blend",
        "id": "7f6b127663af400fa43ddc52c8bdeeb1",
        "progress": 0.0,
        "status": STOPPED,
        "time_elapsed": 1.699430227279663,
        "time_remaining": 0,
        "time_created": 1544986156.003638,
    },
]

testjob01 = {
    "path": "/dev/test1.blend",
    "start_frame": 0,
    "end_frame": 10,
    "render_nodes": test_nodes[0:2],
}

testjob02 = {
    "path": "/dev/test2.blend",
    "start_frame": 0,
    "end_frame": 25,
    "render_nodes": test_nodes,
}

testjob03 = {
    "path": "/dev/test3.blend",
    "start_frame": 0,
    "end_frame": 100,
    "render_nodes": test_nodes[0:2],
}


@pytest.fixture(scope="function")
@mock.patch("rendercontroller.controller.StateDatabase")
@mock.patch("rendercontroller.controller.Config")
def rc_empty(conf, db):
    conf.render_nodes = test_nodes
    return RenderController(conf)


@pytest.fixture(scope="function")
@mock.patch("rendercontroller.controller.RenderJob")
@mock.patch("rendercontroller.controller.uuid4")
def rc_with_mocked_job(uuid, job, rc_empty):
    job_id = "testjob01"
    uuid.return_value.hex = job_id
    job.return_value.id = job_id
    job.return_value.status = WAITING
    rc_empty.new_job(**testjob01)
    return rc_empty, job


@pytest.fixture(scope="function")
def rc_with_three_jobs(rc_empty):
    testjobs = [
        (testjob01, "testjob01", FINISHED),
        (testjob02, "testjob02", WAITING),
        (testjob03, "testjob03", STOPPED),
    ]
    rq = RenderQueue()
    for j in testjobs:
        params, job_id, status = j
        # Convoluted because using @mock.patch results in the same mock object being reused
        job = mock.MagicMock()
        job.id = job_id
        job.status = status
        rq.append(job)
    rc_empty.queue = rq
    return rc_empty


@mock.patch("rendercontroller.controller.StateDatabase")
@mock.patch("rendercontroller.controller.RenderQueue")
@mock.patch("rendercontroller.util.Config")
def test_controller_init(conf, queue, db):
    conf.work_dir = "/tmp"
    queue.assert_not_called()
    db.assert_not_called()
    rc = RenderController(conf)
    assert rc.config is conf
    queue.assert_called_once()
    db.assert_called_with("/tmp/rcontroller.sqlite")
    assert rc.task_thread.running()


@mock.patch("rendercontroller.controller.StateDatabase")
@mock.patch("rendercontroller.controller.Config")
def test_controller_render_nodes(conf, db):
    conf.render_nodes = test_nodes
    rc = RenderController(conf)
    assert rc.render_nodes == test_nodes


@mock.patch("rendercontroller.controller.StateDatabase")
@mock.patch("rendercontroller.controller.Config")
def test_controller_autostart(conf, db):
    conf.autostart = True
    rc = RenderController(conf)
    assert rc.autostart is True
    rc.disable_autostart()
    assert rc.autostart is False
    rc.enable_autostart()
    assert rc.autostart is True


@mock.patch("rendercontroller.controller.RenderJob")
@mock.patch("rendercontroller.controller.uuid4")
def test_controller_new_job(uuid, job, rc_empty):
    job_id = "testuuid01"
    uuid.return_value.hex = job_id
    job.return_value.id = job_id
    job.return_value.status = WAITING
    # Make sure job is not already present
    with pytest.raises(KeyError):
        rc_empty.queue.get_by_id(job_id)
    rc_empty.db.insert_job.assert_not_called()
    res = rc_empty.new_job(**testjob01)
    job.assert_called_with(
        config=rc_empty.config,
        db=rc_empty.db,
        id=job_id,
        path=testjob01["path"],
        start_frame=testjob01["start_frame"],
        end_frame=testjob01["end_frame"],
        render_nodes=testjob01["render_nodes"],
    )
    assert res == job_id
    assert rc_empty.queue.get_by_id(job_id) is job.return_value
    rc_empty.db.insert_job.assert_called_once()
    rc_empty.db.insert_job.assert_called_with(
        job_id,
        WAITING,
        testjob01["path"],
        testjob01["start_frame"],
        testjob01["end_frame"],
        testjob01["render_nodes"],
        0.0,
        0.0,
        [],
        0,
    )


def test_controller_start(rc_with_mocked_job):
    job_id = "testjob01"
    rc, job = rc_with_mocked_job
    job.return_value.id = job_id
    job.return_value.render.assert_not_called()
    rc.start(job_id)
    job.return_value.render.assert_called_once()
    # Test job not found
    with pytest.raises(JobNotFoundError):
        rc.start("badkey")


def test_controller_start_next(rc_with_three_jobs):
    testjobs = [
        (testjob01, "testjob01", FINISHED),
        (testjob02, "testjob02", WAITING),
        (testjob03, "testjob03", STOPPED),
    ]
    assert len(rc_with_three_jobs.queue) == 3
    for i in range(len(testjobs)):
        assert rc_with_three_jobs.queue[i].id == testjobs[i][1]
    assert rc_with_three_jobs.start_next() == "testjob02"
    # Set status manually because RenderJob is mocked.
    rc_with_three_jobs.queue.get_by_id("testjob02").status = RENDERING
    # No WAITING jobs should be left in queue
    assert rc_with_three_jobs.start_next() is None


def test_controller_stop(rc_with_mocked_job):
    rc, job = rc_with_mocked_job
    job_id = "testjob01"
    job.return_value.stop.assert_not_called()
    rc.stop(job_id)
    job.return_value.stop.assert_called_once()
    with pytest.raises(JobNotFoundError):
        rc.stop("badkey")


def test_controller_delete(rc_with_three_jobs):
    assert len(rc_with_three_jobs.queue) == 3
    assert "testjob03" in rc_with_three_jobs.queue
    rc_with_three_jobs.db.delete_job.assert_not_called()
    rc_with_three_jobs.delete("testjob03")
    assert len(rc_with_three_jobs.queue) == 2
    assert "testjob03" not in rc_with_three_jobs.queue
    rc_with_three_jobs.db.delete_job.assert_called_with("testjob03")
    # Make sure it won't delete a job while rendering
    rc_with_three_jobs.queue.get_by_id("testjob01").status = RENDERING
    with pytest.raises(JobStatusError):
        rc_with_three_jobs.delete("testjob01")
    # Test job not found
    with pytest.raises(JobNotFoundError):
        rc_with_three_jobs.delete("badkey")


def test_controller_enable_node(rc_with_mocked_job):
    rc, job = rc_with_mocked_job
    job.return_value.enable_node.assert_not_called()
    rc.enable_node("testjob01", "node4")
    job.return_value.enable_node.assert_called_with("node4")
    # Test job not found
    with pytest.raises(JobNotFoundError):
        rc.enable_node("badkey", "node1")


def test_controller_disable_node(rc_with_mocked_job):
    rc, job = rc_with_mocked_job
    job.return_value.enable_node.assert_not_called()
    rc.disable_node("testjob01", "node4")
    job.return_value.disable_node.assert_called_with("node4")
    # Test job not found
    with pytest.raises(JobNotFoundError):
        rc.disable_node("badkey", "node1")


def test_controller_get_job_data(rc_with_mocked_job):
    job_id = "testjob01"
    rc, job = rc_with_mocked_job
    # Only test that RenderJob.dump() was called and that something was returned.
    # We test the output of RenderJob.dump() in the tests for that class.
    job.return_value.dump.assert_not_called()
    ret = rc.get_job_data(job_id)
    assert isinstance(ret, mock.MagicMock)
    job.return_value.dump.assert_called_once()
    with pytest.raises(JobNotFoundError):
        rc.get_job_data("badkey")


def test_controller_get_all_job_data(rc_with_three_jobs):
    # As above, do not test contents of returned object. That is checked in RenderJob tests.
    assert len(rc_with_three_jobs.queue) == 3
    for job in rc_with_three_jobs.queue:
        job.dump.assert_not_called()
    ret = rc_with_three_jobs.get_all_job_data()
    for job in rc_with_three_jobs.queue:
        job.dump.assert_called_once()
    assert isinstance(ret, list)
    assert len(ret) == 3
    for j in ret:
        assert isinstance(j, mock.MagicMock)


@mock.patch("rendercontroller.controller.StateDatabase")
@mock.patch("rendercontroller.controller.TaskThread")
@mock.patch("rendercontroller.controller.Config")
def test_controller_shutdown(conf, thread, db):
    rc = RenderController(conf)
    thread.return_value.shutdown.assert_not_called()
    rc.shutdown()
    thread.return_value.shutdown.assert_called_once()

#!/usr/bin/env python3

import pytest
import tempfile
import os.path
import sqlite3
from unittest import mock
from importlib import reload

import rendercontroller.controller
import rendercontroller.job
from rendercontroller.exceptions import (
    JobNotFoundError,
    JobStatusError,
    NodeNotFoundError,
)

config_test_dict = {
    "string_val": "val1",
    "int_val": 2,
    "float_val": 3.5,
    "bool_val": True,
}
test_nodes = ["node1", "node2", "node3", "node4"]

# Simulates RenderServer.renderjobs
renderdata = {
    "7f6b127663af400fa43ddc52c8bdeeb1": {
        "_id": 4356967728,
        "complist": [],
        "compstatus": {
            "borg1": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "borg2": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "borg3": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "borg4": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "borg5": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "conundrum": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "eldiente": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob1": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob2": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob3": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob4": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob5": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob6": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "hex1": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "hex2": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "hex3": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "lindsey": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "localhost": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "paradox": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
        },
        "endframe": 4,
        "extraframes": [],
        "path": "/Users/jim/Downloads/test_render/test_render.blend",
        "priority": "Normal",
        "progress": 0.0,
        "queuetime": 1544986156.003638,
        "render_engine": "blend",
        "render_params": None,
        "startframe": 1,
        "starttime": 1544986597.73921,
        "status": "Stopped",
        "stoptime": 1544986599.43864,
        "times": (1.699430227279663, 0.42485755681991577, 0),
        "totalframes": [0, 0, 0, 0],
    },
    "9003067201194900903b257115df33bd": {
        "_id": 4357090216,
        "complist": [
            "localhost",
            "hex1",
            "hex2",
            "hex3",
            "borg1",
            "borg2",
            "borg3",
            "borg4",
            "borg5",
            "grob1",
            "grob2",
            "grob3",
            "grob4",
            "grob5",
            "grob6",
            "eldiente",
            "lindsey",
            "conundrum",
            "paradox",
        ],
        "compstatus": {
            "borg1": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "borg2": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "borg3": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "borg4": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "borg5": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "conundrum": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "eldiente": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob1": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob2": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob3": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob4": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob5": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "grob6": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "hex1": {
                "active": False,
                "error": "Broken pipe",
                "frame": 2,
                "pid": None,
                "progress": 0.0,
                "timer": 1544986615.439296,
            },
            "hex2": {
                "active": False,
                "error": "Broken pipe",
                "frame": 3,
                "pid": None,
                "progress": 0.0,
                "timer": 1544986615.451592,
            },
            "hex3": {
                "active": True,
                "error": None,
                "frame": 1,
                "pid": None,
                "progress": 0.0,
                "timer": 1544986647.636271,
            },
            "lindsey": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "localhost": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
            "paradox": {
                "active": False,
                "error": None,
                "frame": None,
                "pid": None,
                "progress": 0.0,
                "timer": None,
            },
        },
        "endframe": 3,
        "extraframes": [],
        "path": "/Users/jim/Downloads/test_render/test_render_slow.blend",
        "priority": "Normal",
        "progress": 0.0,
        "queuetime": 1544985625.618685,
        "render_engine": "blend",
        "render_params": {"scene": "TestScene"},
        "startframe": 1,
        "starttime": 1544986615.412951,
        "status": "Stopped",
        "stoptime": 1544986647.6129642,
        "times": (32.200013160705566, 10.73333772023519, 0),
        "totalframes": [0, 0, 0],
    },
}

renderjobs = {}
for key, data in renderdata.items():
    job = mock.MagicMock()
    job.get_attrs.return_value = data
    renderjobs[key] = job

summary = [
    {
        "file_path": "/Users/jim/Downloads/test_render/test_render_slow.blend",
        "id": "9003067201194900903b257115df33bd",
        "progress": 0.0,
        "status": "Stopped",
        "time_elapsed": 32.200013160705566,
        "time_remaining": 0,
        "time_created": 1544985625.618685,
    },
    {
        "file_path": "/Users/jim/Downloads/test_render/test_render.blend",
        "id": "7f6b127663af400fa43ddc52c8bdeeb1",
        "progress": 0.0,
        "status": "Stopped",
        "time_elapsed": 1.699430227279663,
        "time_remaining": 0,
        "time_created": 1544986156.003638,
    },
]

status_33bd = {
    "end_frame": 3,
    "file_path": "/Users/jim/Downloads/test_render/test_render_slow.blend",
    "id": "9003067201194900903b257115df33bd",
    "node_status": {
        "borg1": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "borg2": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "borg3": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "borg4": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "borg5": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "conundrum": {
            "enabled": True,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
        "eldiente": {
            "enabled": True,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
        "grob1": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "grob2": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "grob3": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "grob4": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "grob5": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "grob6": {"enabled": True, "frame": None, "progress": 0.0, "rendering": False},
        "hex1": {"enabled": True, "frame": 2, "progress": 0.0, "rendering": False},
        "hex2": {"enabled": True, "frame": 3, "progress": 0.0, "rendering": False},
        "hex3": {"enabled": True, "frame": 1, "progress": 0.0, "rendering": True},
        "lindsey": {
            "enabled": True,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
        "localhost": {
            "enabled": True,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
        "paradox": {
            "enabled": True,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
    },
    "progress": 0.0,
    "render_engine": "blend",
    "render_params": {"scene": "TestScene"},
    "start_frame": 1,
    "status": "Stopped",
    "time_avg": 10.73333772023519,
    "time_elapsed": 32.200013160705566,
    "time_remaining": 0,
    "time_created": 1544985625.618685,
}

status_eeb1 = {
    "end_frame": 4,
    "file_path": "/Users/jim/Downloads/test_render/test_render.blend",
    "id": "7f6b127663af400fa43ddc52c8bdeeb1",
    "node_status": {
        "borg1": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "borg2": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "borg3": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "borg4": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "borg5": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "conundrum": {
            "enabled": False,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
        "eldiente": {
            "enabled": False,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
        "grob1": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "grob2": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "grob3": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "grob4": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "grob5": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "grob6": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "hex1": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "hex2": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "hex3": {"enabled": False, "frame": None, "progress": 0.0, "rendering": False},
        "lindsey": {
            "enabled": False,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
        "localhost": {
            "enabled": False,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
        "paradox": {
            "enabled": False,
            "frame": None,
            "progress": 0.0,
            "rendering": False,
        },
    },
    "progress": 0.0,
    "render_engine": "blend",
    "render_params": None,
    "start_frame": 1,
    "status": "Stopped",
    "time_avg": 0.42485755681991577,
    "time_elapsed": 1.699430227279663,
    "time_remaining": 0,
    "time_created": 1544986156.003638,
}


@pytest.fixture(scope="function")
@mock.patch("rendercontroller.controller.job")
@mock.patch("rendercontroller.controller.Config")
def controller_fix(conf, job):
    return rendercontroller.controller.RenderController(conf)


def test_config_init():
    with pytest.raises(RuntimeError):
        # Make sure we can't instantiate
        rendercontroller.controller.Config()


def test_config_set_get():
    conf = rendercontroller.controller.Config
    with pytest.raises(RuntimeError):
        conf()  # Make sure we can't instantiate
    conf.set_all(config_test_dict)
    # Test get method
    assert conf.get("string_val") == config_test_dict["string_val"]
    assert conf.get("int_val") == config_test_dict["int_val"]
    assert conf.get("float_val") == config_test_dict["float_val"]
    assert conf.get("bool_val") == config_test_dict["bool_val"]
    # Test subscript method
    assert conf.string_val == config_test_dict["string_val"]
    assert conf.int_val == config_test_dict["int_val"]
    assert conf.float_val == config_test_dict["float_val"]
    assert conf.bool_val == config_test_dict["bool_val"]
    # Singleton pollutes the other tests if we don't reload
    reload(rendercontroller.controller)


def test_config_bad_key():
    conf = rendercontroller.controller.Config
    with pytest.raises(AttributeError):
        conf.get("bogus_val")
    with pytest.raises(AttributeError):
        assert conf.bogus_val == True
    assert conf.get("bogus_val", default="something") == "something"


@mock.patch("rendercontroller.controller.job")
@mock.patch("rendercontroller.controller.Config")
def test_controller_init(conf, job):
    job.RenderServer.assert_not_called()
    rc = rendercontroller.controller.RenderController(conf)
    assert rc.config is conf
    job.RenderServer.assert_called_once()


@mock.patch("rendercontroller.controller.job")
@mock.patch("rendercontroller.controller.Config")
def test_controller_render_nodes(conf, job):
    conf.render_nodes = test_nodes
    rc = rendercontroller.controller.RenderController(conf)
    assert rc.render_nodes == test_nodes


@mock.patch("rendercontroller.controller.job")
@mock.patch("rendercontroller.controller.Config")
def test_controller_autostart(conf, job):
    conf.autostart = True
    rc = rendercontroller.controller.RenderController(conf)
    assert rc.autostart is True
    rc.disable_autostart()
    assert rc.autostart is False
    rc.enable_autostart()
    assert rc.autostart is True


@mock.patch("rendercontroller.controller.uuid4")
def test_controller_new_job_no_params(uuid, controller_fix):
    path = "/tmp/testfile.blend"
    start = 1
    end = 10
    engine = "blend"
    nodes = test_nodes[0:2]
    # Override uuid4 so we can verify calls all the way through
    job_id = "2973f9954570424d943afdedee3525b7"
    uuid.return_value.hex = job_id
    controller_fix.server.enqueue.return_value = job_id
    res = controller_fix.new_job(
        path=path, start_frame=start, end_frame=end, render_engine=engine, nodes=nodes
    )
    controller_fix.server.enqueue.assert_called_with(
        {
            "index": job_id,
            "path": path,
            "startframe": start,
            "endframe": end,
            "extraframes": None,
            "render_engine": engine,
            "complist": nodes,
            "render_params": None,
        }
    )
    assert res == job_id


@mock.patch("rendercontroller.controller.uuid4")
def test_controller_new_job_with_params(uuid, controller_fix):
    path = "/tmp/testfile.blend"
    start = 1
    end = 10
    engine = "blend"
    nodes = test_nodes[0:2]
    render_params = {"scene": "NewScene"}
    # Override uuid4 so we can verify calls all the way through
    job_id = "2973f9954570424d943afdedee3525b7"
    uuid.return_value.hex = job_id
    controller_fix.server.enqueue.return_value = job_id
    res = controller_fix.new_job(
        path=path,
        start_frame=start,
        end_frame=end,
        render_engine=engine,
        nodes=nodes,
        render_params=render_params,
    )
    controller_fix.server.enqueue.assert_called_with(
        {
            "index": job_id,
            "path": path,
            "startframe": start,
            "endframe": end,
            "extraframes": None,
            "render_engine": engine,
            "complist": nodes,
            "render_params": {"scene": "NewScene"},
        }
    )
    assert res == job_id


def test_controller_start(controller_fix):
    controller_fix.server.start_render.assert_not_called()
    controller_fix.start("testjob")
    controller_fix.server.start_render.assert_called_once()
    # Test job not found
    controller_fix.server.start_render.side_effect = KeyError("testjob2")
    with pytest.raises(JobNotFoundError):
        controller_fix.start("testjob2")


def test_controller_stop(controller_fix):
    controller_fix.server.kill_render.assert_not_called()
    controller_fix.stop("testjob")
    controller_fix.server.kill_render.assert_called_once()
    # Test default kill arg
    controller_fix.server.kill_render.assert_called_with("testjob", True)
    # Test kill=False
    controller_fix.stop("testjob", kill=False)
    controller_fix.server.kill_render.assert_called_with("testjob", False)
    # Test job not found
    controller_fix.server.kill_render.side_effect = KeyError("testjob2")
    with pytest.raises(JobNotFoundError):
        controller_fix.stop("testjob2")


def test_controller_enqueue(controller_fix):
    controller_fix.server.resume_render.assert_not_called()
    controller_fix.enqueue("testjob")
    controller_fix.server.resume_render.assert_called_once()
    controller_fix.server.resume_render.assert_called_with("testjob", startnow=False)
    # Test job not found
    controller_fix.server.resume_render.side_effect = KeyError("testjob2")
    with pytest.raises(JobNotFoundError):
        controller_fix.enqueue("testjob2")


def test_controller_delete(controller_fix):
    controller_fix.server.clear_job.assert_not_called()
    controller_fix.server.get_status.return_value = "Stopped"
    controller_fix.delete("testjob")
    controller_fix.server.clear_job.assert_called_once()
    # Test rendering job
    controller_fix.server.get_status.return_value = "Rendering"
    with pytest.raises(JobStatusError):
        controller_fix.delete("testjob")
    controller_fix.server.get_status.return_value = "Stopped"
    # Test job not found
    controller_fix.server.clear_job.side_effect = KeyError("testjob2")
    with pytest.raises(JobNotFoundError):
        controller_fix.delete("testjob2")


def test_controller_enable_node(controller_fix):
    controller_fix.config.render_nodes = test_nodes
    controller_fix.server.renderjobs = {"testjob": mock.MagicMock()}
    controller_fix.server.renderjobs["testjob"].add_computer.assert_not_called()
    controller_fix.enable_node("testjob", "node1")
    controller_fix.server.renderjobs["testjob"].add_computer.assert_called_with("node1")
    # Test node not found
    with pytest.raises(NodeNotFoundError):
        controller_fix.enable_node("testjob", "node99")
    # Test job not found
    controller_fix.server.clear_job.side_effect = KeyError("testjob2")
    with pytest.raises(JobNotFoundError):
        controller_fix.delete("testjob2")


def test_controller_disable_node(controller_fix):
    controller_fix.config.render_nodes = test_nodes
    controller_fix.server.renderjobs = {"testjob": mock.MagicMock()}
    controller_fix.server.renderjobs["testjob"].remove_computer.assert_not_called()
    controller_fix.disable_node("testjob", "node1")
    controller_fix.server.renderjobs["testjob"].remove_computer.assert_called_with(
        "node1"
    )
    # Test node not found
    with pytest.raises(NodeNotFoundError):
        controller_fix.disable_node("testjob", "node99")
    # Test job not found
    controller_fix.server.clear_job.side_effect = KeyError("testjob2")
    with pytest.raises(JobNotFoundError):
        controller_fix.delete("testjob2")


def test_controller_get_summary(controller_fix):
    controller_fix.server.renderjobs = renderjobs
    ret = controller_fix.get_summary()
    # Messy because dict ordering might be different
    for i in range(len(ret)):
        assert sorted(ret[i]) == sorted(summary[i])


def test_controller_get_job_status(controller_fix):
    controller_fix.server.renderjobs = renderjobs
    ret = controller_fix.get_job_status("9003067201194900903b257115df33bd")
    assert sorted(ret) == sorted(status_33bd)


def test_controller_get_status(controller_fix):
    controller_fix.server.renderjobs = renderjobs
    ret = controller_fix.get_status()
    statuses = [status_eeb1, status_33bd]
    for i in range(len(ret)):
        assert sorted(ret[i]) == sorted(statuses[i])


def test_controller_shutdown(controller_fix):
    controller_fix.server.shutdown_server.assert_not_called()
    controller_fix.shutdown()
    controller_fix.server.shutdown_server.assert_called_once()


### RenderQueue
class DummyJob(object):
    def __init__(self, id, status):
        self.id = id
        self.status = status


jobs = [
    DummyJob("job1", "Waiting"),
    DummyJob("job2", "Finished"),
    DummyJob("job3", "Rendering"),
    DummyJob("job4", "Stopped"),
    DummyJob("job5", "Finished"),
    DummyJob("job6", "Waiting"),
]
orig_keys = ["job1", "job2", "job3", "job4", "job5", "job6"]


@pytest.fixture(scope="function")
def queue_fix():
    q = rendercontroller.controller.RenderQueue()
    for i in jobs:
        q.append(i)
    return q


def test_render_queue_len(queue_fix):
    assert len(queue_fix) == len(jobs)


def test_render_queue_keys(queue_fix):
    assert queue_fix.keys() == [job.id for job in jobs]


def test_render_queue_values(queue_fix):
    assert queue_fix.values() == jobs


def test_render_queue_order(queue_fix):
    assert queue_fix.keys() == orig_keys


def test_render_queue_slice(queue_fix):
    assert jobs[2] == queue_fix[2]
    assert jobs[1:3] == [j for j in queue_fix[1:3]]
    assert jobs[-1] == queue_fix[-1]
    assert jobs[2:-3] == [j for j in queue_fix[2:-3]]


def test_render_queue_get_by_position(queue_fix):
    for i in range(len(jobs)):
        assert jobs[i].id == queue_fix.get_by_position(i).id


def test_render_queue_get_by_id(queue_fix):
    for i in range(len(jobs)):
        job = jobs[i]
        assert job == queue_fix.get_by_id(job.id)


def test_render_queue_append(queue_fix):
    for i in jobs:
        queue_fix.append(i)
    assert queue_fix.keys() == orig_keys
    queue_fix.append(DummyJob("job7", "Rendering"))
    assert queue_fix.keys() == orig_keys + [
        "job7",
    ]


def test_render_queue_insert(queue_fix):
    for i in jobs:
        queue_fix.append(i)
    assert queue_fix.keys() == orig_keys
    queue_fix.insert(DummyJob("job7", "Rendering"), 3)
    assert queue_fix.keys() == ["job1", "job2", "job3", "job7", "job4", "job5", "job6"]


def test_render_queue_move(queue_fix):
    for i in jobs:
        queue_fix.append(i)
    assert queue_fix.keys() == orig_keys
    queue_fix.move("job2", 4)
    assert queue_fix.keys() == ["job1", "job3", "job4", "job5", "job2", "job6"]


def test_render_queue_pop(queue_fix):
    for i in jobs:
        queue_fix.append(i)
    assert queue_fix.keys() == orig_keys
    job = queue_fix.pop("job4")
    assert job == jobs[3]
    assert job not in queue_fix


def test_render_queue_sort_by_status(queue_fix):
    for i in jobs:
        queue_fix.append(i)
    assert queue_fix.keys() == orig_keys
    queue_fix.sort_by_status()
    assert queue_fix.keys() == ["job1", "job3", "job4", "job6", "job2", "job5"]


def test_render_queue_get_next_waiting(queue_fix):
    for i in jobs:
        queue_fix.append(i)
    assert queue_fix.keys() == orig_keys
    next = queue_fix.get_next_waiting()
    assert next == jobs[0]
    # Simulate starting render
    queue_fix[0].status = "Rendering"
    again = queue_fix.get_next_waiting()
    assert again == jobs[5]
    # Simulate starting again
    queue_fix[5].status = "Rendering"
    # Should be none left
    assert queue_fix.get_next_waiting() is None


def test_render_queue_get_position(queue_fix):
    for i in jobs:
        queue_fix.append(i)
    assert queue_fix.get_position("job1") == 0
    assert queue_fix.get_position("job4") == 3


### StateDatabase
db_testjob1 = {
    "id": "job01",
    "status": "Rendering",
    "path": "/tmp/job1",
    "start_frame": 0,
    "end_frame": 100,
    "render_nodes": ["node1", "node2"],
    "time_start": 1643945597.08555,
    "time_stop": 1643945737.287661,
    "frames_completed": [0, 1, 2, 3, 4, 5],
    "queue_position": 0,
}

db_testjob2 = {
    "id": "job02",
    "status": "Waiting",
    "path": "/tmp/job2",
    "start_frame": 0,
    "end_frame": 25,
    "render_nodes": ["node1", "node2", "node3"],
    "time_start": 1643945770.027214,
    "time_stop": 1643945813.785717,
    "frames_completed": [0, 1, 2, 3, 4, 5, 6, 7, 8],
    "queue_position": 1,
}


@pytest.fixture(scope="module")
def test_db_path():
    temp_dir = tempfile.TemporaryDirectory()
    yield os.path.join(temp_dir.name, "rcontroller-test.sqlite")
    temp_dir.cleanup()


@pytest.fixture(scope="module")
def db(test_db_path):
    yield rendercontroller.controller.StateDatabase(test_db_path)


@pytest.fixture(scope="module")
def cursor(test_db_path):
    con = sqlite3.connect(test_db_path)
    cur = con.cursor()
    yield cur
    con.close()


def test_database_initialize(db, cursor):
    db.initialize()
    cursor.execute("SELECT tbl_name, sql FROM sqlite_schema WHERE type='table'")
    assert cursor.fetchall() == [
        (
            "jobs",
            "CREATE TABLE jobs (id TEXT UNIQUE, status TEXT, path TEXT, start_frame INTEGER, "
            + "end_frame INTEGER, render_nodes BLOB, time_start REAL, time_stop REAL, "
            + "frames_completed BLOB, queue_position INTEGER)",
        ),
    ]


def test_database_insert_job_get_job(db, cursor):
    db.insert_job(**db_testjob1)
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 1  # Make sure right number of jobs are in table
    assert db.get_job(db_testjob1["id"]) == db_testjob1


def test_database_get_all_jobs(db, cursor):
    db.insert_job(**db_testjob2)
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 2  # Make sure right number of jobs in table
    assert db.get_all_jobs() == [db_testjob1, db_testjob2]


def test_database_update_job_status(db):
    assert db.get_job("job01")["status"] == db_testjob1["status"]
    assert db.get_job("job02")["status"] == db_testjob2["status"]
    db.update_job_status("job01", "Stopped")
    assert db.get_job("job01")["status"] == "Stopped"
    # Make sure no changes were made to other job
    assert db.get_job("job02")["status"] == "Waiting"


def test_database_update_time_stop(db):
    assert db.get_job("job01")["time_stop"] == db_testjob1["time_stop"]
    assert db.get_job("job02")["time_stop"] == db_testjob2["time_stop"]
    db.update_job_time_stop("job02", 1234.5678)
    assert db.get_job("job02")["time_stop"] == 1234.5678
    # Make sure no changes were made to other job
    assert db.get_job("job01")["time_stop"] == db_testjob1["time_stop"]


def test_database_update_job_frames_completed(db):
    assert db.get_job("job01")["frames_completed"] == db_testjob1["frames_completed"]
    assert db.get_job("job02")["frames_completed"] == db_testjob2["frames_completed"]
    db.update_job_frames_completed("job01", [7, 8, 9, 10])
    assert db.get_job("job01")["frames_completed"] == [7, 8, 9, 10]
    # Make sure no changes were made to other job
    assert db.get_job("job02")["frames_completed"] == db_testjob2["frames_completed"]


def test_database_update_node(db):
    assert db.get_job("job02")["render_nodes"] == ["node1", "node2", "node3"]
    db.update_node("job02", ["node4", "node5", "node6"])
    assert db.get_job("job02")["render_nodes"] == ["node4", "node5", "node6"]


def test_database_update_queue_position(db):
    assert db.get_job("job01")["queue_position"] == 0
    assert db.get_job("job02")["queue_position"] == 1
    db.update_job_queue_position("job01", 5)
    assert db.get_job("job01")["queue_position"] == 5


def test_database_remove_job(db, cursor):
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 2
    db.remove_job("job02")
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT id FROM jobs")
    assert cursor.fetchone()[0] == "job01"
    db.remove_job("job01")
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 0

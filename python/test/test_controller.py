#!/usr/bin/env python3

import pytest
from unittest import mock
from importlib import reload

import rendercontroller.controller

config_test_dict = {
    "string_val": "val1",
    "int_val": 2,
    "float_val": 3.5,
    "bool_val": True,
}
test_nodes = ["node1", "node2", "node3", "node4"]


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
    rendercontroller.controller.RenderController(None)
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
@mock.patch("rendercontroller.controller.job")
@mock.patch("rendercontroller.controller.Config")
def test_controller_new_job(conf, job, uuid):
    path = "/tmp/testfile.blend"
    start = 1
    end = 10
    engine = "blend"
    nodes = test_nodes[0:2]
    # Override uuid4 so we can verify calls all the way through
    job_id = "2973f9954570424d943afdedee3525b7"
    uuid.return_value.hex = job_id
    rc = rendercontroller.controller.RenderController(conf)
    rc.server.enqueue.return_value = job_id
    res = rc.new_job(
        path=path, start_frame=start, end_frame=end, render_engine=engine, nodes=nodes
    )
    rc.server.enqueue.assert_called_with(
        {
            "index": job_id,
            "path": path,
            "startframe": start,
            "endframe": end,
            "extraframes": None,
            "render_engine": engine,
            "complist": nodes,
        }
    )
    assert res == job_id

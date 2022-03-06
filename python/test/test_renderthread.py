import pytest
from unittest import mock
import shlex
from rendercontroller.renderthread import (
    RenderThread,
    BlenderRenderThread,
    Terragen3RenderThread,
)
from rendercontroller.constants import WAITING, RENDERING, FINISHED, FAILED


@pytest.fixture(scope="function")
def render_nodes():
    return ["node1", "node2", "mac1", "mac2"]


@pytest.fixture(scope="function")
def mconf():
    c = mock.MagicMock(name="rendercontroller.util.Config")
    c.node_timeout = 1000
    c.blenderpath_mac = "/mac/blender"
    c.blenderpath_linux = "/linux/blender"
    c.terragenpath_mac = "/mac/terragen"
    c.terragenpath_linux = "/linux/terragen"
    c.macs = ["mac1", "mac2"]
    return c


@pytest.fixture(scope="function")
def thread_data(mconf):
    """Returns thread that is not specific to any render engine."""
    return {
        "config": mconf,
        "job_id": "job01",
        "node": "node1",
        "path": "/tmp/job1.file",
        "frame": 5,
    }


@pytest.fixture(scope="function")
def mbase(thread_data):
    return RenderThread(
        config=thread_data["config"],
        job_id=thread_data["job_id"],
        node=thread_data["node"],
        path=thread_data["path"],
        frame=thread_data["frame"],
    )


@pytest.fixture(scope="function")
def mblender(thread_data):
    return BlenderRenderThread(
        config=thread_data["config"],
        job_id=thread_data["job_id"],
        node=thread_data["node"],
        path=thread_data["path"],
        frame=thread_data["frame"],
    )


@pytest.fixture(scope="function")
def mtgn(thread_data):
    return Terragen3RenderThread(
        config=thread_data["config"],
        job_id=thread_data["job_id"],
        node=thread_data["node"],
        path=thread_data["path"],
        frame=thread_data["frame"],
    )


@mock.patch("threading.Thread")
def test_base_init(thread, thread_data):
    rt = RenderThread(
        config=thread_data["config"],
        job_id=thread_data["job_id"],
        node=thread_data["node"],
        path=thread_data["path"],
        frame=thread_data["frame"],
    )
    # Check passed values
    assert rt.config == thread_data["config"]
    # Note: job_id is only used to configure logging. There is no instance variable.
    assert rt.node == thread_data["node"]
    assert rt.path == thread_data["path"]
    assert rt.frame == thread_data["frame"]

    # Check generated values
    assert rt.status == WAITING
    assert rt.time_start == 0.0
    assert rt.time_start == 0.0
    assert rt.timeout_timer == 0.0
    assert rt.thread == thread.return_value


@mock.patch("time.time")
def test_base_elapsed_time(time, mbase):
    time.return_value = 200.0
    # Case 1: Render not started
    assert mbase.time_start == 0.0
    assert mbase.elapsed_time() == 0.0

    # Case 2: Render running
    mbase.time_start = 100.0
    assert mbase.elapsed_time() == 100.0

    # Case 3: Render finished/stopped
    mbase.time_stop = 150.0
    assert mbase.elapsed_time() == 50.0


@mock.patch("time.time")
def test_base_start(time, mbase):
    t = mock.MagicMock(name="RenderThread.thread")
    mbase.thread = t
    time.return_value = 100.0
    assert mbase.time_start == 0.0
    assert mbase.timeout_timer == 0.0
    t.start.assert_not_called()

    mbase.start()
    assert mbase.time_start == 100.0
    assert mbase.timeout_timer == 100.0
    t.start.assert_called_once()


@mock.patch("time.time")
def test_base_is_timed_out(time, mbase):
    # Case 1: Timeout timer is not started
    assert mbase.timeout_timer == 0.0
    assert not mbase.is_timed_out()

    # Case 2: Timeout timer started but not over limit
    time.return_value = 200.0
    mbase.timeout_timer = 100.0
    assert mbase.config.node_timeout == 1000
    assert not mbase.is_timed_out()

    # Case 3: Timeout timer started and over limit
    time.return_value = 2000.0
    assert mbase.is_timed_out()


@mock.patch("time.time")
def test_base_stop_render_timer(time, mbase):
    time.return_value = 100.0
    assert mbase.time_stop == 0.0
    mbase.stop_render_timer()
    assert mbase.time_stop == 100.0


def test_base_stop(mbase):
    with pytest.raises(NotImplementedError):
        mbase.stop()


def test_base_worker(mbase):
    with pytest.raises(NotImplementedError):
        mbase.worker()


def test_blender_init(thread_data, mconf):
    # Linux
    bt = BlenderRenderThread(**thread_data)
    assert bt.pid is None
    assert bt.patterns  # Just want to make sure they exist
    assert bt.execpath == mconf.blenderpath_linux

    # Mac
    thread_data["node"] = "mac1"
    bt = BlenderRenderThread(**thread_data)
    assert bt.execpath == mconf.blenderpath_mac


@mock.patch("threading.Thread")
def test_blender_stop(thread, mblender):
    # Case 1: Not rendering
    assert mblender.status == WAITING
    mblender.stop()
    thread.assert_not_called()

    # Case 2: PID not set
    mblender.status = RENDERING
    assert not mblender.pid
    mblender.stop()
    thread.assert_not_called()

    # Case 3: PID set
    mblender.pid = 101
    mblender.stop()
    thread.assert_called_once()
    thread.return_value.start.assert_called_once()


@mock.patch("shutil.which")
@mock.patch("subprocess.call")
def test_blender_ssh_kill_thread(call, which, mblender):
    mblender.pid = 101
    which.return_value = "/test/ssh"
    mblender._ssh_kill_thread()
    call.assert_called_with(["/test/ssh", "node1", f"kill {101}"])


@mock.patch("subprocess.Popen")
def test_blender_worker(popen, mblender):
    popen.return_value.stdout.readline.return_value = ""
    popen.assert_not_called()
    mblender.worker()
    popen.assert_called_once()



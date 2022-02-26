import pytest
import tempfile
import os.path
import sqlite3
from unittest import mock
from rendercontroller.constants import WAITING, RENDERING, STOPPED, FINISHED, FAILED

from rendercontroller.controller import StateDatabase

db_testjob1 = {
    "id": "job01",
    "status": RENDERING,
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
    "status": WAITING,
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
def db_path():
    temp_dir = tempfile.TemporaryDirectory()
    yield os.path.join(temp_dir.name, "rcontroller-test.sqlite")
    temp_dir.cleanup()


@pytest.fixture(scope="module")
def db(db_path):
    db = StateDatabase(db_path)
    db.initialize()
    yield db


@pytest.fixture(scope="module")
def cursor(db_path):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    yield cur
    con.close()


def test_database_initialize(db_path, cursor):
    db = StateDatabase(db_path)
    db.initialize()
    cursor.execute("SELECT tbl_name, sql FROM sqlite_schema WHERE type='table'")
    assert cursor.fetchall() == [
        (
            "jobs",
            "CREATE TABLE jobs (id TEXT UNIQUE, status TEXT, path TEXT, start_frame INTEGER, "
            + "end_frame INTEGER, render_nodes BLOB, time_start REAL, time_stop REAL, "
            + "frames_completed BLOB, queue_position INTEGER, timestamp FLOAT)",
        ),
    ]


@mock.patch("time.time")
def test_database_insert_job_get_job(time, db, cursor):
    time.return_value = 123.456
    db.insert_job(**db_testjob1)
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 1  # Make sure right number of jobs are in table
    actual = db.get_job(db_testjob1["id"])
    assert actual.pop("timestamp") == 123.456
    assert actual == db_testjob1


def test_database_get_all_jobs(db, cursor):
    db.insert_job(**db_testjob2)
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 2  # Make sure right number of jobs in table
    actual = db.get_all_jobs()
    for job in actual:
        # Must remove timestamps because not part of input dict
        job.pop("timestamp")
    assert actual == [db_testjob1, db_testjob2]


def test_database_update_job_status(db):
    assert db.get_job("job01")["status"] == db_testjob1["status"]
    assert db.get_job("job02")["status"] == db_testjob2["status"]
    ts_pre = db.get_job("job01")["timestamp"]
    db.update_job_status("job01", STOPPED)
    assert db.get_job("job01")["status"] == STOPPED
    # Make sure no changes were made to other job
    assert db.get_job("job02")["status"] == WAITING
    # Make sure timestamp was updated
    assert db.get_job("job01")["timestamp"] > ts_pre


def test_database_update_time_start(db):
    assert db.get_job("job01")["time_start"] == db_testjob1["time_start"]
    assert db.get_job("job02")["time_start"] == db_testjob2["time_start"]
    ts_pre = db.get_job("job02")["timestamp"]
    db.update_job_time_start("job02", 1234.5678)
    assert db.get_job("job02")["time_start"] == 1234.5678
    # Make sure no changes were made to other job
    assert db.get_job("job01")["time_start"] == db_testjob1["time_start"]
    # Make sure timestamp was updated
    assert db.get_job("job02")["timestamp"] > ts_pre


def test_database_update_time_stop(db):
    assert db.get_job("job01")["time_stop"] == db_testjob1["time_stop"]
    assert db.get_job("job02")["time_stop"] == db_testjob2["time_stop"]
    ts_pre = db.get_job("job02")["timestamp"]
    db.update_job_time_stop("job02", 1234.5678)
    assert db.get_job("job02")["time_stop"] == 1234.5678
    # Make sure no changes were made to other job
    assert db.get_job("job01")["time_stop"] == db_testjob1["time_stop"]
    # Make sure timestamp was updated
    assert db.get_job("job02")["timestamp"] > ts_pre


def test_database_update_job_frames_completed(db):
    assert db.get_job("job01")["frames_completed"] == db_testjob1["frames_completed"]
    assert db.get_job("job02")["frames_completed"] == db_testjob2["frames_completed"]
    ts_pre = db.get_job("job01")["timestamp"]
    db.update_job_frames_completed("job01", [7, 8, 9, 10])
    assert db.get_job("job01")["frames_completed"] == [7, 8, 9, 10]
    # Make sure no changes were made to other job
    assert db.get_job("job02")["frames_completed"] == db_testjob2["frames_completed"]
    # Make sure timestamp was updated
    assert db.get_job("job01")["timestamp"] > ts_pre


def test_database_update_nodes(db):
    assert db.get_job("job02")["render_nodes"] == ["node1", "node2", "node3"]
    ts_pre = db.get_job("job02")["timestamp"]
    db.update_nodes("job02", ["node4", "node5", "node6"])
    assert db.get_job("job02")["render_nodes"] == ["node4", "node5", "node6"]
    # Make sure timestamp was updated
    assert db.get_job("job02")["timestamp"] > ts_pre


def test_database_update_queue_position(db):
    assert db.get_job("job01")["queue_position"] == 0
    assert db.get_job("job02")["queue_position"] == 1
    ts_pre = db.get_job("job01")["timestamp"]
    db.update_job_queue_position("job01", 5)
    assert db.get_job("job01")["queue_position"] == 5
    # Makes sure timestamp was updated
    assert db.get_job("job01")["timestamp"] > ts_pre


def test_database_delete_job(db, cursor):
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 2
    db.delete_job("job02")
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT id FROM jobs")
    assert cursor.fetchone()[0] == "job01"
    db.delete_job("job01")
    cursor.execute("SELECT COUNT(*) FROM jobs")
    assert cursor.fetchone()[0] == 0

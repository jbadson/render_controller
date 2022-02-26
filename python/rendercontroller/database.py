import time
import json
import sqlite3
from typing import List, Sequence, Dict, Tuple, Set


class StateDatabase(object):
    """Interface for SQLite Database to store server state."""

    def __init__(self, filepath: str):
        self.filepath = filepath

    def initialize(self) -> None:
        jobs_schema = [
            "id TEXT UNIQUE",
            "status TEXT",
            "path TEXT",
            "start_frame INTEGER",
            "end_frame INTEGER",
            "render_nodes BLOB",
            "time_start REAL",
            "time_stop REAL",
            "frames_completed BLOB",
            "queue_position INTEGER",
            "timestamp FLOAT",
        ]
        self.execute(
            f"CREATE TABLE IF NOT EXISTS jobs ({', '.join(jobs_schema)})", commit=True
        )

    def insert_job(
        self,
        id: str,
        status: str,
        path: str,
        start_frame: int,
        end_frame: int,
        render_nodes: Sequence[str],
        time_start: float,
        time_stop: float,
        frames_completed: Set[int],
        queue_position: int,
    ) -> None:
        """Adds a new RenderJob to the database."""
        query = (
            "INSERT INTO jobs (id, status, path, start_frame, end_frame, render_nodes, time_start, time_stop, "
            "frames_completed, queue_position, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            id,
            status,
            path,
            start_frame,
            end_frame,
            json.dumps(render_nodes),
            time_start,
            time_stop,
            json.dumps(
                tuple(frames_completed)
            ),  # Because set is not JSON serializable.
            queue_position,
            time.time(),
        )
        self.execute(query, params, commit=True)

    def update_job_status(self, id: str, status: str) -> None:
        self.execute(
            f"UPDATE jobs SET status = ?, timestamp = ? WHERE id = ?",
            (status, time.time(), id),
            commit=True,
        )

    def update_job_time_start(self, id: str, time_start: float) -> None:
        self.execute(
            f"UPDATE jobs SET time_start = ?, timestamp = ? WHERE id = ?",
            (time_start, time.time(), id),
            commit=True,
        )

    def update_job_time_stop(self, id: str, time_stop: float) -> None:
        self.execute(
            f"UPDATE jobs SET time_stop={time_stop}, timestamp={time.time()} WHERE id='{id}'",
            commit=True,
        )

    def update_job_frames_completed(self, id: str, frames_completed: Set[int]) -> None:
        self.execute(
            f"UPDATE jobs SET frames_completed = ?, timestamp = ? WHERE id = ?",
            (json.dumps(tuple(frames_completed)), time.time(), id),
            commit=True,
        )

    def update_job_queue_position(self, id: str, queue_position: int) -> None:
        self.execute(
            f"UPDATE jobs SET queue_position = ?, timestamp = ? WHERE id = ?",
            (queue_position, time.time(), id),
            commit=True,
        )

    def update_nodes(self, job_id: str, render_nodes: Sequence[str]) -> None:
        self.execute(
            f"UPDATE jobs SET render_nodes = ?, timestamp = ? WHERE id = ?",
            (json.dumps(render_nodes), time.time(), job_id),
            commit=True,
        )

    @staticmethod
    def _parse_job_row(row: Sequence) -> Dict:
        return {
            "id": row[0],
            "status": row[1],
            "path": row[2],
            "start_frame": row[3],
            "end_frame": row[4],
            "render_nodes": json.loads(row[5]),
            "time_start": row[6],
            "time_stop": row[7],
            "frames_completed": set(json.loads(row[8])),
            "queue_position": row[9],
            "timestamp": row[10],
        }

    def get_job(self, id) -> Dict:
        jobs = self.execute(f"SELECT * FROM jobs WHERE id = ?", (id,))
        if len(jobs) > 1:
            raise KeyError("Multiple jobs found with same id.")
        return self._parse_job_row(jobs[0])

    def get_all_jobs(self) -> List[Dict]:
        """Returns a list of all job records ordered by queue position (ascending)."""
        jobs = self.execute("SELECT * FROM jobs ORDER BY queue_position ASC")
        ret = []
        for j in jobs:
            ret.append(self._parse_job_row(j))
        return ret

    def delete_job(self, id) -> None:
        self.execute(f"DELETE FROM jobs WHERE id = ?", (id,), commit=True)

    def execute(self, query: str, params: Tuple = (), commit: bool = False) -> List:
        con = sqlite3.connect(self.filepath)
        cursor = con.cursor()
        cursor.execute(query, params)
        ret = cursor.fetchall()
        if commit:
            con.commit()
        con.close()
        return ret

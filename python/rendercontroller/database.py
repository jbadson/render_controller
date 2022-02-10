import time
import sqlite3
from typing import Type, List, Tuple, Sequence, Dict, Optional


class StateDatabase(object):
    """Interface for SQLite Database to store server state."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        # FIXME Might be better to have conn as instance variable. Would that lock the db file?

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
        self.execute(f"CREATE TABLE IF NOT EXISTS jobs ({', '.join(jobs_schema)})")

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
        frames_completed: Sequence[int],
        queue_position: int,
    ) -> None:
        frames_completed = ",".join([str(i) for i in frames_completed])
        render_nodes = ",".join(render_nodes)
        self.execute(
            f"INSERT INTO jobs VALUES ('{id}', '{status}', '{path}', {start_frame}, {end_frame}, "
            + f"'{render_nodes}', {time_start}, {time_stop}, '{frames_completed}', {queue_position}, "
            + f"{time.time()})",
            commit=True,
        )

    def update_job_status(self, id: str, status: str) -> None:
        self.execute(
            f"UPDATE jobs SET status='{status}', timestamp={time.time()} WHERE id='{id}'",
            commit=True,
        )

    def update_job_time_start(self, id: str, time_start: float) -> None:
        self.execute(
            f"UPDATE jobs SET time_start={time_start}, timestamp={time.time()} WHERE id='{id}'",
            commit=True,
        )

    def update_job_time_stop(self, id: str, time_stop: float) -> None:
        self.execute(
            f"UPDATE jobs SET time_stop={time_stop}, timestamp={time.time()} WHERE id='{id}'",
            commit=True,
        )

    def update_job_frames_completed(self, id: str, frames_completed: List[int]) -> None:
        frames_completed = ",".join([str(i) for i in frames_completed])
        self.execute(
            f"UPDATE jobs SET frames_completed='{frames_completed}', timestamp={time.time()} WHERE id='{id}'",
            commit=True,
        )

    def update_job_queue_position(self, id: str, queue_position: int) -> None:
        self.execute(
            f"UPDATE jobs SET queue_position={queue_position}, timestamp={time.time()} WHERE id='{id}'",
            commit=True,
        )

    def update_nodes(self, job_id: str, render_nodes: Sequence[str]) -> None:
        render_nodes = ",".join(render_nodes)
        self.execute(
            f"UPDATE jobs SET render_nodes='{render_nodes}', timestamp={time.time()} WHERE id='{job_id}'",
            commit=True,
        )

    def _parse_job_row(self, row: Sequence) -> Dict:
        return {
            "id": row[0],
            "status": row[1],
            "path": row[2],
            "start_frame": row[3],
            "end_frame": row[4],
            "render_nodes": row[5].split(","),
            "time_start": row[6],
            "time_stop": row[7],
            "frames_completed": [int(i) for i in row[8].split(",")] if row[8] else [],
            "queue_position": row[9],
            "timestamp": row[10],
        }

    def get_job(self, id) -> Dict:
        job = self.execute(f"SELECT * FROM jobs WHERE id='{id}'")
        if len(job) > 1:
            raise KeyError("Multiple jobs found with same id.")
        return self._parse_job_row(job[0])

    def get_all_jobs(self) -> List[Dict]:
        """Returns a list of all job records ordered by queue position (ascending)."""
        jobs = self.execute("SELECT * FROM jobs ORDER BY queue_position ASC")
        ret = []
        for j in jobs:
            ret.append(self._parse_job_row(j))
        return ret

    def delete_job(self, id) -> None:
        self.execute(f"DELETE FROM jobs WHERE id='{id}'", commit=True)

    def execute(self, query: str, commit: bool = False) -> List:
        # FIXME make this sane. Just want to get something working for now.
        con = sqlite3.connect(self.filepath)
        cursor = con.cursor()
        cursor.execute(query)
        ret = cursor.fetchall()
        if commit:
            con.commit()
        con.close()
        return ret

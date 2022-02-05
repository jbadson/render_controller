import time
import os.path
import queue
import logging
from typing import Type, List, Tuple, Sequence, Dict, Optional
from .controller import Config

logger = logging.getLogger("job")

# Job statuses
WAITING = "Waiting"
RENDERING = "Rendering"
STOPPED = "Stopped"
FINISHED = "Finished"


class RenderJob(object):
    def __init__(
        self,
        config: Type[Config],
        id: str,
        path: str,
        start_frame: int,
        end_frame: int,
        render_nodes: Sequence[str],
        status: Optional[str] = None,
        time_start: Optional[float] = None,
        time_stop: Optional[float] = None,
        frames_completed: Optional[Sequence[int]] = None,
    ):
        self.config = config
        self.id = id
        self.path = path
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.nodes_enabled = render_nodes
        self.status = status if status else WAITING
        self.time_start = time_start if time_start else time.time()
        self.time_stop = time_stop
        self.frames_completed = frames_completed if frames_completed else []

        # LiFo queue because if a frame fails while rendering, we want to re-try it first.
        self.queue = queue.LifoQueue()
        frames = list(range(self.start_frame, self.end_frame + 1))
        frames.reverse()
        for frame in frames:
            if frame not in self.frames_completed:
                self.queue.put(frame)

        self.logger = logger.getChild(os.path.basename(self.path))
        self.logger.info(
            f"placed in queue to render frames {self.start_frame}-{self.end_frame} on nodes {', '.join(self.nodes_enabled)} with ID {self.id}"
        )

        if self.status == RENDERING:
            # FIXME Can't decide if this should happen here, or if we should reset status and make caller re-start the render.
            self.render()

    def render(self) -> None:
        """Starts the render."""
        # FIXME look into newer parallelism options. Might be better to use pool or something instead of manually
        # FIXME creating worker threads.
        pass

    def stop(self) -> None:
        """Stops the render and attempts to terminate all current render processes."""
        pass

    def enable_node(self, node: str) -> None:
        """Enables a node for rendering on this job."""
        pass

    def disable_node(self, node: str) -> None:
        """Disables a node for rendering on this job."""
        pass

    def get_pct_complete(self) -> float:
        """Returns percent complete."""
        pass

    def get_times(self) -> Tuple[float]:
        """Returns tuple of (elapsed_time, avg_time_per_frame, est_time_remaining) in seconds."""
        pass

    def dump(self) -> Dict:
        """Returns dict of all job parameters."""
        pass

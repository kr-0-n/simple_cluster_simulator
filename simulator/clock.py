"""
Simulated time. One step corresponds to `step_duration` of simulated time.
"""
from datetime import datetime, timedelta

DEFAULT_START = datetime(2020, 1, 1)
DEFAULT_STEP = timedelta(minutes=1)


class Clock:
    def __init__(self, start: datetime = DEFAULT_START, step_duration: timedelta = DEFAULT_STEP):
        self.start = start
        self.step_duration = step_duration
        self.step = 0

    @property
    def time(self) -> datetime:
        return self.time_of(self.step)

    def tick(self):
        self.step += 1

    def time_of(self, step: int) -> datetime:
        return self.start + step * self.step_duration

    def step_of(self, time: datetime) -> int:
        return int((time - self.start) / self.step_duration)

"""
Simulated time. One time step corresponds to STEP_DURATION of simulated time.
"""

from datetime import datetime, timedelta

START_TIME: datetime = datetime(2020, 1, 1, 0, 0, 0)
STEP_DURATION: timedelta = timedelta(minutes=1)

simulated_time: datetime = START_TIME
time_step: int = 0


def increment_time():
    """
    Advance the simulation by one time step.
    """
    global simulated_time
    global time_step
    simulated_time += STEP_DURATION
    time_step += 1


def current_time() -> datetime:
    """
    returns the current time as a datetime
    """
    return simulated_time


def current_time_step() -> int:
    """
    returns the current timestep as an integer
    """
    return time_step


def timestep_to_time(timestep: int) -> datetime:
    """
    converts an integer timestep into a datetime
    """
    return START_TIME + timestep * STEP_DURATION


def time_to_timestep(time: datetime) -> int:
    """
    converts a datetime into an integer timestep
    """
    return int((time - START_TIME) / STEP_DURATION)


def sql_time(time_obj: datetime) -> str:
    """
    converts a time object into valid sql time
    """
    return time_obj.strftime("%Y-%m-%d %H:%M:%S")


def reset_time():
    """
    resets the time to START_TIME and the timestep to 0
    """
    global simulated_time
    global time_step
    simulated_time = START_TIME
    time_step = 0

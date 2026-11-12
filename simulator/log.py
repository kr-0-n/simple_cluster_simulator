import logging

FORMAT = "%(asctime)s %(levelname)-7s %(processName)s %(name)s: %(message)s"


def configure_logging(level: int = logging.INFO):
    logging.basicConfig(level=level, format=FORMAT, force=True)

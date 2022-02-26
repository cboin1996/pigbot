import logging

def set_logger_config_globally(timestamp: str) -> None:
    """Sets the python logging module settings for output
    to stdout and to file.

    Args:
        timestamp (str): the timestamp to name the log file.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
    )
import logging.handlers
import sys
from pathlib import Path

from slimbot import Config, SlimBot


def setup_logging(log_loc):
    # Set only the root logger from which all loggers derive their config (Python's logging is hierarchical).
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')

    console_log_handler = logging.StreamHandler()
    console_log_handler.setFormatter(formatter)

    Path(log_loc).parent.mkdir(parents=True, exist_ok=True)
    file_log_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_loc,
        encoding='utf-8',
        when='midnight',
        utc=True
    )
    file_log_handler.setFormatter(formatter)

    logger.addHandler(console_log_handler)
    logger.addHandler(file_log_handler)


if __name__ == '__main__':
    root_dir = Path(__file__).parent.resolve()
    config = Config.parse(root_dir)
    if config is None:
        sys.exit(1)

    bot = SlimBot(config)
    setup_logging(config.log_file)
    bot.run(config.token, log_handler=None)  # Set `log_handler` to `None` as we manually set up logging.

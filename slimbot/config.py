from __future__ import annotations  # TODO Remove in Python version 3.11.

import logging
from pathlib import Path
from typing import Dict

import toml
from toml import TomlDecodeError

_logger = logging.getLogger(__name__)
CONFIG_FILENAME = 'config.toml'
DEFAULT_CONFIG = """# token = '<uncomment this line and insert your Discord token here>'

[defaults]
# These settings only apply if server-specific settings don't overwrite them.
command_prefix = '?'
ticket_cooldown = 3600

[paths]
database = 'database/data.db'
log = 'logs/slimbot.log'
cogs = 'cogs'
images = 'images'
migrations = 'migrations'
"""


class ParseError(Exception):
    """Raised when something goes wrong while parsing the config file."""
    pass


class Config:
    """Contains the configurable values of the bot."""

    def __init__(
            self,
            token: str,
            defaults: Dict[str, str | int],
            root_dir: Path,
            ext_dir: Path,
            img_dir: Path,
            cfg_file: Path,
            db_file: Path,
            log_file: Path
    ) -> None:
        self.token = token
        self.defaults = defaults
        self.root_dir = root_dir
        self.ext_dir = ext_dir
        self.cfg_file = cfg_file
        self.img_dir = img_dir
        self.db_file = db_file
        self.log_file = log_file

    @classmethod
    def parse(cls, root_dir: str | Path) -> Config:
        """Parse the config file. If it does not exist, generate a default one.

        Args:
            root_dir: The root directory of the project.

        Raises:
            ParseError: The config does not file exist, error while decoding toml or missing key.

        Returns:
            The parsed config.
        """
        if isinstance(root_dir, str):
            root_dir = Path(root_dir)

        cfg_file = root_dir / CONFIG_FILENAME
        if not cfg_file.exists():
            _generate_default_config_file(root_dir=root_dir)
            _logger.warning(
                'Config file not found. Generating a default one. '
                'Please uncomment the first line and enter your Discord token.'
            )
            raise ParseError

        try:
            config = toml.loads(cfg_file.read_text())
        except TomlDecodeError:
            _logger.exception('Error while parsing the config file!')
            raise ParseError

        try:
            token: str = config['token']
            defaults: Dict = config['defaults']
            ext_dir = root_dir / config['paths']['cogs']
            img_dir = root_dir / config['paths']['images']
            migr_dir = root_dir / config['paths']['migrations']
            db_file = root_dir / config['paths']['database']
            log_file = root_dir / config['paths']['log']

        except KeyError as err:
            _logger.exception(f'Key `{err.args[0]}` not found in {cfg_file}!')
            raise ParseError
        return cls(
            token=token,
            defaults=defaults,
            root_dir=root_dir,
            ext_dir=ext_dir,
            img_dir=img_dir,
            cfg_file=cfg_file,
            db_file=db_file,
            log_file=log_file,
        )


def _generate_default_config_file(root_dir: Path):
    cfg_file = root_dir / CONFIG_FILENAME
    cfg_file.write_text(DEFAULT_CONFIG)

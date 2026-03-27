#
# Copyright 2023 BredOS
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Any
from .logging import lrun, lp
import os
from pathlib import Path
from pysetting import JSONConfiguration

app_settings = None


def load_settings(settings: Path, default_settings_path: Path) -> None:
    """
    Load the settings from the settings file

        Does the following:
        - Checks if the settings file exists
        - If not, creates it
        - If it does, loads the settings from it

    Parameters:
    - settings: The path to the settings file
    - default_settings_path: The path to the default settings file

    Returns: A JSONConfiguration object
    """
    lp("Settings file: " + str(settings), mode="debug")
    if not settings.exists():
        lp("Settings file does not exist. Creating..")
        create_settings_file(settings)

    global app_settings
    app_settings = JSONConfiguration(settings)


def settings_get(key: str) -> Any:
    """
    Get a setting from the settings file

    Parameters:
    - key: The key to get

    Returns: The value of the key
    """
    return app_settings[key]


def settings_set(key: str, value: Any) -> None:
    """
    Set a setting in the settings file

    Parameters:
    - key: The key to set
    - value: The value to set the key to

    Returns: None
    """
    app_settings[key] = value
    app_settings.write_data()


def create_settings_file(settings: Path, default_settings_path: Path) -> None:
    """
    Creates the settings file from the default settings file

    Parameters:
    - settings: The path to the settings file
    - default_settings_path: The path to the default settings file

    Returns: None
    """
    settings.parents[0].mkdir(parents=True, exist_ok=True)
    os.chmod(settings.parents[0], 0o755)
    lrun(
        [
            "cp",
            str(default_settings_path),
            str(settings),
        ]
    )
    os.chmod(settings, 0o666)

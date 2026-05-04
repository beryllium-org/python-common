#
# Copyright 2026 Beryllium
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

import os
from pathlib import Path
from typing import Callable
from traceback import print_exception
from pyrunning import logging, LogMessage, LoggingHandler, Command, LoggingLevel
from functools import partial

logger = None
handler = None

dryrun = False if "DO_DRYRUN" not in os.listdir() else True


def setup_logging(
    logger_name: str,
    log_dir: str,
    log_name: str,
    console_default_log_level=logging.INFO,
) -> None:
    """
    Setup logging

        Does the following:
        - Creates a logger with a name
        - Sets the format for the logs
        - Sets up logging to a file and future console
    """
    global logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        if not os.path.isdir(log_dir):
            raise FileNotFoundError("The directory {} does not exist".format(log_dir))
        # get write perms
        elif not os.access(log_dir, os.W_OK):
            raise PermissionError(
                "You do not have permission to write to {}".format(log_dir)
            )
    except Exception as e:
        print_exception(type(e), e, e.__traceback__)
        exit(1)
    log_file = os.path.abspath(os.path.join(log_dir, log_name))

    log_file_handler = logging.FileHandler(log_file)
    log_file_handler.setLevel(logging.DEBUG)
    log_file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)8s] %(message)s",
    )
    log_file_handler.setFormatter(log_file_formatter)
    logger.addHandler(log_file_handler)

    log_error_handler = logging.StreamHandler()
    log_error_handler.setLevel(console_default_log_level)
    log_error_formatter = logging.Formatter("%(levelname)8s: %(message)s")
    log_error_handler.setFormatter(log_error_formatter)
    logger.addHandler(log_error_handler)


def setup_handler(*args) -> None:
    """
    Setup the logging handler

    parameters:
    - args: logging functions to pass to the handler

    returns: None

    """
    global handler
    handler = LoggingHandler(
        logger=logger,
        logging_functions=args,
    )


def get_logger() -> logging.Logger:
    """
    Get the configured logger instance.

    Returns:
        logging.Logger: The configured logger instance.
    """
    global logger
    if logger is None:
        raise ValueError("Logger has not been set up. Call setup_logging first.")
    return logger


def get_handler() -> logging.Handler:
    """
    Get the configured logging handler instance.

    Returns:
        logging.Handler: The configured logging handler instance.
    """
    global handler
    if handler is None:
        raise ValueError("Handler has not been set up. Call setup_logging first.")
    return handler


def rm_old_logs(log_dir_path: str, keep: int = 5) -> None:
    """
    Remove old logs from the log directory

    Parameters:
    - log_dir_path: The path to the log directory
    - keep: The number of logs to keep. Default is 5
    """
    logs = sorted(Path(log_dir_path).iterdir(), key=os.path.getmtime)
    for i in range(len(logs) - keep):
        os.remove(logs[i])


def lp(message, mode="info") -> None:
    """
    Log a message to the logger

    Parameters:
    - message: The message to log
    - mode: The mode to log the message in. Default is "info"
    """
    if mode == "info":
        LogMessage.Info(message).write(logging_handler=handler)
    elif mode == "debug":
        LogMessage.Debug(message).write(logging_handler=handler)
    elif mode == "warn":
        LogMessage.Warning(message).write(logging_handler=handler)
    elif mode == "crit":
        LogMessage.Critical(message).write(logging_handler=handler)
    elif mode == "error":
        LogMessage.Error(message).write(logging_handler=handler)
    elif mode == "exception":
        LogMessage.Exception(message).write(logging_handler=handler)
    else:
        raise ValueError("Invalid mode.")


def post_run_cmd(info, exitcode) -> None:
    if exitcode:
        lp(f"Command failed with exit code {exitcode}", mode="error")
        raise Exception(f"Command failed with exit code {exitcode}")


def expected_to_fail(info, exitcode) -> None:
    if exitcode:
        lp(f"Command failed with exit code {exitcode}", mode="error")


def lrun(
    cmd: list,
    force: bool = False,
    silent: bool = False,
    shell: bool = False,
    cwd: str = ".",
    postrunfn: Callable = post_run_cmd,
    wait=True,
) -> None:
    """
    Run a command and log the output

    Parameters:
    - cmd: The command to run
    - force: Whether to run the command even if dryrun is enabled. Default is False
    - silent: Whether to run the command silently. Default is False
    - shell: Whether to run the command in a shell. Default is False
    - cwd: The working directory to run the command in. Default is "."
    Returns: None
    """
    if dryrun and not force:
        lp("Would have run: " + " ".join(cmd))
    else:
        if shell and wait:
            new_cmd = " ".join(cmd)
            Command.Shell(
                new_cmd,
                is_silent=silent,
                working_directory=cwd,
                post_run_function=partial(postrunfn),
                do_send_output_to_post_run_function=True,
                do_send_exit_code_to_post_run_function=True,
            ).run_log_and_wait(logging_handler=handler)
        elif shell and not wait:
            new_cmd = " ".join(cmd)
            Command.Shell(
                new_cmd,
                is_silent=silent,
                working_directory=cwd,
                post_run_function=partial(postrunfn),
                do_send_output_to_post_run_function=True,
                do_send_exit_code_to_post_run_function=True,
            ).run_and_log(logging_handler=handler)
        elif not shell and wait:
            Command(
                cmd,
                is_silent=silent,
                working_directory=cwd,
                post_run_function=partial(postrunfn),
                do_send_output_to_post_run_function=True,
                do_send_exit_code_to_post_run_function=True,
            ).run_log_and_wait(logging_handler=handler)
        elif not shell and not wait:
            Command(
                cmd,
                is_silent=silent,
                working_directory=cwd,
                post_run_function=partial(postrunfn),
                do_send_output_to_post_run_function=True,
                do_send_exit_code_to_post_run_function=True,
            ).run_and_log(logging_handler=handler)

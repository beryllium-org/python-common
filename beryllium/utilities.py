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

import os
import random
import string
import shutil
import secrets
import tempfile
import subprocess
from pathlib import Path
from threading import Lock
from functools import wraps
from time import monotonic, perf_counter
from typing import Iterator, Optional, Callable, Any
from .logging import lrun, lp


class CommandStream:
    # Wrapper to help pretend the elevated streams are like Popen
    def __init__(self, generator: Iterator[str], proc):
        self._gen = generator
        self._iter = iter(generator)
        self._proc = proc
        self.returncode = 1

        self.stdin = proc.stdin
        self.stdout = proc.stdout
        self.stderr = proc.stderr

    def __enter__(self):
        if self._proc:
            return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._proc and hasattr(self._gen, "close"):
            try:
                self.returncode = self._proc.returncode
            except:
                pass
            self._gen.close()
            self._proc = None

    def __iter__(self):
        if self._proc:
            return self

    def __next__(self):
        if self._proc:
            return next(self._iter)

    def read(self) -> str:
        if self._proc:
            return "".join(self._iter)

    def readline(self) -> str:
        if self._proc:
            try:
                return next(self._iter)
            except StopIteration:
                return ""

    def readlines(self) -> list[str]:
        if self._proc:
            return list(self._iter)

    def close(self) -> None:
        if self._proc and hasattr(self._gen, "close"):
            try:
                self.returncode = self._proc.returncode
            except:
                pass
            self._gen.close()
            self._proc = None

    def wait(self) -> None:
        if self._proc:
            try:
                self.returncode = self._proc.returncode
            except:
                pass
            self._gen.close()
            self._proc = None

    def kill(self) -> None:
        if self._proc:
            try:
                self.returncode = self._proc.returncode
            except:
                pass
            self._proc.kill()
            try:
                self.returncode = self._proc.returncode
            except:
                pass
            self._gen.close()
            self._proc = None


def debounce(wait):
    """
    Decorator that will postpone a function's
    execution until after wait seconds
    have elapsed since the last time it was invoked.
    """

    def decorator(func):
        last_time_called = 0
        lock = Lock()

        @wraps(func)
        def debounced(*args, **kwargs):
            nonlocal last_time_called
            with lock:
                elapsed = monotonic() - last_time_called
                remaining = wait - elapsed
                if remaining <= 0:
                    last_time_called = monotonic()
                    return func(*args, **kwargs)
                else:
                    return None

        return debounced

    return decorator


def time_fn(func: Callable) -> Callable:
    @wraps(func)
    def wrapped(*args, **kwargs) -> Any:
        start_time = perf_counter()  # More precise than time.time()
        result = func(*args, **kwargs)
        duration = perf_counter() - start_time
        lp(f"Function '{func.__name__}' took {duration:.4f} seconds to execute.")
        return result

    return wrapped


def catch_exceptions(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            lp(f"Exception in {func.__name__}: {e}", mode="error")
            raise e

    return wrapper


def detect_device() -> str:
    """
    Detect the device model

    Parameters:
    - None

    Returns:
    - str: The device model
    """
    try:
        with open("/sys/firmware/devicetree/base/model", "r") as model_file:
            return model_file.read().rstrip("\n").rstrip("\x00")
    except FileNotFoundError:
        try:
            with open("/sys/class/dmi/id/product_name", "r") as product_name_file:
                return product_name_file.read().rstrip("\n")
        except FileNotFoundError:
            return "unknown"


def detect_session_configuration() -> dict:
    """
    Detect the session configuration

    - Parameters:
        - None

    - Returns:
        - dict: The session configuration
    """
    try:
        xdg_session_type = os.environ.get("XDG_SESSION_TYPE")
    except:
        xdg_session_type = None
    # Check for the XDG_CURRENT_DESKTOP environment variable and lowercase it
    try:
        xdg_current_desktop = os.environ.get("XDG_CURRENT_DESKTOP").lower()
    except:
        xdg_current_desktop = None
    # look at where display-manager.service is symlinked to
    try:
        display_manager = os.path.basename(
            os.path.realpath("/etc/systemd/system/display-manager.service")
        ).replace(".service", "")
    except:
        display_manager = None

    if xdg_session_type == "wayland":
        return {"dm": display_manager, "de": xdg_current_desktop, "is_wayland": True}
    else:
        return {"dm": display_manager, "de": xdg_current_desktop, "is_wayland": False}


def get_ram_size(unit: str = "KB") -> int:
    """
    Get the total RAM size in the system

    Parameters:
    - unit: The unit to return the RAM size in. Default is KB

    Returns:
    - int: The total RAM size in the system
    """
    try:
        with open("/proc/meminfo", "r") as meminfo:
            for line in meminfo:
                if line.startswith("MemTotal:"):
                    if unit == "KB":
                        return int(line.split()[1])
                    elif unit == "MB":
                        return int(line.split()[1]) / 1024
                    elif unit == "GB":
                        return int(line.split()[1]) / 1024 / 1024
                    elif unit == "bytes":
                        return int(line.split()[1]) * 1024
    except FileNotFoundError:
        return 0
    return 0


def wrap_lines(lines: list, width: int) -> list:
    return [wrapped for line in lines for wrapped in textwrap.wrap(line, width)]


def match_filename(cut_filename: str, full_filenames: list) -> str | None:
    cut_lower = cut_filename.lower()
    matches = [
        path
        for path in full_filenames
        if os.path.basename(path).lower().startswith(cut_lower)
    ]
    return matches[0] if len(matches) == 1 else None


class Elevator:
    def __init__(self):
        self.proc = None
        self.secret = secrets.token_hex(32)
        self.script_path = None

    @property
    def spawned(self) -> bool:
        return self.proc != None

    def _make_server_script(self):
        rand = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        self.script_path = Path(tempfile.gettempdir()) / f"elevator.{rand}.py"
        code = f"""#!/usr/bin/env python3
import os
import sys
from time import sleep
import signal
import subprocess

PARENT_PID = os.getppid()

def parent_is_alive() -> bool:
    try:
        os.kill(PARENT_PID, 0)
        return True
    except ProcessLookupError:
        return False

# Background watcher
import threading
def watchdog() -> None:
    while True:
        if not parent_is_alive():
            sys.exit(0)
        sleep(1)

threading.Thread(target=watchdog, daemon=True).start()

try:
    os.unlink(__file__)
except Exception as e:
    pass

AUTHED = False
SECRET = {repr(self.secret)}

def readline():
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    return line.strip()

while True:
    try:
        line = readline()
        if not AUTHED:
            if line == SECRET:
                AUTHED = True
                print("[[AUTH_OK]]")
                sys.stdout.flush()
            else:
                print("[[AUTH_FAIL]]")
                sys.stdout.flush()
                sys.exit(1)
            continue

        proc2 = subprocess.Popen(
            line,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # forward each line immediately
        for out in proc2.stdout:
            print(out, end='', flush=True)
        proc2.wait()
        # end-of-command marker
        print("[[EOC]]", flush=True)
    except Exception as e:
        print(f"ERR: {{e}}", file=sys.stderr, flush=True)
        print("[[EOC]]", flush=True)
"""
        self.script_path.write_text(code)
        self.script_path.chmod(0o600)

    def _spawn(self):
        self._make_server_script()
        self.proc = subprocess.Popen(
            ["pkexec", "python3", str(self.script_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # Send auth key
        self.proc.stdin.write(self.secret + "\n")
        self.proc.stdin.flush()
        response = self.proc.stdout.readline().strip()
        if response != "[[AUTH_OK]]":
            self.script_path.unlink()
            self.proc = None  # Cycle keys for security
            self.secret = secrets.token_hex(32)
            self.script_path = None
            raise RuntimeError("Failed to authenticate with authentication elevator.")

    def run(self, cmd: str) -> CommandStream:
        if self.proc is None or self.proc.poll() is not None:
            self._spawn()

        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

        def generator():
            for line in self.proc.stdout:
                if "[[EOC]]" in line:
                    break
                yield line

        return CommandStream(generator(), proc=self.proc)


def cp(src_file, dst_dir, overwrite=True) -> None:
    """
    Copies `src_file` into `dst_dir`, creating directories if needed.

    Parameters:
    - src_file (str or Path): Path to the source file.
    - dst_dir (str or Path): Path to the destination directory.
    - overwrite (bool): If False, raises an error if file exists.

    Raises:
    - FileNotFoundError: If src_file does not exist.
    - FileExistsError: If destination file exists and overwrite is False.
    - OSError: For other I/O errors.
    """
    src_file = Path(src_file)
    dst_dir = Path(dst_dir)

    if not src_file.is_file():
        raise FileNotFoundError(f"Source file does not exist: {src_file}")

    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise OSError(f"Failed to create destination directory: {dst_dir}") from e

    dst_file = dst_dir / src_file.name

    if dst_file.exists() and not overwrite:
        raise FileExistsError(f"Destination file already exists: {dst_file}")

    try:
        shutil.copy2(src_file, dst_file)
    except Exception as e:
        raise OSError(f"Failed to copy file: {src_file} → {dst_file}") from e


def ls(path: str) -> list:
    """
    Lists entries in a directory, returning full Paths.

    Raises:
    - NotADirectoryError if the path is not a directory.
    - FileNotFoundError if the path does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Directory does not exist: {path}")
    if not p.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    return [entry.resolve() for entry in p.iterdir()]


def rm(file_path: str, missing_ok: str = False):
    """
    Removes a single file.

    Parameters:
    - missing_ok (bool): if True, ignore if file does not exist.

    Raises:
    - FileNotFoundError if the file doesn't exist (unless missing_ok=True).
    - IsADirectoryError if it's actually a directory.
    - OSError for other I/O errors.
    """

    f = Path(file_path)
    if not f.exists():
        if missing_ok:
            return
        raise FileNotFoundError(f"File not found: {file_path}")
    if f.is_dir():
        raise IsADirectoryError(f"Expected file but got directory: {file_path}")

    try:
        f.unlink()
    except Exception as e:
        raise OSError(f"Failed to remove file: {file_path}") from e


def rmr(dir_path: str, missing_ok: bool = False):
    """
    Removes a directory and all contents recursively.

    Parameters:
    - missing_ok (bool): if True, ignore if directory doesn't exist.

    Raises:
    - NotADirectoryError if path exists but is not a directory.
    - FileNotFoundError if path is missing (unless missing_ok=True).
    - OSError for other errors.
    """

    d = Path(dir_path)
    if not d.exists():
        if missing_ok:
            return
        raise FileNotFoundError(f"Directory not found: {dir_path}")
    if not d.is_dir():
        raise NotADirectoryError(f"Expected directory but got file: {dir_path}")

    try:
        shutil.rmtree(d)
    except Exception as e:
        raise OSError(f"Failed to remove directory: {dir_path}") from e


def arm64_v9_or_later() -> bool:
    try:
        with open("/proc/cpuinfo") as f:
            lines = f.readlines()
    except OSError:
        return False

    for line in lines:
        if line.lower().startswith("features"):
            features = line.split(":", 1)[1].lower()
            # ARMv9 mandates FEAT_SVE (Scalable Vector Extension)
            return "sve2" in features
    return False

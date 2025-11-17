#
# Copyright 2024 BredOS
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
import sys
import logging
from typing import List, Dict, Any, Optional, Union, Tuple
import traceback
import pyalpm
from pathlib import Path
import shlex
import subprocess

from bredos.utilities import Elevator

logger = logging.getLogger("bredos.packages")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(levelname)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

elevator = Elevator()


class PackageError(Exception):
    pass


class PackageNotFoundError(PackageError):
    pass


class DependencyError(PackageError):
    pass


class PackageOperationError(PackageError):
    pass


def get_handle(root_dir: str = "/", db_path: str = None) -> pyalpm.Handle:
    """Initialize and return a pyalpm Handle with the specified root directory."""
    try:
        if db_path is None:
            db_path = os.path.join(root_dir, "var/lib/pacman")

        handle = pyalpm.Handle(root_dir, db_path)

        # Only set writable attributes
        handle.arch = "auto"
        handle.logfile = os.path.join(root_dir, "var/log/pacman.log")

        return handle
    except pyalpm.error as e:
        error_msg = f"Failed to initialize pyalpm handle: {e}"
        logger.error(error_msg)
        raise PackageOperationError(error_msg)


def register_syncdbs(handle: pyalpm.Handle, repos: List[str] = None) -> List[pyalpm.DB]:
    """Register available repository databases to the pyalpm handle."""
    try:
        if repos is None:
            # Parse repos from pacman.conf to honor system configuration
            conf_path = os.path.join(handle.root, "etc/pacman.conf")
            repos = _parse_repos_from_conf(conf_path)

            # Fallback repos if parsing fails
            if not repos:
                repos = ["core", "extra", "community"]

        syncdbs = []
        for repo in repos:
            db = handle.register_syncdb(repo, pyalpm.SIG_DATABASE)
            syncdbs.append(db)

        return syncdbs
    except pyalpm.error as e:
        error_msg = f"Failed to register sync databases: {e}"
        logger.error(error_msg)
        raise PackageOperationError(error_msg)


def _parse_repos_from_conf(conf_path: str) -> List[str]:
    """Extract repository definitions from pacman.conf without external dependencies."""
    repos = []
    try:
        if not os.path.exists(conf_path):
            return []

        with open(conf_path, "r") as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Sections in pacman.conf are repository names except for [options]
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1]
                    if section != "options":
                        repos.append(section)

        return repos
    except Exception as e:
        logger.warning(f"Failed to parse repositories from {conf_path}: {e}")
        return []


def list_packages(
    installed_only: bool = True, handle: pyalpm.Handle = None, sysroot: str = "/"
) -> List[Dict[str, Any]]:
    """Retrieve structured information about installed or available packages."""
    try:
        needs_cleanup = handle is None
        if handle is None:
            handle = get_handle(sysroot)
            register_syncdbs(handle)

        results = []

        if installed_only:
            # Only scan local database for installed packages
            localdb = handle.get_localdb()

            for pkg in localdb.pkgcache:
                results.append(
                    {
                        "name": pkg.name,
                        "version": pkg.version,
                        "desc": pkg.desc,
                        "size": pkg.isize,
                        "install_date": pkg.installdate,
                        "installed": True,
                    }
                )
        else:
            # Need to scan all sync DBs and match against local DB
            syncdbs = handle.get_syncdbs()
            localdb = handle.get_localdb()
            installed_pkgs = {pkg.name: pkg for pkg in localdb.pkgcache}

            for db in syncdbs:
                for pkg in db.pkgcache:
                    is_installed = pkg.name in installed_pkgs
                    installed_version = (
                        installed_pkgs[pkg.name].version if is_installed else None
                    )

                    results.append(
                        {
                            "name": pkg.name,
                            "version": pkg.version,
                            "desc": pkg.desc,
                            "repo": db.name,
                            "size": pkg.size,
                            "installed": is_installed,
                            "installed_version": installed_version,
                        }
                    )

        # No need to call release - handle is released when it goes out of scope

        return results
    except Exception as e:
        error_msg = f"Failed to list packages: {e}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        raise PackageOperationError(error_msg)


def search_packages(
    terms: Union[str, List[str]], handle: pyalpm.Handle = None, sysroot: str = "/"
) -> List[Dict[str, Any]]:
    """Find packages matching specified search criteria across repositories."""
    try:
        needs_cleanup = handle is None
        if handle is None:
            handle = get_handle(sysroot)
            register_syncdbs(handle)

        syncdbs = handle.get_syncdbs()
        localdb = handle.get_localdb()
        installed_pkgs = {pkg.name: pkg for pkg in localdb.pkgcache}

        results = []
        seen_pkgs = set()

        # Ensure we have a string (not a list)
        if isinstance(terms, list):
            search_term = " ".join(terms) if terms else ""
        else:
            search_term = str(terms)

        # Manual search over all packages instead of using pyalpm's search
        # This is more reliable and gives us more control
        search_lower = search_term.lower()

        for db in syncdbs:
            for pkg in db.pkgcache:
                if pkg.name in seen_pkgs:
                    continue

                # Check name and description for the search term
                name_match = search_lower in pkg.name.lower()
                desc_match = pkg.desc and search_lower in pkg.desc.lower()

                if name_match or desc_match:
                    seen_pkgs.add(pkg.name)
                    is_installed = pkg.name in installed_pkgs
                    installed_version = (
                        installed_pkgs[pkg.name].version if is_installed else None
                    )

                    results.append(
                        {
                            "name": pkg.name,
                            "version": pkg.version,
                            "desc": pkg.desc,
                            "repo": db.name,
                            "size": pkg.size,
                            "installed": is_installed,
                            "installed_version": installed_version,
                        }
                    )

        return results
    except Exception as e:
        error_msg = f"Failed to search for packages: {e}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        raise PackageOperationError(error_msg)


def get_package_info(
    package_name: str, handle: pyalpm.Handle = None, sysroot: str = "/"
) -> Dict[str, Any]:
    """Retrieve comprehensive package metadata from local or remote repositories."""
    try:
        needs_cleanup = handle is None
        if handle is None:
            handle = get_handle(sysroot)
            register_syncdbs(handle)

        # Check local DB first as it's faster for installed packages
        localdb = handle.get_localdb()
        pkg = localdb.get_pkg(package_name)

        if pkg:
            # Local packages have installation metadata
            info = {
                "name": pkg.name,
                "version": pkg.version,
                "desc": pkg.desc,
                "url": pkg.url,
                "licenses": pkg.licenses,
                "groups": pkg.groups,
                "size": pkg.size,
                "isize": pkg.isize,
                "build_date": pkg.builddate,
                "install_date": pkg.installdate,
                "packager": pkg.packager,
                "arch": pkg.arch,
                "installed": True,
                "dependencies": [dep.name for dep in pkg.depends],
                "optdepends": [f"{dep.name}: {dep.desc}" for dep in pkg.optdepends],
                "provides": [prov.name for prov in pkg.provides],
                "conflicts": [conf.name for conf in pkg.conflicts],
                "replaces": [repl.name for repl in pkg.replaces],
                "backup_files": [(path, md5) for path, md5 in pkg.backup],
            }
        else:
            # Try to find package in sync DBs
            syncdbs = handle.get_syncdbs()
            pkg = None
            for db in syncdbs:
                pkg = db.get_pkg(package_name)
                if pkg:
                    break

            if not pkg:
                # No need to call release - handle is released when it goes out of scope
                raise PackageNotFoundError(f"Package '{package_name}' not found")

            # Remote packages lack installation-specific fields
            info = {
                "name": pkg.name,
                "version": pkg.version,
                "desc": pkg.desc,
                "url": pkg.url,
                "licenses": pkg.licenses,
                "groups": pkg.groups,
                "repo": db.name,
                "size": pkg.size,
                "build_date": pkg.builddate,
                "packager": pkg.packager,
                "arch": pkg.arch,
                "installed": False,
                "dependencies": [dep.name for dep in pkg.depends],
                "optdepends": [f"{dep.name}: {dep.desc}" for dep in pkg.optdepends],
                "provides": [prov.name for prov in pkg.provides],
                "conflicts": [conf.name for conf in pkg.conflicts],
                "replaces": [repl.name for repl in pkg.replaces],
            }

        # No need to call release - handle is released when it goes out of scope

        return info
    except PackageNotFoundError:
        raise
    except Exception as e:
        error_msg = f"Failed to get package information: {e}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        raise PackageOperationError(error_msg)


def install_packages(
    packages: List[str],
    handle: pyalpm.Handle = None,
    sysroot: str = "/",
    no_confirm: bool = False,
    needed_only: bool = False,
    force: bool = False,
) -> bool:
    """Deploy new packages to the system with conflict resolution and dependency handling."""
    try:
        # Build pacman command with appropriate options
        cmd_parts = ["pacman", "-S"]

        if no_confirm:
            cmd_parts.append("--noconfirm")

        if needed_only:
            cmd_parts.append("--needed")

        if force:
            cmd_parts.append("-dd")

        if sysroot and sysroot != "/":
            cmd_parts.extend(["--sysroot", sysroot])

        cmd_parts.extend(packages)

        # Format command for elevator
        cmd = " ".join(shlex.quote(part) for part in cmd_parts)

        logger.debug(f"Running command: {cmd}")

        # Use elevator to run the command with elevated privileges
        try:
            proc = elevator.run(cmd)

            # Read output safely
            output = []
            try:
                # Read the output line by line instead of iterating directly
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    output.append(line)
            except KeyboardInterrupt:
                logger.warning("Installation interrupted by user")
                try:
                    proc.kill()
                except:
                    pass
                raise PackageOperationError("Package installation was interrupted")

            # Wait for process to complete
            proc.wait()

            # Join output lines
            output_text = "".join(output)

            if proc.returncode != 0:
                # Handle package not found errors specifically
                if "target not found" in output_text:
                    missing_pkgs = []
                    for line in output_text.splitlines():
                        if "target not found:" in line:
                            missing_pkgs.append(line.split(":", 1)[1].strip())

                    if missing_pkgs:
                        raise PackageNotFoundError(
                            f"Package(s) not found: {', '.join(missing_pkgs)}"
                        )

                raise PackageOperationError(
                    f"Failed to install packages: {output_text}"
                )

            return True

        except KeyboardInterrupt:
            # Handle user interruption gracefully
            logger.warning("Installation interrupted by user")
            raise PackageOperationError("Package installation was interrupted")

    except PackageNotFoundError:
        raise
    except PackageOperationError:
        raise
    except Exception as e:
        error_msg = f"Failed to install packages: {e}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        raise PackageOperationError(error_msg)


def remove_packages(
    packages: List[str],
    handle: pyalpm.Handle = None,
    sysroot: str = "/",
    no_confirm: bool = False,
    remove_deps: bool = False,
    force: bool = False,
) -> bool:
    """Uninstall packages with optional dependency cleanup and verification."""
    try:
        # Verify packages are installed unless force is specified
        if not force:
            needs_cleanup = handle is None
            if handle is None:
                handle = get_handle(sysroot)

            localdb = handle.get_localdb()
            not_installed = []

            for pkg_name in packages:
                if not localdb.get_pkg(pkg_name):
                    not_installed.append(pkg_name)

            # No need to call release - handle is released when it goes out of scope

            if not_installed:
                raise PackageNotFoundError(
                    f"The following packages are not installed: {', '.join(not_installed)}"
                )

        # Build pacman command with appropriate options
        cmd_parts = ["pacman", "-R"]

        if no_confirm:
            cmd_parts.append("--noconfirm")

        if remove_deps:
            cmd_parts.append("-s")

        if force:
            cmd_parts.append("-dd")

        if sysroot and sysroot != "/":
            cmd_parts.extend(["--sysroot", sysroot])

        cmd_parts.extend(packages)

        # Format command for elevator
        cmd = " ".join(shlex.quote(part) for part in cmd_parts)

        logger.debug(f"Running command: {cmd}")

        # Use elevator to run the command with elevated privileges
        try:
            proc = elevator.run(cmd)

            # Read output safely
            output = []
            try:
                # Read the output line by line instead of iterating directly
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    output.append(line)
            except KeyboardInterrupt:
                logger.warning("Package removal interrupted by user")
                try:
                    proc.kill()
                except:
                    pass
                raise PackageOperationError("Package removal was interrupted")

            # Wait for process to complete
            proc.wait()

            # Join output lines
            output_text = "".join(output)

            if proc.returncode != 0:
                raise PackageOperationError(f"Failed to remove packages: {output_text}")

            return True

        except KeyboardInterrupt:
            # Handle user interruption gracefully
            logger.warning("Package removal interrupted by user")
            raise PackageOperationError("Package removal was interrupted")

    except PackageNotFoundError:
        raise
    except PackageOperationError:
        raise
    except Exception as e:
        error_msg = f"Failed to remove packages: {e}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        raise PackageOperationError(error_msg)


def update_system(
    handle: pyalpm.Handle = None,
    sysroot: str = "/",
    no_confirm: bool = False,
    force: bool = False,
) -> bool:
    """Upgrade all packages to their latest available versions."""
    try:
        # Build pacman command with appropriate options
        cmd_parts = ["pacman", "-Syu"]

        if no_confirm:
            cmd_parts.append("--noconfirm")

        if force:
            cmd_parts.append("-dd")

        if sysroot and sysroot != "/":
            cmd_parts.extend(["--sysroot", sysroot])

        # Format command for elevator
        cmd = " ".join(shlex.quote(part) for part in cmd_parts)

        logger.debug(f"Running command: {cmd}")

        # Use elevator to run the command with elevated privileges
        try:
            proc = elevator.run(cmd)

            # Read output safely
            output = []
            try:
                # Read the output line by line instead of iterating directly
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    output.append(line)
            except KeyboardInterrupt:
                logger.warning("System update interrupted by user")
                try:
                    proc.kill()
                except:
                    pass
                raise PackageOperationError("System update was interrupted")

            # Wait for process to complete
            proc.wait()

            # Join output lines
            output_text = "".join(output)

            if proc.returncode != 0:
                raise PackageOperationError(f"Failed to update system: {output_text}")

            return True

        except KeyboardInterrupt:
            # Handle user interruption gracefully
            logger.warning("System update interrupted by user")
            raise PackageOperationError("System update was interrupted")

    except Exception as e:
        error_msg = f"Failed to update system: {e}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        raise PackageOperationError(error_msg)


def refresh_databases(
    handle: pyalpm.Handle = None, sysroot: str = "/", force: bool = False
) -> bool:
    """Update package database information without installing packages."""
    try:
        # Build pacman command with appropriate options
        cmd_parts = ["pacman", "-Sy"] if not force else ["pacman", "-Syy"]

        if sysroot and sysroot != "/":
            cmd_parts.extend(["--sysroot", sysroot])

        # Format command for elevator
        cmd = " ".join(shlex.quote(part) for part in cmd_parts)

        logger.debug(f"Running command: {cmd}")

        # Use elevator to run the command with elevated privileges
        try:
            proc = elevator.run(cmd)

            # Read output safely
            output = []
            try:
                # Read the output line by line instead of iterating directly
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    output.append(line)
            except KeyboardInterrupt:
                logger.warning("Database refresh interrupted by user")
                try:
                    proc.kill()
                except:
                    pass
                raise PackageOperationError("Database refresh was interrupted")

            # Wait for process to complete
            proc.wait()

            # Join output lines
            output_text = "".join(output)

            if proc.returncode != 0:
                raise PackageOperationError(
                    f"Failed to refresh databases: {output_text}"
                )

            return True

        except KeyboardInterrupt:
            # Handle user interruption gracefully
            logger.warning("Database refresh interrupted by user")
            raise PackageOperationError("Database refresh was interrupted")

    except Exception as e:
        error_msg = f"Failed to refresh databases: {e}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        raise PackageOperationError(error_msg)


def is_package_installed(
    package_name: str, handle: pyalpm.Handle = None, sysroot: str = "/"
) -> bool:
    """Verify package installation state efficiently without exceptions."""
    try:
        needs_cleanup = handle is None
        if handle is None:
            handle = get_handle(sysroot)

        localdb = handle.get_localdb()
        is_installed = localdb.get_pkg(package_name) is not None

        # No need to call release - handle is released when it goes out of scope

        return is_installed
    except Exception as e:
        # Silent failures for this query method
        logger.debug(f"Error checking if package is installed: {e}")
        return False


def get_available_updates(
    handle: pyalpm.Handle = None, sysroot: str = "/"
) -> List[Dict[str, Any]]:
    """Identify packages with newer versions available in repositories."""
    try:
        needs_cleanup = handle is None
        if handle is None:
            handle = get_handle(sysroot)
            register_syncdbs(handle)

        localdb = handle.get_localdb()
        syncdbs = handle.get_syncdbs()

        updates = []

        # For each installed package, check if a newer version exists
        for local_pkg in localdb.pkgcache:
            for db in syncdbs:
                sync_pkg = db.get_pkg(local_pkg.name)
                if sync_pkg and sync_pkg.version != local_pkg.version:
                    updates.append(
                        {
                            "name": local_pkg.name,
                            "current_version": local_pkg.version,
                            "new_version": sync_pkg.version,
                            "repo": db.name,
                        }
                    )
                    break

        # No need to call release - handle is released when it goes out of scope

        return updates
    except Exception as e:
        error_msg = f"Failed to get available updates: {e}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        raise PackageOperationError(error_msg)

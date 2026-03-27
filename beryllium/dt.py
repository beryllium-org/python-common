import os
import re
import shlex
import hashlib
import subprocess
from glob import glob
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

dtcache = {}
DTB_PATH = None
PROC_DT = Path("/proc/device-tree")

candidates = ["/usr/lib/modules/*/dtbs", "/usr/lib/modules/*/dtb", "/boot/dtbs"]


for pattern in candidates:
    matches = sorted(glob(pattern))
    for path in matches:
        if os.path.isdir(path):
            DTB_PATH = Path(path)


def force_quote(val: int | str) -> str:
    if isinstance(val, int):
        return str(val)
    return "'" + str(val).replace("'", "'\"'\"'") + "'"


def parse_uboot() -> dict:
    config = {"U_BOOT_IS_SETUP": "false", "U_BOOT_PARAMETERS": "splash quiet"}
    try:
        with open("/etc/default/u-boot") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    try:
                        val = shlex.split(val, posix=True)
                        val = val[0] if len(val) == 1 else val
                        if isinstance(val, list):
                            for i in range(len(val)):
                                if val[i].isdigit():
                                    try:
                                        val[i] = int(val[i])
                                    except:
                                        pass
                        elif isinstance(val, str):
                            if val.isdigit():
                                try:
                                    val = int(val)
                                except:
                                    pass
                        config[key] = val
                    except ValueError:
                        config[key] = val.strip()
    except:
        pass
    return config


def encode_uboot(config: dict) -> str:
    lines = [
        "## /etc/default/u-boot - configuration file",
    ]
    for key, val in config.items():
        if isinstance(val, list):
            # Join multi-word values if they were stored as list
            val_str = " ".join(val)
        else:
            val_str = val

        quoted_val = force_quote(val_str)
        lines.append(f"{key}={quoted_val}")
    return "\n".join(lines)


def parse_grub() -> dict:
    config = {}
    with open("/etc/default/grub") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                try:
                    val = shlex.split(val, posix=True)
                    val = val[0] if len(val) == 1 else val
                    if isinstance(val, list):
                        for i in range(len(val)):
                            if val[i].isdigit():
                                try:
                                    val[i] = int(val[i])
                                except:
                                    pass
                    elif isinstance(val, str):
                        if val.isdigit():
                            try:
                                val = int(val)
                            except:
                                pass
                    config[key] = val
                except ValueError:
                    config[key] = val.strip()
    return config


def encode_grub(config: dict) -> str:
    lines = [
        "## /etc/default/grub - configuration file",
    ]
    for key, val in config.items():
        if isinstance(val, list):
            # Join multi-word values if they were stored as list
            val_str = " ".join(val)
        else:
            val_str = val

        quoted_val = force_quote(val_str)
        lines.append(f"{key}={quoted_val}")
    return "\n".join(lines)


def parse_extlinux_conf(source) -> dict:
    if hasattr(source, "read"):
        lines = source.read().splitlines()
    else:
        lines = source.splitlines()

    config = {"global": {}, "labels": {}}

    current_label = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.lower().startswith("label "):
            current_label = line[6:].strip()
            config["labels"][current_label] = {}
            continue

        key_value = line.split(None, 1)
        if len(key_value) == 2:
            key, value = key_value
            key = key.lower()
            value = value.strip()

            if key == "fdtoverlays":
                value = value.split()

            if current_label:
                config["labels"][current_label][key] = value
            else:
                config["global"][key] = value
        else:
            key = key_value[0].lower()
            if current_label:
                config["labels"][current_label][key] = None
            else:
                config["global"][key] = None

    return config


def serialize_extlinux_conf(config: dict) -> str:
    lines = []

    for key, value in config.get("global", {}).items():
        if value is None:
            lines.append(key.upper())
        else:
            lines.append(f"{key.upper()} {value}")

    if lines:
        lines.append("")

    for label, directives in config.get("labels", {}).items():
        lines.append(f"LABEL {label}")
        for key, value in directives.items():
            if value is None:
                lines.append(f"    {key.upper()}")
            elif key == "fdtoverlays" and isinstance(value, list):
                joined = " ".join(value)
                lines.append(f"    {key.upper()} {joined}")
            else:
                lines.append(f"    {key.upper()} {value}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _extract_info_wrapper(path_str: str, kind: str) -> tuple[str, str, dict] | None:
    path = Path(path_str)
    result = extract_dtb_info(path)
    if result:
        return (path_str, kind, result)
    return None


def gencache() -> dict:
    global dtcache
    res = {"base": {}, "overlays": {}}

    try:
        base_files = list(DTB_PATH.rglob("*.dtb"))
        overlay_files = list(DTB_PATH.rglob("*.dtbo"))

        all_files = [(str(path), "base") for path in base_files] + [
            (str(path), "overlays") for path in overlay_files
        ]

        with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = {
                executor.submit(_extract_info_wrapper, path, kind): (path, kind)
                for path, kind in all_files
                if path not in dtcache  # skip already cached paths
            }

            for future in as_completed(futures):
                result = future.result()
                if result:
                    path_str, kind, data = result
                    dtcache[path_str] = data
                    res[kind][path_str] = data

        # Also fill `res` from preexisting dtcache
        for path_str, data in dtcache.items():
            if path_str.endswith(".dtb"):
                res["base"][path_str] = data
            elif path_str.endswith(".dtbo"):
                res["overlays"][path_str] = data

    except KeyboardInterrupt:
        pass
    except Exception:
        pass

    return res


def detect_live() -> tuple:
    live_dts = fdt_hash_from_proc()
    if live_dts is None:
        return None, "Could not read live FDT"

    live_dts_str = live_dts.decode()
    live_hash = hash_str(live_dts_str)
    candidates = list(DTB_PATH.rglob("*.dtb"))

    best_match = None
    best_dts = None
    overlay_diff = []
    min_diff = float("inf")

    with ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(dt_process_candidate, dtb, live_hash): dtb
            for dtb in candidates
        }

        for future in as_completed(futures):
            result = future.result()
            if result is None:
                continue
            dtb_relpath, candidate_hash, candidate_dts = result
            if candidate_hash == live_hash:
                return dtb_relpath, []
            else:
                diff_len = len(diff_dts(candidate_dts, live_dts_str))
                if diff_len < min_diff:
                    min_diff = diff_len
                    best_match = dtb_relpath
                    best_dts = candidate_dts

    if best_dts:
        overlay_diff = diff_dts(best_dts, live_dts_str)
        return best_match, overlay_diff

    return None, "No match found"


def identify_base_dtb() -> tuple | None:
    live_dts = fdt_hash_from_proc()
    if live_dts is None:
        return None, "Failed to read live FDT"

    live_hash = hash_str(live_dts.decode())

    candidates = list(DTB_PATH.rglob("*.dtb"))
    matches = []
    for dtb in candidates:
        dts = dtb_to_dts(dtb)
        if dts is None:
            continue
        if hash_str(dts) == live_hash:
            matches.append(dtb.relative_to(DTB_PATH))

    if matches:
        return matches[0], None
    else:
        return None, "No exact match found (overlays likely applied)"


# FIXME: Use /proc/mounts instead
def detect_efidir() -> str | None:
    try:
        df_output = subprocess.check_output(["df"], text=True)
    except subprocess.CalledProcessError:
        return None

    boot_mounts = set()
    for line in df_output.splitlines()[1:]:  # Skip header
        parts = line.split()
        if len(parts) < 6:
            continue
        mount_point = parts[5]
        if mount_point.startswith("/boot"):
            boot_mounts.add(mount_point)

    if "/boot/efi" in boot_mounts:
        return "/boot/efi"
    elif "/boot" in boot_mounts:
        return "/boot"
    else:
        return None


def identify_overlays() -> list:
    res = []
    if booted_with_edk():
        efi = detect_efidir()
        if efi is None:
            raise OSError("Failed to identify EFI Directory")

        overlays_path = Path(efi) / "dtb" / "overlays"
        if not overlays_path.exists() or not overlays_path.is_dir():
            return res  # No overlays directory found

        try:
            for dtbo in overlays_path.rglob("*.dtbo"):
                # Sanity check: only real files, not broken symlinks, etc.
                if dtbo.is_file() and not dtbo.is_symlink():
                    dtbof = str(dtbo.resolve(strict=True))
                    dtbof = dtbof[dtbof.rfind("/") + 1 :]
                    res.append(dtbof)
        except:
            pass
    else:
        ubootcfg = parse_uboot()
        if ubootcfg["U_BOOT_IS_SETUP"]:
            if "U_BOOT_FDT_OVERLAYS" in ubootcfg:
                res += ubootcfg["U_BOOT_FDT_OVERLAYS"].split(" ")
        elif extlinux_exists():
            extcfg = dt.parse_extlinux_conf(
                Path("/boot/extlinux/extlinux.conf").read_text()
            )
            if "fdtoverlays" in extlinux:
                res += extcfg["fdtoverlays"].split(" ")
    return res


def uefi_overriden() -> bool:
    for path in ("/boot/efi/dtb/base/", "/boot/dtb/base/"):
        try:
            if os.path.isdir(path):
                with os.scandir(path) as entries:
                    if any(entry.is_file() for entry in entries):
                        return True
        except:
            continue
    return False


def diff_dts(base_dts, live_dts) -> list:
    base_lines = set(base_dts.splitlines())
    live_lines = set(live_dts.splitlines())
    return list(live_lines - base_lines)


def dt_process_candidate(dtb_path, live_hash) -> tuple | None:
    dts = dtb_to_dts(dtb_path)
    if dts is None:
        return None
    h = hash_str(dts)
    return (dtb_path.relative_to(DTB_PATH), h, dts)


def safe_exists(path: str) -> bool:
    try:
        real_path = os.path.realpath(path)

        boot_path = os.path.dirname(path)
        if not os.path.isdir(boot_path):
            return False

        return os.path.isfile(real_path)
    except Exception:
        return False


def grub_exists() -> bool:
    return safe_exists("/boot/grub/grub.cfg")


def extlinux_exists() -> bool:
    return safe_exists("/boot/extlinux/extlinux.conf")


def booted_with_edk() -> bool:
    try:
        output = subprocess.check_output(["journalctl", "-b"], text=True)
        lines = output.splitlines()[:20]
        pattern = re.compile(r"efi: EFI v[\d.]+ by .+", re.IGNORECASE)
        return any(pattern.search(line) for line in lines)
    except subprocess.CalledProcessError:
        return False


def dtb_to_yaml(dtb_path: Path) -> dict | None:
    dts = dtb_to_dts(dtb_path)
    if not dts:
        return None

    try:
        yaml_raw = subprocess.check_output(
            ["dtc", "-I", "dts", "-O", "yaml", "-q", "-"],
            input=dts.encode(),
            stderr=subprocess.DEVNULL,
        ).decode()

        parsed = parse_dtc_yaml(yaml_raw)
        return parsed
    except subprocess.CalledProcessError:
        return None


def _no_brackets(key: str) -> str:
    return (
        key[1:-1]
        if (key.startswith('"') and key.endswith('"'))
        or (key.startswith("'") and key.endswith("'"))
        else key
    )


def _flatten(obj):
    """
    Recursively collapse any [ [ ... ] ] -> [ ... ] single-element lists of lists.
    """
    if isinstance(obj, dict):
        return {k: _flatten(v) for k, v in obj.items()}
    if isinstance(obj, list):
        lst = [_flatten(v) for v in obj]
        # if it's a single-element list whose only element is itself a list, unwrap:
        if len(lst) == 1 and isinstance(lst[0], list):
            return lst[0]
        return lst
    return obj


def parse_dtc_yaml(data: str) -> dict:
    root: dict = {}
    stack = [root]
    indents = [0]
    last_keys = [None]  # track last key in each dict for list appends

    for line in data.splitlines():
        raw = line.rstrip().rstrip(";")  # strip trailing semicolon
        stripped = raw.lstrip()
        if not stripped or stripped in ("---", "...") or stripped.startswith("#"):
            continue

        indent = len(line) - len(stripped)

        # pop back up when dedenting
        while indent < indents[-1]:
            stack.pop()
            indents.pop()
            last_keys.pop()

        container = stack[-1]

        # list entry?
        if stripped.startswith("- "):
            entry = stripped[2:].strip()
            # split "key: val" in a flow list?
            if ":" in entry and not entry.startswith('"'):
                # e.g. - compatible: [...]
                key, val = entry.split(":", 1)
                key = key.strip().strip('"')
                val = _parse_scalar(val.strip())
                container.setdefault(key, []).append(val)
            else:
                # plain list item under last_keys[-1]
                lk = last_keys[-1]
                if lk is None:
                    continue
                val = _parse_scalar(entry)
                lst = container.setdefault(lk, [])
                if not isinstance(lst, list):
                    container[lk] = lst = [lst]
                lst.append(val)
            continue

        # key: value or key:
        if ":" in stripped:
            key, rest = stripped.split(":", 1)
            key = key.strip().strip('"')
            val_str = rest.strip()
            if val_str == "":
                # new nested mapping
                new_map: dict = {}
                container[_no_brackets(key)] = new_map
                stack.append(new_map)
                indents.append(indent)
                last_keys.append(None)
            else:
                val = _parse_scalar(val_str)
                container[_no_brackets(key)] = val
                last_keys[-1] = key

    return _flatten(root)


def _parse_scalar(val: str):
    val = val.strip()

    # remove surrounding quotes
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]

    # boolean
    if val.lower() in ("true", "false"):
        return val.lower() == "true"

    # flow list (possibly broken or multiline)
    if val.startswith("["):
        inner = val[1:]
        if inner.endswith("]"):
            inner = inner[:-1]

        # remove trailing commas or semicolons from inner list
        inner = inner.strip().rstrip(",;")

        if not inner:
            return []

        # Regex match quoted or unquoted tokens (handles broken dtc lists too)
        items = []
        for m in re.finditer(r'"([^"]*)"|([^,\s\]]+)', inner):
            token = m.group(1) if m.group(1) is not None else m.group(2)
            token = token.strip().rstrip(",")
            items.append(_parse_scalar(token))
        return items

    # numeric
    try:
        if "." in val:
            return float(val)
        return int(val, 0)
    except ValueError:
        return val


def extract_dtb_info(dtb_path: Path) -> dict | None:
    global dtcache

    path_str = str(dtb_path)
    if path_str in dtcache:
        return dtcache[path_str]

    tree = dtb_to_yaml(dtb_path)
    if not tree:
        return None

    name = dtb_path.stem
    description = tree.get("model", "")
    if isinstance(description, list):
        description = " ".join(description)
    compatible = tree.get("compatible", [])

    res = {
        "name": name,
        "description": description,
        "compatible": compatible,
    }

    dtcache[path_str] = res
    return res


def dtb_to_dts(dtb_path) -> str | None:
    try:
        res = subprocess.check_output(
            ["dtc", "-I", "dtb", "-O", "dts", "-q", str(dtb_path)],
            stderr=subprocess.DEVNULL,
        ).decode()

        return res
    except subprocess.CalledProcessError:
        return None


def fdt_hash_from_proc() -> str | None:
    try:
        return subprocess.check_output(
            ["dtc", "-I", "fs", "-O", "dts", "/proc/device-tree"],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None


def hash_str(data):
    return hashlib.sha256(data.encode()).hexdigest()

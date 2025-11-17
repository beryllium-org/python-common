import time, curses, textwrap, sys
import termios, tty, os

stdscr = None
NOCONFIRM = False
DRYRUN = False
APP_NAME = "BredOS"
enabled = False

# Theming, update from app
primary = 166  # ANSI 256 Colors
primary_fallback = 7  # TTY 8 Colors
secondary = 166  # ANSI 256 Colors
secondary_fallback = 7  # TTY 8 Colors
background = None  # ANSI 256 Colors
background_fallback = 0  # ANSI 8 Colors

# Color pair indexes
PRIMARY_PAIR = 10
SECONDARY_PAIR = 11
BACKGROUND_PAIR = 12


# Primary colors follow ANSI conventions.
# Follow: https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797#256-colors

# Fallback colors apply in TTY and other sus terminals.
# 0 - Black
# 1 - Green
# 2 - White
# 3 - Blue
# 4 - Magenta
# 5 - Yellow
# 6 - Cyan
# 7 - Red


def load_colors() -> None:
    global stdscr
    if primary is not None and not isinstance(primary, int):
        raise TypeError("Primary color must be an int (0-255)")
    if not isinstance(primary_fallback, int):
        raise TypeError("Primary fallback color must be an int (0-7)")
    if secondary is not None and not isinstance(secondary, int):
        raise TypeError("Secondary color must be an int (0-255)")
    if not isinstance(secondary_fallback, int):
        raise TypeError("Secondary fallback color must be an int (0-7)")
    if background is not None and not isinstance(background, int):
        raise TypeError("Background color must be an int (0-255)")
    if not isinstance(background_fallback, int):
        raise TypeError("Background fallback color must be an int (0-7)")

    def ttycolor(cid: int):
        if cid == 0:
            return curses.COLOR_BLACK
        elif cid == 1:
            return curses.COLOR_GREEN
        elif cid == 2:
            return curses.COLOR_WHITE
        elif cid == 3:
            return curses.COLOR_BLUE
        elif cid == 4:
            return curses.COLOR_MAGENTA
        elif cid == 5:
            return curses.COLOR_YELLOW
        elif cid == 6:
            return curses.COLOR_CYAN
        else:
            return curses.COLOR_RED

    curses.start_color()
    supports_default_colors = False
    supports_256_colors = False

    try:
        curses.use_default_colors()
        # Test if -1 is actually supported
        try:
            curses.init_pair(100, curses.COLOR_WHITE, -1)  # Test pair
            supports_default_colors = True
        except:
            # -1 is not actually supported despite use_default_colors() succeeding
            supports_default_colors = False

        max_colors = curses.COLORS
        if max_colors >= 256:
            supports_256_colors = True
    except curses.error:
        # Fallback: terminal doesn't support default colors
        max_colors = 8

    # Initialize basic color pairs
    for i in range(min(max_colors, 8)):
        # Foreground i, background default (-1) or black (0)
        bg = -1 if supports_default_colors else 0
        try:
            curses.init_pair(i + 1, i, bg)
        except:
            # If we get an error, try with bg=0 even if we thought default colors were supported
            if supports_default_colors:
                try:
                    curses.init_pair(i + 1, i, 0)
                except:
                    pass
            pass  # Ignore errors if fewer colors supported

    # Setup primary color
    try:
        if supports_256_colors and primary is not None:
            curses.init_pair(
                PRIMARY_PAIR, primary, -1 if supports_default_colors else 0
            )
        else:
            curses.init_pair(
                PRIMARY_PAIR,
                ttycolor(primary_fallback),
                -1 if supports_default_colors else 0,
            )
    except:
        # Fallback to a safe color
        try:
            curses.init_pair(
                PRIMARY_PAIR, curses.COLOR_WHITE, -1 if supports_default_colors else 0
            )
        except:
            pass

    # Setup secondary color
    try:
        if supports_256_colors and secondary is not None:
            curses.init_pair(
                SECONDARY_PAIR, secondary, -1 if supports_default_colors else 0
            )
        else:
            curses.init_pair(
                SECONDARY_PAIR,
                ttycolor(secondary_fallback),
                -1 if supports_default_colors else 0,
            )
    except:
        # Fallback to a safe color
        try:
            curses.init_pair(
                SECONDARY_PAIR, curses.COLOR_CYAN, -1 if supports_default_colors else 0
            )
        except:
            pass

    # Setup background color
    bg_color = -1 if supports_default_colors else 0
    fg_color = curses.COLOR_WHITE  # Default foreground

    try:
        if supports_256_colors and background is not None:
            bg_color = background
            curses.init_pair(BACKGROUND_PAIR, fg_color, bg_color)
        else:
            bg_color = ttycolor(background_fallback)
            curses.init_pair(BACKGROUND_PAIR, fg_color, bg_color)
    except:
        try:
            curses.init_pair(BACKGROUND_PAIR, fg_color, 0)  # Black background fallback
        except:
            pass

    # Apply the background color
    stdscr.bkgd(" ", curses.color_pair(PRIMARY_PAIR))


def detect_pos(timeout=0.3) -> list:
    """
    Detect cursor position. Returns [row, col].
    Works in interactive POSIX terminals.

    BeOS CircuitPython code ported for desktop Python.
    Will work even in hell.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[6n")
        sys.stdout.flush()

        buf = ""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if os.read(fd, 1) == b"\x1b":
                if os.read(fd, 1) == b"[":
                    while True:
                        ch = os.read(fd, 1).decode()
                        buf += ch
                        if ch == "R":
                            break
                    break
        if buf:
            buf = buf.rstrip("R")
            rows, cols = map(int, buf.split(";"))
            return [rows, cols]
    except Exception:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return [0, 0]


def detect_size(timeout=0.3) -> list:
    """
    Detect terminal size by moving cursor to bottom-right and querying position.
    Returns [rows, cols] or None if failed.

    BeOS CircuitPython code ported for desktop Python.
    Will work even in hell.
    """
    res = [24, 80]
    cur = [0, 0]
    delay = False
    while True:
        if cur == res:
            return res
        elif delay:
            time.sleep(0.005)
        else:
            delay = True
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            # Save position
            sys.stdout.write("\x1b[s")
            # Move cursor to huge position
            sys.stdout.write("\x1b[999;999H")
            # Request position
            sys.stdout.write("\x1b[6n")
            sys.stdout.flush()

            buf = ""
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                if os.read(fd, 1) == b"\x1b":
                    if os.read(fd, 1) == b"[":
                        while True:
                            ch = os.read(fd, 1).decode()
                            buf += ch
                            if ch == "R":
                                break
                        break
            # Restore cursor
            sys.stdout.write("\x1b[u")
            sys.stdout.flush()

            if buf:
                buf = buf.rstrip("R")
                rows, cols = map(int, buf.split(";"))
                res = cur.copy()
                cur.clear()
                cur += [rows, cols]
                continue
        except Exception:
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        cur = [24, 80]


def lw(text: list, width: int = None) -> list:
    if width is None:
        width, _ = detect_size()

    return [
        wrapped
        for subline in text
        for wrapped in (textwrap.wrap(subline, width) or [""])
    ]


def _calculate_layout(maxx, sidebar):
    """Calculate layout dimensions based on whether sidebar is present."""
    if sidebar is None:
        return 2, maxx - 4, 0  # content_x, content_width, sidebar_width

    # Calculate sidebar width based on longest item
    max_item_len = max(len(item) for item in sidebar.keys()) if sidebar else 0
    sidebar_width = max(max_item_len + 8, 15)  # "- [x] " + text + padding

    content_x = sidebar_width + 3  # sidebar + border + padding
    content_width = maxx - content_x - 2  # remaining space minus border

    return content_x, content_width, sidebar_width


def _draw_sidebar(stdscr, sidebar, sidebar_width, maxx, maxy):
    """Draw the sidebar with items and checkboxes."""
    if sidebar is None:
        return

    # Draw vertical separator
    for y in range(3, maxy - 1):
        stdscr.addch(y, sidebar_width + 1, "│", curses.color_pair(SECONDARY_PAIR))

    # Draw horizontal separator line under title
    stdscr.addch(2, 0, "├", curses.color_pair(SECONDARY_PAIR))
    stdscr.addch(2, maxx - 1, "┤", curses.color_pair(SECONDARY_PAIR))
    stdscr.addch(y + 1, sidebar_width + 1, "┴", curses.color_pair(SECONDARY_PAIR))
    separator_line = "─" * (maxx - 2)
    stdscr.addstr(2, 1, separator_line, curses.color_pair(SECONDARY_PAIR))
    stdscr.addch(2, sidebar_width + 1, "┬", curses.color_pair(SECONDARY_PAIR))

    # Draw sidebar items
    y = 3
    for item, checked in sidebar.items():
        if y >= maxy - 2:  # Don't draw beyond available space
            break
        sidebar_text = f"- [ ] {item}"
        stdscr.addstr(y, 2, sidebar_text[: sidebar_width - 2])
        if checked:
            stdscr.addch(y, 5, "x", curses.color_pair(SECONDARY_PAIR))
        y += 1


def message(
    text: list, label: str = None, prompt: bool = True, sidebar: dict = None
) -> None:
    if label is None:
        label = APP_NAME
    if stdscr is None:
        for line in text:
            print(line)
        return

    ok = False
    while True:
        try:
            text = [subline for line in text for subline in line.split("\n")]
            cached = [0, 0]
            content_x = None
            content_width = None
            sidebar_width = None
            content_height = None
            scroll = 0
            while True:
                maxy, maxx = detect_size()
                if [maxy, maxx] != cached:
                    cached = [maxy, maxx]
                    # Calculate layout
                    content_x, content_width, sidebar_width = _calculate_layout(
                        maxx, sidebar
                    )
                    content_height = maxy - 5  # borders + label + prompt

                    try:
                        text = lw(text, content_width)
                        scroll = 0

                        stdscr.clear()
                        stdscr.addstr(
                            1,
                            2,
                            label + (" (DRYRUN)" if DRYRUN else ""),
                            curses.A_BOLD | curses.A_UNDERLINE,
                        )
                    except:
                        cached = [0, 0]
                        continue

                try:
                    for i in range(content_height):
                        clear_line(3 + i)

                    visible_lines = text[scroll : scroll + content_height]
                    for i, line in enumerate(visible_lines):
                        stdscr.addstr(3 + i, content_x, line[:content_width])

                    if not prompt:
                        draw_border()
                        _draw_sidebar(stdscr, sidebar, sidebar_width, maxx, maxy)
                        refresh()
                        return

                    clear_line(maxy - 2)

                    draw_border()
                    _draw_sidebar(stdscr, sidebar, sidebar_width, maxx, maxy)

                    stdscr.attron(curses.A_REVERSE)
                    stdscr.addstr(
                        maxy - 2,
                        content_x,
                        (
                            " SCROLL DOWN --"
                            if scroll + content_height < len(text)
                            else ""
                        )
                        + " Press Enter to continue ",
                    )
                    stdscr.attroff(curses.A_REVERSE)
                    refresh()
                except:
                    cached = [0, 0]
                    break

                key = stdscr.getch()
                if key in (ord("\n"), curses.KEY_ENTER):
                    ok = True
                    break
                elif key in (curses.KEY_DOWN, ord("s"), ord("S")):
                    if scroll + content_height < len(text):
                        scroll += 1
                elif key in (curses.KEY_UP, ord("w"), ord("W")):
                    if scroll > 0:
                        scroll -= 1

            wait_clear()
            if ok:
                return
        except KeyboardInterrupt:
            pass
        except:
            pass


def confirm(
    text: list, label: str = None, sidebar: dict = None, important: bool = True
) -> bool:
    global NOCONFIRM
    if NOCONFIRM:
        return True
    if label is None:
        label = APP_NAME

    if stdscr is None:
        for line in text:
            print(line)
        while True:
            try:
                dat = input("(Y/N)> ")
                if dat in ["y", "Y"]:
                    return True
                elif dat in ["n", "N"]:
                    return False
            except (KeyboardInterrupt, EOFError):
                print()
                return False

    original_text = [subline for line in text for subline in line.split("\n")]

    while True:
        try:
            work_text = original_text.copy()
            cached = [0, 0]
            content_x = None
            content_width = None
            sidebar_width = None
            content_height = None
            scroll = 0
            sel = None

            while True:
                maxy, maxx = detect_size()
                if [maxy, maxx] != cached:
                    clear()
                    cached = [maxy, maxx]
                    content_x, content_width, sidebar_width = _calculate_layout(
                        maxx, sidebar
                    )
                    content_height = maxy - 5

                    try:
                        work_text = lw(work_text, content_width)
                        scroll = 0
                        stdscr.clear()
                        stdscr.addstr(
                            1,
                            2,
                            label + (" (DRYRUN)" if DRYRUN else ""),
                            curses.A_BOLD | curses.A_UNDERLINE,
                        )
                    except:
                        cached = [0, 0]
                        break

                try:
                    for i in range(content_height):
                        clear_line(3 + i)
                    visible_lines = work_text[scroll : scroll + content_height]
                    for i, line in enumerate(visible_lines):
                        stdscr.addstr(3 + i, content_x, line[:content_width])

                    clear_line(maxy - 2)
                    stdscr.attron(curses.A_REVERSE)

                    prompt_line = ""
                    if sel is True:
                        prompt_line = " Confirm (Y/N): Y | "
                    elif sel is False:
                        prompt_line = " Confirm (Y/N): N | "
                    else:
                        prompt_line = " Confirm (Y/N): "

                    if scroll + content_height < len(work_text):
                        prompt_line += " SCROLL DOWN --"

                    if sel is not None:
                        prompt_line += " Press enter to continue "

                    stdscr.addstr(maxy - 2, content_x, prompt_line)
                    stdscr.attroff(curses.A_REVERSE)

                    draw_border()
                    _draw_sidebar(stdscr, sidebar, sidebar_width, maxx, maxy)
                    stdscr.move((maxy - 2), content_x + len(prompt_line))
                    refresh()
                except:
                    cached = [0, 0]
                    break

                key = stdscr.getch()

                if key in (ord("\n"), curses.KEY_ENTER):
                    if sel is not None and scroll + content_height >= len(work_text):
                        wait_clear()
                        return sel
                elif key in (curses.KEY_DOWN, ord("s"), ord("S")):
                    if scroll + content_height < len(work_text):
                        scroll += 1
                elif key in (curses.KEY_UP, ord("w"), ord("W")):
                    if scroll > 0:
                        scroll -= 1
                elif key in [ord("y"), ord("Y")]:
                    if not important:
                        wait_clear()
                        return True
                    if sel is not True:
                        sel = True
                elif key in [ord("n"), ord("N")]:
                    if not important:
                        wait_clear()
                        return False
                    if sel is not False:
                        sel = False
                elif sel is not None:
                    sel = None
        except KeyboardInterrupt:
            pass
        except:
            pass


def selector(
    items: list,
    multi: bool,
    label: str | None = None,
    preselect: int | list = -1,
    sidebar: dict = None,
) -> list | int:
    selected = [False] * len(items)
    idx = 0
    offset = 0

    if isinstance(preselect, int):
        if preselect != -1:
            selected[preselect] = True
            idx = preselect
    else:
        for i in preselect:
            selected[i] = True

    while True:
        try:
            search_query = ""
            clear()

            while True:
                try:
                    h, w = detect_size()
                    while h < 5 or w < 75:
                        message(
                            [f"Terminal too small {h}<5||{w}<75"], "Error", prompt=False
                        )
                        time.sleep(0.5)
                        h, w = detect_size()

                    content_x, content_width, sidebar_width = _calculate_layout(
                        w, sidebar
                    )
                    view_h = h - 6  # 1 for title, 3 for items, 2 for help

                    def draw():
                        nonlocal idx, offset, h, w, content_x, content_width, sidebar_width, view_h

                        # Title
                        if label:
                            clear_line(1)
                            stdscr.addstr(
                                1,
                                2,
                                label + (" (DRYRUN)" if DRYRUN else ""),
                                curses.A_BOLD | curses.A_UNDERLINE,
                            )

                        # Filter items based on search query
                        filtered = [
                            (i, item)
                            for i, item in enumerate(items)
                            if search_query.lower() in item.lower()
                        ]

                        # Adjust index and scroll offset
                        if idx >= len(filtered):
                            idx = max(0, len(filtered) - 1)
                        if len(filtered) > 0:
                            if idx < offset:
                                offset = idx
                            elif idx >= offset + view_h:
                                offset = idx - view_h + 1
                        else:
                            offset = 0

                        # Draw items
                        for view_idx in range(view_h):
                            line_y = 3 + view_idx
                            clear_line(line_y)
                            item_global_idx = offset + view_idx
                            if item_global_idx < len(filtered):
                                item_idx, item_str = filtered[item_global_idx]

                                is_selected_in_multi = multi and selected[item_idx]
                                is_current_item = (
                                    len(filtered) > 0 and item_idx == filtered[idx][0]
                                )

                                if multi:
                                    prefix = (
                                        "- [x]" if is_selected_in_multi else "- [ ]"
                                    )
                                else:
                                    prefix = " <*>" if is_current_item else " < >"

                                text = f"{prefix} {item_str}"
                                attr = (
                                    curses.A_REVERSE
                                    if is_current_item
                                    else curses.A_NORMAL
                                )
                                stdscr.addnstr(
                                    line_y, content_x, text, content_width, attr
                                )

                        # Draw bottom help text
                        help_y = h - 2
                        clear_line(help_y)
                        stdscr.addstr(
                            help_y,
                            content_x,
                            "<SPACE>",
                            curses.A_BOLD | curses.A_REVERSE,
                        )
                        stdscr.addstr(
                            help_y,
                            content_x + 8,
                            "Select" if multi else "",
                            curses.A_BOLD,
                        )
                        stdscr.addstr(
                            help_y,
                            content_x + 16,
                            "<ENTER>",
                            curses.A_BOLD | curses.A_REVERSE,
                        )
                        stdscr.addstr(help_y, content_x + 24, "Confirm", curses.A_BOLD)
                        stdscr.addstr(
                            help_y,
                            content_x + 33,
                            "<Q>",
                            curses.A_BOLD | curses.A_REVERSE,
                        )
                        stdscr.addstr(help_y, content_x + 37, "Exit", curses.A_BOLD)
                        stdscr.addstr(
                            help_y,
                            content_x + 44,
                            "</>",
                            curses.A_BOLD | curses.A_REVERSE,
                        )
                        stdscr.addstr(help_y, content_x + 49, "Search", curses.A_BOLD)

                        draw_border()
                        _draw_sidebar(stdscr, sidebar, sidebar_width, w, h)

                        refresh()
                        return filtered

                    filtered = draw()
                    while True:
                        key = stdscr.getch()

                        if key == curses.KEY_RESIZE:
                            h, w = detect_size()
                            stdscr.clear()
                            content_x, content_width, sidebar_width = _calculate_layout(
                                w, sidebar
                            )
                            view_h = h - 6
                            while h < 5 or w < 60:
                                message(
                                    [f"Terminal too small {h}<5||{w}<60"],
                                    "Error",
                                    prompt=False,
                                )
                                time.sleep(0.5)
                                h, w = detect_size()
                            filtered = draw()
                            continue

                        if key == ord("/"):
                            q = text_input(
                                "Search:",
                                prefill=search_query,
                                label=label,
                                sidebar=sidebar,
                            )
                            search_query = q if q is not None else ""
                            idx, offset = 0, 0
                        elif key == curses.KEY_UP:
                            if filtered:
                                idx = (idx - 1 + len(filtered)) % len(filtered)
                        elif key == curses.KEY_DOWN:
                            if filtered:
                                idx = (idx + 1) % len(filtered)
                        elif key == ord(" ") and multi and filtered:
                            selected[filtered[idx][0]] = not selected[filtered[idx][0]]
                        elif key == ord("q") or key == 27:  # q or ESC
                            return [] if multi else None
                        elif key in (curses.KEY_ENTER, 10, 13):
                            if multi:
                                return [i for i, s in enumerate(selected) if s]
                            return filtered[idx][0] if filtered else None

                        filtered = draw()

                except KeyboardInterrupt:
                    pass
                except Exception:
                    break
        except Exception:
            pass


def text_input(
    prompt: str | list = "Input:",
    label: str | None = None,
    prefill: str = "",
    mask: bool = False,
    constraint=None,
    sidebar: dict = None,
) -> str | None:
    if stdscr is None:
        try:
            return input()
        except KeyboardInterrupt:
            return
        except EOFError:
            return
    wait_clear()
    if isinstance(prompt, str):
        prompt = [prompt]

    while True:
        try:
            buf = list(prefill)
            cursor = len(buf)
            start_y = 3
            cached = [0, 0]

            def draw_all(h, w, content_x, content_width, sidebar_width):
                clear()
                # Draw label
                if label:
                    stdscr.addstr(
                        1,
                        2,
                        label + (" (DRYRUN)" if DRYRUN else ""),
                        curses.A_BOLD | curses.A_UNDERLINE,
                    )
                # Draw help text
                stdscr.addstr(
                    h - 2, content_x, "<ENTER>", curses.A_BOLD | curses.A_REVERSE
                )
                stdscr.addstr(h - 2, content_x + 8, "Confirm", curses.A_BOLD)
                stdscr.addstr(
                    h - 2, content_x + 18, "<ESC>", curses.A_BOLD | curses.A_REVERSE
                )
                stdscr.addstr(h - 2, content_x + 25, "Cancel", curses.A_BOLD)

                # Draw prompt
                for i, line in enumerate(prompt):
                    stdscr.addstr(start_y + i, content_x, line, curses.A_BOLD)

                # Draw input field and border/sidebar
                draw_input_field(h, w, content_x, content_width, sidebar_width)

            def draw_input_field(h, w, content_x, content_width, sidebar_width):
                nonlocal cursor
                display = "*" * len(buf) if mask else "".join(buf)

                # Ensure cursor is within buffer bounds
                cursor = max(0, min(len(buf), cursor))

                # Truncate buffer if it's too long for the new width
                if len(buf) >= content_width - 3:
                    buf[:] = buf[: content_width - 4]
                    cursor = min(cursor, len(buf))

                line = display.ljust(content_width)
                clear_line(start_y + len(prompt))
                stdscr.addstr(
                    start_y + len(prompt),
                    content_x + 2,
                    line[: content_width - 3],
                    curses.A_REVERSE,
                )

                draw_border()
                _draw_sidebar(stdscr, sidebar, sidebar_width, w, h)
                stdscr.move(start_y + len(prompt), content_x + 2 + cursor)
                refresh()

            h, w = detect_size()
            content_x, content_width, sidebar_width = _calculate_layout(w, sidebar)
            draw_all(h, w, content_x, content_width, sidebar_width)
            cached = [h, w]

            while True:
                curses.curs_set(1)
                key = stdscr.getch()
                curses.curs_set(0)

                h, w = detect_size()
                if [h, w] != cached:
                    content_x, content_width, sidebar_width = _calculate_layout(
                        w, sidebar
                    )
                    draw_all(h, w, content_x, content_width, sidebar_width)
                    cached = [h, w]
                    continue

                # Recalculate just in case, though the resize block should handle it.
                _, content_width, _ = _calculate_layout(w, sidebar)

                if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                    final = "".join(buf)
                    if constraint and not constraint(final):
                        continue
                    return final
                elif key == 27:  # ESC
                    curses.curs_set(0)
                    return
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    if cursor > 0:
                        cursor -= 1
                        del buf[cursor]
                elif key == curses.KEY_DC:
                    if cursor < len(buf):
                        del buf[cursor]
                elif key == curses.KEY_LEFT:
                    cursor = max(0, cursor - 1)
                elif key == curses.KEY_RIGHT:
                    cursor = min(len(buf), cursor + 1)
                elif 32 <= key <= 126:
                    if len(buf) < content_width - 4:
                        buf.insert(cursor, chr(key))
                        cursor += 1

                draw_input_field(h, w, content_x, content_width, sidebar_width)
        except KeyboardInterrupt:
            pass
        except:
            pass
        curses.curs_set(0)


def draw_border() -> None:
    stdscr.attron(curses.color_pair(SECONDARY_PAIR))
    stdscr.border()
    stdscr.attroff(curses.color_pair(SECONDARY_PAIR))


def wait_clear(timeout: float = 0.2) -> None:
    stdscr.nodelay(True)
    keys_held = True

    while keys_held:
        try:
            keys_held = False
            start_time = time.time()

            while time.time() - start_time < timeout:
                if stdscr.getch() != -1:
                    keys_held = True
                    break
                time.sleep(0.01)
        except KeyboardInterrupt:
            pass
        except:
            pass

    stdscr.nodelay(False)


def clear() -> None:
    """
    Clear the screen, reset cursor and debounce.
    """
    stdscr.clear()
    curses.curs_set(0)
    wait_clear()


def refresh() -> None:
    stdscr.refresh()


def clear_line(y) -> None:
    """
    Move to line y and clear it.
    """
    stdscr.move(y, 0)
    stdscr.clrtoeol()


def draw_list(title: str, options: list, selected: int, special: bool = False) -> None:
    stdscr.addstr(1, 2, title, curses.A_BOLD | curses.A_UNDERLINE)

    h, w = detect_size()
    for idx, option in enumerate(options):
        x = 4
        y = 3 + idx
        clear_line(y)
        draw_border()
        if idx == selected:
            if special:
                stdscr.addstr(y, x, "[< " + option + " >]")
            else:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(y, x, "[> " + option + " <]")
                stdscr.attroff(curses.A_REVERSE)
        else:
            stdscr.addstr(y, x, option)

    refresh()


def draw_menu(title: str, options: list):
    curses.curs_set(0)
    current_row = 0
    wait_clear()
    stdscr.clear()

    while True:
        try:
            draw_list(
                title + (" (DRYRUN)" if DRYRUN else ""),
                options,
                selected=current_row,
            )
            key = stdscr.getch()

            if key == curses.KEY_UP:
                if current_row > 0:
                    current_row -= 1
                else:
                    current_row = len(options) - 1
            elif key == curses.KEY_DOWN:
                if current_row < len(options) - 1:
                    current_row += 1
                else:
                    current_row = 0
            elif key in (curses.KEY_ENTER, ord("\n")):
                draw_list(title, options, selected=current_row)
                time.sleep(0.1)
                draw_list(title, options, selected=current_row, special=True)
                time.sleep(0.1)
                draw_list(title, options, selected=current_row)
                time.sleep(0.1)
                draw_list(title, options, selected=current_row, special=True)
                time.sleep(0.1)
                draw_list(title, options, selected=current_row)
                time.sleep(0.1)
                return current_row
            elif key in (ord("q"), 27):  # ESC or 'q'
                return None
            wait_clear(0.065)
        except KeyboardInterrupt:
            wait_clear()
            stdscr.clear()
        except:
            pass


def draw_custom(commands: list) -> None:
    """
    Bulk draw commands with shortcuts, useful for drawing views.

    Accepted commands:
     function: Executes passed function without parameters.
     list: [-1, x, y, z], direct draw to collumn x, row y, data z, reverse filter.
     list: [0, x, y, z], direct draw to collumn x, row y, data z.
     list: [1, y], clear line y.
     list: [2, x, y], move cursor to collumn x, row y.
     list: [3, t], sleep t seconds.
    """
    for cmd in commands:
        if isinstance(cmd, list):
            if not cmd[0]:
                stdscr.addstr(cmd[2], cmd[1], cmd[3])
            elif cmd[0] == -1:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(cmd[2], cmd[1], cmd[3])
                stdscr.attroff(curses.A_REVERSE)
            elif cmd[0] == 1:
                clear_line(cmd[1])
            elif cmd[0] == 2:
                stdscr.move(cmd[2], cmd[1])
            elif cmd[0] == 3:
                time.sleep(cmd[1])
        else:  # Assume function.
            cmd()


def menu(title: str, actions: dict[str, callable], back: str = "Go Back") -> None:
    """
    Draw, execute and return the result with menu ui.
    """
    options = list(actions.keys()) + [back]

    while True:
        selection = draw_menu(title, options)
        if selection is None or options[selection] == back:
            return

        stdscr.clear()
        refresh()

        action_key = options[selection]
        func = actions.get(action_key)
        if func:
            func()


def suspend() -> None:
    """
    Pause curseapp rendering, toggling framebuffer back to the original one temporarily.

    Use when you run cli apps with output.
    """
    global enabled
    if not enabled:
        return
    enabled = False
    stdscr.clear()
    refresh()
    curses.nocbreak()
    stdscr.keypad(False)
    curses.echo()
    curses.endwin()


def resume() -> None:
    """
    Call once you wanna begin drawing again, after calling suspend()
    """
    global stdscr, enabled
    if enabled:
        return
    stdscr = curses.initscr()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    enabled = True


def init() -> None:
    """
    Call once at the start to initialize.
    """
    global stdscr, enabled
    if enabled:
        return
    resume()
    load_colors()
    stdscr.clear()

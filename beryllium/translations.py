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

import gettext
from os import path


def setup_translations(domain: str, lang: object = None) -> gettext.GNUTranslations:
    """
    Setup translations

        Does the following:
        - Loads the translations from the locale folder
        - Sets the translations for the gettext module

    Parameters:
    - domain: The domain for the translations
    - lang: The language to load translations for

    Returns: A gettext translation object and a pgettext translation object
    """
    lang_path = path.join(path.dirname(__file__), "locale")
    # Load translations
    if lang is not None:
        print("    INFO: Loading translations for", lang)
        gettext.bindtextdomain(domain, lang_path)
        gettext.textdomain(domain)
        translation = gettext.translation(domain, languages=[lang], fallback=True)
        translation.install()
        return translation.gettext, translation.pgettext  # type: ignore
    else:
        gettext.bindtextdomain(domain)
        gettext.textdomain(domain)
        return gettext.gettext, gettext.pgettext  # type: ignore

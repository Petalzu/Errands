#!@PYTHON@

# Copyright 2023 Vlad Krupinskii <mrvladus@yandex.ru>
# SPDX-License-Identifier: MIT

import os
import sys
import signal
import locale
import gettext
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Secret", "1")

from gi.repository import Adw, Gio

APP_ID = "@APP_ID@"
VERSION = "@VERSION@"
PREFIX = "@PREFIX@"
PROFILE = "@PROFILE@"
pkgdatadir = "@pkgdatadir@"
localedir = "@localedir@"

sys.path.insert(1, pkgdatadir)
signal.signal(signal.SIGINT, signal.SIG_DFL)
gettext.install("errands", localedir)
locale.bindtextdomain("errands", localedir)
locale.textdomain("errands")


def main() -> None:
    resource = Gio.Resource.load(os.path.join(pkgdatadir, "errands.gresource"))
    resource._register()

    from errands.utils.logging import Log

    Log.init()
    app = Application()
    sys.exit(app.run(sys.argv))


class Application(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.set_resource_base_path("/io/github/mrvladus/Errands/")

    def do_activate(self) -> None:
        from errands.widgets.window import Window

        win: Window = Window(application=self)
        win.perform_startup()


if __name__ == "__main__":
    main()

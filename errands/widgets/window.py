# Copyright 2023 Vlad Krupinskii <mrvladus@yandex.ru>
# SPDX-License-Identifier: MIT

import json
from gi.repository import Gio, Adw, Gtk, GLib
from __main__ import VERSION, APP_ID

# Import modules
import errands.utils.tasks as TaskUtils
from errands.widgets.preferences import PreferencesWindow
from errands.widgets.task import Task
from errands.widgets.trash_item import TrashItem
from errands.utils.sync import Sync
from errands.utils.animation import scroll
from errands.utils.gsettings import GSettings
from errands.utils.logging import Log
from errands.utils.data import UserData, UserDataDict, UserDataTask
from errands.utils.functions import get_children
from errands.utils.markup import Markup


@Gtk.Template(resource_path="/io/github/mrvladus/Errands/window.ui")
class Window(Adw.ApplicationWindow):
    __gtype_name__ = "Window"

    # - Template children - #
    about_window: Adw.AboutWindow = Gtk.Template.Child()
    clear_trash_btn: Gtk.Button = Gtk.Template.Child()
    confirm_dialog: Adw.MessageDialog = Gtk.Template.Child()
    delete_completed_tasks_btn_rev: Gtk.Revealer = Gtk.Template.Child()
    drop_motion_ctrl: Gtk.DropControllerMotion = Gtk.Template.Child()
    export_dialog: Gtk.FileDialog = Gtk.Template.Child()
    import_dialog: Gtk.FileDialog = Gtk.Template.Child()
    main_menu_btn: Gtk.MenuButton = Gtk.Template.Child()
    scroll_up_btn_rev: Gtk.Revealer = Gtk.Template.Child()
    scrolled_window: Gtk.ScrolledWindow = Gtk.Template.Child()
    shortcuts_window: Gtk.ShortcutsWindow = Gtk.Template.Child()
    split_view: Adw.OverlaySplitView = Gtk.Template.Child()
    sync_btn: Gtk.Button = Gtk.Template.Child()
    tasks_list: Gtk.Box = Gtk.Template.Child()
    title: Adw.WindowTitle = Gtk.Template.Child()
    toast_overlay: Adw.ToastOverlay = Gtk.Template.Child()
    toggle_trash_btn: Gtk.ToggleButton = Gtk.Template.Child()
    trash_list: Gtk.Box = Gtk.Template.Child()
    trash_list_scrl: Gtk.ScrolledWindow = Gtk.Template.Child()

    # - State - #
    scrolling: bool = False  # Is window scrolling
    startup: bool = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Remember window state
        Log.debug("Getting window settings")
        GSettings.bind("width", self, "default_width")
        GSettings.bind("height", self, "default_height")
        GSettings.bind("maximized", self, "maximized")
        GSettings.bind("sidebar-open", self.toggle_trash_btn, "active")
        # Setup theme
        Log.debug("Setting theme")
        Adw.StyleManager.get_default().set_color_scheme(GSettings.get("theme"))
        Log.debug("Present window")
        self.present()

    def perform_startup(self) -> None:
        """
        Startup func. Call after window is presented.
        """
        Log.debug("Window startup")
        Sync.window = self
        self._create_actions()
        self._load_tasks()
        self.startup = False

    def add_task(self, task: dict) -> None:
        new_task = Task(task, self)
        self.tasks_list.append(new_task)
        if not task["deleted"]:
            new_task.toggle_visibility(True)

    def add_toast(self, text: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast.new(title=text))

    def _create_actions(self) -> None:
        """
        Create actions for main menu
        """
        Log.debug("Creating actions")

        def _create_action(name: str, callback: callable, shortcuts=None) -> None:
            action: Gio.SimpleAction = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            if shortcuts:
                self.props.application.set_accels_for_action(f"app.{name}", shortcuts)
            self.props.application.add_action(action)

        def _about(*_) -> None:
            """
            Show about window
            """

            self.about_window.props.version = VERSION
            self.about_window.props.application_icon = APP_ID
            self.about_window.show()

        def _export_tasks(*args) -> None:
            """
            Show export dialog
            """

            def _finish_export(_dial, res, _data) -> None:
                try:
                    file: Gio.File = self.export_dialog.save_finish(res)
                except GLib.GError:
                    Log.info("Export cancelled")
                    self.add_toast(_("Export Cancelled"))  # pyright:ignore
                    return
                try:
                    path: str = file.get_path()
                    with open(path, "w+") as f:
                        json.dump(UserData.get(), f, indent=4, ensure_ascii=False)
                    self.add_toast(_("Tasks Exported"))  # pyright:ignore
                    Log.info(f"Export tasks to: {path}")
                except:
                    self.add_toast(_("Error"))  # pyright:ignore
                    Log.info(f"Can't export tasks to: {path}")

            self.export_dialog.save(self, None, _finish_export, None)

        def _import_tasks(*args) -> None:
            """
            Show import dialog
            """

            def finish_import(_dial, res, _data) -> None:
                Log.info("Importing tasks")

                try:
                    file: Gio.File = self.import_dialog.open_finish(res)
                except GLib.GError:
                    Log.info("Import cancelled")
                    self.add_toast(_("Import Cancelled"))  # pyright:ignore
                    return

                with open(file.get_path(), "r") as f:
                    text: str = f.read()
                    try:
                        text = UserData.convert(json.loads(text))
                    except:
                        Log.error("Invalid file")
                        self.add_toast(_("Invalid File"))  # pyright:ignore
                        return
                    data: dict = UserData.get()
                    ids = [t["id"] for t in data["tasks"]]
                    for task in text["tasks"]:
                        if task["id"] not in ids:
                            data["tasks"].append(task)
                    data = UserData.clean_orphans(data)
                    UserData.set(data)

                # Remove old tasks
                for task in get_children(self.tasks_list):
                    self.tasks_list.remove(task)
                # Remove old trash
                for task in get_children(self.trash_list):
                    self.trash_list.remove(task)
                self._load_tasks()
                Log.info("Tasks imported")
                self.add_toast(_("Tasks Imported"))  # pyright:ignore
                Sync.sync()

            self.import_dialog.open(self, None, finish_import, None)

        def _shortcuts(*_) -> None:
            """
            Show shortcuts window
            """

            self.shortcuts_window.set_transient_for(self)
            self.shortcuts_window.show()

        _create_action(
            "preferences",
            lambda *_: PreferencesWindow(self).show(),
            ["<primary>comma"],
        )
        _create_action("export", _export_tasks, ["<primary>e"])
        _create_action("import", _import_tasks, ["<primary>i"])
        _create_action("shortcuts", _shortcuts, ["<primary>question"])
        _create_action("about", _about)
        _create_action(
            "quit",
            lambda *_: self.props.application.quit(),
            ["<primary>q", "<primary>w"],
        )

    def get_all_tasks(self) -> list[Task]:
        """
        Get list of all tasks widgets including sub-tasks
        """

        tasks: list[Task] = []

        def append_tasks(items: list[Task]) -> None:
            for task in items:
                tasks.append(task)
                children: list[Task] = get_children(task.tasks_list)
                if len(children) > 0:
                    append_tasks(children)

        append_tasks(get_children(self.tasks_list))
        return tasks

    def get_toplevel_tasks(self) -> list[Task]:
        return get_children(self.tasks_list)

    def _load_tasks(self) -> None:
        Log.debug("Loading tasks")

        for task in UserData.get()["tasks"]:
            if not task["parent"]:
                self.add_task(task)
        self.update_status()
        # Expand tasks if needed
        if GSettings.get("expand-on-startup"):
            for task in self.get_all_tasks():
                if len(get_children(task.tasks_list)) > 0:
                    task.expand(True)
        Sync.sync(True)

    def update_ui(self) -> None:
        Log.debug("Updating UI")

        # Update existing tasks
        tasks: list[Task] = self.get_all_tasks()
        data_tasks: list[UserDataTask] = UserData.get()["tasks"]
        to_change_parent: list[UserDataTask] = []
        to_remove: list[Task] = []
        for task in tasks:
            for t in data_tasks:
                if task.task["id"] == t["id"]:
                    # If parent is changed
                    if task.task["parent"] != t["parent"]:
                        to_change_parent.append(t)
                        to_remove.append(task)
                        break
                    # If text changed
                    if task.task["text"] != t["text"]:
                        task.task["text"] = t["text"]
                        task.text = Markup.find_url(Markup.escape(task.task["text"]))
                        task.task_row.props.title = task.text
                    # If completion changed
                    if task.task["completed"] != t["completed"]:
                        task.completed_btn.props.active = t["completed"]

        # Remove old tasks
        for task in to_remove:
            task.purge()

        # Change parents
        for task in to_change_parent:
            if task["parent"] == "":
                self.add_task(task)
            else:
                for t in tasks:
                    if t.task["id"] == task["parent"]:
                        t.add_task(task)
                        break

        # Create new tasks
        tasks_ids: list[str] = [task.task["id"] for task in self.get_all_tasks()]
        for task in data_tasks:
            if task["id"] not in tasks_ids:
                # Add toplevel task and its sub-tasks
                if task["parent"] == "":
                    self.add_task(task)
                # Add sub-task and its sub-tasks
                else:
                    for t in self.get_all_tasks():
                        if t.task["id"] == task["parent"]:
                            t.add_task(task)
                tasks_ids = [task.task["id"] for task in self.get_all_tasks()]

        # Remove tasks
        ids = [t["id"] for t in UserData.get()["tasks"]]
        for task in self.get_all_tasks():
            if task.task["id"] not in ids:
                task.purge()

    def trash_add(self, task: dict) -> None:
        """
        Add item to trash
        """

        self.trash_list.append(TrashItem(task, self))
        self.trash_list_scrl.set_visible(True)

    def trash_clear(self) -> None:
        """
        Clear unneeded items from trash
        """

        tasks: list[UserDataTask] = UserData.get()["tasks"]
        to_remove: list[TrashItem] = []
        trash_children: list[TrashItem] = get_children(self.trash_list)
        for task in tasks:
            if not task["deleted"]:
                for item in trash_children:
                    if item.id == task["id"]:
                        to_remove.append(item)
        for item in to_remove:
            self.trash_list.remove(item)

        self.trash_list_scrl.set_visible(len(get_children(self.trash_list)) > 0)

    def update_status(self) -> None:
        """
        Update status bar on the top
        """

        tasks: list[UserDataTask] = UserData.get()["tasks"]
        n_total: int = 0
        n_completed: int = 0
        n_all_deleted: int = 0
        n_all_completed: int = 0

        for task in tasks:
            if task["parent"] == "":
                if not task["deleted"]:
                    n_total += 1
                    if task["completed"]:
                        n_completed += 1
            if not task["deleted"]:
                if task["completed"]:
                    n_all_completed += 1
            else:
                n_all_deleted += 1

        self.title.set_subtitle(
            _("Completed:") + f" {n_completed} / {n_total}"  # pyright: ignore
            if n_total > 0
            else ""
        )
        self.delete_completed_tasks_btn_rev.set_reveal_child(n_all_completed > 0)
        self.trash_list_scrl.set_visible(n_all_deleted > 0)

    # --- Template handlers --- #

    @Gtk.Template.Callback()
    def on_dnd_scroll(self, _motion, _x, y) -> bool:
        """
        Autoscroll while dragging task
        """

        def _auto_scroll(scroll_up: bool) -> bool:
            """Scroll while drag is near the edge"""
            if not self.scrolling or not self.drop_motion_ctrl.contains_pointer():
                return False
            adj = self.scrolled_window.get_vadjustment()
            if scroll_up:
                adj.set_value(adj.get_value() - 2)
                return True
            else:
                adj.set_value(adj.get_value() + 2)
                return True

        MARGIN: int = 50
        height: int = self.scrolled_window.get_allocation().height
        if y < MARGIN:
            self.scrolling = True
            GLib.timeout_add(100, _auto_scroll, True)
        elif y > height - MARGIN:
            self.scrolling = True
            GLib.timeout_add(100, _auto_scroll, False)
        else:
            self.scrolling = False

    @Gtk.Template.Callback()
    def on_scroll(self, adj) -> None:
        """
        Show scroll up button
        """

        self.scroll_up_btn_rev.set_reveal_child(adj.get_value() > 0)

    @Gtk.Template.Callback()
    def on_scroll_up_btn_clicked(self, _) -> None:
        """
        Scroll up
        """

        scroll(self.scrolled_window, False)

    @Gtk.Template.Callback()
    def on_task_added(self, entry: Gtk.Entry) -> None:
        """
        Add new task
        """

        text: str = entry.props.text
        # Check for empty string or task exists
        if text == "":
            return
        # Add new task
        new_data: UserDataDict = UserData.get()
        new_task: UserDataTask = TaskUtils.new_task(text)
        new_data["tasks"].append(new_task)
        UserData.set(new_data)
        self.add_task(new_task)
        # Clear entry
        entry.props.text = ""
        # Scroll to the end
        scroll(self.scrolled_window, True)
        # Sync
        Sync.sync()

    @Gtk.Template.Callback()
    def on_toggle_trash_btn(self, btn: Gtk.ToggleButton) -> None:
        """
        Move focus to sidebar
        """
        if btn.get_active():
            self.clear_trash_btn.grab_focus()
        else:
            btn.grab_focus()

    @Gtk.Template.Callback()
    def on_delete_completed_tasks_btn_clicked(self, _) -> None:
        """
        Hide completed tasks and move them to trash
        """
        Log.info("Delete completed tasks")

        for task in self.get_all_tasks():
            if task.task["completed"] and not task.task["deleted"]:
                task.delete()

    @Gtk.Template.Callback()
    def on_sync_btn_clicked(self, btn) -> None:
        Sync.sync(True)

    @Gtk.Template.Callback()
    def on_trash_clear(self, _) -> None:
        Log.debug("Show confirm dialog")
        self.confirm_dialog.show()

    @Gtk.Template.Callback()
    def on_trash_clear_confirm(self, _, res) -> None:
        """
        Remove all trash items and tasks
        """

        if res == "cancel":
            Log.debug("Clear Trash cancelled")
            return

        Log.info("Clear Trash")

        # Remove widgets and data
        data: UserDataDict = UserData.get()
        data["deleted"] = [task["id"] for task in data["tasks"] if task["deleted"]]
        data["tasks"] = [task for task in data["tasks"] if not task["deleted"]]
        UserData.set(data)
        to_remove: list[Task] = [
            task for task in self.get_all_tasks() if task.task["deleted"]
        ]
        for task in to_remove:
            task.purge()
        # Remove trash items widgets
        for item in get_children(self.trash_list):
            self.trash_list.remove(item)
        self.trash_list_scrl.set_visible(False)
        # Sync
        Sync.sync()

    @Gtk.Template.Callback()
    def on_trash_close(self, _) -> None:
        Log.debug("Close sidebar")
        self.split_view.set_show_sidebar(False)

    @Gtk.Template.Callback()
    def on_trash_restore(self, _) -> None:
        """
        Remove trash items and restore all tasks
        """

        Log.info("Restore Trash")

        # Restore tasks
        tasks: list[Task] = self.get_all_tasks()
        for task in tasks:
            if task.task["deleted"]:
                task.task["deleted"] = False
                task.update_data()
                task.toggle_visibility(True)
                # Update statusbar
                if not task.task["parent"]:
                    task.update_status()
                else:
                    task.parent.update_status()
                # Expand if needed
                for t in tasks:
                    if t.task["parent"] == task.task["id"]:
                        task.expand(True)
                        break

        # Clear trash
        self.trash_clear()
        self.update_status()

    @Gtk.Template.Callback()
    def on_trash_drop(self, _drop, task: Task, _x, _y) -> None:
        """
        Move task to trash via dnd
        """
        Log.debug(f"Drop task to trash: {task.task['id']}")

        task.delete()
        self.update_status()

    @Gtk.Template.Callback()
    def on_width_changed(self, *_) -> None:
        """
        Breakpoints simulator
        """
        width: int = self.props.default_width
        self.scroll_up_btn_rev.set_visible(width > 400)
        self.split_view.set_collapsed(width < 720)

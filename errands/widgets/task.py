# Copyright 2023 Vlad Krupinskii <mrvladus@yandex.ru>
# SPDX-License-Identifier: MIT

import os
from typing import Self
from gi.repository import Gtk, Adw, Gdk, GObject, Gio, GLib

# Import modules
import errands.utils.tasks as TaskUtils
from errands.utils.sync import Sync
from errands.utils.logging import Log
from errands.utils.data import UserData, UserDataDict, UserDataTask
from errands.utils.markup import Markup
from errands.utils.functions import get_children
from errands.utils.tasks import task_to_ics


@Gtk.Template(resource_path="/io/github/mrvladus/Errands/task.ui")
class Task(Gtk.Revealer):
    __gtype_name__ = "Task"

    # - Template children - #
    main_box: Gtk.Box = Gtk.Template.Child()
    task_box_rev: Gtk.Revealer = Gtk.Template.Child()
    task_row: Adw.ActionRow = Gtk.Template.Child()
    expand_icon: Gtk.Image = Gtk.Template.Child()
    completed_btn: Gtk.Button = Gtk.Template.Child()
    task_edit_entry: Gtk.Entry = Gtk.Template.Child()
    sub_tasks_revealer: Gtk.Revealer = Gtk.Template.Child()
    tasks_list: Gtk.Box = Gtk.Template.Child()

    # - State - #
    just_added: bool = True
    is_sub_task: bool = False
    can_sync: bool = True

    def __init__(
        self, task: UserDataTask, window: Adw.ApplicationWindow, parent=None
    ) -> None:
        super().__init__()
        Log.info(f"Add {'task' if not task['parent'] else 'sub-task'}: " + task["id"])
        self.window: Adw.ApplicationWindow = window
        self.parent: Adw.ApplicationWindow | Task = (
            self.window if not parent else parent
        )
        self.task: UserDataTask = task
        # Set text
        self.text: str = Markup.find_url(Markup.escape(self.task["text"]))
        self.task_row.set_title(self.text)
        # Check if sub-task completed and toggle checkbox
        self.completed_btn.props.active = self.task["completed"]
        # Set accent color
        if self.task["color"] != "":
            self.main_box.add_css_class(f'task-{self.task["color"]}')
        # Add to trash if needed
        if self.task["deleted"]:
            self.window.trash_add(self.task)
        self._check_is_sub()
        self._add_sub_tasks()
        self._add_actions()
        self.just_added = False
        self.parent.update_status()

    def __repr__(self) -> str:
        return f"Task({self.task['id']})"

    def _add_actions(self) -> None:
        group: Gio.SimpleActionGroup = Gio.SimpleActionGroup.new()
        self.insert_action_group("task", group)

        def _add_action(name: str, callback) -> None:
            action: Gio.SimpleAction = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            group.add_action(action)

        def _copy(*args) -> None:
            Log.info("Copy to clipboard")
            clp: Gdk.Clipboard = Gdk.Display.get_default().get_clipboard()
            clp.set(self.task["text"])
            self.window.add_toast(_("Copied to Clipboard"))  # pyright:ignore

        def _open_with(*args) -> None:
            cache_dir: str = os.path.join(GLib.get_user_cache_dir(), "list")
            if not os.path.exists(cache_dir):
                os.mkdir(cache_dir)
            file_path = os.path.join(cache_dir, f"{self.task['id']}.ics")
            with open(file_path, "w") as f:
                f.write(task_to_ics(self.task))
            file: Gio.File = Gio.File.new_for_path(file_path)
            Gtk.FileLauncher.new(file).launch()

        def _edit(*_) -> None:
            self.toggle_edit_mode()
            # Set entry text and select it
            self.task_edit_entry.get_buffer().props.text = self.task["text"]
            self.task_edit_entry.select_region(0, len(self.task["text"]))
            self.task_edit_entry.grab_focus()

        _add_action("delete", self.delete)
        _add_action("edit", _edit)
        _add_action("copy", _copy)
        _add_action("open_with", _open_with)

    def add_task(self, task: dict) -> None:
        sub_task: Task = Task(task, self.window, self)
        self.tasks_list.append(sub_task)
        sub_task.toggle_visibility(not task["deleted"])
        if not self.just_added:
            self.update_status()

    def _add_sub_tasks(self) -> None:
        sub_count: int = 0
        for task in UserData.get()["tasks"]:
            if task["parent"] == self.task["id"]:
                sub_count += 1
                self.add_task(task)
        self.update_status()
        self.window.update_status()

    def _check_is_sub(self) -> None:
        if self.task["parent"] != "":
            self.is_sub_task = True
            self.main_box.add_css_class("sub-task")
            if not self.window.startup and self.parent != self.window:
                self.parent.expand(True)
        else:
            self.main_box.add_css_class("task")

    def delete(self, *_) -> None:
        Log.info(f"Move task to trash: {self.task['id']}")

        self.toggle_visibility(False)
        self.task["deleted"] = True
        self.update_data()
        self.completed_btn.set_active(True)
        self.window.trash_add(self.task)
        for task in get_children(self.tasks_list):
            if not task.task["deleted"]:
                task.delete()
        self.parent.update_status()

    def expand(self, expanded: bool) -> None:
        self.sub_tasks_revealer.set_reveal_child(expanded)
        if expanded:
            self.expand_icon.add_css_class("rotate")
        else:
            self.expand_icon.remove_css_class("rotate")

    def purge(self) -> None:
        """
        Completely remove widget
        """

        self.parent.tasks_list.remove(self)
        self.run_dispose()

    def toggle_edit_mode(self) -> None:
        self.task_box_rev.set_reveal_child(not self.task_box_rev.get_child_revealed())

    def toggle_visibility(self, on: bool) -> None:
        self.set_reveal_child(on)

    def update_status(self) -> None:
        n_completed: int = 0
        n_total: int = 0
        for task in UserData.get()["tasks"]:
            if task["parent"] == self.task["id"]:
                if not task["deleted"]:
                    n_total += 1
                    if task["completed"]:
                        n_completed += 1

        self.task_row.set_subtitle(
            _("Completed:") + f" {n_completed} / {n_total}"  # pyright: ignore
            if n_total > 0
            else ""
        )

    def update_data(self) -> None:
        """
        Sync self.task with user data.json
        """

        data: UserDataDict = UserData.get()
        for i, task in enumerate(data["tasks"]):
            if self.task["id"] == task["id"]:
                data["tasks"][i] = self.task
                UserData.set(data)
                return

    # --- Template handlers --- #

    @Gtk.Template.Callback()
    def on_completed_btn_toggled(self, btn: Gtk.Button) -> None:
        """
        Toggle check button and add style to the text
        """

        def _set_text():
            if btn.get_active():
                self.text = Markup.add_crossline(self.text)
                self.add_css_class("task-completed")
            else:
                self.text = Markup.rm_crossline(self.text)
                self.remove_css_class("task-completed")
            self.task_row.set_title(self.text)

        # If task is just added set text and return to avoid useless sync
        if self.just_added:
            _set_text()
            return

        # Update data
        self.task["completed"] = btn.get_active()
        self.task["synced_caldav"] = False
        self.update_data()
        # Update children
        children: list[Task] = get_children(self.tasks_list)
        for task in children:
            task.can_sync = False
            task.completed_btn.set_active(btn.get_active())
        # Update status
        if self.is_sub_task:
            self.parent.update_status()
        # Set text
        _set_text()
        # Sync
        if self.can_sync:
            Sync.sync()
            self.window.update_status()
            for task in children:
                task.can_sync = True

    @Gtk.Template.Callback()
    def on_expand(self, *_) -> None:
        """
        Expand task row
        """

        self.expand(not self.sub_tasks_revealer.get_child_revealed())

    @Gtk.Template.Callback()
    def on_sub_task_added(self, entry: Gtk.Entry) -> None:
        """
        Add new Sub-Task
        """

        # Return if entry is empty
        if entry.get_buffer().props.text == "":
            return
        # Add new sub-task
        new_sub_task: UserDataTask = TaskUtils.new_task(
            entry.get_buffer().props.text, parent=self.task["id"]
        )
        data: UserDataDict = UserData.get()
        data["tasks"].append(new_sub_task)
        UserData.set(data)
        # Add sub-task
        self.add_task(new_sub_task)
        # Clear entry
        entry.get_buffer().props.text = ""
        # Update status
        self.task["completed"] = False
        self.update_data()
        self.just_added = True
        self.completed_btn.set_active(False)
        self.just_added = False
        self.update_status()
        self.window.update_status()
        # Sync
        Sync.sync()

    @Gtk.Template.Callback()
    def on_task_cancel_edit_btn_clicked(self, *_) -> None:
        self.toggle_edit_mode()

    @Gtk.Template.Callback()
    def on_task_edit(self, entry: Gtk.Entry) -> None:
        """
        Edit task text
        """

        # Get text
        new_text: str = entry.get_buffer().props.text
        # Return if text empty
        if new_text.replace(" ", "") == "":
            return
        # Change task
        Log.info(f"Edit: {self.task['id']}")
        # Set new text
        self.task["text"] = new_text
        # Escape text and find URL's'
        self.text = Markup.find_url(Markup.escape(self.task["text"]))
        self.task_row.props.title = self.text
        # Toggle checkbox
        self.task["completed"] = False
        self.task["synced_caldav"] = False
        self.update_data()
        self.just_added = True
        self.completed_btn.set_active(False)
        self.just_added = False
        self.update_status()
        # Exit edit mode
        self.toggle_edit_mode()
        # Sync
        Sync.sync()

    @Gtk.Template.Callback()
    def on_style_selected(self, btn: Gtk.Button) -> None:
        """
        Apply accent color
        """

        for i in btn.get_css_classes():
            color = ""
            if i.startswith("btn-"):
                color = i.split("-")[1]
                break
        # Color card
        for c in self.main_box.get_css_classes():
            if "task-" in c:
                self.main_box.remove_css_class(c)
                break
        self.main_box.add_css_class(f"task-{color}")
        # Set new color
        self.task["color"] = color
        # Sync
        self.task["synced_caldav"] = False
        self.update_data()
        Sync.sync()

    # --- Drag and Drop --- #

    @Gtk.Template.Callback()
    def on_drag_end(self, *_) -> bool:
        self.set_sensitive(True)

    @Gtk.Template.Callback()
    def on_drag_begin(self, _, drag) -> bool:
        icon: Gtk.DragIcon = Gtk.DragIcon.get_for_drag(drag)
        icon.set_child(
            Gtk.Button(
                label=self.task["text"]
                if len(self.task["text"]) < 20
                else f"{self.task['text'][0:20]}..."
            )
        )

    @Gtk.Template.Callback()
    def on_drag_prepare(self, *_) -> Gdk.ContentProvider:
        self.set_sensitive(False)
        value = GObject.Value(Task)
        value.set_object(self)
        return Gdk.ContentProvider.new_for_value(value)

    @Gtk.Template.Callback()
    def on_task_top_drop(self, _drop, task, _x, _y) -> bool:
        """
        When task is dropped on "+" area on top of task
        """

        # Return if task is itself
        if task == self:
            return False

        # Move data
        data: UserDataDict = UserData.get()
        tasks = data["tasks"]
        for i, t in enumerate(tasks):
            if t["id"] == self.task["id"]:
                self_idx = i
            elif t["id"] == task.task["id"]:
                task_idx = i
        tasks.insert(self_idx, tasks.pop(task_idx))
        UserData.set(data)

        # If task has the same parent
        if task.parent == self.parent:
            # Move widget
            self.parent.tasks_list.reorder_child_after(task, self)
            self.parent.tasks_list.reorder_child_after(self, task)
            return True

        # Change parent if different parents
        task.task["parent"] = self.task["parent"]
        task.task["synced_caldav"] = False
        task.update_data()
        task.purge()
        # Add new task widget
        new_task = Task(task.task, self.window, self.parent)
        self.parent.tasks_list.append(new_task)
        self.parent.tasks_list.reorder_child_after(new_task, self)
        self.parent.tasks_list.reorder_child_after(self, new_task)
        new_task.toggle_visibility(True)
        # Update status
        self.parent.update_status()
        task.parent.update_status()

        # Sync
        Sync.sync()

        return True

    @Gtk.Template.Callback()
    def on_drop(self, _drop, task: Self, _x, _y) -> None:
        """
        When task is dropped on task and becomes sub-task
        """

        if task == self or task.parent == self:
            return

        # Change parent
        task.task["parent"] = self.task["id"]
        task.task["synced_caldav"] = False
        task.update_data()
        # Move data
        data: UserDataDict = UserData.get()
        tasks = data["tasks"]
        last_sub_idx: int = 0
        for i, t in enumerate(tasks):
            if t["parent"] == self.task["id"]:
                last_sub_idx = tasks.index(t)
            if t["id"] == self.task["id"]:
                self_idx = i
            if t["id"] == task.task["id"]:
                task_idx = i
        tasks.insert(self_idx + last_sub_idx, tasks.pop(task_idx))
        UserData.set(data)
        # Remove old task
        task.purge()
        # Add new sub-task
        self.add_task(task.task.copy())
        self.task["completed"] = False
        self.update_data()
        self.just_added = True
        self.completed_btn.set_active(False)
        self.just_added = False
        # Update status
        task.parent.update_status()
        self.update_status()
        self.parent.update_status()

        # Sync
        Sync.sync()

        return True

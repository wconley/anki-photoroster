#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import appdirs  # Requires appdirs: pip install appdirs
import gi       # Requires PyGObj/GTK: apt-get install python3-gi gir1.2-gtk-3.0
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from photoroster import load_existing_students, PhotoRoster

APPNAME = "Anki-PhotoRoster"
AUTHOR = "Will Conley"
CONFIGFILE = "Anki-PhotoRoster.conf"

class AutoBuilder(object):
    def __init__(self, ui_file):
        ui_path = os.path.join(sys.path[0], ui_file)
        self._builder = Gtk.Builder.new_from_file(ui_path)
        self._builder.connect_signals(self)

    def __getattr__(self, attr):
        value = self._builder.get_object(attr)
        setattr(self, attr, value)
        return value


class MainWindow(AutoBuilder):
    def __init__(self):
        "Initialize the main window of our application."

        super().__init__("main-window.ui")
        self.window.show()
        self.progressbar.hide()
        self.anki_folder = preferences.get("anki_folder", None)
        self.roster = None
        self.tag = None
        self.this_course = None
        self.check_anki_collection()

    def enable_all(self, enabled):
        self.photo_roster_entry.set_sensitive(enabled)
        self.photo_roster_button.set_sensitive(enabled)
        self.tag_entry.set_sensitive(enabled)
        self.start_button.set_sensitive(enabled)

    def check_anki_folder(self, path):
        return (os.path.isdir(os.path.join(path, "collection.media")) and 
                os.path.isfile(os.path.join(path, "collection.anki2")))

    def check_anki_collection(self):
        if not self.anki_folder:
            self.anki_folder_label.set_markup("<b>First choose the folder " + 
                    "where your Anki data is stored.</b>")
            self.anki_collection_label.set_text("")
            self.anki_folder_button.set_label("Choose...")
            self.enable_all(False)
            return
        self.anki_folder_label.set_text("Using Anki profile at {}".format(
                self.anki_folder))
        self.anki_folder_button.set_label("Change...")
        try:
            if not self.check_anki_folder(self.anki_folder):
                raise ValueError()
            self.existing_students = load_existing_students(self.anki_folder)
        except:
            self.existing_students = None
            self.anki_folder_image.set_from_icon_name("dialog-warning", 
                    Gtk.IconSize.LARGE_TOOLBAR)
            self.anki_collection_label.set_text("This folder does not appear " + 
                    "to contain an Anki collection.")
            self.enable_all(False)
        else:
            self.anki_folder_image.set_from_icon_name("emblem-default", 
                    Gtk.IconSize.LARGE_TOOLBAR)
            self.anki_collection_label.set_text(("There are {} names and " + 
                    "faces in this Anki collection.").format(
                    len(self.existing_students)))
            self.photo_roster_entry.set_sensitive(True)
            self.photo_roster_button.set_sensitive(True)
            self.check_photo_roster()

    def check_photo_roster(self):
        path = self.photo_roster_entry.get_text()
        if self.roster and self.roster.path == path:
            return
        if not path:
            self.photo_roster_label.hide()
            return
        try:
            self.roster = PhotoRoster(path)
            tag = self.roster.course_tag
        except:
            self.photo_roster_image.set_from_icon_name("dialog-warning", 
                    Gtk.IconSize.LARGE_TOOLBAR)
            self.roster = None
            self.photo_roster_label.show()
            self.photo_roster_label.set_text("This does not appear to be a " + 
                    "valid photo roster.")
            self.tag_entry.set_text("")
            self.tag_entry.set_sensitive(False)
            self.start_button.set_sensitive(False)
        else:
            self.photo_roster_image.set_from_icon_name("emblem-default", 
                    Gtk.IconSize.LARGE_TOOLBAR)
            self.photo_roster_label.show()
            self.photo_roster_label.set_text(("There are {} students in " + 
                    "this photo roster.").format(self.roster.num_students))
            self.tag_entry.set_text(tag)
            self.tag_entry.set_sensitive(True)
            self.start_button.set_sensitive(True)
        self.check_tag()

    def check_tag(self):
        tag = self.tag_entry.get_text()
        if self.tag == tag:
            return
        self.tag = tag
        if tag:
            tag = " {} ".format(tag)
            self.this_course = {idnumber for idnumber, (pn, fn, tags) in 
                    self.existing_students.items() if tag in tags}
            self.tag_label.show()
            self.tag_label.set_text(("There are {} students with this tag " + 
                    "in your current Anki collection.").format(
                    len(self.this_course)))
        else:
            self.this_course = set()
            self.tag_label.hide()

    def anki_folder_button_clicked(self, button):
        dialog = Gtk.FileChooserDialog(title="Choose your Anki data folder", 
                parent=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER, 
                buttons=("_Cancel", Gtk.ResponseType.CANCEL, 
                        "_Open", Gtk.ResponseType.OK))
        dialog.set_modal(True)
        dialog.set_destroy_with_parent(True)
        if self.anki_folder and os.path.isdir(self.anki_folder):
            dialog.set_current_folder(self.anki_folder)
        def selection_changed(dialog):
            path = dialog.get_filename()
            if path is not None:
                dialog.set_response_sensitive(Gtk.ResponseType.OK, 
                        self.check_anki_folder(path))
            return False
        def response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                self.anki_folder = dialog.get_filename()
                preferences["anki_folder"] = self.anki_folder
                self.check_anki_collection()
            dialog.destroy()
            return False
        dialog.connect("selection_changed", selection_changed)
        dialog.connect("response", response)
        dialog.show()
        return False

    def photo_roster_button_clicked(self, button):
        dialog = Gtk.FileChooserDialog(title="Choose a photo roster", 
                parent=self.window, action=Gtk.FileChooserAction.OPEN, 
                buttons=("_Cancel", Gtk.ResponseType.CANCEL, 
                        "_Open", Gtk.ResponseType.OK))
        dialog.set_modal(True)
        dialog.set_destroy_with_parent(True)
        file_filter = Gtk.FileFilter()
        file_filter.set_name("PDF files")
        file_filter.add_mime_type("application/pdf")
        dialog.add_filter(file_filter)
        path = self.photo_roster_entry.get_text()
        if os.path.isdir(path):
            dialog.set_current_folder(path)
        elif os.path.isfile(path):
            dialog.set_current_folder(os.path.dirname(path))
        elif os.path.isdir(preferences.get("last_photoroster_folder", "")):
            dialog.set_current_folder(preferences["last_photoroster_folder"])
        def response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                self.photo_roster_entry.set_text(dialog.get_filename())
                preferences["last_photoroster_folder"] = os.path.dirname(
                        dialog.get_filename())
                self.check_photo_roster()
            dialog.destroy()
            return False
        dialog.connect("response", response)
        dialog.show()
        return False

    def photo_roster_entry_focus_out_event(self, entry, event):
        path = os.path.expanduser(entry.get_text())
        entry.set_text(path)
        self.check_photo_roster()
        return False

    def tag_entry_focus_out_event(self, entry, event):
        self.check_tag()
        return False

    def quit_button_clicked(self, button, event=None):
        Gtk.main_quit()
        return False

    def start_button_clicked(self, button):
        iterator = self.main_iterator()
        GLib.idle_add(lambda: next(iterator, False), priority=GLib.PRIORITY_LOW)

    def main_iterator(self):
        photodir = os.path.join(self.anki_folder, "collection.media")
        outfilepath = os.path.splitext(self.roster.path)[0] + ".Anki_Import.txt"
        num_students = self.roster.num_students
        self.progressbar.show()
        self.progressbar.set_fraction(0)
        #self.progressbar.set_text(None) # Is this needed? Not sure yet...
        conflict_dialog = ConflictDialog(self.window, self.existing_students)
        with open(outfilepath, "w") as outfile:
            for n, student in enumerate(self.roster):
                self.this_course.discard(student.idnumber)
                photo_backup = student.save_photo(photodir)
                conflict_dialog.check_existing(student, photo_backup)
                print(student, file=outfile)
                self.progressbar.set_fraction(n / num_students)
                yield True
        if self.this_course:
            # Need to open a dialog for this instead... Offer to save somewhere?
            print("The following students were already tagged as being in this ")
            print("course in your Anki database, but they're not on this roster. ")
            print("This probably means you've previously imported a roster for ")
            print("this class, and these students have since dropped the class: ")
        for idnumber in self.this_course:
            preferredname, fullname, tags = self.existing_students[idnumber]
            print("    {} ({})".format(preferredname, fullname))


class ConflictDialog(AutoBuilder):
    def __init__(self, parent, existing_students):
        "Initialize the dialog to resolve name and photo conflicts."

        super().__init__("conflict-dialog.ui")
        self.dialog.set_transient_for(parent)
        self.existing_students = existing_students
        self.dialog.hide()

    def check_existing(self, student, existing_photo):
        existing = self.existing_students.get(student.idnumber)
        if not existing:
            return
        preferredname, fullname, tags = existing
        student.merge_tags(tags.split())
        if (preferredname == student.preferredname and 
                fullname == student.fullname and not existing_photo):
            return
        message = "Found some changes:\n"
        if existing_photo:
            photodir = os.path.dirname(existing_photo)
            new_photo = os.path.join(photodir, student.photo_filename())
            message += "    Photo: {} ---> {}\n".format(existing_photo, new_photo)
        if preferredname != student.preferredname:
            message += "    Pref. name: {} ---> {}\n".format(preferredname, student.preferredname)
        if fullname != student.fullname:
            message += "    Full name: {} ---> {}\n".format(fullname, student.fullname)
        parent = self.dialog.get_transient_for()
        dialog = Gtk.MessageDialog(parent, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, message)
        dialog.run()
        dialog.destroy()

    def check_existing2(self, student, existing_photo):
        existing = self.existing_students.get(student.idnumber)
        if not existing:
            if existing_photo:
                print(("This should never happen! There is an existing photo" + 
                        " for {}, but they are not in the Anki database! You" + 
                        " may want to manually remove the photo {}.").format(
                        student.preferredname, existing_photo))
            return
        preferredname, fullname, tags = existing
        student.merge_tags(tags.split())
        if (preferredname == student.preferredname and 
                fullname == student.fullname and not existing_photo):
            return
        if existing_photo:
            photodir = os.path.dirname(existing_photo)
            new_photo = os.path.join(photodir, student.photo_filename())
            # Show the photos section of the dialog, add these photos...
        else:
            self.photo_section.hide()
        if old_preferredname != student.preferredname:
            # Show that part of the dialog, set the labels, etc...
            pass
        else:
            self.preferredname_section.hide()
        if old_fullname != student.fullname:
            # Show that part of the dialog, set the labels, etc...
            pass
        else:
            self.fullname_section.hide()
        self.dialog.show()
        response = self.dialog.run()
        # Now do something with the response... I fucking hate this function

    def existing_prefname_togglebutton_toggled(self, button):
        pass

    def new_prefname_togglebutton_toggled(self, button):
        pass

    def prefname_entry_changed(self, entry):
        pass

    def existing_prefname_checkbutton_toggled(self, button):
        pass

    def new_prefname_checkbutton_toggled(self, button):
        pass

    def existing_fullname_togglebutton_toggled(self, button):
        pass

    def new_fullname_togglebutton_toggled(self, button):
        pass

    def fullname_entry_changed(self, entry):
        pass

    def existing_fullname_checkbutton_toggled(self, button):
        pass

    def new_fullname_checkbutton_toggled(self, button):
        pass


if __name__ == "__main__":
    # First, load preferences from config file, if present
    configdir = appdirs.user_config_dir(APPNAME, AUTHOR)
    try:
        with open(os.path.join(configdir, CONFIGFILE)) as configfile:
            preferences = json.load(configfile)
    except:
        preferences = {}

    # Construct main window
    main_window = MainWindow()
    Gtk.main()

    # Save preferences to config file
    os.makedirs(configdir, mode=0o700, exist_ok=True)
    try:
        with open(os.path.join(configdir, CONFIGFILE), "w") as configfile:
            json.dump(preferences, configfile, indent=4)
    except Exception as e:
        print("Error when trying to save config file:", e)
    print("Done!")



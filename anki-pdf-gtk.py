#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import appdirs  # Requires appdirs: pip install appdirs
import gi       # Requires PyGObj/GTK: apt-get install python3-gi gir1.2-gtk-3.0
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

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
        #self.progressbar.hide()
        self.window.show()
        self.anki_folder = preferences.get("anki_folder", None)
        if self.anki_folder is None:
            self.anki_folder_label.set_markup("<b>First choose the folder where your Anki data is stored.</b>")
            self.enable_all(False)
        else:
            self.anki_folder_entry.set_text(self.anki_folder)
        self.roster = None
        self.existing_students = None
        self.tag = None
        self.this_course = None

    def enable_all(self, enabled):
        self.photo_roster_entry.set_sensitive(enabled)
        self.photo_roster_button.set_sensitive(enabled)
        self.tag_entry.set_sensitive(enabled)
        self.start_button.set_sensitive(enabled)

    def check_anki_folder(self, path):
        return (os.path.isdir(os.path.join(path, "collection.media")) and 
                os.path.isfile(os.path.join(path, "collection.anki2")))

    def check_anki_collection(self):
        path = self.anki_folder_entry.get_text()
        if self.anki_folder == path:
            return
        self.anki_folder = path
        try:
            if not self.check_anki_folder(path):
                raise ValueError()
            self.existing_students = load_existing_students(path)
        except:
            self.existing_students = None
            self.anki_folder_image.set_from_icon_name("dialog-warning", 
                    Gtk.IconSize.LARGE_TOOLBAR)
            self.anki_folder_label.set_text("This folder does not appear to " + 
                    "contain an Anki collection.")
            self.enable_all(False)
        else:
            self.anki_folder_image.set_from_icon_name("emblem-default", 
                    Gtk.IconSize.LARGE_TOOLBAR)
            self.anki_folder_label.set_text(("There are {} names and faces " + 
                    "in this Anki collection.").format(
                    len(self.existing_students)))
            self.photo_roster_entry.set_sensitive(True)
            self.photo_roster_button.set_sensitive(True)
            self.check_photo_roster()

    def anki_folder_button_clicked(self, button):
        dialog = Gtk.FileChooserDialog(title="Choose your Anki data folder", 
                parent=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER, 
                buttons=("_Cancel", Gtk.ResponseType.CANCEL, 
                        "_Open", Gtk.ResponseType.OK))
        dialog.set_modal(True)
        dialog.set_destroy_with_parent(True)
        if os.path.isdir(self.anki_folder_entry.get_text()):
            dialog.set_current_folder(self.anki_folder_entry.get_text())
        def selection_changed(dialog):
            path = dialog.get_filename()
            if path is not None:
                dialog.set_response_sensitive(Gtk.ResponseType.OK, 
                        self.check_anki_folder(path))
            return False
        def response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                self.anki_folder_entry.set_text(dialog.get_filename())
                self.check_anki_collection()
            dialog.destroy()
            return False
        dialog.connect("selection_changed", selection_changed)
        dialog.connect("response", response)
        #dialog.set_current_folder(self.config.anki_folder)
        dialog.show()
        return False

    def anki_folder_entry_focus_out_event(self, entry, event):
        path = os.path.expanduser(entry.get_text())
        entry.set_text(path)
        self.check_anki_collection()
        return False

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
        def response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                self.photo_roster_entry.set_text(dialog.get_filename())
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

    def tag_entry_focus_out_event(self, entry, event):
        self.check_tag()
        return False

    def start_button_clicked(self, button):
        print("Go!")
        return
        ankifilepath = args.photoroster[:-4] + ".Anki_Import.txt"
        photodir = os.path.join(args.ankidir, "collection.media")
        if not os.path.isdir(photodir):
            raise FileNotFoundError("Directory {} does not exist".format(photodir))
        existing_students = load_existing_students(args.ankidir)
        print("Read {} existing people from Anki.".format(len(existing_students)))
        with open(ankifilepath, "w") as ankifile:
            this_course = None
            for student in photo_roster_iterator(args.photoroster):
                if this_course is None:
                    course_tag = " {} ".format(student.tags[0])
                    this_course = {idnumber for idnumber, (pn, fn, tags) in 
                            existing_students.items() if course_tag in tags}
                    print("    {} of them in this class.".format(len(this_course)))
                this_course.discard(student.idnumber)
                student.save_image(photodir, duplicate_callback=warn_user_callback)
                check_existing(student, existing_students)
                print(student, file=ankifile)
        if this_course:
            print("The following students were already tagged as being in this ")
            print("course in your Anki database, but they're not on this roster. ")
            print("This probably means you've previously imported a roster for ")
            print("this class, and these students have since dropped the class: ")
        for idnumber in this_course:
            preferredname, fullname, tags = existing_students[idnumber]
            print("    {} ({})".format(preferredname, fullname))

    def quit_button_clicked(self, button, event=None):
        Gtk.main_quit()
        return False


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



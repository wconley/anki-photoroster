#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import re
import sqlite3
import json
import shutil
import filecmp
from contextlib import ExitStack
from tempfile import TemporaryDirectory

import gi
gi.require_version("Poppler", "0.18")
gi.require_version("Gdk", "3.0")
from gi.repository import Poppler
from gi.repository import Gdk

pdfimages_path = shutil.which("pdfimages")


def load_existing_students(ankidir):
    "Load the existing Anki data. This has nothing to do with PDFs."

    existing_students = {}
    ankidir = os.path.abspath(os.path.expanduser(ankidir))
    uri = "file://{}?mode=ro".format(os.path.join(ankidir, "collection.anki2"))
    with sqlite3.connect(uri, uri=True) as db:
        models = json.loads(db.execute("SELECT models FROM col;").fetchone()[0])
        for modelID, model in models.items():
            if model["name"] == "Names and faces":
                break
        else:
            raise ValueError("Did not find note type called 'Names and faces'.")
        cursor = db.execute("SELECT flds, tags FROM notes WHERE mid = ? ;", 
                (modelID, ))
        for (fields, tags) in cursor:
            idnumber, url, prefname, fullname, *junk = fields.split("\x1f")
            existing_students[idnumber] = (prefname, fullname, tags)
    return existing_students


TERM_ABBREVS = {"W": "Winter", "S": "Spring", "1": "Summer", "F": "Fall"}
COURSEDESC_FORMAT = re.compile(r'\s*(\S+)\s+(\S+)\s+\S+\s+(\S+)\s+-\s+(\S+)\s*')
class PhotoRoster(object):
    def __init__(self, path):
        "Create a PhotoRoster object from the photo roster PDF file at 'path'"

        self.path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(self.path):
            raise FileNotFoundError("File not found: {}".format(self.path))
        uri = "file://" + self.path
        self.roster = Poppler.Document.new_from_file(uri)
        self._course_tag = None

    @property
    def num_students(self):
        "Quickly calculate the number of students in this photo roster"

        n = self.roster.get_n_pages() - 1
        return n * 6 + len(self.roster.get_page(n).get_image_mapping())

    @property
    def course_tag(self):
        "Get the course tag (e.g. 'MATH115A-7-Fall-2013') from top of roster"

        if self._course_tag is None:
            header_text = self.roster.get_page(0).get_text().splitlines()[0]
            match = COURSEDESC_FORMAT.fullmatch(
                    header_text[len("Photo Roster for "):])
            if not match:
                raise ValueError("Could not parse course description {}".format(
                        header_text))
            subject, coursenumber, section, term = match.groups()
            term, year = TERM_ABBREVS[term[2]], term[:2]
            self._course_tag = "{}{}-{}-{}-20{}".format(subject, coursenumber, 
                    section, term, year)
        return self._course_tag

    ##### The main function (generator) that does most of the work #####
    def __iter__(self):
        "Iterate over this roster, yielding a Student object for each student"

        with ExitStack() as context_mgr_stack: # Does nothing, for now
            if pdfimages_path:
                # Create a temp directory, and dump all the photos in it
                # Thanks to the context manager, it's automagically cleaned up
                tempdir = context_mgr_stack.enter_context(TemporaryDirectory())
                image_prefix = os.path.join(tempdir, "photo")
                subprocess.check_call(
                        [pdfimages_path, "-j", self.path, image_prefix], 
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Now iterate over all the students in the roster
            for pagenumber in range(self.roster.get_n_pages()):
                page = self.roster.get_page(pagenumber)
                pagetext = [(rect.y1, rect.x1, char) for char, rect in 
                        zip(page.get_text(), page.get_text_layout()[1])]
                for image_map in page.get_image_mapping():
                    # Top left corner of image:
                    x1, y1 = image_map.area.x1, image_map.area.y1
                    # Grab the text for the student ID number
                    idnumber = PhotoRoster.get_first_line(pagetext, 
                            x1 + 169, x1 + 270, y1, y1 + 197)
                    # Grab the text for the name
                    name = PhotoRoster.get_first_line(pagetext, 
                            x1, x1 + 270, y1 + 197, y1 + 216)
                    # Get the image
                    if pdfimages_path:
                        imagenumber = pagenumber * 6 + image_map.image_id
                        image = "{}-{:03}.jpg".format(image_prefix, imagenumber)
                    else:
                        image = page.get_image(image_map.image_id)
                    # Construct a Student object and yield it
                    yield Student(idnumber, name, image, self.course_tag)

    @staticmethod
    def get_first_line(pagetext, xmin, xmax, ymin, ymax):
        """Get the first line of text within an area of a page"""

        text = [(y, c) for y, x, c in pagetext if 
                xmin <= x <= xmax and ymin <= y <= ymax and c != "\n"]
        top_y = min([y for y, c in text])
        return "".join([c for y, c in text if y == top_y]).strip()


class Student(object):
    """A class to represent a single student's information and photo"""

    def __init__(self, idnumber, name, photo, tags):
        self.idnumber = idnumber
        self.name_on_roster = name
        self.preferredname, self.fullname = Student._format_name(name)
        self.photo = photo
        self.tags = tags.split()

    def photo_filename(self):
        return "UCLA_Student_{}.jpg".format(self.idnumber)

    def save_photo(self, directory):
        """Saves the photo to the specified directory

        If there was already an existing photo for this student, and the 
        existing file is *not* identical to the new one, then the existing 
        photo is backed up to a backup file, and the name of the backup file is 
        returned. Otherwise, the return value from this function is None. This 
        allows the caller to check the return value and either delete the 
        backup file, inform the user of the existence of the backup file, or 
        even present the user with a choice of which file to keep. For the 
        latter case, note that the path to the new photo will be 
            os.path.join(directory, student.photo_filename)
        """

        photopath = os.path.join(directory, self.photo_filename())
        photopath_new = photopath_backup = photopath
        i = 0
        while os.path.exists(photopath_backup):
            i += 1
            photopath_backup = "{}.old{}.jpg".format(photopath[:-4], i)
        if photopath_backup != photopath:
            photopath_new = photopath + ".NEW"
        if pdfimages_path:
            shutil.move(self.photo, photopath_new)
        else:
            pixbuf = Gdk.pixbuf_get_from_surface(self.photo, 0, 0, 
                    self.photo.get_width(), self.photo.get_height())
            pixbuf.savev(photopath_new, "jpeg", ["quality"], ["90"])
        if photopath_backup == photopath: # There was no existing photo
            return None
        if filecmp.cmp(photopath, photopath_new): # New photo is same as old
            os.remove(photopath_new)
            return None
        os.rename(photopath, photopath_backup)
        os.rename(photopath_new, photopath)
        return photopath_backup # New and old photos are different!

    def merge_tags(self, tags):
        for tag in self.tags:
            if tag not in tags:
                tags.append(tag)
        self.tags = tags

    def __str__(self):
        imagetag = '<img src="{}">'.format(self.photo_filename())
        return ";".join((self.idnumber, imagetag, self.preferredname, 
                self.fullname, " ".join(self.tags)))

    ##### Several methods to deal with formatting names nicely #####
    _PARENSFORMAT = re.compile(r'(.*)[(](.*)[)](.*)')
    @staticmethod
    def _format_name(name):
        """Take a name as provided by the registrar, and format it nicely

        The UCLA registrar/my.ucla provides names formatted as 
            LASTNAMES, FIRSTNAMES MIDDLENAMES, SUFFIX
        in all uppercase. More recently, they have started providing the option 
        for students to specify a preferred name, if they wish to be called 
        something other than their "official" first name. In that case, the 
        format is 
            LASTNAMES, PREFERREDNAMES (FIRSTNAMES)
        also in all uppercase. (I have yet to see a name in this format with a 
        suffix.) This method attempts to parse these name formats, decide on 
        an appropriate "preferred name" and "full name", and adjust the case of 
        these so that they're not all uppercase. 

        Arguments: 
            name - A name in one of the formats above, as provided by my.ucla
        Returns: 
            A 2-tuple of the form (preferred_name, full_name)
        """

        match = Student._PARENSFORMAT.match(name)
        if match:
            name, realfirstname, junk = match.groups()
            realfirstname = Student._name_fixcase(realfirstname)
            if junk:
                raise ValueError("Unexpected characters after parentheses " + 
                        "in name {}".format(name))
        else:
            realfirstname = ""
        components = name.split(", ")
        if len(components) > 3:
            raise ValueError("Too many components in name {}".format(name))
        if len(components) == 3:
            suffix = components[2]
            if suffix == "JR" or suffix == "SR":
                suffix = suffix.title()
        else:
            suffix = ""
        if len(components) >= 2:
            if realfirstname:
                firstname = Student._name_fixcase(components[1])
                middlename = ""
            else:
                firstname, junk, middlename = components[1].partition(" ")
                firstname = Student._name_fixcase(firstname)
                middlename = Student._name_fixcase(middlename)
                realfirstname = firstname
        else:
            firstname = middlename = ""
        lastname = Student._name_fixcase(components[0])
        if firstname:
            preferredname = "{} {}".format(firstname, lastname)
        else:
            preferredname = lastname
        fullname = " ".join(filter(None, 
                (realfirstname, middlename, lastname, suffix)))
        return preferredname, fullname

    @staticmethod
    def _name_fixcase(name):
        "Correct the case (and possibly spacing) of an entire name"

        return " ".join([Student._name_fixcase_hyphenated(word) for word in 
                name.split()])

    @staticmethod
    def _name_fixcase_hyphenated(name):
        "Take a single (possibly-hyphenated) word from a name, correct its case"

        if name in ("DE", "EL", "LA", "LOS", "LAS"):
            return name.lower()
        return "-".join([Student._name_fixcase_word(word) for word in 
                name.split("-")])

    @staticmethod
    def _name_fixcase_word(name):
        "Take a single (nonhyphenated) word from a name, correct its case"

        name = name[:1] + name[1:].lower()    # No, I don't mean to use title()
        if name[:2] in ("Mc", "O'", "D'"):
            name = name[:2] + name[2:3].upper() + name[3:]
        return name



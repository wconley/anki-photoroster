#!/usr/bin/env python3

import os
import subprocess
import re
import csv
import shutil
import filecmp
from contextlib import ExitStack
from tempfile import TemporaryDirectory

import gi
gi.require_version("Poppler", "0.18")
gi.require_version("Gdk", "3.0")
from gi.repository import Poppler
from gi.repository import Gdk

USE_PDFIMAGES_PROGRAM = False


def load_existing_students(existingfilepath):
    "Load the existing Anki data, if given. This has nothing to do with PDFs."

    existing_students = {}
    if existingfilepath:
        with open(existingfilepath, newline="") as existingfile:
            csvreader = csv.reader(existingfile, delimiter="\t")
            for idnumber, url, prefname, fullname, foo, bar, tags in csvreader:
                existing_students[idnumber] = (prefname, fullname, tags)
    return existing_students


def open_pdf_file(path):
    "Resolves the path and opens the PDF file, using Poppler"

    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise FileNotFoundError("File not found: {}".format(path))
    uri = "file://" + path
    return Poppler.Document.new_from_file(uri)


def get_num_students(roster):
    "Quickly calculate the number of students in the roster"

    n = roster.get_n_pages() - 1
    return n * 6 + len(roster.get_page(n).get_image_mapping())


TERM_ABBREVS = {"W": "Winter", "S": "Spring", "1": "Summer", "F": "Fall"}
COURSEDESC_FORMAT = re.compile(r'\s*(\S+)\s+(\S+)\s+\S+\s+(\S+)\s+-\s+(\S+)\s*')
def get_course_tag(roster):
    "Get the course tag (e.g. 'MATH115A-7-Fall-2013') from the top of 'roster'"

    header_text = roster.get_page(0).get_text().splitlines()[0]
    match = COURSEDESC_FORMAT.fullmatch(header_text[len("Photo Roster for "):])
    if not match:
        raise ValueError("Could not parse the course description {}".format(
                header_text))
    subject, coursenumber, section, term = match.groups()
    term, year = TERM_ABBREVS[term[2]], term[:2]
    return "{}{}-{}-{}-20{}".format(subject, coursenumber, section, term, year)


##### The main function (generator actually) that does most of the work #####
def photo_roster_iterator(path):
    "Iterate over a photo roster, yielding a Student object for each student"

    with ExitStack() as context_manager_stack: # Does nothing, for now
        if USE_PDFIMAGES_PROGRAM:
            # Create a temp directory, and dump all the photos in it.
            # Thanks to the context manager, it's automagically cleaned up later
            tempdir = context_manager_stack.enter_context(TemporaryDirectory())
            image_prefix = os.path.join(tempdir, "photo")
            subprocess.check_call(["pdfimages", "-j", path, image_prefix], 
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        roster = open_pdf_file(path)
        course_tag = get_course_tag(roster)
        # Now iterate over all the students in the roster
        for pagenum in range(roster.get_n_pages()):
            page = roster.get_page(pagenum)
            pagetext = [(rect.y1, rect.x1, char) for char, rect in 
                    zip(page.get_text(), page.get_text_layout()[1])]
            for image_map in page.get_image_mapping():
                # Grab the text for the student ID number
                xmin, xmax = image_map.area.x1 + 169, image_map.area.x1 + 270
                ymin, ymax = image_map.area.y1, image_map.area.y2
                idnumber = pdf_get_text_line(pagetext, xmin, xmax, ymin, ymax)
                # Grab the text for the name
                xmin, xmax = image_map.area.x1, image_map.area.x1 + 270
                ymin, ymax = image_map.area.y1 + 197, image_map.area.y1 + 216
                name = pdf_get_text_line(pagetext, xmin, xmax, ymin, ymax)
                # Get the image
                if USE_PDFIMAGES_PROGRAM:
                    image_number = pagenum * 6 + image_map.image_id
                    image = "{}-{:03}.jpg".format(image_prefix, image_number)
                else:
                    image = page.get_image(image_map.image_id)
                # Construct a Student object and yield it
                yield Student(idnumber, name, image, course_tag)


def pdf_get_text_line(pagetext, xmin, xmax, ymin, ymax):
    """Get the first line of text within an area of a page"""

    text = [(y, c) for y, x, c in pagetext if 
            xmin <= x <= xmax and ymin <= y <= ymax and c != "\n"]
    top_y = min([y for y, c in text])
    return "".join([c for y, c in text if y == top_y]).strip()


class Student(object):
    """A class to represent a single student's information and photo"""

    def __init__(self, idnumber, name, image, tags):
        self.idnumber = idnumber
        self.preferredname, self.fullname = Student._format_name(name)
        self.image = image
        self.tags = tags.split()

    def image_filename(self):
        return "UCLA_Student_{}.jpg".format(self.idnumber)

    def save_image(self, directory, duplicate_callback=None):
        oldpath = None
        savepath = os.path.join(directory, self.image_filename())
        if os.path.exists(savepath):
            oldpath = savepath
            savepath = savepath[:-4] + ".new.jpg"
        if USE_PDFIMAGES_PROGRAM:
            shutil.move(self.image, savepath)
        else:
            pixbuf = Gdk.pixbuf_get_from_surface(self.image, 0, 0, 
                    self.image.get_width(), self.image.get_height())
            pixbuf.savev(savepath, "jpeg", ["quality"], ["90"])
        if oldpath:
            if filecmp.cmp(oldpath, savepath):
                # The new one is identical to the old one
                os.remove(savepath)
            elif duplicate_callback:
                duplicate_callback(self, oldpath, savepath)

    def merge_tags(self, tags):
        for tag in self.tags:
            if tag not in tags:
                tags.append(tag)
        self.tags = tags

    def __str__(self):
        imagetag = '<img src="{}">'.format(self.image_filename())
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



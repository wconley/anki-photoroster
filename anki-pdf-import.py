#!/usr/bin/env python3
# -*- coding: utf-8 -*-
DESCRIPTION = "Create an Anki import file from a UCLA photo roster PDF file"
EPILOG = """
This program will extract student names, ID numbers, and photos from a UCLA 
photo roster (in PDF format, as can be downloaded from my.ucla), and allow them 
to be imported into Anki. For this to work correctly, you must use the large 
format photo roster with 6 students per page, not the smaller format with 30 
students per page. 

The student photos that are extracted from the PDF file will be placed directly 
in your Anki data folder, in the collection.media subfolder where they belong. 

If you already have some of these same students in your Anki collection (for 
example, if you've already imported this class, but you're re-importing it 
because some students have added/dropped the class, or if you keep your former 
students in the collection, and some of those former students are in this class 
as well) then this program will keep the existing names and tags as they are in 
your Anki collection (possibly adding one new tag for this class), rather than 
overwriting them. However, it will warn you about any differences it finds in 
the names. If a student is already in your Anki collection and their photo in 
the new photo roster is different from the one in your Anki collection, then 
this program will replace the existing photo in Anki with the new one from the 
photo roster. However, it will keep the old photo with an extension of 
.oldX.jpg (where X = 1, 2, etc). This way you can check the two photos later 
and decide which one to keep. Running "Check media" in Anki will clear out 
these duplicate photos. (All of this functionality should be improved in a 
later version.) 
"""

import os
import argparse

from photoroster import load_existing_students, PhotoRoster


def parse_args():
    parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG, 
            formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("photoroster", 
        help="""Name of the PDF file containing the photo roster, as downloaded 
            from my.ucla. Note that this must be in the "large" format, with 6 
            photos per page, rather than 30 photos per page. A new text file 
            will be created, with the same name as this file and in the same 
            directory, but with the ".pdf" extension replaced by 
            ".Anki_Import.txt". You can then import this file into Anki.""")
    parser.add_argument("ankidir", 
        help="""The directory where your personal Anki files are stored. On a 
            Mac or Linux system, this will usually be ~/Anki/[YOUR NAME]/""")
    return parser.parse_args()


##### The following functions should probably be customized further #####
def check_existing(student, existing_students):
    existing = existing_students.get(student.idnumber)
    if not existing:
        return
    preferredname, fullname, tags = existing
    if preferredname != student.preferredname or fullname != student.fullname:
        print("WARNING: Names don't match up for {}:".format(student.idnumber))
        if preferredname != student.preferredname:
            print("    Preferred name in Anki is {}, new one is {}.".format(
                    preferredname, student.preferredname))
        if fullname != student.fullname:
            print("    Full name in Anki is {}, new one is {}.".format(
                    fullname, student.fullname))
        print("    Keeping the names in Anki. You may want to change this.")
        student.preferredname = preferredname
        student.fullname = fullname
    student.merge_tags(tags.split())


def warn_user_callback(student, oldpath, newpath):
    root, extension = os.path.splitext(oldpath)
    n = 1
    while True:
        new_oldpath = "{}.old{}{}".format(root, n, extension)
        if not os.path.exists(new_oldpath):
            break
        n += 1
    os.rename(oldpath, new_oldpath)
    os.rename(newpath, oldpath)
    print("WARNING: A different photo already exists for {}.".format(
            student.preferredname))
    print("    Leaving both in the photos directory.")
    print("    The old one is {}.".format(new_oldpath))
    print("    The new one is {}.".format(oldpath))


if __name__ == "__main__":
    args = parse_args()
    if args.photoroster.lower()[-4:] != ".pdf":
        raise ValueError("{} does not appear to be a PDF file".format(
                args.photoroster))
    ankifilepath = args.photoroster[:-4] + ".Anki_Import.txt"
    photodir = os.path.join(args.ankidir, "collection.media")
    if not os.path.isdir(photodir):
        raise FileNotFoundError("Directory {} does not exist".format(photodir))
    existing_students = load_existing_students(args.ankidir)
    print("Read {} existing people from Anki.".format(len(existing_students)))
    roster = PhotoRoster(args.photoroster)
    course_tag = " {} ".format(roster.course_tag)
    this_course = {idnumber for idnumber, (pn, fn, tags) in 
            existing_students.items() if course_tag in tags}
    print("    {} of them in this class.".format(len(this_course)))
    with open(ankifilepath, "w") as ankifile:
        for student in roster:
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



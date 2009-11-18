# Copyright (C) Cmed Ltd, 2008, 2009
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation; either version 2.1 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA
# 02110-1301, USA.

import os
import unittest

import cmd_env


class ProcessListTest(unittest.TestCase):

    def test_list_processes(self):
        # Assumes /proc is available
        matches = [proc for proc in cmd_env.list_processes()
                   if proc.get_pid() == os.getpid()]
        self.assertEquals(len(matches), 1)
        self.assertEquals(matches[0].get_root_dir(), "/")


class IsPathBelowTest(unittest.TestCase):

    def test(self):
        cases = [("/foo", "/foobar", False),
                 ("/foo", "/bar", False),
                 ("/foo", "/foo/bar", True),
                 ("/foo/", "/foo/bar", True)]
        for parent, child, is_below in cases:
            self.assertEquals(cmd_env.is_path_below(parent, child), is_below)


if __name__ == "__main__":
    unittest.main()

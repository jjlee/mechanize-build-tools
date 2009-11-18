
# Copyright (C) 2008 Mark Seaborn
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

"""
%prog <logset-dir>

Make a warning noise if the most recent completed log contains failures.
"""

import optparse
import sys

import build_log


def main(argv):
    parser = optparse.OptionParser(__doc__.strip())
    options, args = parser.parse_args(argv)
    [log_dir] = args
    logset = build_log.LogSetDir(log_dir)
    build_log.warn_failures(logset.get_logs(), 0)


if __name__ == "__main__":
    main(sys.argv[1:])

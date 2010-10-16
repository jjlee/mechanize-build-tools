
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
%prog [--short] <logset-dir> <output-file>

Output HTML version of logs.
"""

import gc
import optparse
import sys

from build_log import tag
import build_log


def main(argv):
    parser = optparse.OptionParser(__doc__.strip())
    parser.add_option(
        "--short", default=False, dest="short", action="store_true",
        help="Short version, only showing top-level items and errors")
    options, args = parser.parse_args(argv)
    log_dir, output_file = args
    logset = build_log.LogSetDir(log_dir)
    body = build_log.tag("body")
    for log in logset.get_logs():
        if options.short:
            xml = build_log.format_short_summary(
                log.get_xml(), build_log.NullPathnameMapper())
        else:
            xml = build_log.format_top_log(
                log.get_xml(), build_log.NullPathnameMapper())
        body.append(xml)
        body.append(tag("hr"))
    build_log.write_xml_file(output_file, build_log.wrap_body(body))


if __name__ == "__main__":
    main(sys.argv[1:])

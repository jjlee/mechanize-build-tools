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

"""
Usage: python in_chroot_test.py -d CHROOT_DIR
"""

import optparse
import os
import subprocess
import sys


# This is not a fully automated test.
# It requires an already-existing chroot.


def call(args, **kwargs):
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, **kwargs)
    stdout, stderr = proc.communicate()
    rc = proc.wait()
    assert rc == 0, (rc, args, kwargs)
    return stdout


def main(argv):
    parser = optparse.OptionParser("in_chroot [options] command args...")
    parser.add_option("-d", "--chroot-dir", dest="chroot_dir",
                      help="Chroot directory to use")
    options, args = parser.parse_args(argv)
    assert len(args) == 0
    assert options.chroot_dir is not None

    assert "DISPLAY" in os.environ
    assert "SSH_AUTH_SOCK" in os.environ

    in_chroot = ["python", os.path.join(os.path.dirname(__file__),
                                        "in_chroot.py")]

    # Test that command is run as normal user
    stdout = call(in_chroot + ["-d", options.chroot_dir, "id", "-u"])
    expect = "%i\n" % os.getuid()
    assert stdout == expect, (stdout, expect)

    # Test that -s runs the command as root
    stdout = call(in_chroot + ["-d", options.chroot_dir, "-s", "id", "-u"])
    expect = "0\n"
    assert stdout == expect, (stdout, expect)

    # Test that random environment variables are not passed through
    stdout = call(["env", "FOO=BAR"] + in_chroot +
                  ["-d", options.chroot_dir, "sh", "-c", "echo $FOO"])
    expect = "\n"
    assert stdout == expect, (stdout, expect)

    # Test that HOME is set though, because so much depends on it.
    stdout = call(in_chroot + ["-d", options.chroot_dir,
                               "sh", "-c", "echo $HOME"])
    assert stdout.startswith("/"), stdout

    # Test that DISPLAY is not set when -X is not passed
    stdout = call(in_chroot + ["-d", options.chroot_dir,
                               "sh", "-c", "echo $DISPLAY"])
    expect = "\n"
    assert stdout == expect, (stdout, expect)

    # Test that -X forwards the X display
    # Assumes that X tools are installed in chroot
    stdout = call(in_chroot + ["-d", options.chroot_dir, "-X", "xdpyinfo"])
    assert stdout != "\n"

    # Test that SSH_AUTH_SOCK is not set when -A is not passed
    stdout = call(in_chroot + ["-d", options.chroot_dir,
                               "sh", "-c", "echo $SSH_AUTH_SOCK"])
    expect = "\n"
    assert stdout == expect, (stdout, expect)

    # Test that SSH_AUTH_SOCK is passed through when -A is given
    stdout = call(in_chroot + ["-d", options.chroot_dir,
                               "-A", "sh", "-c", "echo $SSH_AUTH_SOCK"])
    expect = "%s\n" % os.environ["SSH_AUTH_SOCK"]
    assert stdout == expect, (stdout, expect)

    # TODO: test that ssh agent forwarding actually works.
    # We would need an ssh server to connect to.

    print "ok"


if __name__ == "__main__":
    main(sys.argv[1:])

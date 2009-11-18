#!/usr/bin/env python

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

import optparse
import os
import sys

import cmd_env


def remove_prefix(prefix, string):
    assert string.startswith(prefix)
    return string[len(prefix):]


def get_chroot_from_cwd():
    if "CHROOTS_DIR" not in os.environ:
        # TODO: print errors more nicely
        raise Exception("Set CHROOTS_DIR to the directory containing "
                        "chroot directories or use the -d option")
    chroots_dir_path = os.environ["CHROOTS_DIR"]
    cwd = os.getcwd()
    chroots = [os.path.realpath(os.path.join(chroots_dir, leafname))
               for chroots_dir in chroots_dir_path.split(":")
               for leafname in os.listdir(chroots_dir)]
    for chroot_dir in chroots:
        cwd_in_chroot = get_cwd_in_chroot(chroot_dir)
        if cwd_in_chroot is not None:
            return chroot_dir, cwd_in_chroot
    raise Exception("cwd not in a defined chroot: %s" % cwd)


def get_cwd_in_chroot(chroot_dir):
    cwd = os.getcwd()
    if cwd == chroot_dir:
        return "/"
    elif cwd.startswith(chroot_dir + "/"):
        return remove_prefix(chroot_dir, cwd)
    else:
        return None


def main(argv):
    parser = optparse.OptionParser("in_chroot [options] command args...")
    parser.allow_interspersed_args = False
    parser.add_option("-d", "--chroot-dir", dest="chroot_dir",
                      help="Chroot directory to use")
    parser.add_option("-s", "--su", "--sudo", dest="as_superuser",
                      default=False, action="store_true",
                      help="Run command as superuser instead of normal user")
    parser.add_option("--user", dest="user",
                      help="User to run the command as")
    parser.add_option("-X", dest="forward_x11",
                      default=False, action="store_true",
                      help="Forward X11 access")
    parser.add_option("-A", dest="forward_ssh_agent",
                      default=False, action="store_true",
                      help="Forward SSH agent")
    parser.add_option("-v", dest="verbose", default=False, action="store_true",
                      help="Verbose: print commands executed")
    options, args = parser.parse_args(argv)

    basic_env = cmd_env.BasicEnv()
    if options.verbose:
        basic_env = cmd_env.VerboseWrapper(basic_env)

    if options.chroot_dir is None:
        options.chroot_dir, cwd_in_chroot = get_chroot_from_cwd()
    else:
        options.chroot_dir = os.path.realpath(options.chroot_dir)
        cwd_in_chroot = get_cwd_in_chroot(options.chroot_dir)

    if len(args) == 0:
        parser.error("No command name given")

    # TODO: use xsudo?
    as_root = cmd_env.PrefixCmdEnv(["sudo"], basic_env)

    if options.user is None:
        # TODO: use SUDO_USER/SUDO_UID when invoked through sudo
        options.user = "#%i" % os.getuid()
    if options.as_superuser:
        options.user = None
    in_chroot = cmd_env.chroot_and_sudo_env(
        options.chroot_dir, as_root, os.environ,
        user=options.user,
        do_forward_x11=options.forward_x11,
        do_forward_ssh_agent=options.forward_ssh_agent)

    in_chroot = cmd_env.bash_login_env(in_chroot)

    if cwd_in_chroot is not None:
        in_chroot = cmd_env.PrefixCmdEnv(cmd_env.in_dir(cwd_in_chroot),
                                         in_chroot)
    if "TERM" in os.environ:
        in_chroot = cmd_env.PrefixCmdEnv(
            ["env", "TERM=%s" % os.environ["TERM"]], in_chroot)

    in_chroot.cmd(args, fork=False)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(1)

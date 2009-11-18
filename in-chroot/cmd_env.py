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

import errno
import os
import pprint
import signal
import subprocess
import time


def read_file(filename):
    fh = open(filename, "r")
    try:
        return fh.read()
    finally:
        fh.close()


def write_file(filename, data):
    fh = open(filename, "w")
    try:
        fh.write(data)
    finally:
        fh.close()


class CommandFailedError(Exception):

    def __init__(self, message, rc):
        Exception.__init__(self, message)
        self.rc = rc


class BasicEnv(object):

    def cmd(self, args, do_wait=True, fork=True, **kwargs):
        if fork:
            process = subprocess.Popen(args, **kwargs)
            if do_wait:
                rc = process.wait()
                if rc != 0:
                    raise CommandFailedError(
                        "Command failed with return code %i: %s" % (rc, args),
                        rc)
            return process
        else:
            # TODO: support other keyword args
            assert len(kwargs) == 0, kwargs
            os.execvp(args[0], args)


def call(args, **kwargs):
    return BasicEnv().cmd(args, **kwargs)


class VerboseWrapper(object):

    def __init__(self, env):
        self._env = env

    def cmd(self, args, **kwargs):
        pprint.pprint(args)
        return self._env.cmd(args, **kwargs)


class PrefixCmdEnv(object):

    def __init__(self, prefix_cmd, env):
        self._prefix_cmd = prefix_cmd
        self._env = env

    def cmd(self, args, **kwargs):
        return self._env.cmd(self._prefix_cmd + args, **kwargs)
        

def in_dir(dir_path):
    return ["sh", "-c", 'cd "$1" && shift && exec "$@"',
            "inline_chdir_script", dir_path]


def write_file_cmd(filename, data):
    return ["sh", "-c", 'echo -n "$1" >"$2"', "inline_script", data, filename]


def append_file_cmd(filename, data):
    return ["sh", "-c", 'echo -n "$1" >>"$2"', "inline_script", data, filename]


def clean_environ_except_home_env(env):
    # Resets everything except HOME, so make sure wrapped env sets
    # HOME correctly (e.g. sudo -H).
    path = "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    return PrefixCmdEnv(
        ["sh", "-c", 'env -i HOME="$HOME" %s "$@"' % path,
         "clean_environ_env"], env)


def set_environ_vars_env(vars, env):
    return PrefixCmdEnv(["env"] + ["%s=%s" % (key, value)
                                   for key, value in vars], env)


def get_all_mounts():
    fh = open("/proc/mounts", "r")
    for line in fh:
        parts = line.split()
        yield parts[1]
    fh.close()


def is_mounted(path):
    return os.path.realpath(path) in list(get_all_mounts())


def is_path_below(parent, child):
    parent = parent.rstrip("/")
    child = child.rstrip("/")
    return parent == child or child.startswith(parent + "/")


DELETED_SUFFIX = "\\040(deleted)"


def get_mounts_below(pathname):
    prefix = os.path.realpath(pathname)
    for mount_path in get_all_mounts():
        # The 2.6.22-14 kernel on our buildbot machine seems to add
        # this to lines in /proc/mounts if the source directory of the
        # bind mount gets deleted.
        if mount_path.endswith(DELETED_SUFFIX):
            mount_path = mount_path[:-len(DELETED_SUFFIX)]
        if is_path_below(prefix, mount_path):
            yield mount_path


def unmount_below(as_root, dir_path):
    # When you use "mount --rbind", you can end up with bind mounts
    # under bind mounts, such as /dev and /dev/pts.  The latter needs
    # to get unmounted first, so sort longest first.
    mounts = sorted(get_mounts_below(dir_path), key=len, reverse=True)
    for mount_path in mounts:
        as_root.cmd(["umount", mount_path])


def mount_proc(root_env, chroot_dir):
    proc_path = os.path.join(chroot_dir, "proc")
    if not is_mounted(proc_path):
        root_env.cmd(["mount", "-t", "proc", "proc", proc_path])


def bind_mount_dev_log(root_env, chroot_dir):
    # Needed for logging to work inside a chroot
    devlog_path = os.path.join(chroot_dir, "dev", "log")
    if not is_mounted(devlog_path):
        root_env.cmd(["touch", devlog_path])
        root_env.cmd(["mount", "--bind", "/dev/log", devlog_path])


def mount_dev_pts(root_env, chroot_dir):
    # /dev/ptmx and /dev/pts are needed for openpty() to work.
    devpts_path = os.path.join(chroot_dir, "dev", "pts")
    if not is_mounted(devpts_path):
        root_env.cmd(["mount", "-t", "devpts", "devpts", devpts_path])


def mount_sys(root_env, chroot_dir):
    # Needed for activitymonitor in chroots on machines without a static IP
    sys_path = os.path.join(chroot_dir, "sys")
    if not is_mounted(sys_path):
        root_env.cmd(["mount", "-t", "sysfs", "sys", sys_path])


def bind_mount_x11(root_env, chroot_dir):
    dest_path = os.path.join(chroot_dir, "tmp/.X11-unix")
    if not is_mounted(dest_path):
        root_env.cmd(["mount", "--bind", "/tmp/.X11-unix", dest_path])


class EnvWithHook(object):

    # Wrapper for an environment with a hook function that gets run
    # the first time the wrapper is used.

    def __init__(self, hook_func, env):
        self._hook_func = hook_func
        self._env = env

    def cmd(self, args, **kwargs):
        self._hook_func()
        self._hook_func = lambda: None
        return self._env.cmd(args, **kwargs)


def chroot_env(chroot_dir, as_root, environ_vars,
               do_forward_x11=False, do_forward_ssh_agent=False):
    def hook():
        # This reads the local /proc/mounts so will not work properly
        # if as_root is remote.
        mount_proc(as_root, chroot_dir)
        mount_sys(as_root, chroot_dir)
        bind_mount_dev_log(as_root, chroot_dir)
        mount_dev_pts(as_root, chroot_dir)
        if do_forward_x11:
            bind_mount_x11(as_root, chroot_dir)
            as_root.cmd(["bash", "-c",
                         """\
xauth nlist | HOME=/root env -u XAUTHORITY chroot "$1" xauth nmerge -""",
                         "inline_chroot_script", chroot_dir])
        if do_forward_ssh_agent:
            forward_ssh_agent(as_root, environ_vars, chroot_dir)
    after_hook = EnvWithHook(hook, as_root)
    if do_forward_x11:
        # Unset XAUTHORITY so that it is treated as defaulting to
        # $HOME/.Xauthority.
        return PrefixCmdEnv(["env", "-u", "XAUTHORITY", "HOME=/root",
                             "chroot", chroot_dir], after_hook)
    else:
        return PrefixCmdEnv(["chroot", chroot_dir], after_hook)


# "user" is a string to pass to sudo, or None for root.
def chroot_and_sudo_env(chroot_dir, as_root, environ_vars,
                        user, do_forward_x11, do_forward_ssh_agent):
    in_chroot = chroot_env(chroot_dir, as_root, environ_vars,
                           do_forward_x11=do_forward_x11,
                           do_forward_ssh_agent=do_forward_ssh_agent)
    if user is not None:
        if do_forward_x11:
            in_chroot = xsudo_env(user, in_chroot)
        else:
            in_chroot = PrefixCmdEnv(["sudo", "-H", "-u", user], in_chroot)
    in_chroot = clean_environ_except_home_env(in_chroot)
    vars_to_keep = {}
    if do_forward_x11 and "DISPLAY" in environ_vars:
        vars_to_keep["DISPLAY"] = environ_vars["DISPLAY"]
    if do_forward_ssh_agent and "SSH_AUTH_SOCK" in environ_vars:
        vars_to_keep["SSH_AUTH_SOCK"] = environ_vars["SSH_AUTH_SOCK"]
    return set_environ_vars_env(vars_to_keep.items(), in_chroot)


def xsudo_env(user_name, env):
    # This copies all Xauthority entries across (using nlist) instead
    # of just the one for DISPLAY (which would use nextract).
    # "xauth nextract" has a bug when used with TCP displays of the
    # form "localhost:N".
    return PrefixCmdEnv(["bash", "-c", """
set -e
function my_sudo {
  sudo -H -p "Password to get from %u to %U on %H: " -u '"""+user_name+"""' "$@"
}
xauth nlist | my_sudo xauth nmerge -
my_sudo "$@"
""", "inline_sudo_script"], env)


def bash_login_env(env):
    # This is useful when running a command directly without starting
    # up an interactive shell, assuming that ~/.bash_profile or
    # ~/.bashrc are responsible for setting PYTHONPATH etc.
    #
    # This is loosely equivalent to "bash --login", which makes bash
    # load ~/.bash_profile.  This typically sets PATH to include
    # conductor/bin.  On typical ThirdPhase stations, ~/.bash_profile
    # just sources /etc/conductor/profile.
    #
    # The default Ubuntu bashrc exits early if PS1 is not set; we set
    # PS1 as a workaround.  (bash sets PS1 when started in interactive
    # mode; it unsets PS1 when started in non-interactive mode.)
    return PrefixCmdEnv(
        ["bash", "-c", """
PS1="$ "
if [ -f ~/.bash_profile ]
  then
    source ~/.bash_profile
  else
    source ~/.profile
fi
exec "$@"
""",
         "inline_shell_script"], env)


def setup_sudo(as_root, username):
    # Warning: this overwrites your sudo config
    as_root.cmd(write_file_cmd("/etc/sudoers", """\
root ALL=(ALL) ALL
%s ALL=(ALL) NOPASSWD:ALL
""" % username))


def make_relative_to_root(path):
    assert path.startswith("/")
    return path.lstrip("/")


def bind_mount(as_root, chroot_dir, abs_path):
    path = make_relative_to_root(abs_path)
    dest_path = os.path.join(chroot_dir, path)
    if not is_mounted(dest_path):
        as_root.cmd(["mkdir", "-p", dest_path])
        as_root.cmd(["mount", "--bind", os.path.join("/", path), dest_path])


def forward_ssh_agent(as_root, environ, chroot_dir):
    path = os.path.dirname(environ["SSH_AUTH_SOCK"])
    bind_mount(as_root, chroot_dir, path)


def disable_daemons(as_root):
    as_root.cmd(write_file_cmd("/usr/sbin/policy-rc.d", "#!/bin/sh\nexit 101"))
    as_root.cmd(["chmod", "+x", "/usr/sbin/policy-rc.d"])


def reenable_daemons(as_root):
    as_root.cmd(["rm", "/usr/sbin/policy-rc.d"])


class Process(object):

    def __init__(self, pid):
        self._pid = pid
        try:
            args = read_file(
                os.path.join("/proc/%i/cmdline" % pid)).split("\0")
        except (OSError, IOError), e:
            if e.errno == errno.ENOENT:
                # The process may have exited
                args = None
            else:
                raise
        if args is not None and args[-1] == "":
            # There is usually a useless trailing \0 in the cmdline
            # file, with the exception of /sbin/init and some programs
            # that modify their argv such as avahi-daemon.
            args.pop()
        self._cmdline = args
        try:
            self._root_dir = os.readlink(os.path.join("/proc/%i/root" % pid))
        except (OSError, IOError), e:
            if e.errno == errno.ENOENT:
                # * If the process terminates, /proc/$pid will not exist
                # * readlink can fail with ENOENT even if /proc/$pid/root shows
                #   up in listdir
                self._root_dir = None
            elif e.errno == errno.EACCES:
                # If we don't own the process we probably will not be
                # allowed to read this
                self._root_dir = None
            else:
                raise

    def get_pid(self):
        return self._pid

    def get_cmdline(self):
        return self._cmdline

    def get_root_dir(self):
        return self._root_dir

    def kill(self, signal_number):
        """Send the specified signal to the specified process

        Returns True if the signal was sent succesfully and False if the 
        specified process did not exist at the time of the attempt.
        """
        try:
            os.kill(self._pid, signal_number)
        except OSError, e:
            if e.errno == errno.ESRCH:
                return False
            else:
                raise
        else:
            return True


def list_processes():
    for pid_string in os.listdir("/proc"):
        try:
            pid = int(pid_string)
        except ValueError:
            pass
        else:
            yield Process(pid)


def find_chrooted(chroot):
    chroot_realpath = os.path.realpath(chroot)
    for proc in list_processes():
        if (proc.get_root_dir() is not None 
            and is_path_below(chroot_realpath, proc.get_root_dir())):
            yield proc


def kill_chrooted(chroot):
    found = set()
    while True:
        procs = list(find_chrooted(chroot))
        if len(procs) == 0:
            break
        for proc in procs:
            if proc.get_pid() not in found:
                print "killing process running in chroot:", \
                      proc.get_pid(), proc.get_cmdline()
            found.add(proc.get_pid())
            proc.kill(signal.SIGKILL)
        time.sleep(0.5)

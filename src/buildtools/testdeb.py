"""%prog WORK_DIR DEBIAN_PACKAGE_FILE

apt-get install and test a debian package in a reproducible chroot environment
using pbuilder.

TODO:
 * Put chroot in work dir (not in /var/cache/pbuilder)
 * Use linux32 as described in pbuilder docs
 * Update chroot periodically
 * Allow using cowbuilder
 * Run piuparts -a to test that purging works
   http://www.netfort.gr.jp/~dancer/software/pbuilder-doc/pbuilder-doc.html
"""

import optparse
import os
import pipes
import sys

import action_tree
import cmd_env

import release


def OutputToGzipFileEnv(env, filename):
    return release.PipeEnv(release.OutputToFileEnv(env, filename), ["gzip"])


class PbuilderActions(object):

    # def __init__(self, env, work_dir, get_deb_path, pbuilder="cowbuilder"):
    def __init__(self, env, work_dir, get_deb_path, pbuilder="pbuilder",
                 test=lambda env: True):
        self._env = env
        self._as_root = cmd_env.PrefixCmdEnv(["sudo"], env)
        self._work_dir = work_dir
        self._test = test
        self._bind_mount_dir = os.path.join(work_dir, "bind-mount")
        self._repo_dir = os.path.join(
            self._bind_mount_dir, "debian-repository")
        self._test_dir = os.path.join(self._bind_mount_dir, "test")
        # Remember to fix clean step when fix this -- don't want to clean chroot
        # self._chroot_dir = os.path.join(self._work_dir, "chroot")
        #self._chroot_base = "/var/cache/pbuilder/base.cow"
        self._chroot_base = "/var/cache/pbuilder/base.tgz"
        self._build_dir = os.path.join(self._work_dir, "build")
        self._in_test_dir = cmd_env.PrefixCmdEnv(
            cmd_env.in_dir(self._test_dir), self._env)
        self._output_file = os.path.join(self._test_dir, "output")
        self._get_deb_path = get_deb_path
        self._pbuilder = pbuilder
        # cowbuilder
        # self._pbuilder_args = ["--basepath", self._chroot_base,
        #                        "--buildplace", self._build_dir]
        self._pbuilder_args = ["--basetgz", self._chroot_base,
                               "--buildplace", self._build_dir]

    def _pbuilder_cmd(self, action, args):
        return [self._pbuilder, action] + self._pbuilder_args + args

    def install_deps(self, log):
        def ensure_installed(package_name, ppa=None):
            release.ensure_installed(self._env, self._as_root,
                                     package_name, ppa)
        ensure_installed("apt-utils")
        ensure_installed("build-essential")
        ensure_installed("pbuilder")

    def clean(self, log):
        self._as_root.cmd(["rm", "-rf", "--one-file-system", self._work_dir])
        self._env.cmd(["mkdir", "-p", self._test_dir])
        self._env.cmd(["mkdir", "-p", self._build_dir])
        self._env.cmd(["mkdir", "-p", self._repo_dir])

    def create_debian_repository(self, log):
        in_repo = cmd_env.PrefixCmdEnv(cmd_env.in_dir(self._repo_dir),
                                       self._env)
        dist = "dists/custom"
        main = os.path.join(dist, "main")
        # TODO: use linux32 as described in pbuilder docs
        # arch_code = "i386"
        arch_code = "amd64"
        arch = os.path.join(main, "binary-%s" % arch_code)
        in_repo.cmd(["mkdir", "-p", arch])
        in_repo.cmd(["mkdir", "-p", os.path.join(main, "source")])
        self._env.cmd(["cp", self._get_deb_path(),
                       os.path.join(self._repo_dir, arch)])
        in_repo.cmd(cmd_env.write_file_cmd("apt-ftparchive.conf", """\
Dir {
  ArchiveDir %(repo_dir)s;
  CacheDir %(repo_dir)s;
};

BinDirectory "dists/custom/main/binary-%(arch_code)s" {
  Packages "dists/custom/main/binary-%(arch_code)s/Packages";
  Contents "dists/custom/Contents-%(arch_code)s";
  SrcPackages "dists/custom/main/source/Sources";
};

Tree "dists/custom" {
  Sections "main";
  Architectures "%(arch_code)s source";
};

TreeDefault {
  BinCacheDB "$(DIST)/packages-$(ARCH).db"
};
""" % dict(repo_dir=os.path.abspath(self._repo_dir),
           arch_code=arch_code)))
        in_repo.cmd(cmd_env.write_file_cmd("apt-custom-release.conf", """\
APT::FTPArchive::Release::Origin "testdeb";
APT::FTPArchive::Release::Label "testdeb";
APT::FTPArchive::Release::Suite "custom";
APT::FTPArchive::Release::Codename "custom";
APT::FTPArchive::Release::Architectures "%(arch_code)s source";
APT::FTPArchive::Release::Components "main";
APT::FTPArchive::Release::Description "Custom debian packages for testdeb";
""" % dict(arch_code=arch_code)))
        OutputToGzipFileEnv(in_repo, os.path.join(arch, "Packages.gz")).cmd(
            ["apt-ftparchive",
             "--db", os.path.join(dist, "packages-%s.db" % arch_code),
             "packages", arch])
        in_repo.cmd(["apt-ftparchive", "generate", "apt-ftparchive.conf"])
        release.OutputToFileEnv(in_repo, os.path.join(dist, "Release")).cmd(
            ["apt-ftparchive", "--config-file", "apt-custom-release.conf",
             "release", dist])
        in_repo.cmd(["gpg", "--output", os.path.join(dist, "Release.gpg"),
                     "-ba", os.path.join(dist, "Release")])

    def create_chroot(self, log):
        self._env.cmd(["rm", "-rf", "--one-file-system", self._chroot_dir])
        create = self._pbuilder_cmd(
            "--create", ["--components", "main universe multiverse"])
        self._as_root.cmd(create)

    def write_test_wrapper(self, log):
        self._in_test_dir.cmd(cmd_env.write_file_cmd(
                "testrepo.list", """\
deb file://%s custom main
""" % os.path.abspath(self._repo_dir)))
        release.OutputToFileEnv(self._in_test_dir, "key").cmd(
            ["gpg", "--export", "--armor", "A362A9D1"])
        deb_name = os.path.basename(self._get_deb_path()).partition("_")[0]
        self._in_test_dir.cmd(cmd_env.write_file_cmd(
                "test.sh",
                """\
cp %(sources_list_file)s /etc/apt/sources.list.d
apt-key add %(key_file)s
apt-get update
apt-get install -y %(deb_name)s
exec "$@" > %(output_file)s
""" % dict(sources_list_file=os.path.join(self._test_dir, "testrepo.list"),
           deb_name=pipes.quote(deb_name),
           key_file=os.path.join(self._test_dir, "key"),
           output_file=self._output_file)))
        self._in_test_dir.cmd(["chmod", "+x", "test.sh"])

    def test(self, log):
        self._test.set_up(self._in_test_dir)
        in_pbuilder = cmd_env.PrefixCmdEnv(self._pbuilder_cmd(
                "--execute",
                ["--bindmounts", os.path.abspath(self._bind_mount_dir), "--",
                 os.path.join(self._test_dir, "test.sh")]), self._as_root)
        test_env = release.CwdEnv(in_pbuilder, self._test_dir)
        self._test.run_test(test_env)
        output = cmd_env.read_file(self._output_file)
        if self._test.verify(output):
            print "OK"
        else:
            sys.exit("FAIL: output:\n%s" % output)

    @action_tree.action_node
    def the_fast_bit(self):
        return [
            self.clean,
            self.create_debian_repository,
            self.write_test_wrapper,
            self.test,
            ]

    @action_tree.action_node
    def all(self):
        return [
            self.install_deps,
            self.create_chroot,
            self.the_fast_bit,
            ]


def parse_options(args):
    parser = optparse.OptionParser(usage=__doc__.strip())
    release.add_basic_env_options(parser)
    options, remaining_args = parser.parse_args(args)
    nr_args = len(remaining_args)
    try:
        options.work_dir = remaining_args.pop(0)
        options.deb_path = remaining_args.pop(0)
    except IndexError:
        parser.error("Expected at least 2 argument, got %d" % nr_args)
    return options, remaining_args


def main(argv):
    options, action_tree_args = parse_options(argv[1:])
    env = release.get_env_from_options(options)
    actions = PbuilderActions(env, options.work_dir, lambda: options.deb_path)
    action_tree.action_main(actions.all, action_tree_args)


if __name__ == "__main__":
    main(sys.argv)

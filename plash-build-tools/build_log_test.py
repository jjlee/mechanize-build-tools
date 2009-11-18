
# Copyright (C) 2007 Mark Seaborn
#
# chroot_build is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation; either version 2.1 of the
# License, or (at your option) any later version.
#
# chroot_build is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with chroot_build; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA
# 02110-1301, USA.

import cStringIO as StringIO
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import lxml.etree as etree

from chroot_build import run_cmd
import action_tree
import build_log
import format_log
import warn_log


class NodeStreamTest(unittest.TestCase):

    def test(self):
        stream = StringIO.StringIO()
        node = build_log.NodeWriter(build_log.NodeStream(stream), "root")
        node.add_attr("attr", "attribute value")
        node2 = node.new_child("child_node")
        node2.add_attr("foo", "bar")
        xml = build_log.get_xml_from_log(StringIO.StringIO(stream.getvalue()))
        self.assertEquals(etree.tostring(xml, pretty_print=True),
                          """\
<root attr="attribute value">
  <child_node foo="bar"/>
</root>\
""")


def write_file(filename, data):
    fh = open(filename, "w")
    try:
        fh.write(data)
    finally:
        fh.close()


class TempDirTestCase(unittest.TestCase):

    def setUp(self):
        super(TempDirTestCase, self).setUp()
        self._temp_dirs = []

    def tearDown(self):
        for temp_dir in self._temp_dirs:
            shutil.rmtree(temp_dir)
        super(TempDirTestCase, self).tearDown()

    def make_temp_dir(self):
        temp_dir = tempfile.mkdtemp(prefix="tmp-%s-" % self.__class__.__name__)
        self._temp_dirs.append(temp_dir)
        return temp_dir


class GoldenTestCase(unittest.TestCase):

    run_meld = False

    # Copied from xjack/golden_test.py.  TODO: share the code.
    def assert_golden(self, dir_got, dir_expect):
        assert os.path.exists(dir_expect), dir_expect
        proc = subprocess.Popen(["diff", "--recursive", "-u", "-N",
                                 "--exclude=.*", dir_expect, dir_got],
                                stdout=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        if len(stdout) > 0:
            if self.run_meld:
                # Put expected output on the right because that is the
                # side we usually edit.
                subprocess.call(["meld", dir_got, dir_expect])
            raise AssertionError(
                "Differences from golden files found.\n"
                "Try running with --meld to update golden files.\n"
                "%s" % stdout)
        self.assertEquals(proc.wait(), 0)


class LogSetDirTest(TempDirTestCase):

    def test_log(self):
        logset = build_log.LogSetDir(os.path.join(self.make_temp_dir(), "logs"))
        # It should work before the directory has been created.
        self.assertEquals(len(list(logset.get_logs())), 0)
        log = logset.make_logger()
        log2 = logset.make_logger()
        self.assertEquals(len(list(logset.get_logs())), 2)
        list(logset.get_logs())[0].get_timestamp()

    def test_start_times(self):
        class Example(object):
            def __init__(self):
                self.count = 0
            def step(self, log):
                self.count += 1
            @action_tree.action_node
            def all_steps(self):
                return [self.step] * 5
        example = Example()
        logset = build_log.LogSetDir(self.make_temp_dir(),
                                     get_time=lambda: example.count)
        log = logset.make_logger()
        example.all_steps(log)
        xml = logset.get_logs().next().get_xml()
        self.assertEquals(xml.xpath(".//@start_time"),
                          ["0", "0", "1", "2", "3", "4"])


# TODO: remove this.
class DummyTarget(object):

    def __init__(self, logset):
        self._logset = logset

    def get_name(self):
        return "dummy"

    def get_logs(self):
        return self._logset.get_logs()


class FormattingTest(TempDirTestCase, GoldenTestCase):

    def test_formatted_log_output(self):
        logs_parent_dir = self.make_temp_dir()
        logs_dir = os.path.join(logs_parent_dir, "logs")
        logset = build_log.LogSetDir(logs_dir, get_time=lambda: 0)
        log = logset.make_logger()
        sublog = log.child_log("foo")
        sublog.finish(0)
        log.finish(0)
        fh = log.make_file()
        fh.write("hello world\n")
        fh.close()
        targets = [DummyTarget(logset)]
        output_dir = self.make_temp_dir()
        mapper = build_log.PathnameMapper(logs_parent_dir)
        build_log.format_logs(
            targets, mapper, os.path.join(output_dir, "long.html"))
        format_log.main(["--short", logs_dir,
                         os.path.join(output_dir, "short.html")])
        self.assert_golden(output_dir, os.path.join(os.path.dirname(__file__),
                                                    "golden-files"))
        warn_log.main([logs_dir])

    def test_format_logs_tool(self):
        log_dir = self.make_temp_dir()
        log = build_log.LogSetDir(log_dir).make_logger()
        log.child_log("foo")
        html_file = os.path.join(self.make_temp_dir(), "log.html")
        subprocess.check_call(["python", os.path.join(os.path.dirname(__file__),
                                                      "format_log.py"),
                               log_dir, html_file])
        assert os.path.exists(html_file)

    def test_time_duration_formatting(self):
        pairs = [(0, "0s"),
                 (0.1, "0s"),
                 (3, "3s"),
                 (10, "10s"),
                 (62, "1m02s"),
                 (60*60*2 + 60 + 3, "2h01m03s"),
                 (24*60*60, "1d00h00m00s")]
        for seconds, expect in pairs:
            self.assertEquals(expect, build_log.format_duration(seconds))


# TODO: make into a unit test
def main():
    log_dir = "out-log"
    if os.path.exists(log_dir):
        shutil.rmtree(log_dir)
    os.mkdir(log_dir)
    maker = build_log.LogDir(log_dir)
    log = maker.make_logger()
    run_cmd(log, ["echo", "Hello world!"])
    log2 = log.child_log("child")
    log2.message("This is a message")
    log2.finish(0)
    log.finish(0)
    print etree.tostring(maker.get_xml(), pretty_print=True)
    html = build_log.wrap_body(build_log.format_log(maker.get_xml()))
    write_file(os.path.join("out-log", "log.html"),
               etree.tostring(html, pretty_print=True))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--meld"]:
        GoldenTestCase.run_meld = True
        sys.argv.pop(1)
    unittest.main()

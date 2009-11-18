
# Copyright (C) 2008 Mark Seaborn
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

import StringIO
import unittest

import action_tree
import build_log


class ExampleTree(object):

    def __init__(self):
        self.got = []

    def foo(self, log):
        self.got.append("foo")

    def bar(self, log):
        self.got.append("bar")

    def baz_unpunned_name(self, log):
        self.got.append("baz")

    @action_tree.action_node
    def subtree1(self):
        return [self.foo,
                self.bar,
                ("baz", self.baz_unpunned_name)]

    def qux(self, log):
        self.got.append("qux")

    def quux(self, log):
        self.got.append("quux")

    @action_tree.action_node
    def subtree2(self):
        return [self.qux, self.quux]

    @action_tree.action_node
    def all_steps(self):
        return [self.subtree1, self.subtree2]


class TreeWithFailure(object):

    def failer(self, log):
        raise Exception("lose")

    @action_tree.action_node
    def subtree(self):
        return [self.leaf1, self.leaf2]

    def leaf1(self, log):
        pass

    def leaf2(self, log):
        pass

    @action_tree.action_node
    def all_steps(self):
        return [self.failer, self.subtree]


class SimpleLog(object):

    def __init__(self, name="top"):
        self._name = name
        self._sublogs = []
        self._result = None

    def start(self):
        pass

    def child_log(self, name, do_start=True):
        child = SimpleLog(name)
        self._sublogs.append(child)
        return child

    def finish(self, result):
        self._result = result

    def format(self, stream, indent=0):
        stream.write("%s%s [%s]\n" % (" " * indent, self._name, self._result))
        for sublog in self._sublogs:
            sublog.format(stream, indent=indent + 2)


def pop_all(lst):
    copy = lst[:]
    lst[:] = []
    return copy


# This is a bit friendlier than unittest's assertEquals() when
# printing non-matching multi-line strings.
def assert_equals(x, y):
    if x != y:
        raise AssertionError('"%s" != "%s"' % (x, y))


def iostring(func):
    stream = StringIO.StringIO()
    func(stream)
    return stream.getvalue()


class ActionTreeTest(unittest.TestCase):

    def test_running(self):
        example = ExampleTree()
        example.all_steps(build_log.DummyLogWriter())
        self.assertEquals(example.got, ["foo", "bar", "baz", "qux", "quux"])

    def test_running_subtrees(self):
        example = ExampleTree()
        # By number
        action_tree.action_main(example.all_steps, ["0"])
        self.assertEquals(pop_all(example.got),
                          ["foo", "bar", "baz", "qux", "quux"])
        action_tree.action_main(example.all_steps, ["1"])
        self.assertEquals(pop_all(example.got), ["foo", "bar", "baz"])
        action_tree.action_main(example.all_steps, ["2"])
        self.assertEquals(pop_all(example.got), ["foo"])
        action_tree.action_main(example.all_steps, ["3"])
        self.assertEquals(pop_all(example.got), ["bar"])
        action_tree.action_main(example.all_steps, ["-t", "3"])
        self.assertEquals(pop_all(example.got), ["bar", "baz", "qux", "quux"])
        action_tree.action_main(example.all_steps, ["-t", "5"])
        self.assertEquals(pop_all(example.got), ["qux", "quux"])
        # By name
        action_tree.action_main(example.all_steps, ["subtree1"])
        self.assertEquals(pop_all(example.got), ["foo", "bar", "baz"])
        action_tree.action_main(example.all_steps, ["foo"])
        self.assertEquals(pop_all(example.got), ["foo"])
        action_tree.action_main(example.all_steps, ["bar"])
        self.assertEquals(pop_all(example.got), ["bar"])

        action_tree.action_main(example.all_steps, ["-t", "bar"])
        self.assertEquals(pop_all(example.got), ["bar", "baz", "qux", "quux"])
        action_tree.action_main(example.all_steps, ["-t", "subtree2"])
        self.assertEquals(pop_all(example.got), ["qux", "quux"])

        action_tree.action_main(example.all_steps, ["-f", "subtree1", "0"])
        self.assertEquals(pop_all(example.got), ["foo", "bar", "baz"])
        action_tree.action_main(example.all_steps, ["-f", "-bar", "0"])
        self.assertEquals(pop_all(example.got), ["foo", "baz", "qux", "quux"])

    def test_formatting(self):
        tree = ExampleTree().all_steps
        stream = StringIO.StringIO()
        action_tree.action_main(tree, [], stdout=stream)
        assert_equals(stream.getvalue(), """\
0: all_steps
  1: subtree1
    2: foo
    3: bar
    4: baz
  5: subtree2
    6: qux
    7: quux
""")

        stream = StringIO.StringIO()
        action_tree.action_main(tree, ["-f", "subtree2"], stdout=stream)
        assert_equals(stream.getvalue(), """\
0: all_steps
  1: subtree2
    2: qux
    3: quux
""")

    def test_logging(self):
        tree = ExampleTree().all_steps
        log = SimpleLog()
        action_tree.action_main(tree, ["0"], log=log)
        assert_equals(iostring(log.format), """\
top [None]
  subtree1 [0]
    foo [0]
    bar [0]
    baz [0]
  subtree2 [0]
    qux [0]
    quux [0]
""")

    def test_logging_enrol_up_front(self):
        tree = TreeWithFailure().all_steps
        log = SimpleLog()
        try:
            action_tree.action_main(tree, ["0"], log=log)
        except:
            pass
        assert_equals(iostring(log.format), """\
top [None]
  failer [1]
  subtree [None]
    leaf1 [None]
    leaf2 [None]
""")


if __name__ == "__main__":
    unittest.main()

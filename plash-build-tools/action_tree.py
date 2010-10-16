
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

import optparse
import sys

import build_log


# Workaround for Python's variable binding semantics.
def thunkify(func, *args):
    return lambda: func(*args)


class ActionTreeNode(object):

    def __init__(self, children, name):
        self.children = children
        self.__name__ = name

    def two_stage_run(self, log):
        steps = []
        for name, node in self.children:
            sublog = log.child_log(name, do_start=False)
            if isinstance(node, ActionTreeNode):
                func = node.two_stage_run(sublog)
            else:
                func = thunkify(node, sublog)
            steps.append((sublog, func))
        def run():
            for sublog, func in steps:
                try:
                    sublog.start()
                    func()
                except (SystemExit, KeyboardInterrupt):
                    raise
                except:
                    sublog.finish(1)
                    raise
                else:
                    sublog.finish(0)
        return run

    def __call__(self, log):
        self.two_stage_run(log)()


def make_node(actions, name):
    return ActionTreeNode([coerce_to_name_action_pair(action)
                           for action in actions], name)


# Intended to be used as a decorator
def action_node(unbound_method):
    def wrapper(self):
        return make_node(unbound_method(self), name=unbound_method.__name__)
    return property(wrapper)


def coerce_to_name_action_pair(val):
    if isinstance(val, tuple):
        return val
    else:
        return (val.__name__, val)


class ActionInContext(object):

    def __init__(self, action, name, path):
        self.action = action
        self.name = name
        self.path = path
        self.index = None # Filled out later

    def get_level(self):
        return len(self.path) - 1

    def run_leaf(self, log):
        if not isinstance(self.action, ActionTreeNode):
            self.action(log)

    def get_names(self):
        for i in range(len(self.path)):
            yield ".".join(self.path[i:])


def flatten_tree(action, name=None, path=[]):
    if name is None:
        name = action.__name__
    path = path + [name]
    yield ActionInContext(action, name, path)
    if isinstance(action, ActionTreeNode):
        for subname, subnode in action.children:
            for result in flatten_tree(subnode, name=subname, path=path):
                yield result


def print_node(action, index, stream):
    stream.write("%s%i: %s\n" %
                 ("   " * action.get_level(), index, action.name))


def print_tree(actions, stream):
    for index, act in enumerate(actions):
        print_node(act, index, stream)


def get_one(lst):
    assert len(lst) == 1, lst
    return lst[0]


def filter_tree(action, label):
    if isinstance(action, ActionTreeNode):
        got = []
        for subname, subnode in action.children:
            if subname == label:
                got.append((subname, subnode))
            else:
                new_node = filter_tree(subnode, label)
                if new_node is not None:
                    got.append((subname, new_node))
        if len(got) > 0:
            return ActionTreeNode(got, action.__name__)
    return None


def negative_filter_tree(action, label):
    if isinstance(action, ActionTreeNode):
        return ActionTreeNode(
            [(subname, negative_filter_tree(subnode, label))
             for subname, subnode in action.children
             if subname != label], "top")
    return action


def add_options(parser):
    parser.add_option("-f", "--filter", dest="filters", default=[],
                      action="append", help="Filter to a subset of the tree")
    parser.add_option("--print", dest="print_tree", action="store_true",
                      default=False)


def action_main_(action, options, args, stdout=sys.stdout,
                 log=build_log.DummyLogWriter()):
    for filter_name in options.filters:
        if filter_name.startswith("-"):
            action = negative_filter_tree(action, filter_name[1:])
        else:
            action = filter_tree(action, filter_name)
    if len(args) == 0:
        print_tree(flatten_tree(action), stdout)
    else:
        flattened = list(flatten_tree(action))
        by_index = {}
        for index, act in enumerate(flattened):
            act.index = index
            for name in list(act.get_names()) + [str(index)]:
                by_index.setdefault(name, []).append(act)
        def action_range(text):
            start, sep, end = text.partition(":")
            if start == "":
                start_action = flattened[0]
            else:
                start_action = get_one(by_index[start])
            if end == "":
                end_action = flattened[-1]
            else:
                end_action = get_one(by_index[end])
            return start_action, end_action
        for arg in args:
            if ":" in arg:
                start_action, end_action = action_range(arg)
                actions = flattened[start_action.index:end_action.index + 1]
                if options.print_tree:
                    print_tree(actions, stdout)
                else:
                    for action in actions:
                        action.run_leaf(log)
            else:
                if options.print_tree:
                    print_tree(flattened, stdout)
                else:
                    get_one(by_index[arg]).action(log)


def action_main(action, args, stdout=sys.stdout,
                log=build_log.DummyLogWriter()):
    parser = optparse.OptionParser()
    add_options(parser)
    options, remaining_args = parser.parse_args(args)
    action_main_(action, options, remaining_args, stdout, log)


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

import os
import subprocess
import time

from buildutils import remove_prefix
import lxml.etree as etree


class NodeStream(object):

    def __init__(self, output):
        self.output = output
        self._names = set()

    def alloc_name(self, name):
        if name in self._names:
            suffix = 1
            while True:
                new_name = "%s_%i" % (name, suffix)
                if new_name not in self._names:
                    break
                suffix += 1
        else:
            new_name = name
        self._names.add(new_name)
        return new_name


class NodeWriter(object):

    def __init__(self, stream, id):
        self._stream = stream
        self._id = id

    def new_child(self, tag_name, attrs=[], id_name=None):
        if id_name is None:
            id_name = tag_name
        new_id = self._stream.alloc_name(id_name)
        self._stream.output.write("%s add %s %s\n" %
                                  (self._id, tag_name, new_id))
        child = NodeWriter(self._stream, new_id)
        for key, value in attrs:
            child.add_attr(key, value)
        return child

    def add_attr(self, key, value):
        assert isinstance(key, str)
        assert isinstance(value, str)
        assert " " not in key
        assert "\n" not in key
        assert "\n" not in value
        self._stream.output.write("%s %s %s\n" % (self._id, key, value))


class StreamReader(object):

    def __init__(self):
        self._root_node = etree.Element("root")
        self._map = {"root": self._root_node}

    def process_line(self, line):
        node_id, attr, arg = line.split(" ", 2)
        node = self._map[node_id]
        if attr == "add":
            tag_name, new_node_id = arg.split(" ", 1)
            new_node = etree.Element(tag_name)
            assert arg not in self._map
            self._map[new_node_id] = new_node
            node.append(new_node)
        else:
            node.attrib[attr] = arg

    def process_file(self, fh):
        for line in fh:
            self.process_line(line.rstrip("\n"))

    def get_root(self):
        return self._root_node


def get_xml_from_log(input_file):
    reader = StreamReader()
    reader.process_file(input_file)
    return reader.get_root()


class LogDir(object):

    def __init__(self, dir_path, get_time=time.time):
        self._dir_path = dir_path
        self._get_time = get_time
        self._counter = 0
        self._log_file = os.path.join(self._dir_path, "0000-log")

    def make_filename(self, name):
        self._counter += 1
        basename = "%04i-%s" % (self._counter, name)
        return basename, os.path.join(self._dir_path, basename)

    def make_logger(self):
        assert not os.path.exists(self._log_file)
        stream = NodeStream(open(self._log_file, "w", buffering=0))
        log = LogWriter(NodeWriter(stream, "root"),
                        self, "root", self._get_time)
        log.start()
        return log

    def get_xml(self):
        log = get_xml_from_log(open(self._log_file, "r"))
        for file_node in log.xpath(".//file"):
            file_node.attrib["pathname"] = \
                os.path.join(self._dir_path, file_node.attrib["filename"])
        return log

    def get_timestamp(self):
        return os.stat(self._log_file).st_mtime


class LogWriter(object):

    def __init__(self, node, log_dir, name, get_time):
        self._node = node
        self._log_dir = log_dir
        self._name = name
        self._get_time = get_time

    def start(self):
        self._node.add_attr("start_time", str(self._get_time()))

    def message(self, message):
        self._node.new_child("message", [("text", message)])

    def child_log(self, name, do_start=True):
        sublog = LogWriter(self._node.new_child("log", [("name", name)],
                                                id_name=name),
                           self._log_dir, name, self._get_time)
        if do_start:
            sublog.start()
        return sublog

    def make_file(self):
        relative_name, filename = self._log_dir.make_filename(self._name)
        self._node.new_child("file", [("filename", relative_name)])
        assert not os.path.exists(filename)
        return open(filename, "w")

    def finish(self, result):
        self._node.add_attr("end_time", str(self._get_time()))
        self._node.add_attr("result", str(result))


class DummyLogWriter(object):

    def start(self):
        pass

    def message(self, message):
        pass

    def child_log(self, name, do_start=True):
        return DummyLogWriter()

    def make_file(self):
        return open("/dev/null", "w")

    def finish(self, result):
        pass


class LogSetDir(object):

    def __init__(self, dir_path, get_time=time.time):
        self._dir = dir_path
        self._get_time = get_time

    def make_logger(self):
        time_now = time.gmtime(self._get_time())
        subdir_base = time.strftime("%Y/%m/%d", time_now)
        i = 0
        while True:
            log_dir = os.path.join(self._dir, "%s/%04i" % (subdir_base, i))
            if not os.path.exists(log_dir):
                break
            i += 1
        os.makedirs(log_dir)
        return LogDir(log_dir, self._get_time).make_logger()

    def _sorted_leafnames(self, dir_path):
        # For compatibility with existing log dirs, sort by number not
        # by string.
        leafnames = []
        for leafname in os.listdir(dir_path):
            try:
                num = int(leafname)
            except ValueError:
                pass
            else:
                leafnames.append((num, leafname))
        leafnames.sort(reverse=True)
        return [name for num, name in leafnames]

    def _get_logs(self, dir_path):
        if os.path.exists(os.path.join(dir_path, "0000-log")):
            yield LogDir(dir_path, self._get_time)
        else:
            if os.path.exists(dir_path):
                for leafname in self._sorted_leafnames(dir_path):
                    for log in self._get_logs(os.path.join(dir_path, leafname)):
                        yield log

    def get_logs(self):
        return self._get_logs(self._dir)


class NullPathnameMapper(object):

    def map_pathname(self, pathname):
        return pathname


class PathnameMapper(object):

    def __init__(self, dir_path):
        self._dir_path = dir_path

    def map_pathname(self, pathname):
        return remove_prefix(self._dir_path + "/", pathname)


def flatten(val):
    got = []

    def recurse(x):
        if isinstance(x, (list, tuple)):
            for y in x:
                recurse(y)
        else:
            got.append(x)

    recurse(val)
    return got


def tagp(tag_name, attrs, *children):
    element = etree.Element(tag_name)
    for key, value in attrs:
        element.attrib[key] = value
    last_child = None
    for child in flatten(children):
        if isinstance(child, basestring):
            assert last_child is None
            element.text = child
        else:
            element.append(child)
            last_child = child
    return element


def tag(tag_name, *children):
    return tagp(tag_name, [], *children)


def log_class(log):
    if "result" not in log.attrib:
        return "result_unknown"
    elif int(log.attrib["result"]) == 0:
        return "result_success"
    else:
        return "result_failure"


def format_log(log, path_mapper, filter=lambda log: True):
    sub_logs = [format_log(sublog, path_mapper, filter)
                for sublog in reversed(log.xpath("log"))]
    if not filter(log):
        return sub_logs
    classes = ["log", log_class(log)]
    html = tagp("div", [("class", " ".join(classes))])
    html.append(tag("span", log_duration(log) + log.attrib.get("name", "")))
    for file_node in log.xpath("file"):
        pathname = file_node.attrib["pathname"]
        relative_name = path_mapper.map_pathname(pathname)
        if os.stat(pathname).st_size > 0:
            html.append(tagp("a", [("href", relative_name)], "[log]"))
    html.extend(flatten(sub_logs))
    return html


def format_time(log, attr):
    # TODO: use local timezone without breaking golden tests
    if attr in log.attrib:
        timeval = float(log.attrib[attr])
        string = time.strftime("%a, %d %b %Y %H:%M",
                               time.gmtime(timeval))
    else:
        string = "time not known"
    return tagp("div", [("class", "time")], string)


def format_duration(seconds):
    if int(seconds) == 0:
        return "0s"
    got = []
    minutes, val = divmod(seconds, 60)
    got.append("%02is" % val)
    if minutes != 0:
        hours, val = divmod(minutes, 60)
        got.append("%02im" % val)
        if hours != 0:
            days, val = divmod(hours, 24)
            got.append("%02ih" % val)
            if days != 0:
                got.append("%id" % days)
    return "".join(reversed(got)).lstrip("0")


def log_duration(log):
    if "start_time" in log.attrib and "end_time" in log.attrib:
        return "[%s] " % format_duration(float(log.attrib["end_time"]) -
                                         float(log.attrib["start_time"]))
    else:
        return ""


def format_top_log(log, path_mapper):
    return tag("div",
               format_time(log, "end_time"),
               format_log(log, path_mapper),
               format_time(log, "start_time"))


def write_xml(fh, xml):
    fh.write(etree.tostring(xml, pretty_print=True))


def write_xml_file(filename, xml):
    fh = open(filename, "w")
    try:
        write_xml(fh, xml)
    finally:
        fh.close()


def format_logs(targets, path_mapper, dest_filename):
    headings = tag("tr", *[tag("th", target.get_name())
                           for target in targets])
    columns = tag("tr")
    for target in targets:
        column = tag("td")
        for log in target.get_logs():
            column.append(format_top_log(log.get_xml(), path_mapper))
        columns.append(column)
    html = wrap_body(tagp("table", [("class", "summary")],
                          headings, columns))
    write_xml_file(dest_filename, html)


def format_short_summary(log, path_mapper):
    table = tagp("table", [("class", "short_results")])
    for child in reversed(log.xpath("log")):
        row = tag("tr")
        row.append(tag("td", child.attrib["name"]))
        row.append(tag("td", format_time(child, "end_time")))
        row.append(tag("td", log_duration(child)))

        def filter(log):
            return int(log.attrib.get("result", "0")) != 0

        info = flatten(format_log(child, path_mapper, filter))
        if len(info) == 0:
            info = tagp("div", [("class", "log %s" % log_class(child))], "ok")
        row.append(tag("td", info))
        table.append(row)
    return table


def for_some(iterator):
    for x in iterator:
        if x:
            return True
    return False


def log_has_failed(log):
    return (int(log.attrib.get("result", 0)) != 0 or
            for_some(log_has_failed(sublog) for sublog in log.xpath("log")))


def warn_failures(logs, stamp_time):
    for log in logs:
        if log_has_failed(log.get_xml()):
            if log.get_timestamp() > stamp_time:
                print "failed"
                subprocess.call("beep -l 10 -f 1000", shell=True)
        return
    print "no completed logs"


def wrap_body(body):
    return tagp("html", [],
                tagp("link", [("rel", "stylesheet"), ("href", "log.css")]),
                body)

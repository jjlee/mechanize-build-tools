import collections
import doctest
import os
import pipes
import re
import subprocess
import sys
import time
import xml.sax.saxutils

import cmd_env


def tag(tag, *body):
    return "<%s>" % tag, body, "</%s>" % tag


def tagp(tag, attrs, *body):
    attrs_part = "".join(" %s=%s" % (k, xml.sax.saxutils.quoteattr(v)) for
                         k, v in attrs)
    return "<%s%s>" % (tag, attrs_part), body, "</%s>" % tag


class Page(object):

    def __init__(self, name, url, title=None):
        self.name = name
        if title is None:
            title = name
        self.url = url
        self.title = title
        self.children = []

    def add(self, page):
        self.children.append(page)
        return page


def site_map():
    # TODO: shuffle content around into hierarchy something like this
    root = Page("Root", "/")

    home = root.add(Page("Home", "/mechanize/"))
    download = root.add(Page("Download", "/mechanize/download.html"))
    support = root.add(Page("Support", "/mechanize/docs/ChangeLog.txt"))
    development = root.add(Page("Development", "/mechanize/todo.html"))

    support.add(Page("Changelog", "/mechanize/docs/ChangeLog.txt"))
    docs = support.add(Page("Docs", "/mechanize/docs.html"))

    docs.add(Page("mechanize", "/mechanize/"))
    docs.add(Page("GeneralFAQ", "/mechanize/GeneralFAQ.html",
                  title="General FAQs"))
    docs.add(Page("doc", "/mechanize/doc.html", title="handlers etc."))
    docs.add(Page("forms", "/mechanize/forms.html"))

    return root


def find_page(site_map, name):
    if site_map.name == name:
        return site_map, []

    for page in site_map.children:
        try:
            found, parents = find_page(page, name)
        except ValueError:
            continue

        return found, parents + [page]

    raise ValueError(name)


def toc_link(current_page, page):
    if page.url == current_page.url:
        link = tagp("span", [("class", "thispage")], page.title)
    else:
        link = tagp("a", [("href", page.url)], page.title)
    return link


def toc_tag(current_page, page):
    if len(page.children) == 0:
        return toc_link(current_page, page)
    else:
        body = [tag("li", toc_tag(current_page, child))
                for child in page.children]
        return tagp("ul", [("id", "toc")], *body)


def html(tags):
    r = []
    if isinstance(tags, basestring):
        r.append(tags)
    else:
        for tag in tags:
            r.append(html(tag))
    return "\n".join(r)


def toc_html(site_map, page_name):
    current_page, parents = find_page(site_map, page_name)
    toc_root = parents[-2]  # ..., nested_toc, toc, nav
    return html(toc_tag(current_page, toc_root))


class NullWrapper(object):

    def __init__(self, env):
        self._env = env

    def cmd(self, args, **kwargs):
        return self._env.cmd(["true"], **kwargs)


def get_cmd_stdout(env, args, **kwargs):
    child = env.cmd(args, do_wait=False, stdout=subprocess.PIPE, **kwargs)
    stdout, stderr = child.communicate()
    rc = child.returncode
    if rc != 0:
        raise cmd_env.CommandFailedError(
            "Command failed with return code %i: %s:\n%s" % (rc, args, stderr),
            rc)
    else:
        return stdout


def try_int(v):
    if v is None:
        return v
    try:
        return int(v)
    except ValueError:
        return v


VersionTuple = collections.namedtuple("VersionTuple",
                                      "major minor bugfix state pre svn")


VERSION_RE = re.compile(
    r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<bugfix>\d+)(?P<state>[ab])?"
    r"(?:-pre)?(?P<pre>\d+)?"
    r"(?:\.dev-r(?P<svn>\d+))?$")


def parse_version(text):
    """
>>> parse_version("0.0.1").tuple
VersionTuple(major=0, minor=0, bugfix=1, state=None, pre=None, svn=None)
>>> parse_version("0.2.3b").tuple
VersionTuple(major=0, minor=2, bugfix=3, state='b', pre=None, svn=None)
>>> parse_version("1.0.3a").tuple
VersionTuple(major=1, minor=0, bugfix=3, state='a', pre=None, svn=None)
>>> parse_version("123.012.304a").tuple
VersionTuple(major=123, minor=12, bugfix=304, state='a', pre=None, svn=None)
>>> parse_version("1.0.3c")
Traceback (most recent call last):
ValueError: 1.0.3c
>>> parse_version("1.0.3a-pre1").tuple
VersionTuple(major=1, minor=0, bugfix=3, state='a', pre=1, svn=None)
>>> parse_version("1.0.3a-pre234").tuple
VersionTuple(major=1, minor=0, bugfix=3, state='a', pre=234, svn=None)
>>> parse_version("0.0.11a.dev-r20458").tuple
VersionTuple(major=0, minor=0, bugfix=11, state='a', pre=None, svn=20458)
>>> parse_version("1.0.3a-preblah")
Traceback (most recent call last):
ValueError: 1.0.3a-preblah
    """
    m = VERSION_RE.match(text)
    if m is None:
        raise ValueError(text)
    parts = [try_int(m.groupdict()[part]) for part in VersionTuple._fields]
    return Version(VersionTuple(*parts))


def unparse_version(tup):
    """
>>> unparse_version(('0', '0', '1', None, None, None))
'0.0.1'
>>> unparse_version(('0', '2', '3', 'b', None, None))
'0.2.3b'
>>> unparse_version()
Traceback (most recent call last):
  File "<stdin>", line 1, in ?
TypeError: unparse_version() takes exactly 1 argument (0 given)
>>> unparse_version(('1', '0', '3', 'a', None, None))
'1.0.3a'
>>> unparse_version(('123', '012', '304', 'a', None, None))
'123.012.304a'
>>> unparse_version(('1', '0', '3', 'a', '1', None))
'1.0.3a-pre1'
>>> unparse_version(('1', '0', '3', 'a', '234', None))
'1.0.3a-pre234'
    """
    major, minor, bugfix, state_char, pre, svn = tup
    fmt = "%s.%s.%s"
    args = [major, minor, bugfix]
    if state_char is not None:
        fmt += "%s"
        args.append(state_char)
    if pre is not None:
        fmt += "-pre%s"
        args.append(pre)
    if svn is not None:
        fmt += ".dev-r%s"
        args.append(svn)
    return fmt % tuple(args)


class Version(object):

    def __init__(self, version_tuple):
        self.tuple = version_tuple

    def __lt__(self, other):
        return self.tuple < other.tuple

    def next_version(self):
        this = self.tuple
        return Version(VersionTuple(
                this.major, this.minor, int(this.bugfix) + 1,
                this.state, this.pre, this.svn))

    def __str__(self):
        return unparse_version(self.tuple)

    def __repr__(self):
        return "<Version '%s'>" % self


def output_to_file_cmd(filename):
    return ["sh", "-c", 'f="$1" && shift && exec "$@" > "$f"', "inline_script",
            filename]


def make_env_maker(prefix_cmd_maker):
    def env_maker(env, *args, **kwargs):
        return cmd_env.PrefixCmdEnv(prefix_cmd_maker(*args, **kwargs), env)
    return env_maker


OutputToFileEnv = make_env_maker(output_to_file_cmd)


CwdEnv = make_env_maker(cmd_env.in_dir)


def shell_escape(args):
    return " ".join(pipes.quote(arg) for arg in args)


class PipeEnv(object):

    def __init__(self, env, args):
        self._env = env
        self._args = args

    def cmd(self, args, **kwargs):
        pipeline = '%s | %s' % (shell_escape(args), shell_escape(self._args))
        return self._env.cmd(["sh", "-c", pipeline])


def trim(text, suffix):
    assert text.endswith(suffix)
    return text[:-len(suffix)]


def empy_cmd(filename, defines=()):
    return ["empy"] + ["-D%s" % define for define in defines] + [filename]


def empy(env, filename, defines=()):
    return OutputToFileEnv(env, trim(filename, ".in")).cmd(
        empy_cmd(filename, defines))


def pandoc_cmd(filename, variables=()):
    variables = sum([["-V", "%s=%s" % item] for item in variables], [])
    return ["pandoc",
            "--smart",
            "--standalone",
            "--template", "html.template"] + variables + [filename]


def pandoc(env, filename, output_dir="html", variables=()):
    html = os.path.join(output_dir, trim(filename, ".txt") + ".html")
    tidy_py = os.path.join(os.path.dirname(__file__), "tidy.py")
    return PipeEnv(OutputToFileEnv(env, html),
                   ["python", tidy_py]).cmd(pandoc_cmd(filename, variables))

def read_file_from_env(env, filename):
    return get_cmd_stdout(env, ["cat", filename])


def ensure_installed(env, as_root_env, package_name, ppa=None):
    try:
        output = get_cmd_stdout(env, ["dpkg", "-s", package_name])
    except cmd_env.CommandFailedError:
        installed = False
    else:
        installed = "Status: install ok installed" in output
    if not installed:
        if ppa is not None:
            as_root_env.cmd(["add-apt-repository", "ppa:%s" % ppa])
            as_root_env.cmd(["apt-get", "update"])
        as_root_env.cmd(["apt-get", "install", "-y", package_name])


def GitPagerWrapper(env):
    return cmd_env.PrefixCmdEnv(["env", "GIT_PAGER=cat"], env)


def last_modified_cmd(path):
    return ["git", "log", "-1", "--pretty=format:%ci", path]


def rm_rf_cmd(dir_path):
    return ["rm", "-rf", "--one-file-system", dir_path]


# for use from doc templates
def last_modified(path, env=None):
    if env is None:
        env = GitPagerWrapper(cmd_env.BasicEnv())
    timestamp = get_cmd_stdout(env, last_modified_cmd(path))
    if timestamp == "":
        # not tracked by git, return bogus time for convenience of testing
        # before committed
        epoch = time.gmtime(0)
        return epoch
    # only really interested in the approx. date, strip timezone
    timestamp = re.sub("([0-9]{4,4}-[0-9]{2,2}-[0-9]{2,2} " \
                           "[0-9]{2,2}:[0-9]{2,2}:[0-9]{2,2}) [+-][0-9]{4,4}",
                       "\\1", timestamp)
    return time.strptime(timestamp, "%Y-%m-%d %H:%M:%S")


def get_env_from_options(options):
    env = cmd_env.BasicEnv()
    if options.pretend:
        env = NullWrapper(env)
    if options.verbose:
        env = cmd_env.VerboseWrapper(env)
    return env


def add_basic_env_options(parser):
    parser.add_option("-v", "--verbose", action="store_true")
    parser.add_option("-n", "--pretend", action="store_true",
                      help=("run commands in a do-nothing environment.  "
                            "Note that not all actions do their work by "
                            "running a command."))


if __name__ == "__main__":
    failure_count, unused = doctest.testmod()
    sys.exit(not(failure_count == 0))

import collections
import doctest
import email.mime.text
import os
import pipes
import re
import subprocess
import smtplib
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

    def iter_pages(self):
        yield self
        for child in self.children:
            for descendant in child.iter_pages():
                yield descendant

    def add(self, page):
        self.children.append(page)
        return page


def site_map():
    root = Page("Root", "/")

    root.add(Page("index", "./", title="Home"))
    root.add(Page("download", "download.html", title="Download"))
    support = root.add(Page("support", "support.html", title="Support"))
    root.add(Page("development", "development.html", title="Development"))

    docs = support.add(Page("documentation", "documentation.html",
                            title="Documentation"))
    support.add(Page("Changelog", "ChangeLog.txt"))

    docs.add(Page("faq", "faq.html", title="FAQ"))
    docs.add(Page("doc", "doc.html", title="Handlers etc."))
    docs.add(Page("forms", "forms.html", title="Forms"))
    docs.add(Page("hints", "hints.html", title="Hints"))

    return root


def find_page(site_map, name):
    if site_map.name == name:
        return [site_map]

    for page in site_map.children:
        try:
            ancestor_or_self = find_page(page, name)
        except ValueError:
            continue

        return [site_map] + ancestor_or_self

    raise ValueError(name)


def link(current_page, page):
    if page.url == current_page.url:
        link = tagp("span", [("class", "thispage")], page.title)
    else:
        link = tagp("a", [("href", page.url)], page.title)
    return link


def subnav_tag(current_page, page, level=0):
    if level != 0:
        yield link(current_page, page)
    if len(page.children) != 0:
        body = [tag("li", subnav_tag(current_page, child, level + 1))
                for child in page.children]
        attrs = []
        if level == 0:
            attrs.append(("id", "subnav"))
        yield tagp("ul", attrs, *body)


def nav_tag(current_nav, page):
    body = [tag("li", link(current_nav, child))
            for child in page.children]
    return tagp("ul", [("id", "nav")], *body)


def html(tags):
    r = []
    if isinstance(tags, basestring):
        r.append(tags)
    else:
        for tag in tags:
            r.append(html(tag))
    return "\n".join(r)


def subnav_html(site_map, page_name):
    ancestor_or_self = find_page(site_map, page_name)
    # ancestor_or_self == root, nav[, subnav, subsubnav]
    current_page = ancestor_or_self[-1]
    nav = ancestor_or_self[1]
    if len(nav.children) == 0:
        return ""
    # Include a link for the parent nav level.  This allows rendering the nav
    # link (at the top of the page) as text to indicate current nav location,
    # but also allowing a way to get back to the top-level nav page via the
    # subnav links.
    subtree_root = Page("", "")
    subtree_root.add(nav)
    return html(subnav_tag(current_page, subtree_root))


def nav_html(site_map, page_name):
    ancestor_or_self = find_page(site_map, page_name)
    nav = ancestor_or_self[1]
    root = site_map
    return html(nav_tag(nav, root))


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
        assert isinstance(version_tuple, tuple)
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


def output_to_file(path):
    return ["sh", "-c", 'out="$1" && shift && exec "$@" > "$out" 2>&1',
            "inline_script"]


def pipe_cmd(cmd):
    return ["sh", "-c", 'exec "$@" | %s' % shell_escape(cmd), "inline_script"]


PipeEnv = make_env_maker(pipe_cmd)


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
            "--template", "html.template",
            "--toc"] + variables + [filename]


def pandoc(env, filename, output_dir="html", variables=()):
    html = os.path.join(output_dir, trim(filename, ".txt") + ".html")
    tidy_py = os.path.join(os.path.dirname(__file__), "tidy.py")
    return PipeEnv(OutputToFileEnv(env, html),
                   ["python", tidy_py]).cmd(pandoc_cmd(filename, variables))


def read_file_from_env(env, filename):
    return get_cmd_stdout(env, ["cat", filename])


def write_file_to_env(env, filename, data):
    env.cmd(cmd_env.write_file_cmd(filename, data))


def append_file_to_env(env, filename, data):
    env.cmd(cmd_env.append_file_cmd(filename, data))


def install(env, filename, data):
    env.cmd(["mkdir", "-p", os.path.dirname(filename)])
    write_file_to_env(env, filename, data)


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


def ensure_trailing_slash(path):
    return path.rstrip("/") + "/"


def clean_dir(env, path):
    env.cmd(rm_rf_cmd(path))
    env.cmd(["mkdir", "-p", path])


def is_git_repository(path):
    return os.path.exists(os.path.join(path, ".git"))


def ensure_unmodified(env, path):
    # raise if working tree differs from HEAD
    CwdEnv(env, path).cmd(["git", "diff", "--exit-code", "HEAD"])


def add_to_path_cmd(value):
    set_path_script = """\
if [ -n "$PATH" ]
  then
    export PATH="$PATH":%(value)s
  else
    export PATH=%(value)s
fi
exec "$@"
""" % dict(value=value)
    return ["sh", "-c", set_path_script, "inline_script"]


def get_home_dir(env):
    return trim(get_cmd_stdout(env, ["sh", "-c", "echo $HOME"]), "\n")


def get_user_env(as_root, username):
    as_user = cmd_env.PrefixCmdEnv(["sudo", "-u", username, "-H"], as_root)
    return CwdEnv(as_user, get_home_dir(as_user))


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


def send_email(from_address, to_address, subject, body):
    msg = email.mime.text.MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['To'] = to_address
    # print "from_address %r" % from_address
    # print "to_address %r" % to_address
    # print "msg.as_string():\n%s" % msg.as_string()
    s = smtplib.SMTP()
    s.connect()
    s.sendmail(from_address, [to_address], msg.as_string())
    s.quit()


def get_env_from_options(options):
    env = cmd_env.BasicEnv()
    if options.pretend:
        env = NullWrapper(env)
    if options.verbose:
        env = cmd_env.VerboseWrapper(env)
    return env


def _add_basic_env_options(add_option):
    add_option("-v", "--verbose", action="store_true")
    add_option("-n", "--pretend", action="store_true",
               help=("run commands in a do-nothing environment.  "
                     "Note that not all actions do their work by "
                     "running a command."))


def add_basic_env_options(parser):
    _add_basic_env_options(parser.add_option)


def add_basic_env_arguments(parser):
    _add_basic_env_options(parser.add_argument)


if __name__ == "__main__":
    failure_count, unused = doctest.testmod()
    sys.exit(not(failure_count == 0))

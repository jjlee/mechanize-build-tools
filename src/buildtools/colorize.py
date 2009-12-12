"""Syntax-colourize Python source code.

Taken from Python Cookbook (originally from MoinMoin Python Source Parser).

HTML code coverage support:

Original recipe:
 http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52298

Original Authors:
 - J\ufffdrgen Hermann
 - Mike Brown <http://skew.org/~mike/>
 - Christopher Arndt <http://chrisarndt.de>

Hacked a bit by John J Lee <jjl@pobox.com>.  Reduced the amount of markup
generated, and I forget what else...

"""

# Imports
import os, cgi, string, sys, cStringIO
import keyword, token, tokenize


#############################################################################
### Python Source Parser (does Hilighting)
#############################################################################

_KEYWORD = token.NT_OFFSET + 1
_TEXT    = token.NT_OFFSET + 2

py = "py"  # '#444444' grey
pystr = "pystr"  # '#a08070' light brown
pycmt = "pycmt"  # '#a34727' dark brown
pykw = "pykw"  # "#9668d7" lilac

_colors = {
    token.NUMBER:       py,
    token.OP:           py,
    token.STRING:       pystr,
    tokenize.COMMENT:   pycmt,
    token.NAME:         py,
    token.ERRORTOKEN:   py,
    _KEYWORD:           pykw,
    _TEXT:              py,
}

def colorize(text):
    # for use with EmPy
    print colorize_ex(text)

def colorize_ex(text):
    from StringIO import StringIO
    text = str(text)  # we don't like unicode
    inp = StringIO(text)
    out = StringIO()
    Parser(inp.read(), out).format(None, None)
    return out.getvalue()


class Parser:
    """ Send colored python source.

    >>> colorize('import blah\\n\\ndef foo():\\n    blah()\\nprint "bye"\\n#comment\\n')
    <pre><span class="pykw">import</span> blah
    <BLANKLINE>
    <span class="pykw">def</span> foo():
        blah()
    <span class="pykw">print</span> <span class="pystr">"bye"</span>
    <span class="pycmt">#comment</span></pre>

    >>> colorize(u'import blah\\n\\ndef foo():\\n    blah()\\nprint "bye"\\n#comment\\n')
    <pre><span class="pykw">import</span> blah
    <BLANKLINE>
    <span class="pykw">def</span> foo():
        blah()
    <span class="pykw">print</span> <span class="pystr">"bye"</span>
    <span class="pycmt">#comment</span></pre>

    """

    def __init__(self, raw, out = sys.stdout, not_covered=[]):
        """ Store the source text.
        """
        self.raw = string.expandtabs(raw).rstrip()
        self.out = out
        self.not_covered = not_covered  # not covered list of lines
        self.cover_flag = False  # is there a <span> tag opened?

    def format(self, formatter, form):
        """ Parse and send the colored source.
        """
        # store line offsets in self.lines
        self.lines = [0, 0]
        pos = 0
        while 1:
            pos = self.raw.find('\n', pos) + 1
            if not pos: break
            self.lines.append(pos)
        self.lines.append(len(self.raw))

        # parse the source and write it
        self.pos = 0
        text = cStringIO.StringIO(self.raw)
        self.out.write('<pre>')
        try:
            tokenize.tokenize(text.readline, self)
        except tokenize.TokenError, ex:
            msg = ex[0]
            line = ex[1][0]
            self.out.write("<h3>ERROR: %s</h3>%s\n" % (
                msg, self.raw[self.lines[line]:]))
        self.out.write('</pre>')

    def __call__(self, toktype, toktext, (srow,scol), (erow,ecol), line):
        """ Token handler.
        """
        if 0:
            print "type", toktype, token.tok_name[toktype], "text", toktext,
            print "start", srow,scol, "end", erow,ecol, "<br>"

        # calculate new positions
        oldpos = self.pos
        newpos = self.lines[srow] + scol
        self.pos = newpos + len(toktext)

        if not self.cover_flag and srow in self.not_covered:
            self.out.write('<span class="notcovered">')
            self.cover_flag = True

        # handle newlines
        if toktype in [token.NEWLINE, tokenize.NL]:
            if self.cover_flag:
                self.out.write('</span>')
                self.cover_flag = False
##             self.out.write('\n')
##             return

        # send the original whitespace, if needed
        if newpos > oldpos:
            self.out.write(self.raw[oldpos:newpos])

        # skip indenting tokens
        if toktype in [token.INDENT, token.DEDENT]:
            self.pos = newpos
            return

        # map token type to a color group
        if token.LPAR <= toktype and toktype <= token.OP:
            toktype = token.OP
        elif toktype == token.NAME and keyword.iskeyword(toktext):
            toktype = _KEYWORD
        color = _colors.get(toktype, _colors[_TEXT])

##         style = ''
##         if toktype == token.ERRORTOKEN:
##             style = ' style="border: solid 1.5pt #FF0000;"'

        # send text
        if color != "py":
            self.out.write('<span class="%s">' % color)
        self.out.write(cgi.escape(toktext))
        if color != "py":
            self.out.write('</span>')

# code coverage
# --------------------------------------------------------------------

_HTML_HEADER = """\
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
  "http://www.w3.org/TR/html4/loose.dtd">
<html>
<head>
<title>code coverage of %(title)s</title>
<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">

<style type="text/css">
pre.code {font-style: Lucida,"Courier New";}
.pystr {color:#a08070;}
.pycmt {color:#a34727;}
.pykw {color:#9668d7;}
.notcovered {background-color: #FFB2B2;}
</style>

</head>
<body>
"""

_HTML_FOOTER = """\
</body>
</html>
"""

class MissingList(list):
    def __init__(self, i):
        list.__init__(self, i)

    def __contains__(self, elem):
        for i in list.__iter__(self):
            v_ = m_ = s_ = None
            try:
                v_ = int(i)
            except ValueError:
                m_, s_ = i.split('-')
            if v_ is not None and v_ == elem:
                return True
            elif (m_ is not None) and (s_ is not None) and \
                     (int(m_) <= elem) and (elem <= int(s_)):
                return True
        return False

def colorize_file(filename, outstream=sys.stdout, not_covered=[]):
    """
    Convert a python source file into colorized HTML.

    Reads file and writes to outstream (default sys.stdout).
    """
    fo = file(filename, 'rb')
    try:
        source = fo.read()
    finally:
        fo.close()
    outstream.write(_HTML_HEADER % {'title': os.path.basename(filename)})
    Parser(source, out=outstream,
           not_covered=MissingList((not_covered and \
                                    not_covered.split(', ')) or \
                                   [])).format(None, None)
    outstream.write(_HTML_FOOTER)


# --------------------------------------------------------------------


def test_main():
    import doctest
    doctest.testmod()

def demo():
    import os, sys
    print "Formatting..."

    # open own source
    source = open('/home/john/lib/python/colorize.py').read()

    # write colorized version to "python.html"
    Parser(source, open('python.html', 'wt')).format(None, None)

    # load HTML page into browser
    if os.name == "nt":
        os.system("explorer python.html")
    else:
        os.system("konqueror python.html &")


if __name__ == "__main__":
    test_main()

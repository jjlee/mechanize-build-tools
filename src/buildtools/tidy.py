import optparse
import sys

import lxml.etree
import lxml.html


def join_not_none(values, sep=""):
    return sep.join(x for x in values if x is not None)


def collapse_p_span(tree):
    # <p><span class="q"></span></p> --> <p class="q"></p>
    # because:
    #  * Awkward to produce latter markup direct from markdown (using pandoc)
    #  * I had some CSS trouble with the former; life's too short for that
    for span in tree.xpath("//p/span[@class='q']"):
        span.getparent().set("class", "q")
        span.drop_tag()


def collapse_pre_code(tree):
    # <pre><code></code></pre> --> <pre></pre>
    # because:
    #  * pandoc generates that markup for embedded code
    #  * Had some CSS trouble with that markup
    for span in tree.xpath("//pre/code"):
        span.drop_tag()


def collapse_normal(tree):
    # e.g. <span class="Normal NormalText">x</span> --> x
    # because:
    #  * pandoc syntax highlighting output is too verbose
    for span in tree.xpath("(//span[@class='Normal NormalText'])|"
                           "(//span[@class='Normal'])|"
                           "(//span[@class='Normal Operator'])"):
        span.drop_tag()


def remove_emacs_comments(tree):
    # remove stuff like this:
    # <!-- Local Variables: -->
    # <!-- fill-column:79 -->
    # <!-- End: -->
    # because:
    #  * There seems to be no markdown comment syntax
    #  * Inappropriate to suggest editing a non-source file
    #  * HTML is less noisy without it
    for comment in tree.getiterator(lxml.etree.Comment):
        if comment.text.strip() == "Local Variables:":
            unwanted = []
            node = comment
            while node.tag is lxml.etree.Comment:
                unwanted.append(node)
                if node.text.strip() == "End:":
                    break
                node = node.getnext()
            parent = comment.getparent()
            for node in unwanted:
                parent.remove(node)


def parse_options(args):
    parser = optparse.OptionParser()
    options, remaining_args = parser.parse_args(args)
    try:
        options.input_filename = remaining_args.pop(0)
    except IndexError:
        options.input_filename = None
    return options


def main(args):
    # this is intended as a special purpose post-processor just for use on
    # pandoc output from mechanize markdown input files
    options = parse_options(args)
    if options.input_filename is None:
        html = sys.stdin.read()
    else:
        html = open(options.input_filename).read()
    tree = lxml.html.fromstring(html)
    collapse_p_span(tree)
    collapse_pre_code(tree)
    collapse_normal(tree)
    remove_emacs_comments(tree)
    # serialize in non-bizarre fashion: don't write newlines inside tags,
    # unlike pandoc :-)
    sys.stdout.write(tree.getroottree().docinfo.doctype)
    sys.stdout.write("\n")
    sys.stdout.write(lxml.html.tostring(tree, pretty_print=True))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])

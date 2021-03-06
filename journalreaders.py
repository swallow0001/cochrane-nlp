#  Journal readers
#  Iain
#  2012-12-08

#
#  *** REQUIRES UNIX/LINUX OS WITH pdftotext INSTALLED ***
#

import os
import glob
import codecs
#from bs4 import BeautifulSoup
import BeautifulSoup
import subprocess
import re

class TextReader:
    """Reads plain text files, and base class for other file types

    >>> t = TextReader('testdata/simpletest/textreader.txt')
    >>> print t.get_text()
    Test Journal Article
    by the authors

    """
    def __init__(self, filename):
        self.data = {"filetype": "text",
                     "raw": self.import_text(filename)}

    def import_text(self, filename):
        "gets unicode utf-8 file contents"
        with codecs.open(filename, "rb", "utf-8") as f:
            raw_text = f.read()
        return raw_text.strip()

    def get_text(self):
        return self.data["raw"]


class PdfReader(TextReader):
    """imports PDF text; currently using linux only command line *pdftotext*
     utility

    >>> t = PdfReader('testdata/simpletest/textreader.pdf')
    >>> print t.get_text()
    Test Journal Article
    by the authors
    """

    def __init__(self, filename):
        self.data = {"filetype": "pdf",
                     "raw": self.import_pdf(filename)}

    def import_pdf(self, filename):
        """
            runs pdftotext command line util via python subprocess

        """
        # bcw -- the quotes around the file path are necessary on
        # some systems!
        rawtext = subprocess.check_output(['pdftotext', "%s" % filename, '-'])
        return rawtext.strip() # remove any multiple blank lines at the end


class HtmlReader(TextReader):
    """imports HTML text using BeautifulSoup

    >>> t = HtmlReader('testdata/simpletest/textreader.html')
    >>> print t.get_text()
    Test Journal Article
    by the authors

    """
    def __init__(self, filename):
        self.data = {"filetype": "html",
                     "raw": self.import_html(filename)}

    def import_html(self, filename):
        "retrieves text from an HTML file"
        html = self.import_text(filename)
        raw_text = BeautifulSoup(html).body.get_text().strip()
        return raw_text


class JournalReader:
    "Journal reader base class"

    def __init__(self, filename):
        self.file_obj = self.import_file_obj(filename)

    def import_file_obj(self, filename):
        "adds an appropriate reader class to the jread object"
        ext = os.path.splitext(filename)[-1].lower()
        if ext == ".pdf":
            file_obj = pdf_reader(filename)
        elif ext == ".htm" or ext == ".html":
            file_obj = html_reader(filename)
        else:
            file_obj = text_reader(filename)
        return file_obj

    def get_text(self):
        "returns the contents as plain text"
        return self.file_obj.get_text()


class LabeledAbstractReader:
    ''' 
    Parses labeled citations from the provided path. Assumes format is like:

        Abstract 1 of 500
        Prothrombin fragments (F1+2) ...
            ...
        BiviewID 42957; PMID 11927130

    '''
    def __init__(self, path_to_data="data/drug_trials_in_cochrane_BCW.txt", num_labeled_abstracts=150):
        # @TODO probably want to read things in lazily, rather than
        # reading everything into memory at once...
        self.abstracts = []
        self.abstract_index = 1 # for iterator
        self.path_to_abstracts = path_to_data
        print "parsing data from {0}".format(self.path_to_abstracts)

        self.num_abstracts = num_labeled_abstracts
        self.parse_abstracts()

        self.num_citations = len(self.citation_d) 
        print "ok."

    def __getitem__(self, key):
        return self.citation_d[key-1]

    def get_file_id(self, file_id):
        for i in self:
            if i["file_id"] == file_id:
                return i
        else:
            raise IndexError("File ID %d not in reader" % (file_id,))

    def get_biview_id(self, biview_id):
        for i in self:
            if i["Biview_id"] == str(biview_id):
                return i
        else:
            raise IndexError("BiViewer ID %d not in reader" % (biview_id,))


    def __iter__(self):
        self.abstract_index = 0
        return self

    def __len__(self):
        return self.num_citations

    def next(self):
        if self.abstract_index >= self.num_citations:
            raise StopIteration
        else:
            self.abstract_index += 1
            return self.citation_d[self.abstract_index-1]
            

    def _is_demarcater(self, l):
        '''
        True iff l is a line separating two citations.
        Demarcating lines look like "BiviewID 42957; PMID 11927130"
        '''

        # reasonably sure this will not give any false positives...
        return l.startswith("BiviewID") and "PMID" in l

    def _get_IDs(self, l):
        ''' Assumes l is a demarcating line; returns Biview and PMID ID's '''
        grab_id = lambda s : s.lstrip().split(" ")[1].strip()
        biview_id, pmid = [grab_id(s) for s in l.split(";")]
        return biview_id, pmid

    def _is_new_citation_line(self, l):
        return l.startswith("Abstract ")

    def parse_abstracts(self):
        self.citation_d = {}
        in_citation = False
        # abstract_num is the arbitrary, per-file, sequentially
        # incremented id assigned abstracts. this is *not*
        # zero-indexed and varies across files. we need to hold
        # on to this to cross-ref with the annotations_parser 
        # (agreement.py) module -- this is the ID that lib uses!
        #
        # abstract_index is used only internally; the difference
        # is that we only hold on to abstracts that have annotations
        # (many do not, especially when using just, e.g., my file)
        abstract_num, abstract_index = 1, 0 
        with open(self.path_to_abstracts, 'rU') as abstracts_file:
            cur_abstract = ""
            
            for line in abstracts_file.readlines():
                line = line.strip()
                if self._is_demarcater(line):
                    biview_id, pmid = self._get_IDs(line)

                    if LabeledAbstractReader.is_annotated(cur_abstract):


                        self.citation_d[abstract_index] = {"abstract":cur_abstract, 
                                                           "Biview_id":biview_id,
                                                           "pubmed_id":pmid,
                                                           "file_id":abstract_num} # yes, redundant
                        abstract_index += 1
                    else:
                        print "no annotations for {0} -- ignoring!".format(abstract_num)

                    cur_abstract = ""
                    in_citation = False
                    abstract_num += 1
                elif in_citation and line:
                    # then this is the abstract
                    cur_abstract = line
                elif self._is_new_citation_line(line):
                    in_citation = True

                if abstract_num > self.num_abstracts:
                    return self.citation_d

        return self.citation_d

    @staticmethod
    def is_annotated(text):
        ###
        # IM: change to checking abstract text for any opening tag
        # to save repeating full annotation parse
        if re.search("<([a-z0-9_]+)>", text):
            return True
        else:
            return False

    def get_text(self):
        return [cit["abstract"] for cit in self.citation_d.values()]


def main():
    import doctest
    doctest.testmod()




if __name__ == '__main__':
    main()


#
#   rm5reader
#   subclasses xmlbase
#

import xml.etree.cElementTree as ET
import re
import collections
from xmlbase import XMLReader
from pprint import pprint # for testing purposes

class RM5(XMLReader):
    
    def __init__(self, filename):
        XMLReader.__init__(self, filename)
        self.section_map["title"] = "COVER_SHEET/TITLE"

    def title(self):
        return self.text_filtered(part_id="title")
        
    def cdno(self):
        #
        #   first try to get cdno from filename (most reliable), else try to extract from DOI
        #
        try:
            cdno = re.search('(?:CD|MR)[0-9]+', self.filename).group(0)
        except:
            doi = self.data.getroot().attrib.get("DOI")
            parts = doi.split('.')
            for part in parts:
                if part[:2] == "CD" or part[:2] == "MR":
                    cdno = part
                else:
                    cdno = "Unknown"
        return cdno

    def review_type(self):
        return self.data.getroot().attrib.get("TYPE")

    def included_study_ids(self):
        studies = self.data.findall('STUDIES_AND_REFERENCES/STUDIES/INCLUDED_STUDIES/STUDY')
        return [study.attrib.get("ID") for study in studies]


    def ref_characteristics(self):

        studies_characteristics = self.data.findall("CHARACTERISTICS_OF_STUDIES/CHARACTERISTICS_OF_INCLUDED_STUDIES/INCLUDED_CHAR")
        output = {}
        
        for study_characteristics in studies_characteristics:
            
            id = study_characteristics.attrib.get("STUDY_ID")
            
            characteristics = {"CHAR_METHODS": self._ETfind("CHAR_METHODS", study_characteristics),
                               "CHAR_PARTICIPANTS": self._ETfind("CHAR_PARTICIPANTS", study_characteristics),
                               "CHAR_INTERVENTIONS": self._ETfind("CHAR_INTERVENTIONS", study_characteristics),
                               "CHAR_OUTCOMES": self._ETfind("CHAR_OUTCOMES", study_characteristics),
                               "CHAR_NOTES": self._ETfind("CHAR_NOTES", study_characteristics)}
            
            output.update({id: characteristics})
            
        return output
            

    def ref_quality(self):
      
        quality_items = self.data.findall("QUALITY_ITEMS/QUALITY_ITEM")
        output = collections.defaultdict(list)
          
        for item in quality_items:
              
            name = self._ETfind("NAME", item)
            description = self._ETfind("DESCRIPTION", item)
            
            data_entries = item.findall("QUALITY_ITEM_DATA/QUALITY_ITEM_DATA_ENTRY")

            for entry in data_entries:
                id = entry.attrib.get("STUDY_ID")
                description = self._ETfind("DESCRIPTION", entry)
                rating = entry.attrib.get("RESULT")
                output[id].append({"DOMAIN": name, "DESCRIPTION": description, "RATING": rating})

        return output
    

    def refs(self, full_parse=False, return_dict=False):

        studies_ET = self.data.findall("STUDIES_AND_REFERENCES/STUDIES/INCLUDED_STUDIES/STUDY")
        
        if full_parse:
            characteristics = self.ref_characteristics()
            quality = self.ref_quality()
        else:
            characteristics = None
            quality = None
 
                   
        def _ref_parse_to_dict(study_ET, characteristics=None, quality=None):

            references = study_ET.findall("REFERENCE")



            for i, reference in enumerate(references):
                if reference.get("PRIMARY") == "YES":
                    # either get the first references marked as the primary ref
                    primary_ref = reference
                    primary_status = "YES"
                    index_ref = i
                    break
            else:
                
                # or set the primary ref to the first one
                primary_ref = study_ET.find("REFERENCE") # select first one
                # if no references, should return empty
                primary_status = "NO"
                index_ref = 0
                

            if primary_ref:
                output_dict = {"TI": self._ETfind("TI", primary_ref),
                              "SO": self._ETfind("SO", primary_ref),
                              "AU": self._refs_AU(self._ETfind("AU", primary_ref)),
                              "fAU": self._refs_AU(self._ETfind("AU", primary_ref))[0],
                              "YR": self._ETfind("YR", primary_ref),
                              "PG": self._refs_PG(self._ETfind("PG", primary_ref)),
                              "fPG": self._refs_PG(self._ETfind("PG", primary_ref))[0],
                              "VL": self._ETfind("VL", primary_ref),
                              "NO": self._ETfind("NO", primary_ref),
                              "ID": study_ET.attrib.get("ID"),
                              "PRIMARY": primary_status,
                              "REF_INDEX": index_ref}
            else: # else no data in cochrane review
                output_dict = {"TI": "",
                              "SO": "",
                              "AU": [],
                              "fAU": "",
                              "YR": "",
                              "PG": [],
                              "fPG": "",
                              "VL": "",
                              "NO": "",
                              "ID": study_ET.attrib.get("ID"),
                              "PRIMARY": -1,
                              "REF_INDEX": -1}

                          
            if characteristics != None:
                id = output_dict["ID"]
                output_dict.update(characteristics.get(id, {}))
                
            if quality != None:
                id = output_dict["ID"]
                output_dict["QUALITY"] = quality.get(id, {})
           
            return output_dict
        if return_dict:
            return {study_ET.attrib.get("ID"): _ref_parse_to_dict(study_ET, characteristics=characteristics, quality=quality) for study_ET in studies_ET}
        else:
            return [_ref_parse_to_dict(study_ET, characteristics=characteristics, quality=quality) for study_ET in studies_ET]
            
        
    def _refs_PG(self, ref):
        "Accepts string with page number e.g. 1254-63; outputs tuple (start, end)"
        
        if ref is None:
            return ("", "")
        
        ref_parts = ref.split('-')

        start = ref_parts[0]
        
        if len(ref_parts) == 1:
            return (start, start)

        elif len(ref_parts) == 2:
            end = ref_parts[1]
            
            if len(end) < len(start):
                end = start[:(len(start)-len(end))] + end
            
            return (start, end)
        else:
            return ("", "")
            
    def _refs_AU(self, author_string):
        "Accepts string with list of authors; outputs list, et als removed"
        author_string = re.sub("[\s\.,]*et al", "", author_string)
        authors = author_string.split(', ')
        return authors

    def sof_table(self):
        result = self.data.find("SOF_TABLES/SOF_TABLE")
        if result:
            return ET.tostring(result, encoding='utf8', method='xml')
        else:
            return None
        




def main():

    # example - show some data from a random review
    # and give some details about the first included trial in the review
    
    import random
    import glob

    rm5_files_path = '/users/iain/code/data/cdsr2013/'
    rm5_files = glob.glob(rm5_files_path + '*.rm5')

    reader = RM5(random.choice(rm5_files))


    print "Title:"
    print reader.title()
    print

    print "Review type:"
    print reader.review_type()
    print

    print "Included study IDs:"
    print reader.included_study_ids()
    print

    print "Cochrane ID:"
    print reader.cdno()
    print

    refs = reader.refs(full_parse=True) # False just retrieves the citation
    print "No included studies: %d" % (len(refs),)
    print

    print "First included study title:"
    print refs[0]["TI"]
    print

    print "Population details"
    print refs[0]["CHAR_PARTICIPANTS"]
    print

    print "Summary or findings table"
    print reader.sof_table()
    print

    print "Risk of bias"
    print

    for i, domain in enumerate(refs[0]["QUALITY"]):
        print "Domain number %d" % (i, )
        print "Name\t\t" + domain["DOMAIN"]
        print "Description\t" + domain["DESCRIPTION"]
        print "Rating\t\t" + domain["RATING"]
        




if __name__ == '__main__':
    main()







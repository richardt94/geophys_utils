'''
Created on 23Feb.,2017

@author: u76345
'''
import re
import copy
from pprint import pprint
from datetime import datetime, timedelta
from owslib import fes
import argparse
from owslib.csw import CatalogueServiceWeb
from owslib.wms import WebMapService
from owslib.wcs import WebCoverageService

class CSWUtils(object):
    '''
    CSW query utilities
    '''
    DEFAULT_CSW_URL = 'http://ecat.ga.gov.au/geonetwork/srv/eng/csw' # GA's externally-facing eCat
    DEFAULT_TIMEOUT = 30 # Timeout in seconds
    DEFAULT_CRS = 'EPSG:4326' # Unprojected WGS84
    DEFAULT_MAXRECORDS = 100 # Retrieve only this many datasets per CSW query
    DEFAULT_MAXTOTALRECORDS = 500 # Maximum total number of records to retrieve

    def __init__(self, csw_url=None, timeout=None):
        '''
        Constructor for CSWUtils class
        @param csw_url: URL for CSW service. Defaults to value of CSWUtils.DEFAULT_CSW_URL
        @param timeout: Timeout in seconds. Defaults to value of CSWUtils.DEFAULT_TIMEOUT
        '''
        csw_url = csw_url or CSWUtils.DEFAULT_CSW_URL
        timeout = timeout or CSWUtils.DEFAULT_TIMEOUT

        self.csw = CatalogueServiceWeb(csw_url, timeout=timeout)

    def list_from_comma_separated_string(self, comma_separated_string):
        '''
        Helper function to return list of strings from a comma-separated string
        Substitute single-character wildcard for whitespace characters
        @param comma_separated_string: comma-separated string
        @return: list of strings
        '''
        return [re.sub('(\s)', '_', keyword.strip()) for keyword in comma_separated_string.split(',')]

    # A helper function for date range filtering
    def get_date_filter(self, start_datetime=None, stop_datetime=None, constraint='overlaps'):
        '''
        Helper function to return a list containing a pair of FES filters for a date range
        @param  start_datetime: datetime object for start of time period to search
        @param stop_datetime: datetime object for end of time period to search
        @param constraint: string value of either 'overlaps' or 'within' to indicate type of temporal search

        @return: list containing a pair of FES filters for a date range
        '''
        if start_datetime:
            start_date_string = start_datetime.isoformat()
        else:
            start_date_string = '1900-01-01T00:00:00'

        if start_datetime:
            stop_date_string = start_datetime.isoformat()
        else:
            stop_date_string = '2100-01-01T23:59:59'

        if constraint == 'overlaps':
            start_filter = fes.PropertyIsLessThanOrEqualTo(propertyname='ows100:TempExtent_begin', literal=stop_date_string)
            stop_filter = fes.PropertyIsGreaterThanOrEqualTo(propertyname='ows100:TempExtent_end', literal=start_date_string)
        elif constraint == 'within':
            start_filter = fes.PropertyIsGreaterThanOrEqualTo(propertyname='ows100:TempExtent_begin', literal=start_date_string)
            stop_filter = fes.PropertyIsLessThanOrEqualTo(propertyname='ows100:TempExtent_end', literal=stop_date_string)

        return [start_filter, stop_filter]

    def get_csw_info(self, fes_filters, maxrecords=None):
        '''
        Function to find all distributions for all records returned
        Returns a nested dict keyed by UUID
        @param fes_filters: List of fes filters to apply to CSW query
        @param maxrecords: Maximum number of records to return per CSW query. Defaults to value of CSWUtils.DEFAULT_MAXRECORDS

        @return: Nested dict object containing information about each record including distributions
        '''
        dataset_dict = {} # Dataset details keyed by title

        maxrecords = maxrecords or CSWUtils.DEFAULT_MAXRECORDS
        startposition = 1 # N.B: This is 1-based, not 0-based

        while True: # Keep querying until all results have been retrieved
            # apply all the filters using the "and" syntax: [[filter1, filter2]]
            self.csw.getrecords2(constraints=[fes_filters],
                                 esn='full',
                                 maxrecords=maxrecords,
                                 startposition=startposition)

    #        print 'csw.request = %s' % csw.request
    #        print 'csw.response = %s' % csw.response

            record_count = len(self.csw.records)

            for uuid in self.csw.records.keys():
                record = self.csw.records[uuid]
                title = record.title

                # Ignore datasets with no distributions
                if not record.uris:
                    #print 'No distribution(s) found for "%s"' % title
                    continue

#                print 'bbox = %s' % record.bbox.__dict__

                record_dict = {'uuid': uuid,
                               'title': title,
                               'publisher': record.publisher,
                               'author': record.creator,
                               'abstract': record.abstract,
                              }

                if record.bbox:
                    record_dict['bbox'] = [record.bbox.minx, record.bbox.minx, record.bbox.maxx, record.bbox.maxy],
                    record_dict['bbox_crs'] = record.bbox.crs or 'EPSG:4326'

                distribution_info_list = copy.deepcopy(record.uris)

                # Add layer information for web services
                for distribution_info in [distribution_info
                                          for distribution_info in distribution_info_list
                                          if distribution_info['protocol'] == 'OGC:WMS'
                                          ]:
                    wms = WebMapService(distribution_info['url'], version='1.1.1')
                    distribution_info['layers'] = wms.contents.keys()

                for distribution_info in [distribution_info
                                          for distribution_info in distribution_info_list
                                          if distribution_info['protocol'] == 'OGC:WCS'
                                          ]:
                    wcs = WebCoverageService(distribution_info['url'], version='1.0.0')
                    distribution_info['layers'] = wcs.contents.keys()

                record_dict['distributions'] = distribution_info_list
                record_dict['keywords'] = record.subjects

                dataset_dict[uuid] = record_dict
                #print '%d distribution(s) found for "%s"' % (len(info_list), title)

            if len(dataset_dict) >= CSWUtils.DEFAULT_MAXTOTALRECORDS:  # Don't go around again for another query - maximum retrieved
                break

            if record_count < maxrecords:  # Don't go around again for another query - should be the end
                break

            startposition += maxrecords

        #assert distribution_dict, 'No URLs found'
        #print '%d records found.' % len(dataset_dict)
        return dataset_dict

    def query_csw(self,
                  keyword_list=None,
                  bounding_box=None,
                  bounding_box_crs=None,
                  anytext_list=None,
                  titleword_list=None,
                  start_datetime=None,
                  stop_datetime=None
                  ):
        '''
        Function to query CSW using AND combination of provided search parameters
        @param keyword_list: List of strings or comma-separated string containing keyword search terms
        @param bounding_box: Bounding box to search as a list of ordinates [bbox.minx, bbox.minx, bbox.maxx, bbox.maxy]
        @param bounding_box_crs: Coordinate reference system for bounding box. Defaults to value of CSWUtils.DEFAULT_CRS
        @param anytext_list: List of strings or comma-separated string containing any text search terms
        @param titleword: List of strings or comma-separated string containing title search terms
        @param start_datetime: Datetime object defining start of temporal search period
        @param stop_datetime: Datetime object defining end of temporal search period
        '''

        bounding_box_crs = bounding_box_crs or CSWUtils.DEFAULT_CRS

        # Convert strings to lists if required
        if type(keyword_list) == str:
            keyword_list = self.list_from_comma_separated_string(keyword_list)

        if type(anytext_list) == str:
            anytext_list = self.list_from_comma_separated_string(anytext_list)

        if type(titleword_list) == str:
            titleword_list = self.list_from_comma_separated_string(titleword_list)

        # Build filter list
        fes_filter_list = []
        if keyword_list:
            fes_filter_list += [fes.PropertyIsLike(propertyname='Subject', literal=keyword, matchCase=False) for keyword in keyword_list]
        if anytext_list:
            fes_filter_list += [fes.PropertyIsLike(propertyname='anyText', literal=phrase, matchCase=False) for phrase in anytext_list]
        if start_datetime or stop_datetime:
            fes_filter_list += self.get_date_filter(start_datetime, stop_datetime)
        if titleword_list:
            fes_filter_list += [fes.PropertyIsLike(propertyname='title', literal=titleword, matchCase=False) for titleword in titleword_list]
        if bounding_box:
            fes_filter_list += [fes.BBox(bounding_box, crs=bounding_box_crs)]

        assert fes_filter_list, 'No search criteria defined'

        if titleword_list:
            fes_filter_list += [fes.PropertyIsLike(propertyname='title', literal=titleword, matchCase=False) for titleword in titleword_list]
        if bounding_box:
            fes_filter_list += [fes.BBox(bounding_box, crs=bounding_box_crs)]


        if len(fes_filter_list) == 1:
            fes_filter_list = fes_filter_list[0]

        return self.get_csw_info(fes_filter_list)

    def find_distributions(self, distribution_protocol, dataset_dict):
        '''
        Function to return flattened list of dicts containing information for all
        distributions matching specified distribution_protocol (partial string match)
        '''
        result_list = []
        for record_dict in dataset_dict.values():
            for distribution_dict in record_dict['distributions']:
                if distribution_protocol.upper() in distribution_dict['protocol'].upper(): # If protocol match is found
                    dataset_distribution_dict = copy.copy(record_dict) # Create shallow copy of record dict

                    # Delete list of all distributions from copy of record dict
                    del dataset_distribution_dict['distributions']

                    # Convert lists to strings
                    #dataset_distribution_dict['keywords'] = ', '.join(dataset_distribution_dict['keywords'])
                    #dataset_distribution_dict['bbox'] = ', '.join([str(ordinate) for ordinate in dataset_distribution_dict['bbox']])

                    # Merge distribution info into copy of record dict
                    dataset_distribution_dict.update(distribution_dict)
                    # Remove any leading " file://" from URL to give plain filename
                    dataset_distribution_dict['url'] = re.sub('^file://', '', dataset_distribution_dict['url'])

                    result_list.append(dataset_distribution_dict)

        return result_list





def main():
    '''
    Quick and dirty main function for on-the-fly testing
    '''

    DATE_FORMAT_LIST = ['%Y%m%d', '%d/%m/%Y']

    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--keywords", help="comma-separated list of keywords", type=str)
    parser.add_argument("-t", "--titlewords", help="comma-separated list of titlewords", type=str)
    parser.add_argument("-a", "--anytext", help="comma-seperated list of text snippets", type=str)
    parser.add_argument("-b", "--bounds", help="comma-separated <minx>,<miny>,<maxx>,<maxy> ordinates of bounding box",
                        type=str)
    parser.add_argument("-bc", "--bounds_crs", help="coordinate reference system for bounding box coordinates",
                        type=str)
    parser.add_argument("-s", "--start_date", help="start date", type=str)
    parser.add_argument("-e", "--end_date", help="end date", type=str)
    args = parser.parse_args()

    print 'args.keywords = "%s"' % args.keywords
    print 'args.titlewords = "%s"' % args.titlewords
    print args.anytext
    print 'args.bounds = "%s"' % args.bounds
    print 'args.bounds_crs = "%s"' % args.bounds_crs
    print 'args.start_date = "%s"' % args.start_date

    if args.bounds:
        bounds = [float(ordinate) for ordinate in args.bounds.split(',')]
    else:
        bounds = None

    print 'bounds = "%s"' % bounds

    start_date = None
    if args.start_date:
        for format_string in DATE_FORMAT_LIST:
            try:
                start_date = datetime.strptime(args.start_date, format_string)
                break
            except ValueError:
                pass

    print 'start_date = "%s"' % start_date.isoformat()

    end_date = None
    if args.end_date:
        for format_string in DATE_FORMAT_LIST:
            try:
                # Add one day to make date inclusive
                end_date = datetime.strptime(args.end_date, format_string) + timedelta(days=1)
                break
            except ValueError:
                pass

    print 'end_date = "%s"' % end_date.isoformat()

    #create a CSW object and populate the parameters with argparse inputs - print results
    cswu = CSWUtils()
    result_dict = cswu.query_csw(keyword_list=args.keywords,
                                 anytext_list=args.anytext,
                                 titleword_list=args.titlewords,
                                 bounding_box=bounds,
                                 start_datetime=start_date,
                                 stop_datetime=end_date
                                 )
    pprint(result_dict)
    print '%d results found.' % len(result_dict)

    pprint(result_dict)
    print '%d results found.' % len(result_dict)

    print 'Files:'
    for distribution in cswu.find_distributions('file', result_dict):
        print distribution['url'], distribution['title']

    print 'WMS:'
    for distribution in cswu.find_distributions('wms', result_dict):
        print distribution['url'], distribution['title']



if __name__ == '__main__':
    main()
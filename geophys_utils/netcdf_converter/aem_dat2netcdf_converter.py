#!/usr/bin/env python

#===============================================================================
#    Copyright 2017 Geoscience Australia
# 
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
# 
#        http://www.apache.org/licenses/LICENSE-2.0
# 
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
#===============================================================================
'''
AEMDAT2NetCDFConverter concrete class for converting AEM .dat data to netCDF

Created on 28Mar.2018

@author: Alex Ip
'''
from collections import OrderedDict
import numpy as np
import re
from pprint import pprint

from geophys_utils.netcdf_converter import NetCDFConverter, NetCDFVariable
from geophys_utils import get_spatial_ref_from_wkt


class AEMDAT2NetCDFConverter(NetCDFConverter):
    '''
    AEMDAT2NetCDFConverter concrete class for converting AEMDAT data to netCDF
    '''
    def __init__(self, nc_out_path, aem_dat_path, dfn_path, netcdf_format='NETCDF4_CLASSIC'):
        '''
        Concrete constructor for subclass AEMDAT2NetCDFConverter
        Needs to initialise object with everything that is required for the other Concrete methods
        N.B: Make sure the base class constructor is called from the subclass constructor
        '''
        #TODO: Make this a bit easier to work with - it's a bit opaque at the moment
        def parse_dfn_file(dfn_path):
            print('Reading definitions file {}'.format(dfn_path))
            field_definitions = []
            crs=None
            
            dfn_file = open(dfn_path, 'r')
            for line in dfn_file:
                # generate nested lists split by ";", ":", "," then "="
                split_lists = [[[[equals_split_string.strip() for equals_split_string in comma_split_string.split('=')]
                    for comma_split_string in [comma_split_string.strip() for comma_split_string in colon_split_string.split(',')]
                    ]
                        for colon_split_string in [colon_split_string.strip() for colon_split_string in semicolon_split_string.split(':')]
                        ]
                            for semicolon_split_string in [semicolon_split_string.strip() for semicolon_split_string in line.split(';')]
                            ] 
                #pprint(split_lists) 
                
                try:
                    rt = split_lists[0][0][1][1] # RecordType?
                     
                    if rt == '' and len(split_lists[1]) > 1:
                        units = None
                        long_name= None
                        
                        short_name = split_lists[1][0][0][0]
                        
                        fmt = split_lists[1][1][0][0]
                        
                        if len(split_lists[1]) > 2:
                            if len(split_lists[1][2]) == 1: # Only short_name, format and long_name defined
                                long_name = split_lists[1][2][0][0]
                                
                            
                            elif len(split_lists[1][2][0]) == 2 and split_lists[1][2][0][0] == 'UNITS':
                                units = split_lists[1][2][0][1]
                                long_name = split_lists[1][2][1][0]
                            else:
                                long_name = split_lists[1][2][0][0]
                                
                        field_dict = {'short_name': short_name,
                                      'format': fmt,
                                      'long_name': long_name,
                                      }
                        if units:
                            field_dict['units'] = units
                            
                        field_definitions.append(field_dict)
                        
                    elif rt == 'PROJ':
                        #pprint(split_lists[1])
                        
                        #TODO: Parse projection
                        if (split_lists[1][0][0][0] == 'PROJNAME' 
                            and split_lists[1][2][0][1] == 'GDA94 / MGA zone 54'):
                            
                            # TODO: Remove this hard-coded hack
                            wkt = '''PROJCS["GDA94 / MGA zone 54",
    GEOGCS["GDA94",
        DATUM["Geocentric_Datum_of_Australia_1994",
            SPHEROID["GRS 1980",6378137,298.257222101,
                AUTHORITY["EPSG","7019"]],
            TOWGS84[0,0,0,0,0,0,0],
            AUTHORITY["EPSG","6283"]],
        PRIMEM["Greenwich",0,
            AUTHORITY["EPSG","8901"]],
        UNIT["degree",0.01745329251994328,
            AUTHORITY["EPSG","9122"]],
        AUTHORITY["EPSG","4283"]],
    UNIT["metre",1,
        AUTHORITY["EPSG","9001"]],
    PROJECTION["Transverse_Mercator"],
    PARAMETER["latitude_of_origin",0],
    PARAMETER["central_meridian",141],
    PARAMETER["scale_factor",0.9996],
    PARAMETER["false_easting",500000],
    PARAMETER["false_northing",10000000],
    AUTHORITY["EPSG","28354"],
    AXIS["Easting",EAST],
    AXIS["Northing",NORTH]]'''
                            crs = get_spatial_ref_from_wkt(wkt)
                            break # Nothing more to do
                    
                except IndexError:
                    continue
            
            dfn_file.close()
            
            
            #pprint(field_definitions)
            return field_definitions, crs
            
        # Start of __init__() definition
        NetCDFConverter.__init__(self, nc_out_path, netcdf_format)
        
        self.field_definitions, self.crs = parse_dfn_file(dfn_path)
        
        self.layer_count_index = self.field_definitions.index([field_def 
                                                               for field_def in self.field_definitions 
                                                               if field_def['short_name'] == 'nlayers'][0]
                                                               )
        #print(self.layer_count_index)   
          
        self.fields_per_layer = len(self.field_definitions) - self.layer_count_index - 1
        
        print('Reading data file {}'.format(aem_dat_path))
        self.aem_dat_path = aem_dat_path
        aem_dat_file = open(aem_dat_path, 'r')
         
        # Convert entire numeric file into a single array of float32 datatype
        # This is done to permit efficient column-wise data access but it will fail for any
        # invalid floating point values in data file
        row_list = []
        self.field_count = 0
        
        for line in aem_dat_file:
            line = line.strip()
            if not line: # Skip empty lines
                continue
            row = re.sub('\s+', ',', line).split(',')
            #print(row)
            
            if self.field_count:
                assert self.field_count == len(row), 'Inconsistent field count. Expected {}, found {}.'.format(self.field_count, 
                                                                                                               len(row)
                                                                                                               )
            else: # First row
                self.field_count = len(row)
            
            row_list.append(row)
            
        aem_dat_file.close()
         
        #pprint(row_list)
        self.raw_data_array = np.array(row_list, dtype='float32') # Convert to numpy array
        print('{} points found'.format(self.raw_data_array.shape[0]))
        
        self.layer_count = int(self.raw_data_array[0, self.layer_count_index]) # Only check first row for layer count value
        print('{} layers found'.format(self.layer_count))
        
        assert not np.any(self.raw_data_array[:,self.layer_count_index] - self.layer_count), 'Inconsistent layer count(s) found in column {}'.format(self.layer_count_index + 1)
        
        # Check field count
        expected_field_count = self.layer_count_index + self.layer_count * self.fields_per_layer + 1
        assert self.field_count == expected_field_count, 'Invalid field count. Expected {}, found {}'.format(expected_field_count,
                                                                                                             self.field_count)
    
    def get_global_attributes(self):
        '''
        Concrete method to return dict of global attribute <key>:<value> pairs       
        '''
        return {'title': 'test AEM .dat dataset'}
    
    def get_dimensions(self):
        '''
        Concrete method to return OrderedDict of <dimension_name>:<dimension_size> pairs       
        '''
        dimensions = OrderedDict()
        
        # Example lat/lon dimensions
        dimensions['points'] = self.raw_data_array.shape[0]
        dimensions['layers'] = self.layer_count
              
        return dimensions
    
    def variable_generator(self):
        '''
        Concrete generator to yield NetCDFVariable objects       
        '''        
        # Create crs variable (points)
        yield self.build_crs_variable(self.crs)
        
        # Create 1D variables
        for field_index in range(self.layer_count_index):
            short_name = self.field_definitions[field_index]['short_name']
            
            field_attributes = {}
            
            long_name = self.field_definitions[field_index].get('long_name')
            if long_name:
                field_attributes['long_name'] = long_name
                
            units = self.field_definitions[field_index].get('units')
            if units:
                field_attributes['units'] = units
                
            fmt = self.field_definitions[field_index].get('format')
            if fmt[0] =='I': # Integer field
                #TODO: see if we can reduce the size of the integer datatype
                dtype = 'int32' 
            else:
                dtype='float32'
                
            print('\tWriting 1D variable {}'.format(short_name))
                
            yield NetCDFVariable(short_name=short_name, 
                                 data=self.raw_data_array[:,field_index], 
                                 dimensions=['points'], 
                                 fill_value=None, 
                                 attributes=field_attributes, 
                                 dtype=dtype
                                 )
        
        
        # Create 2D variables (points x layers)
        for layer_field_index in range(self.fields_per_layer):
            field_definition_index = self.layer_count_index + 1 + layer_field_index

            field_start_index = self.layer_count_index + 1 + (layer_field_index * self.layer_count)
            field_end_index = self.layer_count_index + 1 + ((layer_field_index + 1) * self.layer_count)
            
            short_name = self.field_definitions[field_definition_index]['short_name']
            print('\tWriting 2D variable {}'.format(short_name))
            
            #print(layer_field_index, field_definition_index, field_start_index, field_end_index)
            
            long_name = self.field_definitions[field_definition_index].get('long_name')
            if long_name:
                field_attributes['long_name'] = long_name
                 
            units = self.field_definitions[field_definition_index].get('units')
            if units:
                field_attributes['units'] = units
                 
            fmt = self.field_definitions[field_index].get('format')
            if fmt[0] =='I': # Integer field
                #TODO: see if we can reduce the size of the integer datatype
                dtype = 'int32' 
            else:
                dtype='float32'
                
            yield NetCDFVariable(short_name=short_name, 
                                 data=self.raw_data_array[:,field_start_index:field_end_index], 
                                 dimensions=['points', 'layers'], 
                                 fill_value=None, 
                                 attributes=field_attributes, 
                                 dtype=dtype
                                 )
        
        return
    
def main():
    dat_in_path = 'C:\\Users\\u76345\\Downloads\\Groundwater Data\\ord_bonaparte_nbc_main_aquifer_clipped.dat'
    dfn_in_path = 'C:\\Users\\u76345\\Downloads\\Groundwater Data\\nbc_20160421.dfn'
    nc_out_path = 'C:\\Temp\\dat_test.nc'
    d2n = AEMDAT2NetCDFConverter(nc_out_path, dat_in_path, dfn_in_path)
    d2n.convert2netcdf()
    print('Finished writing netCDF file {}'.format(nc_out_path))
    
    print('Dimensions:')
    pprint(d2n.nc_output_dataset.dimensions)
    print('Variables:')
    pprint(d2n.nc_output_dataset.variables)

if __name__ == '__main__':
    main()
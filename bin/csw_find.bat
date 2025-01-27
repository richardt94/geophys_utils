@ECHO OFF
::===============================================================================
::    Copyright 2017 Geoscience Australia
:: 
::    Licensed under the Apache License, Version 2.0 (the "License");
::    you may not use this file except in compliance with the License.
::    You may obtain a copy of the License at
:: 
::        http://www.apache.org/licenses/LICENSE-2.0
:: 
::    Unless required by applicable law or agreed to in writing, software
::    distributed under the License is distributed on an "AS IS" BASIS,
::    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
::    See the License for the specific language governing permissions and
::    limitations under the License.
::===============================================================================
:: Batch file to invoke _csw_utils Python script in MS-Windows
:: Written by Written by Alex Ip & Andrew Turner 27/2/2017
:: Example invocation: csw_find -k "NCI, AU, grid, potassium" -b 148.996,-35.48,149.399,-35.124

python -m geophys_utils.csw_find  %*

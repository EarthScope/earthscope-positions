# coding: utf-8

"""
    EarthScope API (Beta) Documentation

    ![EarthScope Facility Logo](https://www.earthscope.org/app/uploads/2024/01/gage_sage_primary_color.svg)  Welcome to the EarthScope Consortium API documentation.   Our API is intended for programmatic access to NSF GAGE and SAGE Facilities' data and metadata. This API can be used with command line tools for automating data access, e.g., **cURL** and **Wget**, and can be directly incorporated into your programs to fetch data.   Our API also powers our online tools for data discovery and access. The dynamic OpenAPI documentation presented here allows you to easily try our API. However, the \"try it out\" forms in these docs are not intended as the primary interface for regular usage.  Authentication is required to use GAGE and SAGE services, please see the [Authentication](#authentication) section below.  ## <a id=\"versions\"></a> Versions The following versions of the EarthScope API have been released: - [beta](/beta/docs)  ##  <a id=\"authentication\"></a> Authentication Our API requires registration and authentication for reporting anonymized usage metrics to our sponsors.  1. [Register and login](https://www.earthscope.org/user/) - [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/user-profile.html). 2. Pass your authentication/access token in an Authorization header along with your API request. [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/file-server-access-examples.html).  Please see [Authentication](https://www.earthscope.org/data/authentication).  ##  <a id=\"policies\"></a> Policies Access and use of EarthScope's NSF GAGE and NSF SAGE Facility data is governed by the following policies. ### <a id=\"data-policies\"></a> Data Policies - [GAGE Data Policy](https://www.unavco.org/data/policies_forms/data-policy/data-policy.html) - [SAGE Data Policy](https://ds.iris.edu/ds/docs/) - [EarthScope Privacy Policy](https://www.earthscope.org/privacy-policy/) - [EarthScope Terms of Service](https://www.earthscope.org/terms-of-service/)  ### <a id=\"versioning\"></a> Versioning The versioning protocol adopted by the NSF GAGE and SAGE Facilities, operated by EarthScope Consortium, applies to each release of a collection of individual web services, collectively referred to as the EarthScope API. An API version is identified by  the first node of the path following the host name, e.g.,  `api.earthscope.org/beta`, or `api.earthscope.org/v1`, where `beta` indicates a pre-production release and `v1` is the serialized production release version.  The EarthScope API uses [Semantic Versioning](https://semver.org/) to designate specific releases of an API. We increment the API major version whenever we introduce breaking changes. Internally, we use minor and patch versions whenever we add functionality and backward-compatible updates. When we release a new major version of the EarthScope API, clients can choose to either continue using a supported (see our [deprecation policy](#deprecation)) existing major version or migrate to the new one. Here forward, we simply use “version” to refer to our major version releases.  Versions will either be `beta` to indicate pre-production releases or `v1` for specific production version releases, where the number increments, e.g., `v1` to `v2` with each major release. Endpoints identified as `beta` are subject to change \"in place\" without notification and should not be used in critical production systems.  The following points describe what kinds of changes result in an updated version: - A URL path is never really changed; if such a modification is required, the original service path will be [deprecated](#deprecation) and a new one created with a version identifier of `beta` or it's version number incremented. - A change to the internal process of an existing web service will not result in an updated version. - A non-backward compatible change to the output produced by an existing web service will result in an updated version. - The addition of a new, optional, query parameter will not result in a new version and the default value of the query parameter will be set so that the web service will behave as previously if the new parameter is not specified. - The addition of a new, required parameter or a change in formatting of parameter values will result in an updated version.  ### <a id=\"deprecation\"></a> Deprecation   - API version deprecation (end of life) will be announced publicly via our [Data Announcements](https://groups.google.com/a/earthscope.org/g/data-announcements) email list.   - Deprecated services will be labelled “Deprecated” in the respective online API documentation.   - Deprecated services will be retired and removed from our documentation after a period of time to be determined in the deprecation announcement. The deprecation period is intended to allow users time to migrate to newer supported versions of our API. 

    The version of the OpenAPI document: beta
    Contact: data-help@earthscope.org
    Generated by OpenAPI Generator (https://openapi-generator.tech)

    Do not edit the class manually.
"""  # noqa: E501

import warnings
from pydantic import validate_call, Field, StrictFloat, StrictStr, StrictInt
from typing import Any, Dict, List, Optional, Tuple, Union
from typing_extensions import Annotated

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr
from typing import List, Optional, Union
from typing_extensions import Annotated
from earthscope_client.models.facility import Facility
from earthscope_client.models.reference_position_tier import ReferencePositionTier
from earthscope_client.models.response_default_find_networks import ResponseDefaultFindNetworks
from earthscope_client.models.response_default_find_sessions import ResponseDefaultFindSessions
from earthscope_client.models.response_default_find_stations import ResponseDefaultFindStations
from earthscope_client.models.response_default_find_streams import ResponseDefaultFindStreams
from earthscope_client.models.response_radial_search_streams_refpos_search_radial_get import ResponseRadialSearchStreamsRefposSearchRadialGet
from earthscope_client.models.session_roll_period import SessionRollPeriod
from earthscope_client.models.session_sample_interval import SessionSampleInterval
from earthscope_client.models.stream_sample_interval import StreamSampleInterval
from earthscope_client.models.stream_software import StreamSoftware
from earthscope_client.models.stream_type import StreamType

from earthscope_client.api_client import ApiClient, RequestSerialized
from earthscope_client.api_response import ApiResponse
from earthscope_client.rest import RESTResponseType


class DiscoverApi:
    """NOTE: This class is auto generated by OpenAPI Generator
    Ref: https://openapi-generator.tech

    Do not edit the class manually.
    """

    def __init__(self, api_client=None) -> None:
        if api_client is None:
            api_client = ApiClient.get_default()
        self.api_client = api_client


    @validate_call
    def find_gnss_stations_radial(
        self,
        latitude: Annotated[Union[Annotated[float, Field(le=90, strict=True, ge=-90)], Annotated[int, Field(le=90, strict=True, ge=-90)]], Field(description="Latitude in decimal degrees")],
        longitude: Annotated[Union[Annotated[float, Field(le=180, strict=True, ge=-180)], Annotated[int, Field(le=180, strict=True, ge=-180)]], Field(description="Longitude in decimal degrees")],
        distance: Annotated[Union[StrictFloat, StrictInt], Field(description="Search radius distance in km")],
        tier: Annotated[Optional[ReferencePositionTier], Field(description="Whether to search for stations or streams.")] = None,
        network: Annotated[Optional[List[StrictStr]], Field(description="Network name(s). Can contain leading/trailing wildcards. Used to filter both stations and streams. Omit to search all networks.          ShakeAlert uses the network namespace `SHAKE:`, with valid network names being `SHAKE:ShakeAlert` (all stations in ShakeAlert), `SHAKE:IGS`, `SHAKE:PNGA`, `SHAKE:WCDA`, `SHAKE:ORGN`, `SHAKE:NOTA`, `SHAKE:CRTN`, `SHAKE:NCGN`, `SHAKE:BARD`, and `SHAKE:WSRN`. ")] = None,
        stream_type: Annotated[Optional[StreamType], Field(description="Filter stream results by type. Defaults to all stream types. This only applies to streams.")] = None,
        facility: Annotated[Optional[Facility], Field(description="Filter stream results based on facility, i.e. where the position was processed, not where the raw stream originated. Defaults to all facilities. Only applies to streams.")] = None,
        with_information: Annotated[Optional[StrictBool], Field(description="Include station/stream name(s) and location). Defaults to `false`, and only returns EarthScope Datasource IDs (EDIDs).")] = None,
        bypass_cache: Annotated[Optional[StrictBool], Field(description="Skip the cached result and fetch fresh data. The fresh result is still written to the cache.")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ResponseRadialSearchStreamsRefposSearchRadialGet:
        """GNSS Station Radial Search

        Find stations or streams within a certain distance (in km) from a given center point (latitude and longitude in decimal degrees).  Uses the [Haversine formula](https://en.wikipedia.org/wiki/Haversine_formula) to compute great-circle distance.  Usage notes: - The `with_information` query parameter controls the shape of the reponse. Either of the following is returned:     - a list of the EarthScope Datasource IDs (EDIDs) of the stations/streams     - a list of more complete information about stations/streams including names and locations - `network` is used to filter both stations and streams, though the actual network name is not returned in the results. - `facility` and `stream_type` are both used to filter stream results only, and are ignored if `tier` is set to `station`.  This endpoint will temporarily be available for public access while we develop other endpoints.

        :param latitude: Latitude in decimal degrees (required)
        :type latitude: float
        :param longitude: Longitude in decimal degrees (required)
        :type longitude: float
        :param distance: Search radius distance in km (required)
        :type distance: float
        :param tier: Whether to search for stations or streams.
        :type tier: ReferencePositionTier
        :param network: Network name(s). Can contain leading/trailing wildcards. Used to filter both stations and streams. Omit to search all networks.          ShakeAlert uses the network namespace `SHAKE:`, with valid network names being `SHAKE:ShakeAlert` (all stations in ShakeAlert), `SHAKE:IGS`, `SHAKE:PNGA`, `SHAKE:WCDA`, `SHAKE:ORGN`, `SHAKE:NOTA`, `SHAKE:CRTN`, `SHAKE:NCGN`, `SHAKE:BARD`, and `SHAKE:WSRN`. 
        :type network: List[str]
        :param stream_type: Filter stream results by type. Defaults to all stream types. This only applies to streams.
        :type stream_type: StreamType
        :param facility: Filter stream results based on facility, i.e. where the position was processed, not where the raw stream originated. Defaults to all facilities. Only applies to streams.
        :type facility: Facility
        :param with_information: Include station/stream name(s) and location). Defaults to `false`, and only returns EarthScope Datasource IDs (EDIDs).
        :type with_information: bool
        :param bypass_cache: Skip the cached result and fetch fresh data. The fresh result is still written to the cache.
        :type bypass_cache: bool
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_gnss_stations_radial_serialize(
            latitude=latitude,
            longitude=longitude,
            distance=distance,
            tier=tier,
            network=network,
            stream_type=stream_type,
            facility=facility,
            with_information=with_information,
            bypass_cache=bypass_cache,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseRadialSearchStreamsRefposSearchRadialGet",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data


    @validate_call
    def find_gnss_stations_radial_with_http_info(
        self,
        latitude: Annotated[Union[Annotated[float, Field(le=90, strict=True, ge=-90)], Annotated[int, Field(le=90, strict=True, ge=-90)]], Field(description="Latitude in decimal degrees")],
        longitude: Annotated[Union[Annotated[float, Field(le=180, strict=True, ge=-180)], Annotated[int, Field(le=180, strict=True, ge=-180)]], Field(description="Longitude in decimal degrees")],
        distance: Annotated[Union[StrictFloat, StrictInt], Field(description="Search radius distance in km")],
        tier: Annotated[Optional[ReferencePositionTier], Field(description="Whether to search for stations or streams.")] = None,
        network: Annotated[Optional[List[StrictStr]], Field(description="Network name(s). Can contain leading/trailing wildcards. Used to filter both stations and streams. Omit to search all networks.          ShakeAlert uses the network namespace `SHAKE:`, with valid network names being `SHAKE:ShakeAlert` (all stations in ShakeAlert), `SHAKE:IGS`, `SHAKE:PNGA`, `SHAKE:WCDA`, `SHAKE:ORGN`, `SHAKE:NOTA`, `SHAKE:CRTN`, `SHAKE:NCGN`, `SHAKE:BARD`, and `SHAKE:WSRN`. ")] = None,
        stream_type: Annotated[Optional[StreamType], Field(description="Filter stream results by type. Defaults to all stream types. This only applies to streams.")] = None,
        facility: Annotated[Optional[Facility], Field(description="Filter stream results based on facility, i.e. where the position was processed, not where the raw stream originated. Defaults to all facilities. Only applies to streams.")] = None,
        with_information: Annotated[Optional[StrictBool], Field(description="Include station/stream name(s) and location). Defaults to `false`, and only returns EarthScope Datasource IDs (EDIDs).")] = None,
        bypass_cache: Annotated[Optional[StrictBool], Field(description="Skip the cached result and fetch fresh data. The fresh result is still written to the cache.")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[ResponseRadialSearchStreamsRefposSearchRadialGet]:
        """GNSS Station Radial Search

        Find stations or streams within a certain distance (in km) from a given center point (latitude and longitude in decimal degrees).  Uses the [Haversine formula](https://en.wikipedia.org/wiki/Haversine_formula) to compute great-circle distance.  Usage notes: - The `with_information` query parameter controls the shape of the reponse. Either of the following is returned:     - a list of the EarthScope Datasource IDs (EDIDs) of the stations/streams     - a list of more complete information about stations/streams including names and locations - `network` is used to filter both stations and streams, though the actual network name is not returned in the results. - `facility` and `stream_type` are both used to filter stream results only, and are ignored if `tier` is set to `station`.  This endpoint will temporarily be available for public access while we develop other endpoints.

        :param latitude: Latitude in decimal degrees (required)
        :type latitude: float
        :param longitude: Longitude in decimal degrees (required)
        :type longitude: float
        :param distance: Search radius distance in km (required)
        :type distance: float
        :param tier: Whether to search for stations or streams.
        :type tier: ReferencePositionTier
        :param network: Network name(s). Can contain leading/trailing wildcards. Used to filter both stations and streams. Omit to search all networks.          ShakeAlert uses the network namespace `SHAKE:`, with valid network names being `SHAKE:ShakeAlert` (all stations in ShakeAlert), `SHAKE:IGS`, `SHAKE:PNGA`, `SHAKE:WCDA`, `SHAKE:ORGN`, `SHAKE:NOTA`, `SHAKE:CRTN`, `SHAKE:NCGN`, `SHAKE:BARD`, and `SHAKE:WSRN`. 
        :type network: List[str]
        :param stream_type: Filter stream results by type. Defaults to all stream types. This only applies to streams.
        :type stream_type: StreamType
        :param facility: Filter stream results based on facility, i.e. where the position was processed, not where the raw stream originated. Defaults to all facilities. Only applies to streams.
        :type facility: Facility
        :param with_information: Include station/stream name(s) and location). Defaults to `false`, and only returns EarthScope Datasource IDs (EDIDs).
        :type with_information: bool
        :param bypass_cache: Skip the cached result and fetch fresh data. The fresh result is still written to the cache.
        :type bypass_cache: bool
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_gnss_stations_radial_serialize(
            latitude=latitude,
            longitude=longitude,
            distance=distance,
            tier=tier,
            network=network,
            stream_type=stream_type,
            facility=facility,
            with_information=with_information,
            bypass_cache=bypass_cache,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseRadialSearchStreamsRefposSearchRadialGet",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )


    @validate_call
    def find_gnss_stations_radial_without_preload_content(
        self,
        latitude: Annotated[Union[Annotated[float, Field(le=90, strict=True, ge=-90)], Annotated[int, Field(le=90, strict=True, ge=-90)]], Field(description="Latitude in decimal degrees")],
        longitude: Annotated[Union[Annotated[float, Field(le=180, strict=True, ge=-180)], Annotated[int, Field(le=180, strict=True, ge=-180)]], Field(description="Longitude in decimal degrees")],
        distance: Annotated[Union[StrictFloat, StrictInt], Field(description="Search radius distance in km")],
        tier: Annotated[Optional[ReferencePositionTier], Field(description="Whether to search for stations or streams.")] = None,
        network: Annotated[Optional[List[StrictStr]], Field(description="Network name(s). Can contain leading/trailing wildcards. Used to filter both stations and streams. Omit to search all networks.          ShakeAlert uses the network namespace `SHAKE:`, with valid network names being `SHAKE:ShakeAlert` (all stations in ShakeAlert), `SHAKE:IGS`, `SHAKE:PNGA`, `SHAKE:WCDA`, `SHAKE:ORGN`, `SHAKE:NOTA`, `SHAKE:CRTN`, `SHAKE:NCGN`, `SHAKE:BARD`, and `SHAKE:WSRN`. ")] = None,
        stream_type: Annotated[Optional[StreamType], Field(description="Filter stream results by type. Defaults to all stream types. This only applies to streams.")] = None,
        facility: Annotated[Optional[Facility], Field(description="Filter stream results based on facility, i.e. where the position was processed, not where the raw stream originated. Defaults to all facilities. Only applies to streams.")] = None,
        with_information: Annotated[Optional[StrictBool], Field(description="Include station/stream name(s) and location). Defaults to `false`, and only returns EarthScope Datasource IDs (EDIDs).")] = None,
        bypass_cache: Annotated[Optional[StrictBool], Field(description="Skip the cached result and fetch fresh data. The fresh result is still written to the cache.")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """GNSS Station Radial Search

        Find stations or streams within a certain distance (in km) from a given center point (latitude and longitude in decimal degrees).  Uses the [Haversine formula](https://en.wikipedia.org/wiki/Haversine_formula) to compute great-circle distance.  Usage notes: - The `with_information` query parameter controls the shape of the reponse. Either of the following is returned:     - a list of the EarthScope Datasource IDs (EDIDs) of the stations/streams     - a list of more complete information about stations/streams including names and locations - `network` is used to filter both stations and streams, though the actual network name is not returned in the results. - `facility` and `stream_type` are both used to filter stream results only, and are ignored if `tier` is set to `station`.  This endpoint will temporarily be available for public access while we develop other endpoints.

        :param latitude: Latitude in decimal degrees (required)
        :type latitude: float
        :param longitude: Longitude in decimal degrees (required)
        :type longitude: float
        :param distance: Search radius distance in km (required)
        :type distance: float
        :param tier: Whether to search for stations or streams.
        :type tier: ReferencePositionTier
        :param network: Network name(s). Can contain leading/trailing wildcards. Used to filter both stations and streams. Omit to search all networks.          ShakeAlert uses the network namespace `SHAKE:`, with valid network names being `SHAKE:ShakeAlert` (all stations in ShakeAlert), `SHAKE:IGS`, `SHAKE:PNGA`, `SHAKE:WCDA`, `SHAKE:ORGN`, `SHAKE:NOTA`, `SHAKE:CRTN`, `SHAKE:NCGN`, `SHAKE:BARD`, and `SHAKE:WSRN`. 
        :type network: List[str]
        :param stream_type: Filter stream results by type. Defaults to all stream types. This only applies to streams.
        :type stream_type: StreamType
        :param facility: Filter stream results based on facility, i.e. where the position was processed, not where the raw stream originated. Defaults to all facilities. Only applies to streams.
        :type facility: Facility
        :param with_information: Include station/stream name(s) and location). Defaults to `false`, and only returns EarthScope Datasource IDs (EDIDs).
        :type with_information: bool
        :param bypass_cache: Skip the cached result and fetch fresh data. The fresh result is still written to the cache.
        :type bypass_cache: bool
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_gnss_stations_radial_serialize(
            latitude=latitude,
            longitude=longitude,
            distance=distance,
            tier=tier,
            network=network,
            stream_type=stream_type,
            facility=facility,
            with_information=with_information,
            bypass_cache=bypass_cache,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseRadialSearchStreamsRefposSearchRadialGet",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _find_gnss_stations_radial_serialize(
        self,
        latitude,
        longitude,
        distance,
        tier,
        network,
        stream_type,
        facility,
        with_information,
        bypass_cache,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'network': 'multi',
        }

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        # process the query parameters
        if latitude is not None:
            
            _query_params.append(('latitude', latitude))
            
        if longitude is not None:
            
            _query_params.append(('longitude', longitude))
            
        if distance is not None:
            
            _query_params.append(('distance', distance))
            
        if tier is not None:
            
            _query_params.append(('tier', tier.value))
            
        if network is not None:
            
            _query_params.append(('network', network))
            
        if stream_type is not None:
            
            _query_params.append(('stream_type', stream_type.value))
            
        if facility is not None:
            
            _query_params.append(('facility', facility.value))
            
        if with_information is not None:
            
            _query_params.append(('with_information', with_information))
            
        if bypass_cache is not None:
            
            _query_params.append(('bypass_cache', bypass_cache))
            
        # process the header parameters
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/json'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/discover/gnss/radial',
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth
        )




    @validate_call
    def find_network_datasources(
        self,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ResponseDefaultFindNetworks:
        """Find Network Datasources

        Find Network datasources

        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_network_datasources_serialize(
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindNetworks",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data


    @validate_call
    def find_network_datasources_with_http_info(
        self,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[ResponseDefaultFindNetworks]:
        """Find Network Datasources

        Find Network datasources

        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_network_datasources_serialize(
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindNetworks",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )


    @validate_call
    def find_network_datasources_without_preload_content(
        self,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Find Network Datasources

        Find Network datasources

        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_network_datasources_serialize(
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindNetworks",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _find_network_datasources_serialize(
        self,
        network_name,
        network_edid,
        with_edid_only,
        with_parents,
        with_parent_edids,
        limit,
        offset,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'network_name': 'multi',
            'network_edid': 'multi',
        }

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        # process the query parameters
        if network_name is not None:
            
            _query_params.append(('network_name', network_name))
            
        if network_edid is not None:
            
            _query_params.append(('network_edid', network_edid))
            
        if with_edid_only is not None:
            
            _query_params.append(('with_edid_only', with_edid_only))
            
        if with_parents is not None:
            
            _query_params.append(('with_parents', with_parents))
            
        if with_parent_edids is not None:
            
            _query_params.append(('with_parent_edids', with_parent_edids))
            
        if limit is not None:
            
            _query_params.append(('limit', limit))
            
        if offset is not None:
            
            _query_params.append(('offset', offset))
            
        # process the header parameters
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/json'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/discover/datasource/network',
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth
        )




    @validate_call
    def find_session_datasources(
        self,
        session_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Session name(s).  It is recommended to specify fully-qualified session names including namespace. If a namespace is not specified, then it is assumed to be `DATAFLOW`.  | **Namespace** | **Example**                | **Description**                    | | ------------- | -------------------------- | -----------------------------------| | `DATAFLOW`    | `DATAFLOW:A`, `DATAFLOW:M` | EarthScope data-flow naming scheme |  ---  Common session names and their meanings:  | Type   | Name             | Sample Interval | File Roll Period | Description                                                  | | ------ | ---------------- | --------------- | ---------------- | ------------------------------------------------------------- | | GNSS   | `DATAFLOW:A`     | 15s             | 24h (86,400s)    | 15-second, daily GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:B`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:C`     | 5Hz             |  1h  (3,600s)    | 5Hz, hourly GNSS observations file (receiver download)        | | GNSS   | `DATAFLOW:F`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:M`     | 15s             |  1h  (3,600s)    | 15-second, hourly GNSS observations file (receiver download)  | | GNSS   | `DATAFLOW:R`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (realtime stream)     | | Strain | `DATAFLOW:Day`   | 10m             | 24h (86,400s)    | 10-minute, daily strain file                                  | | Strain | `DATAFLOW:Hour`  | 1s              |  1h  (3,600s)    | 1-second, hourly strain file                                  | | Strain | `DATAFLOW:Min`   | 20Hz            |  1h  (3,600s)    | 20Hz, hourly strain file                                      | ")] = None,
        session_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Session EDID(s)")] = None,
        sample_interval: Annotated[Optional[SessionSampleInterval], Field(description="Session sample interval (in milliseconds)")] = None,
        roll: Annotated[Optional[SessionRollPeriod], Field(description="Session file roll period (in seconds)")] = None,
        station_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | ")] = None,
        station_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Station EDID(s)")] = None,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ResponseDefaultFindSessions:
        """Find Session Datasources

        Find Session datasources

        :param session_name: Session name(s).  It is recommended to specify fully-qualified session names including namespace. If a namespace is not specified, then it is assumed to be `DATAFLOW`.  | **Namespace** | **Example**                | **Description**                    | | ------------- | -------------------------- | -----------------------------------| | `DATAFLOW`    | `DATAFLOW:A`, `DATAFLOW:M` | EarthScope data-flow naming scheme |  ---  Common session names and their meanings:  | Type   | Name             | Sample Interval | File Roll Period | Description                                                  | | ------ | ---------------- | --------------- | ---------------- | ------------------------------------------------------------- | | GNSS   | `DATAFLOW:A`     | 15s             | 24h (86,400s)    | 15-second, daily GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:B`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:C`     | 5Hz             |  1h  (3,600s)    | 5Hz, hourly GNSS observations file (receiver download)        | | GNSS   | `DATAFLOW:F`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:M`     | 15s             |  1h  (3,600s)    | 15-second, hourly GNSS observations file (receiver download)  | | GNSS   | `DATAFLOW:R`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (realtime stream)     | | Strain | `DATAFLOW:Day`   | 10m             | 24h (86,400s)    | 10-minute, daily strain file                                  | | Strain | `DATAFLOW:Hour`  | 1s              |  1h  (3,600s)    | 1-second, hourly strain file                                  | | Strain | `DATAFLOW:Min`   | 20Hz            |  1h  (3,600s)    | 20Hz, hourly strain file                                      | 
        :type session_name: List[str]
        :param session_edid: Session EDID(s)
        :type session_edid: List[str]
        :param sample_interval: Session sample interval (in milliseconds)
        :type sample_interval: SessionSampleInterval
        :param roll: Session file roll period (in seconds)
        :type roll: SessionRollPeriod
        :param station_name: Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | 
        :type station_name: List[str]
        :param station_edid: Station EDID(s)
        :type station_edid: List[str]
        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_session_datasources_serialize(
            session_name=session_name,
            session_edid=session_edid,
            sample_interval=sample_interval,
            roll=roll,
            station_name=station_name,
            station_edid=station_edid,
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindSessions",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data


    @validate_call
    def find_session_datasources_with_http_info(
        self,
        session_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Session name(s).  It is recommended to specify fully-qualified session names including namespace. If a namespace is not specified, then it is assumed to be `DATAFLOW`.  | **Namespace** | **Example**                | **Description**                    | | ------------- | -------------------------- | -----------------------------------| | `DATAFLOW`    | `DATAFLOW:A`, `DATAFLOW:M` | EarthScope data-flow naming scheme |  ---  Common session names and their meanings:  | Type   | Name             | Sample Interval | File Roll Period | Description                                                  | | ------ | ---------------- | --------------- | ---------------- | ------------------------------------------------------------- | | GNSS   | `DATAFLOW:A`     | 15s             | 24h (86,400s)    | 15-second, daily GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:B`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:C`     | 5Hz             |  1h  (3,600s)    | 5Hz, hourly GNSS observations file (receiver download)        | | GNSS   | `DATAFLOW:F`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:M`     | 15s             |  1h  (3,600s)    | 15-second, hourly GNSS observations file (receiver download)  | | GNSS   | `DATAFLOW:R`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (realtime stream)     | | Strain | `DATAFLOW:Day`   | 10m             | 24h (86,400s)    | 10-minute, daily strain file                                  | | Strain | `DATAFLOW:Hour`  | 1s              |  1h  (3,600s)    | 1-second, hourly strain file                                  | | Strain | `DATAFLOW:Min`   | 20Hz            |  1h  (3,600s)    | 20Hz, hourly strain file                                      | ")] = None,
        session_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Session EDID(s)")] = None,
        sample_interval: Annotated[Optional[SessionSampleInterval], Field(description="Session sample interval (in milliseconds)")] = None,
        roll: Annotated[Optional[SessionRollPeriod], Field(description="Session file roll period (in seconds)")] = None,
        station_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | ")] = None,
        station_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Station EDID(s)")] = None,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[ResponseDefaultFindSessions]:
        """Find Session Datasources

        Find Session datasources

        :param session_name: Session name(s).  It is recommended to specify fully-qualified session names including namespace. If a namespace is not specified, then it is assumed to be `DATAFLOW`.  | **Namespace** | **Example**                | **Description**                    | | ------------- | -------------------------- | -----------------------------------| | `DATAFLOW`    | `DATAFLOW:A`, `DATAFLOW:M` | EarthScope data-flow naming scheme |  ---  Common session names and their meanings:  | Type   | Name             | Sample Interval | File Roll Period | Description                                                  | | ------ | ---------------- | --------------- | ---------------- | ------------------------------------------------------------- | | GNSS   | `DATAFLOW:A`     | 15s             | 24h (86,400s)    | 15-second, daily GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:B`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:C`     | 5Hz             |  1h  (3,600s)    | 5Hz, hourly GNSS observations file (receiver download)        | | GNSS   | `DATAFLOW:F`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:M`     | 15s             |  1h  (3,600s)    | 15-second, hourly GNSS observations file (receiver download)  | | GNSS   | `DATAFLOW:R`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (realtime stream)     | | Strain | `DATAFLOW:Day`   | 10m             | 24h (86,400s)    | 10-minute, daily strain file                                  | | Strain | `DATAFLOW:Hour`  | 1s              |  1h  (3,600s)    | 1-second, hourly strain file                                  | | Strain | `DATAFLOW:Min`   | 20Hz            |  1h  (3,600s)    | 20Hz, hourly strain file                                      | 
        :type session_name: List[str]
        :param session_edid: Session EDID(s)
        :type session_edid: List[str]
        :param sample_interval: Session sample interval (in milliseconds)
        :type sample_interval: SessionSampleInterval
        :param roll: Session file roll period (in seconds)
        :type roll: SessionRollPeriod
        :param station_name: Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | 
        :type station_name: List[str]
        :param station_edid: Station EDID(s)
        :type station_edid: List[str]
        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_session_datasources_serialize(
            session_name=session_name,
            session_edid=session_edid,
            sample_interval=sample_interval,
            roll=roll,
            station_name=station_name,
            station_edid=station_edid,
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindSessions",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )


    @validate_call
    def find_session_datasources_without_preload_content(
        self,
        session_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Session name(s).  It is recommended to specify fully-qualified session names including namespace. If a namespace is not specified, then it is assumed to be `DATAFLOW`.  | **Namespace** | **Example**                | **Description**                    | | ------------- | -------------------------- | -----------------------------------| | `DATAFLOW`    | `DATAFLOW:A`, `DATAFLOW:M` | EarthScope data-flow naming scheme |  ---  Common session names and their meanings:  | Type   | Name             | Sample Interval | File Roll Period | Description                                                  | | ------ | ---------------- | --------------- | ---------------- | ------------------------------------------------------------- | | GNSS   | `DATAFLOW:A`     | 15s             | 24h (86,400s)    | 15-second, daily GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:B`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:C`     | 5Hz             |  1h  (3,600s)    | 5Hz, hourly GNSS observations file (receiver download)        | | GNSS   | `DATAFLOW:F`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:M`     | 15s             |  1h  (3,600s)    | 15-second, hourly GNSS observations file (receiver download)  | | GNSS   | `DATAFLOW:R`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (realtime stream)     | | Strain | `DATAFLOW:Day`   | 10m             | 24h (86,400s)    | 10-minute, daily strain file                                  | | Strain | `DATAFLOW:Hour`  | 1s              |  1h  (3,600s)    | 1-second, hourly strain file                                  | | Strain | `DATAFLOW:Min`   | 20Hz            |  1h  (3,600s)    | 20Hz, hourly strain file                                      | ")] = None,
        session_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Session EDID(s)")] = None,
        sample_interval: Annotated[Optional[SessionSampleInterval], Field(description="Session sample interval (in milliseconds)")] = None,
        roll: Annotated[Optional[SessionRollPeriod], Field(description="Session file roll period (in seconds)")] = None,
        station_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | ")] = None,
        station_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Station EDID(s)")] = None,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Find Session Datasources

        Find Session datasources

        :param session_name: Session name(s).  It is recommended to specify fully-qualified session names including namespace. If a namespace is not specified, then it is assumed to be `DATAFLOW`.  | **Namespace** | **Example**                | **Description**                    | | ------------- | -------------------------- | -----------------------------------| | `DATAFLOW`    | `DATAFLOW:A`, `DATAFLOW:M` | EarthScope data-flow naming scheme |  ---  Common session names and their meanings:  | Type   | Name             | Sample Interval | File Roll Period | Description                                                  | | ------ | ---------------- | --------------- | ---------------- | ------------------------------------------------------------- | | GNSS   | `DATAFLOW:A`     | 15s             | 24h (86,400s)    | 15-second, daily GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:B`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:C`     | 5Hz             |  1h  (3,600s)    | 5Hz, hourly GNSS observations file (receiver download)        | | GNSS   | `DATAFLOW:F`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (receiver download)   | | GNSS   | `DATAFLOW:M`     | 15s             |  1h  (3,600s)    | 15-second, hourly GNSS observations file (receiver download)  | | GNSS   | `DATAFLOW:R`     | 1s              |  1h  (3,600s)    | 1-second, hourly GNSS observations file (realtime stream)     | | Strain | `DATAFLOW:Day`   | 10m             | 24h (86,400s)    | 10-minute, daily strain file                                  | | Strain | `DATAFLOW:Hour`  | 1s              |  1h  (3,600s)    | 1-second, hourly strain file                                  | | Strain | `DATAFLOW:Min`   | 20Hz            |  1h  (3,600s)    | 20Hz, hourly strain file                                      | 
        :type session_name: List[str]
        :param session_edid: Session EDID(s)
        :type session_edid: List[str]
        :param sample_interval: Session sample interval (in milliseconds)
        :type sample_interval: SessionSampleInterval
        :param roll: Session file roll period (in seconds)
        :type roll: SessionRollPeriod
        :param station_name: Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | 
        :type station_name: List[str]
        :param station_edid: Station EDID(s)
        :type station_edid: List[str]
        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_session_datasources_serialize(
            session_name=session_name,
            session_edid=session_edid,
            sample_interval=sample_interval,
            roll=roll,
            station_name=station_name,
            station_edid=station_edid,
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindSessions",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _find_session_datasources_serialize(
        self,
        session_name,
        session_edid,
        sample_interval,
        roll,
        station_name,
        station_edid,
        network_name,
        network_edid,
        with_edid_only,
        with_parents,
        with_parent_edids,
        limit,
        offset,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'session_name': 'multi',
            'session_edid': 'multi',
            'station_name': 'multi',
            'station_edid': 'multi',
            'network_name': 'multi',
            'network_edid': 'multi',
        }

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        # process the query parameters
        if session_name is not None:
            
            _query_params.append(('session_name', session_name))
            
        if session_edid is not None:
            
            _query_params.append(('session_edid', session_edid))
            
        if sample_interval is not None:
            
            _query_params.append(('sample_interval', sample_interval.value))
            
        if roll is not None:
            
            _query_params.append(('roll', roll.value))
            
        if station_name is not None:
            
            _query_params.append(('station_name', station_name))
            
        if station_edid is not None:
            
            _query_params.append(('station_edid', station_edid))
            
        if network_name is not None:
            
            _query_params.append(('network_name', network_name))
            
        if network_edid is not None:
            
            _query_params.append(('network_edid', network_edid))
            
        if with_edid_only is not None:
            
            _query_params.append(('with_edid_only', with_edid_only))
            
        if with_parents is not None:
            
            _query_params.append(('with_parents', with_parents))
            
        if with_parent_edids is not None:
            
            _query_params.append(('with_parent_edids', with_parent_edids))
            
        if limit is not None:
            
            _query_params.append(('limit', limit))
            
        if offset is not None:
            
            _query_params.append(('offset', offset))
            
        # process the header parameters
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/json'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/discover/datasource/session',
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth
        )




    @validate_call
    def find_station_datasources(
        self,
        station_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | ")] = None,
        station_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Station EDID(s)")] = None,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ResponseDefaultFindStations:
        """Find Station Datasources

        Find Station datasources

        :param station_name: Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | 
        :type station_name: List[str]
        :param station_edid: Station EDID(s)
        :type station_edid: List[str]
        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_station_datasources_serialize(
            station_name=station_name,
            station_edid=station_edid,
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindStations",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data


    @validate_call
    def find_station_datasources_with_http_info(
        self,
        station_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | ")] = None,
        station_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Station EDID(s)")] = None,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[ResponseDefaultFindStations]:
        """Find Station Datasources

        Find Station datasources

        :param station_name: Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | 
        :type station_name: List[str]
        :param station_edid: Station EDID(s)
        :type station_edid: List[str]
        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_station_datasources_serialize(
            station_name=station_name,
            station_edid=station_edid,
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindStations",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )


    @validate_call
    def find_station_datasources_without_preload_content(
        self,
        station_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | ")] = None,
        station_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Station EDID(s)")] = None,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Find Station Datasources

        Find Station datasources

        :param station_name: Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | 
        :type station_name: List[str]
        :param station_edid: Station EDID(s)
        :type station_edid: List[str]
        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_station_datasources_serialize(
            station_name=station_name,
            station_edid=station_edid,
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindStations",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _find_station_datasources_serialize(
        self,
        station_name,
        station_edid,
        network_name,
        network_edid,
        with_edid_only,
        with_parents,
        with_parent_edids,
        limit,
        offset,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'station_name': 'multi',
            'station_edid': 'multi',
            'network_name': 'multi',
            'network_edid': 'multi',
        }

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        # process the query parameters
        if station_name is not None:
            
            _query_params.append(('station_name', station_name))
            
        if station_edid is not None:
            
            _query_params.append(('station_edid', station_edid))
            
        if network_name is not None:
            
            _query_params.append(('network_name', network_name))
            
        if network_edid is not None:
            
            _query_params.append(('network_edid', network_edid))
            
        if with_edid_only is not None:
            
            _query_params.append(('with_edid_only', with_edid_only))
            
        if with_parents is not None:
            
            _query_params.append(('with_parents', with_parents))
            
        if with_parent_edids is not None:
            
            _query_params.append(('with_parent_edids', with_parent_edids))
            
        if limit is not None:
            
            _query_params.append(('limit', limit))
            
        if offset is not None:
            
            _query_params.append(('offset', offset))
            
        # process the header parameters
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/json'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/discover/datasource/station',
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth
        )




    @validate_call
    def find_stream_datasources(
        self,
        stream_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Stream name(s).  It is recommended to specify fully-qualified stream names including namespace. If a namespace is not specified, then it is guessed based on the input.  | **Namespace** | **Example**                      | **Description**                               | | ------------- | -------------------------------- | --------------------------------------------- | | `GEOSNCL`     | `GEOSNCL:P146.PB.LY_.00`         | ShakeAlert GNSS position stream naming scheme | | `SN`          | `SN:P146.RAW.EARTHSCOPE.1HZ`     | EarthScope descriptive stream naming scheme   | ")] = None,
        stream_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Stream EDID(s)")] = None,
        stream_type: Annotated[Optional[StreamType], Field(description="What type of stream is this?   |Value|Description| |-|-| |`gnss_ppp`|GNSS precise point position stream| |`gnss_raw`|GNSS raw data stream (normally BINEX or RTCM)| |`gnss_tdcp`|GNSS TDCP velocity stream| ")] = None,
        facility: Annotated[Optional[Facility], Field(description="From which facility did this stream originate?   |Value|Description| |-|-| |`caltech`|California Institute of Technology| |`csn`|Centro Sismológico Nacional, Universidad de Chile| |`cwu`|Central Washington University| |`earthscope`|EarthScope Consortium| |`igepn`|El Instituto Geofísico de la Escuela Politécnica Nacional| |`ineter`|Instituto Nicaragüense de Estudios Territoriales| |`ncgn`|Northern California Geodetic Network| |`sgc`|Servicio Geológico Colombiano| |`ucb`|UC Berkeley| |`ucsb`|UC Santa Barbara| |`unknown`|Unknown facility| |`usgs_csrc`|USGS California Spatial Reference Center| |`usgs_menlo_park`|USGS Menlo Park| |`usgs_pasadena`|USGS Pasadena| ")] = None,
        software: Annotated[Optional[StreamSoftware], Field(description="What software created this stream?")] = None,
        label: Annotated[Optional[StrictStr], Field(description="Free-form string label for the stream")] = None,
        sample_interval: Annotated[Optional[StreamSampleInterval], Field(description="Stream sample interval (in milliseconds)")] = None,
        station_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | ")] = None,
        station_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Station EDID(s)")] = None,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ResponseDefaultFindStreams:
        """Find Stream Datasources

        Find Stream datasources

        :param stream_name: Stream name(s).  It is recommended to specify fully-qualified stream names including namespace. If a namespace is not specified, then it is guessed based on the input.  | **Namespace** | **Example**                      | **Description**                               | | ------------- | -------------------------------- | --------------------------------------------- | | `GEOSNCL`     | `GEOSNCL:P146.PB.LY_.00`         | ShakeAlert GNSS position stream naming scheme | | `SN`          | `SN:P146.RAW.EARTHSCOPE.1HZ`     | EarthScope descriptive stream naming scheme   | 
        :type stream_name: List[str]
        :param stream_edid: Stream EDID(s)
        :type stream_edid: List[str]
        :param stream_type: What type of stream is this?   |Value|Description| |-|-| |`gnss_ppp`|GNSS precise point position stream| |`gnss_raw`|GNSS raw data stream (normally BINEX or RTCM)| |`gnss_tdcp`|GNSS TDCP velocity stream| 
        :type stream_type: StreamType
        :param facility: From which facility did this stream originate?   |Value|Description| |-|-| |`caltech`|California Institute of Technology| |`csn`|Centro Sismológico Nacional, Universidad de Chile| |`cwu`|Central Washington University| |`earthscope`|EarthScope Consortium| |`igepn`|El Instituto Geofísico de la Escuela Politécnica Nacional| |`ineter`|Instituto Nicaragüense de Estudios Territoriales| |`ncgn`|Northern California Geodetic Network| |`sgc`|Servicio Geológico Colombiano| |`ucb`|UC Berkeley| |`ucsb`|UC Santa Barbara| |`unknown`|Unknown facility| |`usgs_csrc`|USGS California Spatial Reference Center| |`usgs_menlo_park`|USGS Menlo Park| |`usgs_pasadena`|USGS Pasadena| 
        :type facility: Facility
        :param software: What software created this stream?
        :type software: StreamSoftware
        :param label: Free-form string label for the stream
        :type label: str
        :param sample_interval: Stream sample interval (in milliseconds)
        :type sample_interval: StreamSampleInterval
        :param station_name: Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | 
        :type station_name: List[str]
        :param station_edid: Station EDID(s)
        :type station_edid: List[str]
        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_stream_datasources_serialize(
            stream_name=stream_name,
            stream_edid=stream_edid,
            stream_type=stream_type,
            facility=facility,
            software=software,
            label=label,
            sample_interval=sample_interval,
            station_name=station_name,
            station_edid=station_edid,
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindStreams",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        ).data


    @validate_call
    def find_stream_datasources_with_http_info(
        self,
        stream_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Stream name(s).  It is recommended to specify fully-qualified stream names including namespace. If a namespace is not specified, then it is guessed based on the input.  | **Namespace** | **Example**                      | **Description**                               | | ------------- | -------------------------------- | --------------------------------------------- | | `GEOSNCL`     | `GEOSNCL:P146.PB.LY_.00`         | ShakeAlert GNSS position stream naming scheme | | `SN`          | `SN:P146.RAW.EARTHSCOPE.1HZ`     | EarthScope descriptive stream naming scheme   | ")] = None,
        stream_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Stream EDID(s)")] = None,
        stream_type: Annotated[Optional[StreamType], Field(description="What type of stream is this?   |Value|Description| |-|-| |`gnss_ppp`|GNSS precise point position stream| |`gnss_raw`|GNSS raw data stream (normally BINEX or RTCM)| |`gnss_tdcp`|GNSS TDCP velocity stream| ")] = None,
        facility: Annotated[Optional[Facility], Field(description="From which facility did this stream originate?   |Value|Description| |-|-| |`caltech`|California Institute of Technology| |`csn`|Centro Sismológico Nacional, Universidad de Chile| |`cwu`|Central Washington University| |`earthscope`|EarthScope Consortium| |`igepn`|El Instituto Geofísico de la Escuela Politécnica Nacional| |`ineter`|Instituto Nicaragüense de Estudios Territoriales| |`ncgn`|Northern California Geodetic Network| |`sgc`|Servicio Geológico Colombiano| |`ucb`|UC Berkeley| |`ucsb`|UC Santa Barbara| |`unknown`|Unknown facility| |`usgs_csrc`|USGS California Spatial Reference Center| |`usgs_menlo_park`|USGS Menlo Park| |`usgs_pasadena`|USGS Pasadena| ")] = None,
        software: Annotated[Optional[StreamSoftware], Field(description="What software created this stream?")] = None,
        label: Annotated[Optional[StrictStr], Field(description="Free-form string label for the stream")] = None,
        sample_interval: Annotated[Optional[StreamSampleInterval], Field(description="Stream sample interval (in milliseconds)")] = None,
        station_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | ")] = None,
        station_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Station EDID(s)")] = None,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> ApiResponse[ResponseDefaultFindStreams]:
        """Find Stream Datasources

        Find Stream datasources

        :param stream_name: Stream name(s).  It is recommended to specify fully-qualified stream names including namespace. If a namespace is not specified, then it is guessed based on the input.  | **Namespace** | **Example**                      | **Description**                               | | ------------- | -------------------------------- | --------------------------------------------- | | `GEOSNCL`     | `GEOSNCL:P146.PB.LY_.00`         | ShakeAlert GNSS position stream naming scheme | | `SN`          | `SN:P146.RAW.EARTHSCOPE.1HZ`     | EarthScope descriptive stream naming scheme   | 
        :type stream_name: List[str]
        :param stream_edid: Stream EDID(s)
        :type stream_edid: List[str]
        :param stream_type: What type of stream is this?   |Value|Description| |-|-| |`gnss_ppp`|GNSS precise point position stream| |`gnss_raw`|GNSS raw data stream (normally BINEX or RTCM)| |`gnss_tdcp`|GNSS TDCP velocity stream| 
        :type stream_type: StreamType
        :param facility: From which facility did this stream originate?   |Value|Description| |-|-| |`caltech`|California Institute of Technology| |`csn`|Centro Sismológico Nacional, Universidad de Chile| |`cwu`|Central Washington University| |`earthscope`|EarthScope Consortium| |`igepn`|El Instituto Geofísico de la Escuela Politécnica Nacional| |`ineter`|Instituto Nicaragüense de Estudios Territoriales| |`ncgn`|Northern California Geodetic Network| |`sgc`|Servicio Geológico Colombiano| |`ucb`|UC Berkeley| |`ucsb`|UC Santa Barbara| |`unknown`|Unknown facility| |`usgs_csrc`|USGS California Spatial Reference Center| |`usgs_menlo_park`|USGS Menlo Park| |`usgs_pasadena`|USGS Pasadena| 
        :type facility: Facility
        :param software: What software created this stream?
        :type software: StreamSoftware
        :param label: Free-form string label for the stream
        :type label: str
        :param sample_interval: Stream sample interval (in milliseconds)
        :type sample_interval: StreamSampleInterval
        :param station_name: Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | 
        :type station_name: List[str]
        :param station_edid: Station EDID(s)
        :type station_edid: List[str]
        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_stream_datasources_serialize(
            stream_name=stream_name,
            stream_edid=stream_edid,
            stream_type=stream_type,
            facility=facility,
            software=software,
            label=label,
            sample_interval=sample_interval,
            station_name=station_name,
            station_edid=station_edid,
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindStreams",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        response_data.read()
        return self.api_client.response_deserialize(
            response_data=response_data,
            response_types_map=_response_types_map,
        )


    @validate_call
    def find_stream_datasources_without_preload_content(
        self,
        stream_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Stream name(s).  It is recommended to specify fully-qualified stream names including namespace. If a namespace is not specified, then it is guessed based on the input.  | **Namespace** | **Example**                      | **Description**                               | | ------------- | -------------------------------- | --------------------------------------------- | | `GEOSNCL`     | `GEOSNCL:P146.PB.LY_.00`         | ShakeAlert GNSS position stream naming scheme | | `SN`          | `SN:P146.RAW.EARTHSCOPE.1HZ`     | EarthScope descriptive stream naming scheme   | ")] = None,
        stream_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Stream EDID(s)")] = None,
        stream_type: Annotated[Optional[StreamType], Field(description="What type of stream is this?   |Value|Description| |-|-| |`gnss_ppp`|GNSS precise point position stream| |`gnss_raw`|GNSS raw data stream (normally BINEX or RTCM)| |`gnss_tdcp`|GNSS TDCP velocity stream| ")] = None,
        facility: Annotated[Optional[Facility], Field(description="From which facility did this stream originate?   |Value|Description| |-|-| |`caltech`|California Institute of Technology| |`csn`|Centro Sismológico Nacional, Universidad de Chile| |`cwu`|Central Washington University| |`earthscope`|EarthScope Consortium| |`igepn`|El Instituto Geofísico de la Escuela Politécnica Nacional| |`ineter`|Instituto Nicaragüense de Estudios Territoriales| |`ncgn`|Northern California Geodetic Network| |`sgc`|Servicio Geológico Colombiano| |`ucb`|UC Berkeley| |`ucsb`|UC Santa Barbara| |`unknown`|Unknown facility| |`usgs_csrc`|USGS California Spatial Reference Center| |`usgs_menlo_park`|USGS Menlo Park| |`usgs_pasadena`|USGS Pasadena| ")] = None,
        software: Annotated[Optional[StreamSoftware], Field(description="What software created this stream?")] = None,
        label: Annotated[Optional[StrictStr], Field(description="Free-form string label for the stream")] = None,
        sample_interval: Annotated[Optional[StreamSampleInterval], Field(description="Stream sample interval (in milliseconds)")] = None,
        station_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | ")] = None,
        station_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Station EDID(s)")] = None,
        network_name: Annotated[Optional[Annotated[List[StrictStr], Field(max_length=100)]], Field(description="Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | ")] = None,
        network_edid: Annotated[Optional[Annotated[List[Annotated[str, Field(min_length=26, strict=True, max_length=26)]], Field(max_length=100)]], Field(description="Network EDID(s)")] = None,
        with_edid_only: Annotated[Optional[StrictBool], Field(description="Overrides all other projection properties to only return the datasource EDID(s)")] = None,
        with_parents: Annotated[Optional[StrictBool], Field(description="Include this datasource's parent(s) in the response model")] = None,
        with_parent_edids: Annotated[Optional[StrictBool], Field(description="Include this datasource's parents' EDIDs in the response model")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Pagination size limit")] = None,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Pagination start offset")] = None,
        _request_timeout: Union[
            None,
            Annotated[StrictFloat, Field(gt=0)],
            Tuple[
                Annotated[StrictFloat, Field(gt=0)],
                Annotated[StrictFloat, Field(gt=0)]
            ]
        ] = None,
        _request_auth: Optional[Dict[StrictStr, Any]] = None,
        _content_type: Optional[StrictStr] = None,
        _headers: Optional[Dict[StrictStr, Any]] = None,
        _host_index: Annotated[StrictInt, Field(ge=0, le=0)] = 0,
    ) -> RESTResponseType:
        """Find Stream Datasources

        Find Stream datasources

        :param stream_name: Stream name(s).  It is recommended to specify fully-qualified stream names including namespace. If a namespace is not specified, then it is guessed based on the input.  | **Namespace** | **Example**                      | **Description**                               | | ------------- | -------------------------------- | --------------------------------------------- | | `GEOSNCL`     | `GEOSNCL:P146.PB.LY_.00`         | ShakeAlert GNSS position stream naming scheme | | `SN`          | `SN:P146.RAW.EARTHSCOPE.1HZ`     | EarthScope descriptive stream naming scheme   | 
        :type stream_name: List[str]
        :param stream_edid: Stream EDID(s)
        :type stream_edid: List[str]
        :param stream_type: What type of stream is this?   |Value|Description| |-|-| |`gnss_ppp`|GNSS precise point position stream| |`gnss_raw`|GNSS raw data stream (normally BINEX or RTCM)| |`gnss_tdcp`|GNSS TDCP velocity stream| 
        :type stream_type: StreamType
        :param facility: From which facility did this stream originate?   |Value|Description| |-|-| |`caltech`|California Institute of Technology| |`csn`|Centro Sismológico Nacional, Universidad de Chile| |`cwu`|Central Washington University| |`earthscope`|EarthScope Consortium| |`igepn`|El Instituto Geofísico de la Escuela Politécnica Nacional| |`ineter`|Instituto Nicaragüense de Estudios Territoriales| |`ncgn`|Northern California Geodetic Network| |`sgc`|Servicio Geológico Colombiano| |`ucb`|UC Berkeley| |`ucsb`|UC Santa Barbara| |`unknown`|Unknown facility| |`usgs_csrc`|USGS California Spatial Reference Center| |`usgs_menlo_park`|USGS Menlo Park| |`usgs_pasadena`|USGS Pasadena| 
        :type facility: Facility
        :param software: What software created this stream?
        :type software: StreamSoftware
        :param label: Free-form string label for the stream
        :type label: str
        :param sample_interval: Stream sample interval (in milliseconds)
        :type sample_interval: StreamSampleInterval
        :param station_name: Station name(s).  It is recommended to specify fully-qualified station names including namespace. If a namespace is not specified, then it is guessed based on the length of the name you submit.  | **Namespace** | **Example**     | **Description**                                    | **Notes**                         | | ------------- | --------------- | -------------------------------------------------- | --------------------------------- | | `FDSN`        | `FDSN:PB_B207`  | FDSN Source Identifier station name                |                                   | | `IGS`         | `IGS:P14600USA` | IGS 9-character GNSS station naming scheme         |                                   | | `4CHARID`     | `4CHARID:P146`  | traditional 4-character GNSS station naming scheme | **DEPRECATED**: prefer `IGS` name | 
        :type station_name: List[str]
        :param station_edid: Station EDID(s)
        :type station_edid: List[str]
        :param network_name: Network name(s)  It is recommended to specify fully-qualified network names including namespace.  | **Namespace** | **Example**      | **Description**                                          | | ------------- | ---------------- | -------------------------------------------------------- | | `BSM`         | `BSM:NOTA`       | Borehole strainmeter network name                        | | `FDSN`        | `FDSN:PB`        | FDSN Source Identifier network name                      | | `PERM`        | `PERM:NOTA Core` | 'Permanent' network name from legacy Archive DB sets     | | `RTDB`        | `RTDB:PBO`       | 'Realtime' network name from legacy Realtime DB projects | | `SHAKE`       | `SHAKE:NOTA`     | ShakeAlert network name                                  | 
        :type network_name: List[str]
        :param network_edid: Network EDID(s)
        :type network_edid: List[str]
        :param with_edid_only: Overrides all other projection properties to only return the datasource EDID(s)
        :type with_edid_only: bool
        :param with_parents: Include this datasource's parent(s) in the response model
        :type with_parents: bool
        :param with_parent_edids: Include this datasource's parents' EDIDs in the response model
        :type with_parent_edids: bool
        :param limit: Pagination size limit
        :type limit: int
        :param offset: Pagination start offset
        :type offset: int
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        :type _request_timeout: int, tuple(int, int), optional
        :param _request_auth: set to override the auth_settings for an a single
                              request; this effectively ignores the
                              authentication in the spec for a single request.
        :type _request_auth: dict, optional
        :param _content_type: force content-type for the request.
        :type _content_type: str, Optional
        :param _headers: set to override the headers for a single
                         request; this effectively ignores the headers
                         in the spec for a single request.
        :type _headers: dict, optional
        :param _host_index: set to override the host_index for a single
                            request; this effectively ignores the host_index
                            in the spec for a single request.
        :type _host_index: int, optional
        :return: Returns the result object.
        """ # noqa: E501

        _param = self._find_stream_datasources_serialize(
            stream_name=stream_name,
            stream_edid=stream_edid,
            stream_type=stream_type,
            facility=facility,
            software=software,
            label=label,
            sample_interval=sample_interval,
            station_name=station_name,
            station_edid=station_edid,
            network_name=network_name,
            network_edid=network_edid,
            with_edid_only=with_edid_only,
            with_parents=with_parents,
            with_parent_edids=with_parent_edids,
            limit=limit,
            offset=offset,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "ResponseDefaultFindStreams",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _find_stream_datasources_serialize(
        self,
        stream_name,
        stream_edid,
        stream_type,
        facility,
        software,
        label,
        sample_interval,
        station_name,
        station_edid,
        network_name,
        network_edid,
        with_edid_only,
        with_parents,
        with_parent_edids,
        limit,
        offset,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'stream_name': 'multi',
            'stream_edid': 'multi',
            'station_name': 'multi',
            'station_edid': 'multi',
            'network_name': 'multi',
            'network_edid': 'multi',
        }

        _path_params: Dict[str, str] = {}
        _query_params: List[Tuple[str, str]] = []
        _header_params: Dict[str, Optional[str]] = _headers or {}
        _form_params: List[Tuple[str, str]] = []
        _files: Dict[
            str, Union[str, bytes, List[str], List[bytes], List[Tuple[str, bytes]]]
        ] = {}
        _body_params: Optional[bytes] = None

        # process the path parameters
        # process the query parameters
        if stream_name is not None:
            
            _query_params.append(('stream_name', stream_name))
            
        if stream_edid is not None:
            
            _query_params.append(('stream_edid', stream_edid))
            
        if stream_type is not None:
            
            _query_params.append(('stream_type', stream_type.value))
            
        if facility is not None:
            
            _query_params.append(('facility', facility.value))
            
        if software is not None:
            
            _query_params.append(('software', software.value))
            
        if label is not None:
            
            _query_params.append(('label', label))
            
        if sample_interval is not None:
            
            _query_params.append(('sample_interval', sample_interval.value))
            
        if station_name is not None:
            
            _query_params.append(('station_name', station_name))
            
        if station_edid is not None:
            
            _query_params.append(('station_edid', station_edid))
            
        if network_name is not None:
            
            _query_params.append(('network_name', network_name))
            
        if network_edid is not None:
            
            _query_params.append(('network_edid', network_edid))
            
        if with_edid_only is not None:
            
            _query_params.append(('with_edid_only', with_edid_only))
            
        if with_parents is not None:
            
            _query_params.append(('with_parents', with_parents))
            
        if with_parent_edids is not None:
            
            _query_params.append(('with_parent_edids', with_parent_edids))
            
        if limit is not None:
            
            _query_params.append(('limit', limit))
            
        if offset is not None:
            
            _query_params.append(('offset', offset))
            
        # process the header parameters
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/json'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/discover/datasource/stream',
            path_params=_path_params,
            query_params=_query_params,
            header_params=_header_params,
            body=_body_params,
            post_params=_form_params,
            files=_files,
            auth_settings=_auth_settings,
            collection_formats=_collection_formats,
            _host=_host,
            _request_auth=_request_auth
        )



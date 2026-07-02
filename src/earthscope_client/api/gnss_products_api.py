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

from datetime import datetime
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator
from typing import List, Optional, Union
from typing_extensions import Annotated
from earthscope_client.models.content_encoding import ContentEncoding
from earthscope_client.models.content_type import ContentType
from earthscope_client.models.inst_position import InstPosition
from earthscope_client.models.my_generic_ephemeris import MyGenericEphemeris
from earthscope_client.models.stream_data_split_response import StreamDataSplitResponse

from earthscope_client.api_client import ApiClient, RequestSerialized
from earthscope_client.api_response import ApiResponse
from earthscope_client.rest import RESTResponseType


class GNSSProductsApi:
    """NOTE: This class is auto generated by OpenAPI Generator
    Ref: https://openapi-generator.tech

    Do not edit the class manually.
    """

    def __init__(self, api_client=None) -> None:
        if api_client is None:
            api_client = ApiClient.get_default()
        self.api_client = api_client


    @validate_call
    def get_gnss_ephemeris(
        self,
        start_datetime: Annotated[datetime, Field(description="Start time (RFC3339), e.g. 2025-01-01T00:00:00Z.")],
        end_datetime: Annotated[datetime, Field(description="End time (RFC3339), e.g. 2025-01-01T23:59:59Z.")],
        accept: Annotated[Optional[StrictStr], Field(description="Response format. Use 'application/json' for JSON array, or 'text/plain' for RINEX navigation file.")] = None,
        system: Annotated[Optional[List[StrictStr]], Field(description="Constellations to include: G, R, E, J, C, I, S. Multiple allowed. For RINEX v2 output, exactly one system (G) is required.")] = None,
        satellite: Annotated[Optional[List[StrictInt]], Field(description="The Satellites by number to include, such as '2', '8', or '15'.")] = None,
        version: Annotated[Optional[Annotated[int, Field(le=4, strict=True, ge=2)]], Field(description="RINEX version for text/plain responses. 2 (default), 3, or 4. v2 supports GPS-only and single constellation; v3/v4 support multi-constellation.")] = None,
        dtype: Annotated[Optional[StrictStr], Field(description="Ephemeris data type, e.g. EPH.")] = None,
        mtype: Annotated[Optional[StrictStr], Field(description="Ephemeris message type, e.g. LNAV, INAV, FNAV, FDMA, etc.")] = None,
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
    ) -> List[MyGenericEphemeris]:
        """Ephemeris

        Ensure that the **system** parameter is one of the supported constellations (G, R, E, S, J, C). The order of the ephemeris values and their units can be found in the [RINEX 4.02 specification](https://files.igs.org/pub/data/format/rinex_4.02.pdf). The **dtype** parameter is the data type of the ephemeris record (e.g. EPH), and the **mtype** parameter is the message type of the ephemeris record (e.g. LNAV).  Content negotiation: - Set header 'Accept: application/json' to stream a JSON array of ephemeris objects. - Set header 'Accept: text/plain' to stream a RINEX navigation file. - Gzip compression is applied if the client sends 'Accept-Encoding: gzip'.  RINEX version & multi-constellation behavior (when Accept is text/plain): - 'version=2' (default): RINEX 2.11, requires exactly one system and supports GPS (G) only. - 'version=3' or 'version=4': RINEX 3.05 / 4.02, supports multiple constellations in a single file.  Filenames (via Content-Disposition attachment): - RINEX 2: short name 'brdcDDD0.YYn' (DDD=day-of-year, YY=2-digit year). - RINEX 3/4: long name 'BRDC00ORG_R_YYYYJJJhhmm_NNS_MN.rnx' where ORG is 'RINEX_ORG_CODE' (default IGS), timestamp is UTC start time, and NNS is the span (e.g., 01D). MN indicates multi-constellation nav.

        :param start_datetime: Start time (RFC3339), e.g. 2025-01-01T00:00:00Z. (required)
        :type start_datetime: datetime
        :param end_datetime: End time (RFC3339), e.g. 2025-01-01T23:59:59Z. (required)
        :type end_datetime: datetime
        :param accept: Response format. Use 'application/json' for JSON array, or 'text/plain' for RINEX navigation file.
        :type accept: str
        :param system: Constellations to include: G, R, E, J, C, I, S. Multiple allowed. For RINEX v2 output, exactly one system (G) is required.
        :type system: List[str]
        :param satellite: The Satellites by number to include, such as '2', '8', or '15'.
        :type satellite: List[int]
        :param version: RINEX version for text/plain responses. 2 (default), 3, or 4. v2 supports GPS-only and single constellation; v3/v4 support multi-constellation.
        :type version: int
        :param dtype: Ephemeris data type, e.g. EPH.
        :type dtype: str
        :param mtype: Ephemeris message type, e.g. LNAV, INAV, FNAV, FDMA, etc.
        :type mtype: str
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

        _param = self._get_gnss_ephemeris_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            accept=accept,
            system=system,
            satellite=satellite,
            version=version,
            dtype=dtype,
            mtype=mtype,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "List[MyGenericEphemeris]",
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
    def get_gnss_ephemeris_with_http_info(
        self,
        start_datetime: Annotated[datetime, Field(description="Start time (RFC3339), e.g. 2025-01-01T00:00:00Z.")],
        end_datetime: Annotated[datetime, Field(description="End time (RFC3339), e.g. 2025-01-01T23:59:59Z.")],
        accept: Annotated[Optional[StrictStr], Field(description="Response format. Use 'application/json' for JSON array, or 'text/plain' for RINEX navigation file.")] = None,
        system: Annotated[Optional[List[StrictStr]], Field(description="Constellations to include: G, R, E, J, C, I, S. Multiple allowed. For RINEX v2 output, exactly one system (G) is required.")] = None,
        satellite: Annotated[Optional[List[StrictInt]], Field(description="The Satellites by number to include, such as '2', '8', or '15'.")] = None,
        version: Annotated[Optional[Annotated[int, Field(le=4, strict=True, ge=2)]], Field(description="RINEX version for text/plain responses. 2 (default), 3, or 4. v2 supports GPS-only and single constellation; v3/v4 support multi-constellation.")] = None,
        dtype: Annotated[Optional[StrictStr], Field(description="Ephemeris data type, e.g. EPH.")] = None,
        mtype: Annotated[Optional[StrictStr], Field(description="Ephemeris message type, e.g. LNAV, INAV, FNAV, FDMA, etc.")] = None,
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
    ) -> ApiResponse[List[MyGenericEphemeris]]:
        """Ephemeris

        Ensure that the **system** parameter is one of the supported constellations (G, R, E, S, J, C). The order of the ephemeris values and their units can be found in the [RINEX 4.02 specification](https://files.igs.org/pub/data/format/rinex_4.02.pdf). The **dtype** parameter is the data type of the ephemeris record (e.g. EPH), and the **mtype** parameter is the message type of the ephemeris record (e.g. LNAV).  Content negotiation: - Set header 'Accept: application/json' to stream a JSON array of ephemeris objects. - Set header 'Accept: text/plain' to stream a RINEX navigation file. - Gzip compression is applied if the client sends 'Accept-Encoding: gzip'.  RINEX version & multi-constellation behavior (when Accept is text/plain): - 'version=2' (default): RINEX 2.11, requires exactly one system and supports GPS (G) only. - 'version=3' or 'version=4': RINEX 3.05 / 4.02, supports multiple constellations in a single file.  Filenames (via Content-Disposition attachment): - RINEX 2: short name 'brdcDDD0.YYn' (DDD=day-of-year, YY=2-digit year). - RINEX 3/4: long name 'BRDC00ORG_R_YYYYJJJhhmm_NNS_MN.rnx' where ORG is 'RINEX_ORG_CODE' (default IGS), timestamp is UTC start time, and NNS is the span (e.g., 01D). MN indicates multi-constellation nav.

        :param start_datetime: Start time (RFC3339), e.g. 2025-01-01T00:00:00Z. (required)
        :type start_datetime: datetime
        :param end_datetime: End time (RFC3339), e.g. 2025-01-01T23:59:59Z. (required)
        :type end_datetime: datetime
        :param accept: Response format. Use 'application/json' for JSON array, or 'text/plain' for RINEX navigation file.
        :type accept: str
        :param system: Constellations to include: G, R, E, J, C, I, S. Multiple allowed. For RINEX v2 output, exactly one system (G) is required.
        :type system: List[str]
        :param satellite: The Satellites by number to include, such as '2', '8', or '15'.
        :type satellite: List[int]
        :param version: RINEX version for text/plain responses. 2 (default), 3, or 4. v2 supports GPS-only and single constellation; v3/v4 support multi-constellation.
        :type version: int
        :param dtype: Ephemeris data type, e.g. EPH.
        :type dtype: str
        :param mtype: Ephemeris message type, e.g. LNAV, INAV, FNAV, FDMA, etc.
        :type mtype: str
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

        _param = self._get_gnss_ephemeris_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            accept=accept,
            system=system,
            satellite=satellite,
            version=version,
            dtype=dtype,
            mtype=mtype,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "List[MyGenericEphemeris]",
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
    def get_gnss_ephemeris_without_preload_content(
        self,
        start_datetime: Annotated[datetime, Field(description="Start time (RFC3339), e.g. 2025-01-01T00:00:00Z.")],
        end_datetime: Annotated[datetime, Field(description="End time (RFC3339), e.g. 2025-01-01T23:59:59Z.")],
        accept: Annotated[Optional[StrictStr], Field(description="Response format. Use 'application/json' for JSON array, or 'text/plain' for RINEX navigation file.")] = None,
        system: Annotated[Optional[List[StrictStr]], Field(description="Constellations to include: G, R, E, J, C, I, S. Multiple allowed. For RINEX v2 output, exactly one system (G) is required.")] = None,
        satellite: Annotated[Optional[List[StrictInt]], Field(description="The Satellites by number to include, such as '2', '8', or '15'.")] = None,
        version: Annotated[Optional[Annotated[int, Field(le=4, strict=True, ge=2)]], Field(description="RINEX version for text/plain responses. 2 (default), 3, or 4. v2 supports GPS-only and single constellation; v3/v4 support multi-constellation.")] = None,
        dtype: Annotated[Optional[StrictStr], Field(description="Ephemeris data type, e.g. EPH.")] = None,
        mtype: Annotated[Optional[StrictStr], Field(description="Ephemeris message type, e.g. LNAV, INAV, FNAV, FDMA, etc.")] = None,
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
        """Ephemeris

        Ensure that the **system** parameter is one of the supported constellations (G, R, E, S, J, C). The order of the ephemeris values and their units can be found in the [RINEX 4.02 specification](https://files.igs.org/pub/data/format/rinex_4.02.pdf). The **dtype** parameter is the data type of the ephemeris record (e.g. EPH), and the **mtype** parameter is the message type of the ephemeris record (e.g. LNAV).  Content negotiation: - Set header 'Accept: application/json' to stream a JSON array of ephemeris objects. - Set header 'Accept: text/plain' to stream a RINEX navigation file. - Gzip compression is applied if the client sends 'Accept-Encoding: gzip'.  RINEX version & multi-constellation behavior (when Accept is text/plain): - 'version=2' (default): RINEX 2.11, requires exactly one system and supports GPS (G) only. - 'version=3' or 'version=4': RINEX 3.05 / 4.02, supports multiple constellations in a single file.  Filenames (via Content-Disposition attachment): - RINEX 2: short name 'brdcDDD0.YYn' (DDD=day-of-year, YY=2-digit year). - RINEX 3/4: long name 'BRDC00ORG_R_YYYYJJJhhmm_NNS_MN.rnx' where ORG is 'RINEX_ORG_CODE' (default IGS), timestamp is UTC start time, and NNS is the span (e.g., 01D). MN indicates multi-constellation nav.

        :param start_datetime: Start time (RFC3339), e.g. 2025-01-01T00:00:00Z. (required)
        :type start_datetime: datetime
        :param end_datetime: End time (RFC3339), e.g. 2025-01-01T23:59:59Z. (required)
        :type end_datetime: datetime
        :param accept: Response format. Use 'application/json' for JSON array, or 'text/plain' for RINEX navigation file.
        :type accept: str
        :param system: Constellations to include: G, R, E, J, C, I, S. Multiple allowed. For RINEX v2 output, exactly one system (G) is required.
        :type system: List[str]
        :param satellite: The Satellites by number to include, such as '2', '8', or '15'.
        :type satellite: List[int]
        :param version: RINEX version for text/plain responses. 2 (default), 3, or 4. v2 supports GPS-only and single constellation; v3/v4 support multi-constellation.
        :type version: int
        :param dtype: Ephemeris data type, e.g. EPH.
        :type dtype: str
        :param mtype: Ephemeris message type, e.g. LNAV, INAV, FNAV, FDMA, etc.
        :type mtype: str
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

        _param = self._get_gnss_ephemeris_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            accept=accept,
            system=system,
            satellite=satellite,
            version=version,
            dtype=dtype,
            mtype=mtype,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "List[MyGenericEphemeris]",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _get_gnss_ephemeris_serialize(
        self,
        start_datetime,
        end_datetime,
        accept,
        system,
        satellite,
        version,
        dtype,
        mtype,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'system': 'multi',
            'satellite': 'multi',
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
        if start_datetime is not None:
            if isinstance(start_datetime, datetime):
                _query_params.append(
                    (
                        'start_datetime',
                        start_datetime.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('start_datetime', start_datetime))
            
        if end_datetime is not None:
            if isinstance(end_datetime, datetime):
                _query_params.append(
                    (
                        'end_datetime',
                        end_datetime.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('end_datetime', end_datetime))
            
        if system is not None:
            
            _query_params.append(('system', system))
            
        if satellite is not None:
            
            _query_params.append(('satellite', satellite))
            
        if version is not None:
            
            _query_params.append(('version', version))
            
        if dtype is not None:
            
            _query_params.append(('dtype', dtype))
            
        if mtype is not None:
            
            _query_params.append(('mtype', mtype))
            
        # process the header parameters
        if accept is not None:
            _header_params['accept'] = accept
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/json', 
                    'text/plain', 
                    'application/problem+json'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/data-products/gnss/ephemeris',
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
    def get_gnss_ephemeris_positions(
        self,
        start_datetime: Annotated[datetime, Field(description="Start time (RFC3339), e.g. 2025-01-01T00:00:00Z.")],
        end_datetime: Annotated[datetime, Field(description="End time (RFC3339), e.g. 2025-01-01T23:59:59Z.")],
        sample_period: Annotated[int, Field(strict=True, ge=200, description="Sample period specified in milliseconds")],
        var_field: Annotated[Optional[List[StrictStr]], Field(description="The satellite fields to return. The values include the following:  - **x**: x coordinate (meters)  - **y**: y coordinate (meters)  - **z**: z coordinate (meters)  - **elevation**: elevation (degrees)  - **azimuth**: azimuth (degrees)  - **clock**: satellite clock (seconds)  - **relativity**: relativity correction (seconds)  Satellite elevation and azimuth are only available when a latitude, longitude, and height are provided.")] = None,
        system: Annotated[Optional[StrictStr], Field(description="The GNSS Constellation to use: G, R, E, S, C.  - **G**: GPS  - **R**: GLONASS  - **E**: Galileo  - **S**: SBAS  - **C**: Beidou  Support for other constellations will be added in the future.")] = None,
        satellite: Annotated[Optional[List[StrictInt]], Field(description="The Satellites by number to include, such as '2', '8', or '15'.")] = None,
        latitude: Annotated[Optional[Union[Annotated[float, Field(le=90, strict=True, ge=-90)], Annotated[int, Field(le=90, strict=True, ge=-90)]]], Field(description="Latitude in degrees.")] = None,
        longitude: Annotated[Optional[Union[Annotated[float, Field(le=180, strict=True, ge=-180)], Annotated[int, Field(le=180, strict=True, ge=-180)]]], Field(description="Longitude in degrees.")] = None,
        height: Annotated[Optional[Union[StrictFloat, StrictInt]], Field(description="Height in meters.")] = None,
        elevation_filter: Annotated[Optional[StrictStr], Field(description="Elevation filter in degrees.")] = None,
        azimuth_filter: Annotated[Optional[StrictStr], Field(description="Azimuth filter in degrees.")] = None,
        allow_partial: Annotated[Optional[StrictBool], Field(description="Allow partial results when ephemeris data is unavailable for some time periods. When false, returns an error if any requested time exceeds ephemeris validity window.")] = None,
        max_validity_hours: Annotated[Optional[Annotated[int, Field(le=24, strict=True, ge=1)]], Field(description="Maximum hours beyond ephemeris Time of Ephemeris (ToE) to consider valid. Default is 4 hours (2 hours before and 2 hours after ToE).")] = None,
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
    ) -> None:
        """Ephemeris Positions

        Retrieve a time series of satellite positions, and optionally azimuth and elevation from a known position.  Satellite positions are derived from broadcast ephemeris and provided in Earth-Centered, Earth-Fixed (ECEF) coordinates. These positions are not suitable for use in precise positioning, but they are sufficient for computing satellite elevation and azimuth from a known position or for visualization.  Coordinates are provided in meters, azimuth and elevation in degrees.  Results are returned as an Apache Arrow stream.  Azimuth and Elevation: - Azimuth and elevation are only available when a latitude, longitude, and height are provided. An error is returned if these parameters are not provided when requesting azimuth or elevation.  Filtering: - Azimuth and elevation are filtered by the `azimuth_filter` and `elevation_filter` parameters. 

        :param start_datetime: Start time (RFC3339), e.g. 2025-01-01T00:00:00Z. (required)
        :type start_datetime: datetime
        :param end_datetime: End time (RFC3339), e.g. 2025-01-01T23:59:59Z. (required)
        :type end_datetime: datetime
        :param sample_period: Sample period specified in milliseconds (required)
        :type sample_period: int
        :param var_field: The satellite fields to return. The values include the following:  - **x**: x coordinate (meters)  - **y**: y coordinate (meters)  - **z**: z coordinate (meters)  - **elevation**: elevation (degrees)  - **azimuth**: azimuth (degrees)  - **clock**: satellite clock (seconds)  - **relativity**: relativity correction (seconds)  Satellite elevation and azimuth are only available when a latitude, longitude, and height are provided.
        :type var_field: List[str]
        :param system: The GNSS Constellation to use: G, R, E, S, C.  - **G**: GPS  - **R**: GLONASS  - **E**: Galileo  - **S**: SBAS  - **C**: Beidou  Support for other constellations will be added in the future.
        :type system: str
        :param satellite: The Satellites by number to include, such as '2', '8', or '15'.
        :type satellite: List[int]
        :param latitude: Latitude in degrees.
        :type latitude: float
        :param longitude: Longitude in degrees.
        :type longitude: float
        :param height: Height in meters.
        :type height: float
        :param elevation_filter: Elevation filter in degrees.
        :type elevation_filter: str
        :param azimuth_filter: Azimuth filter in degrees.
        :type azimuth_filter: str
        :param allow_partial: Allow partial results when ephemeris data is unavailable for some time periods. When false, returns an error if any requested time exceeds ephemeris validity window.
        :type allow_partial: bool
        :param max_validity_hours: Maximum hours beyond ephemeris Time of Ephemeris (ToE) to consider valid. Default is 4 hours (2 hours before and 2 hours after ToE).
        :type max_validity_hours: int
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

        _param = self._get_gnss_ephemeris_positions_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            sample_period=sample_period,
            var_field=var_field,
            system=system,
            satellite=satellite,
            latitude=latitude,
            longitude=longitude,
            height=height,
            elevation_filter=elevation_filter,
            azimuth_filter=azimuth_filter,
            allow_partial=allow_partial,
            max_validity_hours=max_validity_hours,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': None,
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
    def get_gnss_ephemeris_positions_with_http_info(
        self,
        start_datetime: Annotated[datetime, Field(description="Start time (RFC3339), e.g. 2025-01-01T00:00:00Z.")],
        end_datetime: Annotated[datetime, Field(description="End time (RFC3339), e.g. 2025-01-01T23:59:59Z.")],
        sample_period: Annotated[int, Field(strict=True, ge=200, description="Sample period specified in milliseconds")],
        var_field: Annotated[Optional[List[StrictStr]], Field(description="The satellite fields to return. The values include the following:  - **x**: x coordinate (meters)  - **y**: y coordinate (meters)  - **z**: z coordinate (meters)  - **elevation**: elevation (degrees)  - **azimuth**: azimuth (degrees)  - **clock**: satellite clock (seconds)  - **relativity**: relativity correction (seconds)  Satellite elevation and azimuth are only available when a latitude, longitude, and height are provided.")] = None,
        system: Annotated[Optional[StrictStr], Field(description="The GNSS Constellation to use: G, R, E, S, C.  - **G**: GPS  - **R**: GLONASS  - **E**: Galileo  - **S**: SBAS  - **C**: Beidou  Support for other constellations will be added in the future.")] = None,
        satellite: Annotated[Optional[List[StrictInt]], Field(description="The Satellites by number to include, such as '2', '8', or '15'.")] = None,
        latitude: Annotated[Optional[Union[Annotated[float, Field(le=90, strict=True, ge=-90)], Annotated[int, Field(le=90, strict=True, ge=-90)]]], Field(description="Latitude in degrees.")] = None,
        longitude: Annotated[Optional[Union[Annotated[float, Field(le=180, strict=True, ge=-180)], Annotated[int, Field(le=180, strict=True, ge=-180)]]], Field(description="Longitude in degrees.")] = None,
        height: Annotated[Optional[Union[StrictFloat, StrictInt]], Field(description="Height in meters.")] = None,
        elevation_filter: Annotated[Optional[StrictStr], Field(description="Elevation filter in degrees.")] = None,
        azimuth_filter: Annotated[Optional[StrictStr], Field(description="Azimuth filter in degrees.")] = None,
        allow_partial: Annotated[Optional[StrictBool], Field(description="Allow partial results when ephemeris data is unavailable for some time periods. When false, returns an error if any requested time exceeds ephemeris validity window.")] = None,
        max_validity_hours: Annotated[Optional[Annotated[int, Field(le=24, strict=True, ge=1)]], Field(description="Maximum hours beyond ephemeris Time of Ephemeris (ToE) to consider valid. Default is 4 hours (2 hours before and 2 hours after ToE).")] = None,
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
    ) -> ApiResponse[None]:
        """Ephemeris Positions

        Retrieve a time series of satellite positions, and optionally azimuth and elevation from a known position.  Satellite positions are derived from broadcast ephemeris and provided in Earth-Centered, Earth-Fixed (ECEF) coordinates. These positions are not suitable for use in precise positioning, but they are sufficient for computing satellite elevation and azimuth from a known position or for visualization.  Coordinates are provided in meters, azimuth and elevation in degrees.  Results are returned as an Apache Arrow stream.  Azimuth and Elevation: - Azimuth and elevation are only available when a latitude, longitude, and height are provided. An error is returned if these parameters are not provided when requesting azimuth or elevation.  Filtering: - Azimuth and elevation are filtered by the `azimuth_filter` and `elevation_filter` parameters. 

        :param start_datetime: Start time (RFC3339), e.g. 2025-01-01T00:00:00Z. (required)
        :type start_datetime: datetime
        :param end_datetime: End time (RFC3339), e.g. 2025-01-01T23:59:59Z. (required)
        :type end_datetime: datetime
        :param sample_period: Sample period specified in milliseconds (required)
        :type sample_period: int
        :param var_field: The satellite fields to return. The values include the following:  - **x**: x coordinate (meters)  - **y**: y coordinate (meters)  - **z**: z coordinate (meters)  - **elevation**: elevation (degrees)  - **azimuth**: azimuth (degrees)  - **clock**: satellite clock (seconds)  - **relativity**: relativity correction (seconds)  Satellite elevation and azimuth are only available when a latitude, longitude, and height are provided.
        :type var_field: List[str]
        :param system: The GNSS Constellation to use: G, R, E, S, C.  - **G**: GPS  - **R**: GLONASS  - **E**: Galileo  - **S**: SBAS  - **C**: Beidou  Support for other constellations will be added in the future.
        :type system: str
        :param satellite: The Satellites by number to include, such as '2', '8', or '15'.
        :type satellite: List[int]
        :param latitude: Latitude in degrees.
        :type latitude: float
        :param longitude: Longitude in degrees.
        :type longitude: float
        :param height: Height in meters.
        :type height: float
        :param elevation_filter: Elevation filter in degrees.
        :type elevation_filter: str
        :param azimuth_filter: Azimuth filter in degrees.
        :type azimuth_filter: str
        :param allow_partial: Allow partial results when ephemeris data is unavailable for some time periods. When false, returns an error if any requested time exceeds ephemeris validity window.
        :type allow_partial: bool
        :param max_validity_hours: Maximum hours beyond ephemeris Time of Ephemeris (ToE) to consider valid. Default is 4 hours (2 hours before and 2 hours after ToE).
        :type max_validity_hours: int
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

        _param = self._get_gnss_ephemeris_positions_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            sample_period=sample_period,
            var_field=var_field,
            system=system,
            satellite=satellite,
            latitude=latitude,
            longitude=longitude,
            height=height,
            elevation_filter=elevation_filter,
            azimuth_filter=azimuth_filter,
            allow_partial=allow_partial,
            max_validity_hours=max_validity_hours,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': None,
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
    def get_gnss_ephemeris_positions_without_preload_content(
        self,
        start_datetime: Annotated[datetime, Field(description="Start time (RFC3339), e.g. 2025-01-01T00:00:00Z.")],
        end_datetime: Annotated[datetime, Field(description="End time (RFC3339), e.g. 2025-01-01T23:59:59Z.")],
        sample_period: Annotated[int, Field(strict=True, ge=200, description="Sample period specified in milliseconds")],
        var_field: Annotated[Optional[List[StrictStr]], Field(description="The satellite fields to return. The values include the following:  - **x**: x coordinate (meters)  - **y**: y coordinate (meters)  - **z**: z coordinate (meters)  - **elevation**: elevation (degrees)  - **azimuth**: azimuth (degrees)  - **clock**: satellite clock (seconds)  - **relativity**: relativity correction (seconds)  Satellite elevation and azimuth are only available when a latitude, longitude, and height are provided.")] = None,
        system: Annotated[Optional[StrictStr], Field(description="The GNSS Constellation to use: G, R, E, S, C.  - **G**: GPS  - **R**: GLONASS  - **E**: Galileo  - **S**: SBAS  - **C**: Beidou  Support for other constellations will be added in the future.")] = None,
        satellite: Annotated[Optional[List[StrictInt]], Field(description="The Satellites by number to include, such as '2', '8', or '15'.")] = None,
        latitude: Annotated[Optional[Union[Annotated[float, Field(le=90, strict=True, ge=-90)], Annotated[int, Field(le=90, strict=True, ge=-90)]]], Field(description="Latitude in degrees.")] = None,
        longitude: Annotated[Optional[Union[Annotated[float, Field(le=180, strict=True, ge=-180)], Annotated[int, Field(le=180, strict=True, ge=-180)]]], Field(description="Longitude in degrees.")] = None,
        height: Annotated[Optional[Union[StrictFloat, StrictInt]], Field(description="Height in meters.")] = None,
        elevation_filter: Annotated[Optional[StrictStr], Field(description="Elevation filter in degrees.")] = None,
        azimuth_filter: Annotated[Optional[StrictStr], Field(description="Azimuth filter in degrees.")] = None,
        allow_partial: Annotated[Optional[StrictBool], Field(description="Allow partial results when ephemeris data is unavailable for some time periods. When false, returns an error if any requested time exceeds ephemeris validity window.")] = None,
        max_validity_hours: Annotated[Optional[Annotated[int, Field(le=24, strict=True, ge=1)]], Field(description="Maximum hours beyond ephemeris Time of Ephemeris (ToE) to consider valid. Default is 4 hours (2 hours before and 2 hours after ToE).")] = None,
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
        """Ephemeris Positions

        Retrieve a time series of satellite positions, and optionally azimuth and elevation from a known position.  Satellite positions are derived from broadcast ephemeris and provided in Earth-Centered, Earth-Fixed (ECEF) coordinates. These positions are not suitable for use in precise positioning, but they are sufficient for computing satellite elevation and azimuth from a known position or for visualization.  Coordinates are provided in meters, azimuth and elevation in degrees.  Results are returned as an Apache Arrow stream.  Azimuth and Elevation: - Azimuth and elevation are only available when a latitude, longitude, and height are provided. An error is returned if these parameters are not provided when requesting azimuth or elevation.  Filtering: - Azimuth and elevation are filtered by the `azimuth_filter` and `elevation_filter` parameters. 

        :param start_datetime: Start time (RFC3339), e.g. 2025-01-01T00:00:00Z. (required)
        :type start_datetime: datetime
        :param end_datetime: End time (RFC3339), e.g. 2025-01-01T23:59:59Z. (required)
        :type end_datetime: datetime
        :param sample_period: Sample period specified in milliseconds (required)
        :type sample_period: int
        :param var_field: The satellite fields to return. The values include the following:  - **x**: x coordinate (meters)  - **y**: y coordinate (meters)  - **z**: z coordinate (meters)  - **elevation**: elevation (degrees)  - **azimuth**: azimuth (degrees)  - **clock**: satellite clock (seconds)  - **relativity**: relativity correction (seconds)  Satellite elevation and azimuth are only available when a latitude, longitude, and height are provided.
        :type var_field: List[str]
        :param system: The GNSS Constellation to use: G, R, E, S, C.  - **G**: GPS  - **R**: GLONASS  - **E**: Galileo  - **S**: SBAS  - **C**: Beidou  Support for other constellations will be added in the future.
        :type system: str
        :param satellite: The Satellites by number to include, such as '2', '8', or '15'.
        :type satellite: List[int]
        :param latitude: Latitude in degrees.
        :type latitude: float
        :param longitude: Longitude in degrees.
        :type longitude: float
        :param height: Height in meters.
        :type height: float
        :param elevation_filter: Elevation filter in degrees.
        :type elevation_filter: str
        :param azimuth_filter: Azimuth filter in degrees.
        :type azimuth_filter: str
        :param allow_partial: Allow partial results when ephemeris data is unavailable for some time periods. When false, returns an error if any requested time exceeds ephemeris validity window.
        :type allow_partial: bool
        :param max_validity_hours: Maximum hours beyond ephemeris Time of Ephemeris (ToE) to consider valid. Default is 4 hours (2 hours before and 2 hours after ToE).
        :type max_validity_hours: int
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

        _param = self._get_gnss_ephemeris_positions_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            sample_period=sample_period,
            var_field=var_field,
            system=system,
            satellite=satellite,
            latitude=latitude,
            longitude=longitude,
            height=height,
            elevation_filter=elevation_filter,
            azimuth_filter=azimuth_filter,
            allow_partial=allow_partial,
            max_validity_hours=max_validity_hours,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': None,
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _get_gnss_ephemeris_positions_serialize(
        self,
        start_datetime,
        end_datetime,
        sample_period,
        var_field,
        system,
        satellite,
        latitude,
        longitude,
        height,
        elevation_filter,
        azimuth_filter,
        allow_partial,
        max_validity_hours,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'field': 'multi',
            'satellite': 'multi',
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
        if var_field is not None:
            
            _query_params.append(('field', var_field))
            
        if start_datetime is not None:
            if isinstance(start_datetime, datetime):
                _query_params.append(
                    (
                        'start_datetime',
                        start_datetime.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('start_datetime', start_datetime))
            
        if end_datetime is not None:
            if isinstance(end_datetime, datetime):
                _query_params.append(
                    (
                        'end_datetime',
                        end_datetime.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('end_datetime', end_datetime))
            
        if sample_period is not None:
            
            _query_params.append(('sample_period', sample_period))
            
        if system is not None:
            
            _query_params.append(('system', system))
            
        if satellite is not None:
            
            _query_params.append(('satellite', satellite))
            
        if latitude is not None:
            
            _query_params.append(('latitude', latitude))
            
        if longitude is not None:
            
            _query_params.append(('longitude', longitude))
            
        if height is not None:
            
            _query_params.append(('height', height))
            
        if elevation_filter is not None:
            
            _query_params.append(('elevation_filter', elevation_filter))
            
        if azimuth_filter is not None:
            
            _query_params.append(('azimuth_filter', azimuth_filter))
            
        if allow_partial is not None:
            
            _query_params.append(('allow_partial', allow_partial))
            
        if max_validity_hours is not None:
            
            _query_params.append(('max_validity_hours', max_validity_hours))
            
        # process the header parameters
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/problem+json'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/data-products/gnss/ephemeris/positions',
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
    def get_gnss_inst_positions(
        self,
        stream_id: Annotated[StrictStr, Field(description="The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`).")],
        start_datetime: Annotated[datetime, Field(description="The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        end_datetime: Annotated[datetime, Field(description="The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        accept: Annotated[Optional[List[ContentType]], Field(description="Desired response format. See `Accept` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept).  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept` header is controlled by > the dropdown in the `Response` section. ")] = None,
        accept_encoding: Annotated[Optional[List[ContentEncoding]], Field(description="Desired response compression. See `Accept-Encoding` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding).  Use `identity` to request no modification or compression.  The following table illustrates compatibility between `Content-Encoding` and `Content-Type`:   |Content-Type|br|gzip|identity|lz4|snappy|zstd| |-|-|-|-|-|-|-| |`application/json`|❌|✅|✅|❌|❌|❌| |`application/json+compact-geojson`|❌|✅|✅|❌|❌|❌| |`application/json+series`|❌|✅|✅|❌|❌|❌| |`application/vnd.apache.arrow.file`|❌|❌|✅|✅|❌|✅| |`application/vnd.apache.parquet`|✅|✅|✅|✅|✅|✅| |`text/csv`|❌|✅|✅|❌|❌|❌|  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept-Encoding` header is overridden > by the documentation. ")] = None,
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
    ) -> List[InstPosition]:
        """(Deprecated) Instantaneous Positions (Deprecated)

        Query the real-time PPP data for GNSS stations.

        :param stream_id: The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`). (required)
        :type stream_id: str
        :param start_datetime: The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type start_datetime: datetime
        :param end_datetime: The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type end_datetime: datetime
        :param accept: Desired response format. See `Accept` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept).  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept` header is controlled by > the dropdown in the `Response` section. 
        :type accept: List[ContentType]
        :param accept_encoding: Desired response compression. See `Accept-Encoding` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding).  Use `identity` to request no modification or compression.  The following table illustrates compatibility between `Content-Encoding` and `Content-Type`:   |Content-Type|br|gzip|identity|lz4|snappy|zstd| |-|-|-|-|-|-|-| |`application/json`|❌|✅|✅|❌|❌|❌| |`application/json+compact-geojson`|❌|✅|✅|❌|❌|❌| |`application/json+series`|❌|✅|✅|❌|❌|❌| |`application/vnd.apache.arrow.file`|❌|❌|✅|✅|❌|✅| |`application/vnd.apache.parquet`|✅|✅|✅|✅|✅|✅| |`text/csv`|❌|✅|✅|❌|❌|❌|  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept-Encoding` header is overridden > by the documentation. 
        :type accept_encoding: List[ContentEncoding]
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
        warnings.warn("GET /data-products/gnss/positions/instantaneous is deprecated.", DeprecationWarning)

        _param = self._get_gnss_inst_positions_serialize(
            stream_id=stream_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            accept=accept,
            accept_encoding=accept_encoding,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "List[InstPosition]",
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
    def get_gnss_inst_positions_with_http_info(
        self,
        stream_id: Annotated[StrictStr, Field(description="The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`).")],
        start_datetime: Annotated[datetime, Field(description="The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        end_datetime: Annotated[datetime, Field(description="The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        accept: Annotated[Optional[List[ContentType]], Field(description="Desired response format. See `Accept` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept).  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept` header is controlled by > the dropdown in the `Response` section. ")] = None,
        accept_encoding: Annotated[Optional[List[ContentEncoding]], Field(description="Desired response compression. See `Accept-Encoding` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding).  Use `identity` to request no modification or compression.  The following table illustrates compatibility between `Content-Encoding` and `Content-Type`:   |Content-Type|br|gzip|identity|lz4|snappy|zstd| |-|-|-|-|-|-|-| |`application/json`|❌|✅|✅|❌|❌|❌| |`application/json+compact-geojson`|❌|✅|✅|❌|❌|❌| |`application/json+series`|❌|✅|✅|❌|❌|❌| |`application/vnd.apache.arrow.file`|❌|❌|✅|✅|❌|✅| |`application/vnd.apache.parquet`|✅|✅|✅|✅|✅|✅| |`text/csv`|❌|✅|✅|❌|❌|❌|  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept-Encoding` header is overridden > by the documentation. ")] = None,
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
    ) -> ApiResponse[List[InstPosition]]:
        """(Deprecated) Instantaneous Positions (Deprecated)

        Query the real-time PPP data for GNSS stations.

        :param stream_id: The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`). (required)
        :type stream_id: str
        :param start_datetime: The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type start_datetime: datetime
        :param end_datetime: The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type end_datetime: datetime
        :param accept: Desired response format. See `Accept` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept).  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept` header is controlled by > the dropdown in the `Response` section. 
        :type accept: List[ContentType]
        :param accept_encoding: Desired response compression. See `Accept-Encoding` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding).  Use `identity` to request no modification or compression.  The following table illustrates compatibility between `Content-Encoding` and `Content-Type`:   |Content-Type|br|gzip|identity|lz4|snappy|zstd| |-|-|-|-|-|-|-| |`application/json`|❌|✅|✅|❌|❌|❌| |`application/json+compact-geojson`|❌|✅|✅|❌|❌|❌| |`application/json+series`|❌|✅|✅|❌|❌|❌| |`application/vnd.apache.arrow.file`|❌|❌|✅|✅|❌|✅| |`application/vnd.apache.parquet`|✅|✅|✅|✅|✅|✅| |`text/csv`|❌|✅|✅|❌|❌|❌|  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept-Encoding` header is overridden > by the documentation. 
        :type accept_encoding: List[ContentEncoding]
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
        warnings.warn("GET /data-products/gnss/positions/instantaneous is deprecated.", DeprecationWarning)

        _param = self._get_gnss_inst_positions_serialize(
            stream_id=stream_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            accept=accept,
            accept_encoding=accept_encoding,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "List[InstPosition]",
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
    def get_gnss_inst_positions_without_preload_content(
        self,
        stream_id: Annotated[StrictStr, Field(description="The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`).")],
        start_datetime: Annotated[datetime, Field(description="The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        end_datetime: Annotated[datetime, Field(description="The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        accept: Annotated[Optional[List[ContentType]], Field(description="Desired response format. See `Accept` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept).  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept` header is controlled by > the dropdown in the `Response` section. ")] = None,
        accept_encoding: Annotated[Optional[List[ContentEncoding]], Field(description="Desired response compression. See `Accept-Encoding` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding).  Use `identity` to request no modification or compression.  The following table illustrates compatibility between `Content-Encoding` and `Content-Type`:   |Content-Type|br|gzip|identity|lz4|snappy|zstd| |-|-|-|-|-|-|-| |`application/json`|❌|✅|✅|❌|❌|❌| |`application/json+compact-geojson`|❌|✅|✅|❌|❌|❌| |`application/json+series`|❌|✅|✅|❌|❌|❌| |`application/vnd.apache.arrow.file`|❌|❌|✅|✅|❌|✅| |`application/vnd.apache.parquet`|✅|✅|✅|✅|✅|✅| |`text/csv`|❌|✅|✅|❌|❌|❌|  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept-Encoding` header is overridden > by the documentation. ")] = None,
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
        """(Deprecated) Instantaneous Positions (Deprecated)

        Query the real-time PPP data for GNSS stations.

        :param stream_id: The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`). (required)
        :type stream_id: str
        :param start_datetime: The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type start_datetime: datetime
        :param end_datetime: The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type end_datetime: datetime
        :param accept: Desired response format. See `Accept` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept).  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept` header is controlled by > the dropdown in the `Response` section. 
        :type accept: List[ContentType]
        :param accept_encoding: Desired response compression. See `Accept-Encoding` Header [MDN docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding).  Use `identity` to request no modification or compression.  The following table illustrates compatibility between `Content-Encoding` and `Content-Type`:   |Content-Type|br|gzip|identity|lz4|snappy|zstd| |-|-|-|-|-|-|-| |`application/json`|❌|✅|✅|❌|❌|❌| |`application/json+compact-geojson`|❌|✅|✅|❌|❌|❌| |`application/json+series`|❌|✅|✅|❌|❌|❌| |`application/vnd.apache.arrow.file`|❌|❌|✅|✅|❌|✅| |`application/vnd.apache.parquet`|✅|✅|✅|✅|✅|✅| |`text/csv`|❌|✅|✅|❌|❌|❌|  > **NOTE:** When looking at this endpoint in the web documentation, the `Accept-Encoding` header is overridden > by the documentation. 
        :type accept_encoding: List[ContentEncoding]
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
        warnings.warn("GET /data-products/gnss/positions/instantaneous is deprecated.", DeprecationWarning)

        _param = self._get_gnss_inst_positions_serialize(
            stream_id=stream_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            accept=accept,
            accept_encoding=accept_encoding,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "List[InstPosition]",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _get_gnss_inst_positions_serialize(
        self,
        stream_id,
        start_datetime,
        end_datetime,
        accept,
        accept_encoding,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'Accept': 'csv',
            'Accept-Encoding': 'csv',
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
        if stream_id is not None:
            
            _query_params.append(('stream_id', stream_id))
            
        if start_datetime is not None:
            if isinstance(start_datetime, datetime):
                _query_params.append(
                    (
                        'start_datetime',
                        start_datetime.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('start_datetime', start_datetime))
            
        if end_datetime is not None:
            if isinstance(end_datetime, datetime):
                _query_params.append(
                    (
                        'end_datetime',
                        end_datetime.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('end_datetime', end_datetime))
            
        # process the header parameters
        if accept is not None:
            _header_params['Accept'] = accept
        if accept_encoding is not None:
            _header_params['Accept-Encoding'] = accept_encoding
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/json', 
                    'application/json+series', 
                    'application/json+compact-geojson', 
                    'text/csv', 
                    'application/vnd.apache.parquet', 
                    'application/vnd.apache.arrow.file'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/data-products/gnss/positions/instantaneous',
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
    def get_gnss_inst_positions_manifest(
        self,
        stream_id: Annotated[StrictStr, Field(description="The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`).")],
        start_datetime: Annotated[datetime, Field(description="The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        end_datetime: Annotated[datetime, Field(description="The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        interval_limit: Annotated[Optional[Annotated[int, Field(le=24, strict=True)]], Field(description="The time window (in hours) to chunk the list of relative URLs. Defaults to 24 (24 hours).")] = None,
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
    ) -> StreamDataSplitResponse:
        """(Deprecated) Instantaneous Positions Manifest (Deprecated)

        Get a list of relative URLs for querying PPP data. The response will include a list relative URL(s) that use the PPP EDID (26 character ULID).

        :param stream_id: The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`). (required)
        :type stream_id: str
        :param start_datetime: The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type start_datetime: datetime
        :param end_datetime: The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type end_datetime: datetime
        :param interval_limit: The time window (in hours) to chunk the list of relative URLs. Defaults to 24 (24 hours).
        :type interval_limit: int
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
        warnings.warn("GET /data-products/gnss/positions/instantaneous/manifest is deprecated.", DeprecationWarning)

        _param = self._get_gnss_inst_positions_manifest_serialize(
            stream_id=stream_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            interval_limit=interval_limit,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "StreamDataSplitResponse",
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
    def get_gnss_inst_positions_manifest_with_http_info(
        self,
        stream_id: Annotated[StrictStr, Field(description="The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`).")],
        start_datetime: Annotated[datetime, Field(description="The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        end_datetime: Annotated[datetime, Field(description="The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        interval_limit: Annotated[Optional[Annotated[int, Field(le=24, strict=True)]], Field(description="The time window (in hours) to chunk the list of relative URLs. Defaults to 24 (24 hours).")] = None,
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
    ) -> ApiResponse[StreamDataSplitResponse]:
        """(Deprecated) Instantaneous Positions Manifest (Deprecated)

        Get a list of relative URLs for querying PPP data. The response will include a list relative URL(s) that use the PPP EDID (26 character ULID).

        :param stream_id: The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`). (required)
        :type stream_id: str
        :param start_datetime: The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type start_datetime: datetime
        :param end_datetime: The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type end_datetime: datetime
        :param interval_limit: The time window (in hours) to chunk the list of relative URLs. Defaults to 24 (24 hours).
        :type interval_limit: int
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
        warnings.warn("GET /data-products/gnss/positions/instantaneous/manifest is deprecated.", DeprecationWarning)

        _param = self._get_gnss_inst_positions_manifest_serialize(
            stream_id=stream_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            interval_limit=interval_limit,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "StreamDataSplitResponse",
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
    def get_gnss_inst_positions_manifest_without_preload_content(
        self,
        stream_id: Annotated[StrictStr, Field(description="The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`).")],
        start_datetime: Annotated[datetime, Field(description="The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        end_datetime: Annotated[datetime, Field(description="The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`.")],
        interval_limit: Annotated[Optional[Annotated[int, Field(le=24, strict=True)]], Field(description="The time window (in hours) to chunk the list of relative URLs. Defaults to 24 (24 hours).")] = None,
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
        """(Deprecated) Instantaneous Positions Manifest (Deprecated)

        Get a list of relative URLs for querying PPP data. The response will include a list relative URL(s) that use the PPP EDID (26 character ULID).

        :param stream_id: The GNSS PPP data identifier. Either a GEOSNCL and SN ID (e.g: `GEOSNCL:P548.CI.LY_.20`) or EDID (26 Character ULID, e.g: `01H46MV50Q2ZDXNFG8ZWBF2PZY`). (required)
        :type stream_id: str
        :param start_datetime: The start date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type start_datetime: datetime
        :param end_datetime: The end date or datetime represented as a string in ISO 8601 format like `2008-09-15` or `2021-06-21T15:53:00+00:00`. (required)
        :type end_datetime: datetime
        :param interval_limit: The time window (in hours) to chunk the list of relative URLs. Defaults to 24 (24 hours).
        :type interval_limit: int
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
        warnings.warn("GET /data-products/gnss/positions/instantaneous/manifest is deprecated.", DeprecationWarning)

        _param = self._get_gnss_inst_positions_manifest_serialize(
            stream_id=stream_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            interval_limit=interval_limit,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "StreamDataSplitResponse",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _get_gnss_inst_positions_manifest_serialize(
        self,
        stream_id,
        start_datetime,
        end_datetime,
        interval_limit,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
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
        if interval_limit is not None:
            
            _query_params.append(('interval_limit', interval_limit))
            
        if stream_id is not None:
            
            _query_params.append(('stream_id', stream_id))
            
        if start_datetime is not None:
            if isinstance(start_datetime, datetime):
                _query_params.append(
                    (
                        'start_datetime',
                        start_datetime.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('start_datetime', start_datetime))
            
        if end_datetime is not None:
            if isinstance(end_datetime, datetime):
                _query_params.append(
                    (
                        'end_datetime',
                        end_datetime.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('end_datetime', end_datetime))
            
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
            resource_path='/data-products/gnss/positions/instantaneous/manifest',
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
    def get_gnss_inst_positions_v2(
        self,
        start_datetime: Annotated[StrictStr, Field(description="The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        end_datetime: Annotated[StrictStr, Field(description="The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        stream_id: Annotated[StrictStr, Field(description="The GNSS Stream identifier EDID (26 character ULID).")],
        var_field: Annotated[Optional[List[StrictStr]], Field(description="The position solution fields to return. This can be one or more of the enumerated values.  Defaults to 'time, east, north, up, sigEE, sigNN, sigUU, qChannel, ingestLatency, processingDelay' if not specified.  Latency fields are in milliseconds (ms): 'ingestLatency' (Station to Ingest), 'processingDelay' (Ingest to public bus).")] = None,
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
    ) -> None:
        """Instantaneous Positions

        Returns GNSS position data in Apache Arrow format.

        :param start_datetime: The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type start_datetime: str
        :param end_datetime: The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type end_datetime: str
        :param stream_id: The GNSS Stream identifier EDID (26 character ULID). (required)
        :type stream_id: str
        :param var_field: The position solution fields to return. This can be one or more of the enumerated values.  Defaults to 'time, east, north, up, sigEE, sigNN, sigUU, qChannel, ingestLatency, processingDelay' if not specified.  Latency fields are in milliseconds (ms): 'ingestLatency' (Station to Ingest), 'processingDelay' (Ingest to public bus).
        :type var_field: List[str]
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

        _param = self._get_gnss_inst_positions_v2_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            stream_id=stream_id,
            var_field=var_field,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': None,
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
    def get_gnss_inst_positions_v2_with_http_info(
        self,
        start_datetime: Annotated[StrictStr, Field(description="The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        end_datetime: Annotated[StrictStr, Field(description="The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        stream_id: Annotated[StrictStr, Field(description="The GNSS Stream identifier EDID (26 character ULID).")],
        var_field: Annotated[Optional[List[StrictStr]], Field(description="The position solution fields to return. This can be one or more of the enumerated values.  Defaults to 'time, east, north, up, sigEE, sigNN, sigUU, qChannel, ingestLatency, processingDelay' if not specified.  Latency fields are in milliseconds (ms): 'ingestLatency' (Station to Ingest), 'processingDelay' (Ingest to public bus).")] = None,
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
    ) -> ApiResponse[None]:
        """Instantaneous Positions

        Returns GNSS position data in Apache Arrow format.

        :param start_datetime: The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type start_datetime: str
        :param end_datetime: The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type end_datetime: str
        :param stream_id: The GNSS Stream identifier EDID (26 character ULID). (required)
        :type stream_id: str
        :param var_field: The position solution fields to return. This can be one or more of the enumerated values.  Defaults to 'time, east, north, up, sigEE, sigNN, sigUU, qChannel, ingestLatency, processingDelay' if not specified.  Latency fields are in milliseconds (ms): 'ingestLatency' (Station to Ingest), 'processingDelay' (Ingest to public bus).
        :type var_field: List[str]
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

        _param = self._get_gnss_inst_positions_v2_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            stream_id=stream_id,
            var_field=var_field,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': None,
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
    def get_gnss_inst_positions_v2_without_preload_content(
        self,
        start_datetime: Annotated[StrictStr, Field(description="The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        end_datetime: Annotated[StrictStr, Field(description="The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        stream_id: Annotated[StrictStr, Field(description="The GNSS Stream identifier EDID (26 character ULID).")],
        var_field: Annotated[Optional[List[StrictStr]], Field(description="The position solution fields to return. This can be one or more of the enumerated values.  Defaults to 'time, east, north, up, sigEE, sigNN, sigUU, qChannel, ingestLatency, processingDelay' if not specified.  Latency fields are in milliseconds (ms): 'ingestLatency' (Station to Ingest), 'processingDelay' (Ingest to public bus).")] = None,
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
        """Instantaneous Positions

        Returns GNSS position data in Apache Arrow format.

        :param start_datetime: The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type start_datetime: str
        :param end_datetime: The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type end_datetime: str
        :param stream_id: The GNSS Stream identifier EDID (26 character ULID). (required)
        :type stream_id: str
        :param var_field: The position solution fields to return. This can be one or more of the enumerated values.  Defaults to 'time, east, north, up, sigEE, sigNN, sigUU, qChannel, ingestLatency, processingDelay' if not specified.  Latency fields are in milliseconds (ms): 'ingestLatency' (Station to Ingest), 'processingDelay' (Ingest to public bus).
        :type var_field: List[str]
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

        _param = self._get_gnss_inst_positions_v2_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            stream_id=stream_id,
            var_field=var_field,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': None,
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _get_gnss_inst_positions_v2_serialize(
        self,
        start_datetime,
        end_datetime,
        stream_id,
        var_field,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'field': 'multi',
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
        if start_datetime is not None:
            
            _query_params.append(('start_datetime', start_datetime))
            
        if end_datetime is not None:
            
            _query_params.append(('end_datetime', end_datetime))
            
        if stream_id is not None:
            
            _query_params.append(('stream_id', stream_id))
            
        if var_field is not None:
            
            _query_params.append(('field', var_field))
            
        # process the header parameters
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/problem+json'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/data-products/gnss/positions/instantaneous/v2',
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
    def get_gnss_observations(
        self,
        start_datetime: Annotated[StrictStr, Field(description="The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        end_datetime: Annotated[StrictStr, Field(description="The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        session_id: Annotated[StrictStr, Field(description="The GNSS Session identifier EDID (26 character ULID).")],
        var_field: Annotated[Optional[List[StrictStr]], Field(description="The observation fields to return. The values include the following:  **range**: code / psuedorange  **phase**: carrier phase  **doppler**: doppler shift  **snr**: signal to noise ratio  **slip**: carrier phase cycle slip occurred  **flags**: event flags  **fcn**: GLONASS frequency channel number.  All fields except doppler are included by default.  If any fields are specified, only those fields are returned.")] = None,
        system: Annotated[Optional[List[StrictStr]], Field(description="The GNSS Constellations to include, such as 'G', 'R', or 'E'.  **G**: GPS  **R**: GLONASS  **E**: Galileo  **J**: QZSS  **C**: BeiDou  **I**: NavIC  **S**: SBAS")] = None,
        satellite: Annotated[Optional[List[Annotated[int, Field(le=254, strict=True, ge=1)]]], Field(description="The Satellites by number to include, such as '2', '8', or '15'.")] = None,
        obs_code: Annotated[Optional[List[StrictStr]], Field(description="The GNSS observation codes to include (Band + Attribute two char code), such as '1C' or '2L'.")] = None,
        version: Annotated[Optional[Annotated[int, Field(le=4, strict=True, ge=2)]], Field(description="The version of RINEX to return. Not applicable to arrow requests.")] = None,
        accept: Annotated[Optional[StrictStr], Field(description="The content type to return. If application/vnd.apache.arrow.stream is specified, an Apache arrow stream is returned. Otherwise, a gzipped RINEX is returned.")] = None,
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
    ) -> None:
        """Observations

        Returns GNSS observation data in either Apache Arrow or RINEX format. The desired format is specified via the `Accept` HTTP header. Use `application/vnd.apache.arrow.stream` for Arrow format. RINEX format is the default if the header is not provided.

        :param start_datetime: The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type start_datetime: str
        :param end_datetime: The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type end_datetime: str
        :param session_id: The GNSS Session identifier EDID (26 character ULID). (required)
        :type session_id: str
        :param var_field: The observation fields to return. The values include the following:  **range**: code / psuedorange  **phase**: carrier phase  **doppler**: doppler shift  **snr**: signal to noise ratio  **slip**: carrier phase cycle slip occurred  **flags**: event flags  **fcn**: GLONASS frequency channel number.  All fields except doppler are included by default.  If any fields are specified, only those fields are returned.
        :type var_field: List[str]
        :param system: The GNSS Constellations to include, such as 'G', 'R', or 'E'.  **G**: GPS  **R**: GLONASS  **E**: Galileo  **J**: QZSS  **C**: BeiDou  **I**: NavIC  **S**: SBAS
        :type system: List[str]
        :param satellite: The Satellites by number to include, such as '2', '8', or '15'.
        :type satellite: List[int]
        :param obs_code: The GNSS observation codes to include (Band + Attribute two char code), such as '1C' or '2L'.
        :type obs_code: List[str]
        :param version: The version of RINEX to return. Not applicable to arrow requests.
        :type version: int
        :param accept: The content type to return. If application/vnd.apache.arrow.stream is specified, an Apache arrow stream is returned. Otherwise, a gzipped RINEX is returned.
        :type accept: str
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

        _param = self._get_gnss_observations_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            session_id=session_id,
            var_field=var_field,
            system=system,
            satellite=satellite,
            obs_code=obs_code,
            version=version,
            accept=accept,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': None,
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
    def get_gnss_observations_with_http_info(
        self,
        start_datetime: Annotated[StrictStr, Field(description="The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        end_datetime: Annotated[StrictStr, Field(description="The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        session_id: Annotated[StrictStr, Field(description="The GNSS Session identifier EDID (26 character ULID).")],
        var_field: Annotated[Optional[List[StrictStr]], Field(description="The observation fields to return. The values include the following:  **range**: code / psuedorange  **phase**: carrier phase  **doppler**: doppler shift  **snr**: signal to noise ratio  **slip**: carrier phase cycle slip occurred  **flags**: event flags  **fcn**: GLONASS frequency channel number.  All fields except doppler are included by default.  If any fields are specified, only those fields are returned.")] = None,
        system: Annotated[Optional[List[StrictStr]], Field(description="The GNSS Constellations to include, such as 'G', 'R', or 'E'.  **G**: GPS  **R**: GLONASS  **E**: Galileo  **J**: QZSS  **C**: BeiDou  **I**: NavIC  **S**: SBAS")] = None,
        satellite: Annotated[Optional[List[Annotated[int, Field(le=254, strict=True, ge=1)]]], Field(description="The Satellites by number to include, such as '2', '8', or '15'.")] = None,
        obs_code: Annotated[Optional[List[StrictStr]], Field(description="The GNSS observation codes to include (Band + Attribute two char code), such as '1C' or '2L'.")] = None,
        version: Annotated[Optional[Annotated[int, Field(le=4, strict=True, ge=2)]], Field(description="The version of RINEX to return. Not applicable to arrow requests.")] = None,
        accept: Annotated[Optional[StrictStr], Field(description="The content type to return. If application/vnd.apache.arrow.stream is specified, an Apache arrow stream is returned. Otherwise, a gzipped RINEX is returned.")] = None,
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
    ) -> ApiResponse[None]:
        """Observations

        Returns GNSS observation data in either Apache Arrow or RINEX format. The desired format is specified via the `Accept` HTTP header. Use `application/vnd.apache.arrow.stream` for Arrow format. RINEX format is the default if the header is not provided.

        :param start_datetime: The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type start_datetime: str
        :param end_datetime: The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type end_datetime: str
        :param session_id: The GNSS Session identifier EDID (26 character ULID). (required)
        :type session_id: str
        :param var_field: The observation fields to return. The values include the following:  **range**: code / psuedorange  **phase**: carrier phase  **doppler**: doppler shift  **snr**: signal to noise ratio  **slip**: carrier phase cycle slip occurred  **flags**: event flags  **fcn**: GLONASS frequency channel number.  All fields except doppler are included by default.  If any fields are specified, only those fields are returned.
        :type var_field: List[str]
        :param system: The GNSS Constellations to include, such as 'G', 'R', or 'E'.  **G**: GPS  **R**: GLONASS  **E**: Galileo  **J**: QZSS  **C**: BeiDou  **I**: NavIC  **S**: SBAS
        :type system: List[str]
        :param satellite: The Satellites by number to include, such as '2', '8', or '15'.
        :type satellite: List[int]
        :param obs_code: The GNSS observation codes to include (Band + Attribute two char code), such as '1C' or '2L'.
        :type obs_code: List[str]
        :param version: The version of RINEX to return. Not applicable to arrow requests.
        :type version: int
        :param accept: The content type to return. If application/vnd.apache.arrow.stream is specified, an Apache arrow stream is returned. Otherwise, a gzipped RINEX is returned.
        :type accept: str
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

        _param = self._get_gnss_observations_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            session_id=session_id,
            var_field=var_field,
            system=system,
            satellite=satellite,
            obs_code=obs_code,
            version=version,
            accept=accept,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': None,
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
    def get_gnss_observations_without_preload_content(
        self,
        start_datetime: Annotated[StrictStr, Field(description="The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        end_datetime: Annotated[StrictStr, Field(description="The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00.")],
        session_id: Annotated[StrictStr, Field(description="The GNSS Session identifier EDID (26 character ULID).")],
        var_field: Annotated[Optional[List[StrictStr]], Field(description="The observation fields to return. The values include the following:  **range**: code / psuedorange  **phase**: carrier phase  **doppler**: doppler shift  **snr**: signal to noise ratio  **slip**: carrier phase cycle slip occurred  **flags**: event flags  **fcn**: GLONASS frequency channel number.  All fields except doppler are included by default.  If any fields are specified, only those fields are returned.")] = None,
        system: Annotated[Optional[List[StrictStr]], Field(description="The GNSS Constellations to include, such as 'G', 'R', or 'E'.  **G**: GPS  **R**: GLONASS  **E**: Galileo  **J**: QZSS  **C**: BeiDou  **I**: NavIC  **S**: SBAS")] = None,
        satellite: Annotated[Optional[List[Annotated[int, Field(le=254, strict=True, ge=1)]]], Field(description="The Satellites by number to include, such as '2', '8', or '15'.")] = None,
        obs_code: Annotated[Optional[List[StrictStr]], Field(description="The GNSS observation codes to include (Band + Attribute two char code), such as '1C' or '2L'.")] = None,
        version: Annotated[Optional[Annotated[int, Field(le=4, strict=True, ge=2)]], Field(description="The version of RINEX to return. Not applicable to arrow requests.")] = None,
        accept: Annotated[Optional[StrictStr], Field(description="The content type to return. If application/vnd.apache.arrow.stream is specified, an Apache arrow stream is returned. Otherwise, a gzipped RINEX is returned.")] = None,
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
        """Observations

        Returns GNSS observation data in either Apache Arrow or RINEX format. The desired format is specified via the `Accept` HTTP header. Use `application/vnd.apache.arrow.stream` for Arrow format. RINEX format is the default if the header is not provided.

        :param start_datetime: The start date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type start_datetime: str
        :param end_datetime: The end date or datetime in RFC3339 format such as 2008-09-15 or 2021-06-21T15:53:00+00:00. (required)
        :type end_datetime: str
        :param session_id: The GNSS Session identifier EDID (26 character ULID). (required)
        :type session_id: str
        :param var_field: The observation fields to return. The values include the following:  **range**: code / psuedorange  **phase**: carrier phase  **doppler**: doppler shift  **snr**: signal to noise ratio  **slip**: carrier phase cycle slip occurred  **flags**: event flags  **fcn**: GLONASS frequency channel number.  All fields except doppler are included by default.  If any fields are specified, only those fields are returned.
        :type var_field: List[str]
        :param system: The GNSS Constellations to include, such as 'G', 'R', or 'E'.  **G**: GPS  **R**: GLONASS  **E**: Galileo  **J**: QZSS  **C**: BeiDou  **I**: NavIC  **S**: SBAS
        :type system: List[str]
        :param satellite: The Satellites by number to include, such as '2', '8', or '15'.
        :type satellite: List[int]
        :param obs_code: The GNSS observation codes to include (Band + Attribute two char code), such as '1C' or '2L'.
        :type obs_code: List[str]
        :param version: The version of RINEX to return. Not applicable to arrow requests.
        :type version: int
        :param accept: The content type to return. If application/vnd.apache.arrow.stream is specified, an Apache arrow stream is returned. Otherwise, a gzipped RINEX is returned.
        :type accept: str
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

        _param = self._get_gnss_observations_serialize(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            session_id=session_id,
            var_field=var_field,
            system=system,
            satellite=satellite,
            obs_code=obs_code,
            version=version,
            accept=accept,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': None,
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _get_gnss_observations_serialize(
        self,
        start_datetime,
        end_datetime,
        session_id,
        var_field,
        system,
        satellite,
        obs_code,
        version,
        accept,
        _request_auth,
        _content_type,
        _headers,
        _host_index,
    ) -> RequestSerialized:

        _host = None

        _collection_formats: Dict[str, str] = {
            'field': 'multi',
            'system': 'multi',
            'satellite': 'multi',
            'obs_code': 'multi',
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
        if start_datetime is not None:
            
            _query_params.append(('start_datetime', start_datetime))
            
        if end_datetime is not None:
            
            _query_params.append(('end_datetime', end_datetime))
            
        if session_id is not None:
            
            _query_params.append(('session_id', session_id))
            
        if var_field is not None:
            
            _query_params.append(('field', var_field))
            
        if system is not None:
            
            _query_params.append(('system', system))
            
        if satellite is not None:
            
            _query_params.append(('satellite', satellite))
            
        if obs_code is not None:
            
            _query_params.append(('obs_code', obs_code))
            
        if version is not None:
            
            _query_params.append(('version', version))
            
        # process the header parameters
        if accept is not None:
            _header_params['accept'] = accept
        # process the form parameters
        # process the body parameter


        # set the HTTP header `Accept`
        if 'Accept' not in _header_params:
            _header_params['Accept'] = self.api_client.select_header_accept(
                [
                    'application/problem+json'
                ]
            )


        # authentication setting
        _auth_settings: List[str] = [
            'HTTPBearer', 
            'Oauth2Implicit'
        ]

        return self.api_client.param_serialize(
            method='GET',
            resource_path='/data-products/gnss/observations',
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



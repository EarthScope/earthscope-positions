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
from pydantic import Field, StrictStr
from typing import Optional
from typing_extensions import Annotated
from earthscope_client.models.category import Category
from earthscope_client.models.page_dropoff_items import PageDropoffItems
from earthscope_client.models.status import Status
from earthscope_client.models.status_summary_response import StatusSummaryResponse

from earthscope_client.api_client import ApiClient, RequestSerialized
from earthscope_client.api_response import ApiResponse
from earthscope_client.rest import RESTResponseType


class DataContributionApi:
    """NOTE: This class is auto generated by OpenAPI Generator
    Ref: https://openapi-generator.tech

    Do not edit the class manually.
    """

    def __init__(self, api_client=None) -> None:
        if api_client is None:
            api_client = ApiClient.get_default()
        self.api_client = api_client


    @validate_call
    def dropoff_list(
        self,
        category: Category,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Starting index from results list")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=500, strict=True, ge=1)]], Field(description="Number of results to return")] = None,
        prefix: Annotated[Optional[StrictStr], Field(description="Only return keys that start with this string")] = None,
        submitted_after: Annotated[Optional[datetime], Field(description="Only return items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
        submitted_before: Annotated[Optional[datetime], Field(description="Only return items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
        status: Annotated[Optional[Status], Field(description="Only return items with this status. Example: 'RECEIVED'")] = None,
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
    ) -> PageDropoffItems:
        """Dropoff List

        This endpoint returns summary information for some or all (up to 100 per page)              of the objects you've submitted to EarthScope previously, and the status of              their processing and acceptance. You can use the request parameters as              selection criteria to return a subset of the objects

        :param category: (required)
        :type category: Category
        :param offset: Starting index from results list
        :type offset: int
        :param limit: Number of results to return
        :type limit: int
        :param prefix: Only return keys that start with this string
        :type prefix: str
        :param submitted_after: Only return items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_after: datetime
        :param submitted_before: Only return items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_before: datetime
        :param status: Only return items with this status. Example: 'RECEIVED'
        :type status: Status
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

        _param = self._dropoff_list_serialize(
            category=category,
            offset=offset,
            limit=limit,
            prefix=prefix,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            status=status,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "PageDropoffItems",
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
    def dropoff_list_with_http_info(
        self,
        category: Category,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Starting index from results list")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=500, strict=True, ge=1)]], Field(description="Number of results to return")] = None,
        prefix: Annotated[Optional[StrictStr], Field(description="Only return keys that start with this string")] = None,
        submitted_after: Annotated[Optional[datetime], Field(description="Only return items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
        submitted_before: Annotated[Optional[datetime], Field(description="Only return items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
        status: Annotated[Optional[Status], Field(description="Only return items with this status. Example: 'RECEIVED'")] = None,
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
    ) -> ApiResponse[PageDropoffItems]:
        """Dropoff List

        This endpoint returns summary information for some or all (up to 100 per page)              of the objects you've submitted to EarthScope previously, and the status of              their processing and acceptance. You can use the request parameters as              selection criteria to return a subset of the objects

        :param category: (required)
        :type category: Category
        :param offset: Starting index from results list
        :type offset: int
        :param limit: Number of results to return
        :type limit: int
        :param prefix: Only return keys that start with this string
        :type prefix: str
        :param submitted_after: Only return items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_after: datetime
        :param submitted_before: Only return items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_before: datetime
        :param status: Only return items with this status. Example: 'RECEIVED'
        :type status: Status
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

        _param = self._dropoff_list_serialize(
            category=category,
            offset=offset,
            limit=limit,
            prefix=prefix,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            status=status,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "PageDropoffItems",
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
    def dropoff_list_without_preload_content(
        self,
        category: Category,
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Starting index from results list")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=500, strict=True, ge=1)]], Field(description="Number of results to return")] = None,
        prefix: Annotated[Optional[StrictStr], Field(description="Only return keys that start with this string")] = None,
        submitted_after: Annotated[Optional[datetime], Field(description="Only return items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
        submitted_before: Annotated[Optional[datetime], Field(description="Only return items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
        status: Annotated[Optional[Status], Field(description="Only return items with this status. Example: 'RECEIVED'")] = None,
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
        """Dropoff List

        This endpoint returns summary information for some or all (up to 100 per page)              of the objects you've submitted to EarthScope previously, and the status of              their processing and acceptance. You can use the request parameters as              selection criteria to return a subset of the objects

        :param category: (required)
        :type category: Category
        :param offset: Starting index from results list
        :type offset: int
        :param limit: Number of results to return
        :type limit: int
        :param prefix: Only return keys that start with this string
        :type prefix: str
        :param submitted_after: Only return items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_after: datetime
        :param submitted_before: Only return items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_before: datetime
        :param status: Only return items with this status. Example: 'RECEIVED'
        :type status: Status
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

        _param = self._dropoff_list_serialize(
            category=category,
            offset=offset,
            limit=limit,
            prefix=prefix,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            status=status,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "PageDropoffItems",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _dropoff_list_serialize(
        self,
        category,
        offset,
        limit,
        prefix,
        submitted_after,
        submitted_before,
        status,
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
        if category is not None:
            _path_params['category'] = category.value
        # process the query parameters
        if offset is not None:
            
            _query_params.append(('offset', offset))
            
        if limit is not None:
            
            _query_params.append(('limit', limit))
            
        if prefix is not None:
            
            _query_params.append(('prefix', prefix))
            
        if submitted_after is not None:
            if isinstance(submitted_after, datetime):
                _query_params.append(
                    (
                        'submitted_after',
                        submitted_after.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('submitted_after', submitted_after))
            
        if submitted_before is not None:
            if isinstance(submitted_before, datetime):
                _query_params.append(
                    (
                        'submitted_before',
                        submitted_before.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('submitted_before', submitted_before))
            
        if status is not None:
            
            _query_params.append(('status', status.value))
            
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
            resource_path='/dropoff/{category}',
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
    def dropoff_status(
        self,
        category: Category,
        key: Annotated[StrictStr, Field(description="Key to get submission history of")],
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Starting index from results list")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Number of results to return")] = None,
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
    ) -> PageDropoffItems:
        """Dropoff Status

        This endpoint returns a detailed history of all activity for the submitted              file (up to 100 per page). This can include activity from multiple attempts              to upload the file.  You can use the request parameters as selection criteria              to return a subset of the history.

        :param category: (required)
        :type category: Category
        :param key: Key to get submission history of (required)
        :type key: str
        :param offset: Starting index from results list
        :type offset: int
        :param limit: Number of results to return
        :type limit: int
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

        _param = self._dropoff_status_serialize(
            category=category,
            key=key,
            offset=offset,
            limit=limit,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "PageDropoffItems",
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
    def dropoff_status_with_http_info(
        self,
        category: Category,
        key: Annotated[StrictStr, Field(description="Key to get submission history of")],
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Starting index from results list")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Number of results to return")] = None,
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
    ) -> ApiResponse[PageDropoffItems]:
        """Dropoff Status

        This endpoint returns a detailed history of all activity for the submitted              file (up to 100 per page). This can include activity from multiple attempts              to upload the file.  You can use the request parameters as selection criteria              to return a subset of the history.

        :param category: (required)
        :type category: Category
        :param key: Key to get submission history of (required)
        :type key: str
        :param offset: Starting index from results list
        :type offset: int
        :param limit: Number of results to return
        :type limit: int
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

        _param = self._dropoff_status_serialize(
            category=category,
            key=key,
            offset=offset,
            limit=limit,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "PageDropoffItems",
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
    def dropoff_status_without_preload_content(
        self,
        category: Category,
        key: Annotated[StrictStr, Field(description="Key to get submission history of")],
        offset: Annotated[Optional[Annotated[int, Field(strict=True, ge=0)]], Field(description="Starting index from results list")] = None,
        limit: Annotated[Optional[Annotated[int, Field(le=100, strict=True, ge=1)]], Field(description="Number of results to return")] = None,
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
        """Dropoff Status

        This endpoint returns a detailed history of all activity for the submitted              file (up to 100 per page). This can include activity from multiple attempts              to upload the file.  You can use the request parameters as selection criteria              to return a subset of the history.

        :param category: (required)
        :type category: Category
        :param key: Key to get submission history of (required)
        :type key: str
        :param offset: Starting index from results list
        :type offset: int
        :param limit: Number of results to return
        :type limit: int
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

        _param = self._dropoff_status_serialize(
            category=category,
            key=key,
            offset=offset,
            limit=limit,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "PageDropoffItems",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _dropoff_status_serialize(
        self,
        category,
        key,
        offset,
        limit,
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
        if category is not None:
            _path_params['category'] = category.value
        # process the query parameters
        if key is not None:
            
            _query_params.append(('key', key))
            
        if offset is not None:
            
            _query_params.append(('offset', offset))
            
        if limit is not None:
            
            _query_params.append(('limit', limit))
            
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
            resource_path='/dropoff/{category}/status',
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
    def dropoff_summary(
        self,
        category: Category,
        prefix: Annotated[Optional[StrictStr], Field(description="Only count keys that start with this string")] = None,
        submitted_after: Annotated[Optional[datetime], Field(description="Only count items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
        submitted_before: Annotated[Optional[datetime], Field(description="Only count items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
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
    ) -> StatusSummaryResponse:
        """Dropoff Summary

        This endpoint returns a count of all of the objects you've submitted to EarthScope              previously, grouped by status. You can use the request parameters as selection criteria              to return a subset of the objects

        :param category: (required)
        :type category: Category
        :param prefix: Only count keys that start with this string
        :type prefix: str
        :param submitted_after: Only count items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_after: datetime
        :param submitted_before: Only count items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_before: datetime
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

        _param = self._dropoff_summary_serialize(
            category=category,
            prefix=prefix,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "StatusSummaryResponse",
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
    def dropoff_summary_with_http_info(
        self,
        category: Category,
        prefix: Annotated[Optional[StrictStr], Field(description="Only count keys that start with this string")] = None,
        submitted_after: Annotated[Optional[datetime], Field(description="Only count items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
        submitted_before: Annotated[Optional[datetime], Field(description="Only count items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
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
    ) -> ApiResponse[StatusSummaryResponse]:
        """Dropoff Summary

        This endpoint returns a count of all of the objects you've submitted to EarthScope              previously, grouped by status. You can use the request parameters as selection criteria              to return a subset of the objects

        :param category: (required)
        :type category: Category
        :param prefix: Only count keys that start with this string
        :type prefix: str
        :param submitted_after: Only count items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_after: datetime
        :param submitted_before: Only count items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_before: datetime
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

        _param = self._dropoff_summary_serialize(
            category=category,
            prefix=prefix,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "StatusSummaryResponse",
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
    def dropoff_summary_without_preload_content(
        self,
        category: Category,
        prefix: Annotated[Optional[StrictStr], Field(description="Only count keys that start with this string")] = None,
        submitted_after: Annotated[Optional[datetime], Field(description="Only count items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
        submitted_before: Annotated[Optional[datetime], Field(description="Only count items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'")] = None,
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
        """Dropoff Summary

        This endpoint returns a count of all of the objects you've submitted to EarthScope              previously, grouped by status. You can use the request parameters as selection criteria              to return a subset of the objects

        :param category: (required)
        :type category: Category
        :param prefix: Only count keys that start with this string
        :type prefix: str
        :param submitted_after: Only count items created at or after this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_after: datetime
        :param submitted_before: Only count items created before this ISO timestamp. Example: '2026-01-01T00:00:00Z'
        :type submitted_before: datetime
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

        _param = self._dropoff_summary_serialize(
            category=category,
            prefix=prefix,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
            _request_auth=_request_auth,
            _content_type=_content_type,
            _headers=_headers,
            _host_index=_host_index
        )

        _response_types_map: Dict[str, Optional[str]] = {
            '200': "StatusSummaryResponse",
            '422': "HTTPValidationError",
        }
        response_data = self.api_client.call_api(
            *_param,
            _request_timeout=_request_timeout
        )
        return response_data.response


    def _dropoff_summary_serialize(
        self,
        category,
        prefix,
        submitted_after,
        submitted_before,
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
        if category is not None:
            _path_params['category'] = category.value
        # process the query parameters
        if prefix is not None:
            
            _query_params.append(('prefix', prefix))
            
        if submitted_after is not None:
            if isinstance(submitted_after, datetime):
                _query_params.append(
                    (
                        'submitted_after',
                        submitted_after.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('submitted_after', submitted_after))
            
        if submitted_before is not None:
            if isinstance(submitted_before, datetime):
                _query_params.append(
                    (
                        'submitted_before',
                        submitted_before.strftime(
                            self.api_client.configuration.datetime_format
                        )
                    )
                )
            else:
                _query_params.append(('submitted_before', submitted_before))
            
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
            resource_path='/dropoff/{category}/summary',
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



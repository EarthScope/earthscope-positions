# coding: utf-8

# flake8: noqa
"""
    EarthScope API (Beta) Documentation

    ![EarthScope Facility Logo](https://www.earthscope.org/app/uploads/2024/01/gage_sage_primary_color.svg)  Welcome to the EarthScope Consortium API documentation.   Our API is intended for programmatic access to NSF GAGE and SAGE Facilities' data and metadata. This API can be used with command line tools for automating data access, e.g., **cURL** and **Wget**, and can be directly incorporated into your programs to fetch data.   Our API also powers our online tools for data discovery and access. The dynamic OpenAPI documentation presented here allows you to easily try our API. However, the \"try it out\" forms in these docs are not intended as the primary interface for regular usage.  Authentication is required to use GAGE and SAGE services, please see the [Authentication](#authentication) section below.  ## <a id=\"versions\"></a> Versions The following versions of the EarthScope API have been released: - [beta](/beta/docs)  ##  <a id=\"authentication\"></a> Authentication Our API requires registration and authentication for reporting anonymized usage metrics to our sponsors.  1. [Register and login](https://www.earthscope.org/user/) - [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/user-profile.html). 2. Pass your authentication/access token in an Authorization header along with your API request. [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/file-server-access-examples.html).  Please see [Authentication](https://www.earthscope.org/data/authentication).  ##  <a id=\"policies\"></a> Policies Access and use of EarthScope's NSF GAGE and NSF SAGE Facility data is governed by the following policies. ### <a id=\"data-policies\"></a> Data Policies - [GAGE Data Policy](https://www.unavco.org/data/policies_forms/data-policy/data-policy.html) - [SAGE Data Policy](https://ds.iris.edu/ds/docs/) - [EarthScope Privacy Policy](https://www.earthscope.org/privacy-policy/) - [EarthScope Terms of Service](https://www.earthscope.org/terms-of-service/)  ### <a id=\"versioning\"></a> Versioning The versioning protocol adopted by the NSF GAGE and SAGE Facilities, operated by EarthScope Consortium, applies to each release of a collection of individual web services, collectively referred to as the EarthScope API. An API version is identified by  the first node of the path following the host name, e.g.,  `api.earthscope.org/beta`, or `api.earthscope.org/v1`, where `beta` indicates a pre-production release and `v1` is the serialized production release version.  The EarthScope API uses [Semantic Versioning](https://semver.org/) to designate specific releases of an API. We increment the API major version whenever we introduce breaking changes. Internally, we use minor and patch versions whenever we add functionality and backward-compatible updates. When we release a new major version of the EarthScope API, clients can choose to either continue using a supported (see our [deprecation policy](#deprecation)) existing major version or migrate to the new one. Here forward, we simply use “version” to refer to our major version releases.  Versions will either be `beta` to indicate pre-production releases or `v1` for specific production version releases, where the number increments, e.g., `v1` to `v2` with each major release. Endpoints identified as `beta` are subject to change \"in place\" without notification and should not be used in critical production systems.  The following points describe what kinds of changes result in an updated version: - A URL path is never really changed; if such a modification is required, the original service path will be [deprecated](#deprecation) and a new one created with a version identifier of `beta` or it's version number incremented. - A change to the internal process of an existing web service will not result in an updated version. - A non-backward compatible change to the output produced by an existing web service will result in an updated version. - The addition of a new, optional, query parameter will not result in a new version and the default value of the query parameter will be set so that the web service will behave as previously if the new parameter is not specified. - The addition of a new, required parameter or a change in formatting of parameter values will result in an updated version.  ### <a id=\"deprecation\"></a> Deprecation   - API version deprecation (end of life) will be announced publicly via our [Data Announcements](https://groups.google.com/a/earthscope.org/g/data-announcements) email list.   - Deprecated services will be labelled “Deprecated” in the respective online API documentation.   - Deprecated services will be retired and removed from our documentation after a period of time to be determined in the deprecation announcement. The deprecation period is intended to allow users time to migrate to newer supported versions of our API. 

    The version of the OpenAPI document: beta
    Contact: data-help@earthscope.org
    Generated by OpenAPI Generator (https://openapi-generator.tech)

    Do not edit the class manually.
"""  # noqa: E501


# import models into model package
from earthscope_client.models.aws_role import AwsRole
from earthscope_client.models.aws_temporary_credentials import AwsTemporaryCredentials
from earthscope_client.models.basic_cred_application import BasicCredApplication
from earthscope_client.models.category import Category
from earthscope_client.models.compact_geo_json import CompactGeoJSON
from earthscope_client.models.content_encoding import ContentEncoding
from earthscope_client.models.content_type import ContentType
from earthscope_client.models.context_value import ContextValue
from earthscope_client.models.error_detail import ErrorDetail
from earthscope_client.models.error_model import ErrorModel
from earthscope_client.models.facility import Facility
from earthscope_client.models.http_validation_error import HTTPValidationError
from earthscope_client.models.inst_position import InstPosition
from earthscope_client.models.inst_position_series import InstPositionSeries
from earthscope_client.models.item import Item
from earthscope_client.models.my_generic_ephemeris import MyGenericEphemeris
from earthscope_client.models.network_name_map import NetworkNameMap
from earthscope_client.models.page_dropoff_items import PageDropoffItems
from earthscope_client.models.public_network_datasource import PublicNetworkDatasource
from earthscope_client.models.public_page_annotated_ulid_ulid_pydantic_annotation import PublicPageAnnotatedULIDUlidPydanticAnnotation
from earthscope_client.models.public_page_public_network_datasource import PublicPagePublicNetworkDatasource
from earthscope_client.models.public_page_public_session_datasource import PublicPagePublicSessionDatasource
from earthscope_client.models.public_page_public_station_datasource import PublicPagePublicStationDatasource
from earthscope_client.models.public_page_public_stream_datasource import PublicPagePublicStreamDatasource
from earthscope_client.models.public_session_datasource import PublicSessionDatasource
from earthscope_client.models.public_station_datasource import PublicStationDatasource
from earthscope_client.models.public_stream_datasource import PublicStreamDatasource
from earthscope_client.models.reference_position_tier import ReferencePositionTier
from earthscope_client.models.response_default_find_networks import ResponseDefaultFindNetworks
from earthscope_client.models.response_default_find_sessions import ResponseDefaultFindSessions
from earthscope_client.models.response_default_find_stations import ResponseDefaultFindStations
from earthscope_client.models.response_default_find_streams import ResponseDefaultFindStreams
from earthscope_client.models.response_radial_search_streams_refpos_search_radial_get import ResponseRadialSearchStreamsRefposSearchRadialGet
from earthscope_client.models.sto_fields import STOFields
from earthscope_client.models.session_name_map import SessionNameMap
from earthscope_client.models.session_roll_period import SessionRollPeriod
from earthscope_client.models.session_sample_interval import SessionSampleInterval
from earthscope_client.models.station_info import StationInfo
from earthscope_client.models.station_name_map import StationNameMap
from earthscope_client.models.status import Status
from earthscope_client.models.status_count_item import StatusCountItem
from earthscope_client.models.status_summary_response import StatusSummaryResponse
from earthscope_client.models.stream_data_split_response import StreamDataSplitResponse
from earthscope_client.models.stream_info import StreamInfo
from earthscope_client.models.stream_name_map import StreamNameMap
from earthscope_client.models.stream_sample_interval import StreamSampleInterval
from earthscope_client.models.stream_software import StreamSoftware
from earthscope_client.models.stream_type import StreamType
from earthscope_client.models.user_basic_creds import UserBasicCreds
from earthscope_client.models.user_profile import UserProfile
from earthscope_client.models.validation_error import ValidationError
from earthscope_client.models.validation_error1 import ValidationError1
from earthscope_client.models.validation_error2 import ValidationError2
from earthscope_client.models.validation_error3 import ValidationError3
from earthscope_client.models.validation_error4 import ValidationError4
from earthscope_client.models.validation_error_loc_inner import ValidationErrorLocInner
from earthscope_client.models.work_sector import WorkSector

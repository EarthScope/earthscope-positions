# coding: utf-8

"""
    EarthScope API (Beta) Documentation

    ![EarthScope Facility Logo](https://www.earthscope.org/app/uploads/2024/01/gage_sage_primary_color.svg)  Welcome to the EarthScope Consortium API documentation.   Our API is intended for programmatic access to NSF GAGE and SAGE Facilities' data and metadata. This API can be used with command line tools for automating data access, e.g., **cURL** and **Wget**, and can be directly incorporated into your programs to fetch data.   Our API also powers our online tools for data discovery and access. The dynamic OpenAPI documentation presented here allows you to easily try our API. However, the \"try it out\" forms in these docs are not intended as the primary interface for regular usage.  Authentication is required to use GAGE and SAGE services, please see the [Authentication](#authentication) section below.  ## <a id=\"versions\"></a> Versions The following versions of the EarthScope API have been released: - [beta](/beta/docs)  ##  <a id=\"authentication\"></a> Authentication Our API requires registration and authentication for reporting anonymized usage metrics to our sponsors.  1. [Register and login](https://www.earthscope.org/user/) - [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/user-profile.html). 2. Pass your authentication/access token in an Authorization header along with your API request. [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/file-server-access-examples.html).  Please see [Authentication](https://www.earthscope.org/data/authentication).  ##  <a id=\"policies\"></a> Policies Access and use of EarthScope's NSF GAGE and NSF SAGE Facility data is governed by the following policies. ### <a id=\"data-policies\"></a> Data Policies - [GAGE Data Policy](https://www.unavco.org/data/policies_forms/data-policy/data-policy.html) - [SAGE Data Policy](https://ds.iris.edu/ds/docs/) - [EarthScope Privacy Policy](https://www.earthscope.org/privacy-policy/) - [EarthScope Terms of Service](https://www.earthscope.org/terms-of-service/)  ### <a id=\"versioning\"></a> Versioning The versioning protocol adopted by the NSF GAGE and SAGE Facilities, operated by EarthScope Consortium, applies to each release of a collection of individual web services, collectively referred to as the EarthScope API. An API version is identified by  the first node of the path following the host name, e.g.,  `api.earthscope.org/beta`, or `api.earthscope.org/v1`, where `beta` indicates a pre-production release and `v1` is the serialized production release version.  The EarthScope API uses [Semantic Versioning](https://semver.org/) to designate specific releases of an API. We increment the API major version whenever we introduce breaking changes. Internally, we use minor and patch versions whenever we add functionality and backward-compatible updates. When we release a new major version of the EarthScope API, clients can choose to either continue using a supported (see our [deprecation policy](#deprecation)) existing major version or migrate to the new one. Here forward, we simply use “version” to refer to our major version releases.  Versions will either be `beta` to indicate pre-production releases or `v1` for specific production version releases, where the number increments, e.g., `v1` to `v2` with each major release. Endpoints identified as `beta` are subject to change \"in place\" without notification and should not be used in critical production systems.  The following points describe what kinds of changes result in an updated version: - A URL path is never really changed; if such a modification is required, the original service path will be [deprecated](#deprecation) and a new one created with a version identifier of `beta` or it's version number incremented. - A change to the internal process of an existing web service will not result in an updated version. - A non-backward compatible change to the output produced by an existing web service will result in an updated version. - The addition of a new, optional, query parameter will not result in a new version and the default value of the query parameter will be set so that the web service will behave as previously if the new parameter is not specified. - The addition of a new, required parameter or a change in formatting of parameter values will result in an updated version.  ### <a id=\"deprecation\"></a> Deprecation   - API version deprecation (end of life) will be announced publicly via our [Data Announcements](https://groups.google.com/a/earthscope.org/g/data-announcements) email list.   - Deprecated services will be labelled “Deprecated” in the respective online API documentation.   - Deprecated services will be retired and removed from our documentation after a period of time to be determined in the deprecation announcement. The deprecation period is intended to allow users time to migrate to newer supported versions of our API. 

    The version of the OpenAPI document: beta
    Contact: data-help@earthscope.org
    Generated by OpenAPI Generator (https://openapi-generator.tech)

    Do not edit the class manually.
"""  # noqa: E501


from __future__ import annotations
from inspect import getfullargspec
import json
import pprint
import re  # noqa: F401
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator
from typing import List, Optional
from earthscope_client.models.station_info import StationInfo
from earthscope_client.models.stream_info import StreamInfo
from typing import Union, Any, List, Set, TYPE_CHECKING, Optional, Dict
from typing_extensions import Literal, Self
from pydantic import Field

RESPONSERADIALSEARCHSTREAMSREFPOSSEARCHRADIALGET_ANY_OF_SCHEMAS = ["List[StationInfo]", "List[StreamInfo]", "List[str]"]

class ResponseRadialSearchStreamsRefposSearchRadialGet(BaseModel):
    """
    ResponseRadialSearchStreamsRefposSearchRadialGet
    """

    # data type: List[str]
    anyof_schema_1_validator: Optional[List[StrictStr]] = None
    # data type: List[StreamInfo]
    anyof_schema_2_validator: Optional[List[StreamInfo]] = None
    # data type: List[StationInfo]
    anyof_schema_3_validator: Optional[List[StationInfo]] = None
    if TYPE_CHECKING:
        actual_instance: Optional[Union[List[StationInfo], List[StreamInfo], List[str]]] = None
    else:
        actual_instance: Any = None
    any_of_schemas: Set[str] = { "List[StationInfo]", "List[StreamInfo]", "List[str]" }

    model_config = {
        "validate_assignment": True,
        "protected_namespaces": (),
    }

    def __init__(self, *args, **kwargs) -> None:
        if args:
            if len(args) > 1:
                raise ValueError("If a position argument is used, only 1 is allowed to set `actual_instance`")
            if kwargs:
                raise ValueError("If a position argument is used, keyword arguments cannot be used.")
            super().__init__(actual_instance=args[0])
        else:
            super().__init__(**kwargs)

    @field_validator('actual_instance')
    def actual_instance_must_validate_anyof(cls, v):
        instance = ResponseRadialSearchStreamsRefposSearchRadialGet.model_construct()
        error_messages = []
        # validate data type: List[str]
        try:
            instance.anyof_schema_1_validator = v
            return v
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))
        # validate data type: List[StreamInfo]
        try:
            instance.anyof_schema_2_validator = v
            return v
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))
        # validate data type: List[StationInfo]
        try:
            instance.anyof_schema_3_validator = v
            return v
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))
        if error_messages:
            # no match
            raise ValueError("No match found when setting the actual_instance in ResponseRadialSearchStreamsRefposSearchRadialGet with anyOf schemas: List[StationInfo], List[StreamInfo], List[str]. Details: " + ", ".join(error_messages))
        else:
            return v

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]) -> Self:
        return cls.from_json(json.dumps(obj))

    @classmethod
    def from_json(cls, json_str: str) -> Self:
        """Returns the object represented by the json string"""
        instance = cls.model_construct()
        error_messages = []
        # deserialize data into List[str]
        try:
            # validation
            instance.anyof_schema_1_validator = json.loads(json_str)
            # assign value to actual_instance
            instance.actual_instance = instance.anyof_schema_1_validator
            return instance
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))
        # deserialize data into List[StreamInfo]
        try:
            # validation
            instance.anyof_schema_2_validator = json.loads(json_str)
            # assign value to actual_instance
            instance.actual_instance = instance.anyof_schema_2_validator
            return instance
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))
        # deserialize data into List[StationInfo]
        try:
            # validation
            instance.anyof_schema_3_validator = json.loads(json_str)
            # assign value to actual_instance
            instance.actual_instance = instance.anyof_schema_3_validator
            return instance
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))

        if error_messages:
            # no match
            raise ValueError("No match found when deserializing the JSON string into ResponseRadialSearchStreamsRefposSearchRadialGet with anyOf schemas: List[StationInfo], List[StreamInfo], List[str]. Details: " + ", ".join(error_messages))
        else:
            return instance

    def to_json(self) -> str:
        """Returns the JSON representation of the actual instance"""
        if self.actual_instance is None:
            return "null"

        if hasattr(self.actual_instance, "to_json") and callable(self.actual_instance.to_json):
            return self.actual_instance.to_json()
        else:
            return json.dumps(self.actual_instance)

    def to_dict(self) -> Optional[Union[Dict[str, Any], List[StationInfo], List[StreamInfo], List[str]]]:
        """Returns the dict representation of the actual instance"""
        if self.actual_instance is None:
            return None

        if hasattr(self.actual_instance, "to_dict") and callable(self.actual_instance.to_dict):
            return self.actual_instance.to_dict()
        else:
            return self.actual_instance

    def to_str(self) -> str:
        """Returns the string representation of the actual instance"""
        return pprint.pformat(self.model_dump())



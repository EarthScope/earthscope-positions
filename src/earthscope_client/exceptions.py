# coding: utf-8

"""
    EarthScope API (Beta) Documentation

    ![EarthScope Facility Logo](https://www.earthscope.org/app/uploads/2024/01/gage_sage_primary_color.svg)  Welcome to the EarthScope Consortium API documentation.   Our API is intended for programmatic access to NSF GAGE and SAGE Facilities' data and metadata. This API can be used with command line tools for automating data access, e.g., **cURL** and **Wget**, and can be directly incorporated into your programs to fetch data.   Our API also powers our online tools for data discovery and access. The dynamic OpenAPI documentation presented here allows you to easily try our API. However, the \"try it out\" forms in these docs are not intended as the primary interface for regular usage.  Authentication is required to use GAGE and SAGE services, please see the [Authentication](#authentication) section below.  ## <a id=\"versions\"></a> Versions The following versions of the EarthScope API have been released: - [beta](/beta/docs)  ##  <a id=\"authentication\"></a> Authentication Our API requires registration and authentication for reporting anonymized usage metrics to our sponsors.  1. [Register and login](https://www.earthscope.org/user/) - [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/user-profile.html). 2. Pass your authentication/access token in an Authorization header along with your API request. [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/file-server-access-examples.html).  Please see [Authentication](https://www.earthscope.org/data/authentication).  ##  <a id=\"policies\"></a> Policies Access and use of EarthScope's NSF GAGE and NSF SAGE Facility data is governed by the following policies. ### <a id=\"data-policies\"></a> Data Policies - [GAGE Data Policy](https://www.unavco.org/data/policies_forms/data-policy/data-policy.html) - [SAGE Data Policy](https://ds.iris.edu/ds/docs/) - [EarthScope Privacy Policy](https://www.earthscope.org/privacy-policy/) - [EarthScope Terms of Service](https://www.earthscope.org/terms-of-service/)  ### <a id=\"versioning\"></a> Versioning The versioning protocol adopted by the NSF GAGE and SAGE Facilities, operated by EarthScope Consortium, applies to each release of a collection of individual web services, collectively referred to as the EarthScope API. An API version is identified by  the first node of the path following the host name, e.g.,  `api.earthscope.org/beta`, or `api.earthscope.org/v1`, where `beta` indicates a pre-production release and `v1` is the serialized production release version.  The EarthScope API uses [Semantic Versioning](https://semver.org/) to designate specific releases of an API. We increment the API major version whenever we introduce breaking changes. Internally, we use minor and patch versions whenever we add functionality and backward-compatible updates. When we release a new major version of the EarthScope API, clients can choose to either continue using a supported (see our [deprecation policy](#deprecation)) existing major version or migrate to the new one. Here forward, we simply use “version” to refer to our major version releases.  Versions will either be `beta` to indicate pre-production releases or `v1` for specific production version releases, where the number increments, e.g., `v1` to `v2` with each major release. Endpoints identified as `beta` are subject to change \"in place\" without notification and should not be used in critical production systems.  The following points describe what kinds of changes result in an updated version: - A URL path is never really changed; if such a modification is required, the original service path will be [deprecated](#deprecation) and a new one created with a version identifier of `beta` or it's version number incremented. - A change to the internal process of an existing web service will not result in an updated version. - A non-backward compatible change to the output produced by an existing web service will result in an updated version. - The addition of a new, optional, query parameter will not result in a new version and the default value of the query parameter will be set so that the web service will behave as previously if the new parameter is not specified. - The addition of a new, required parameter or a change in formatting of parameter values will result in an updated version.  ### <a id=\"deprecation\"></a> Deprecation   - API version deprecation (end of life) will be announced publicly via our [Data Announcements](https://groups.google.com/a/earthscope.org/g/data-announcements) email list.   - Deprecated services will be labelled “Deprecated” in the respective online API documentation.   - Deprecated services will be retired and removed from our documentation after a period of time to be determined in the deprecation announcement. The deprecation period is intended to allow users time to migrate to newer supported versions of our API. 

    The version of the OpenAPI document: beta
    Contact: data-help@earthscope.org
    Generated by OpenAPI Generator (https://openapi-generator.tech)

    Do not edit the class manually.
"""  # noqa: E501

from typing import Any, Optional
from typing_extensions import Self

class OpenApiException(Exception):
    """The base exception class for all OpenAPIExceptions"""


class ApiTypeError(OpenApiException, TypeError):
    def __init__(self, msg, path_to_item=None, valid_classes=None,
                 key_type=None) -> None:
        """ Raises an exception for TypeErrors

        Args:
            msg (str): the exception message

        Keyword Args:
            path_to_item (list): a list of keys an indices to get to the
                                 current_item
                                 None if unset
            valid_classes (tuple): the primitive classes that current item
                                   should be an instance of
                                   None if unset
            key_type (bool): False if our value is a value in a dict
                             True if it is a key in a dict
                             False if our item is an item in a list
                             None if unset
        """
        self.path_to_item = path_to_item
        self.valid_classes = valid_classes
        self.key_type = key_type
        full_msg = msg
        if path_to_item:
            full_msg = "{0} at {1}".format(msg, render_path(path_to_item))
        super(ApiTypeError, self).__init__(full_msg)


class ApiValueError(OpenApiException, ValueError):
    def __init__(self, msg, path_to_item=None) -> None:
        """
        Args:
            msg (str): the exception message

        Keyword Args:
            path_to_item (list) the path to the exception in the
                received_data dict. None if unset
        """

        self.path_to_item = path_to_item
        full_msg = msg
        if path_to_item:
            full_msg = "{0} at {1}".format(msg, render_path(path_to_item))
        super(ApiValueError, self).__init__(full_msg)


class ApiAttributeError(OpenApiException, AttributeError):
    def __init__(self, msg, path_to_item=None) -> None:
        """
        Raised when an attribute reference or assignment fails.

        Args:
            msg (str): the exception message

        Keyword Args:
            path_to_item (None/list) the path to the exception in the
                received_data dict
        """
        self.path_to_item = path_to_item
        full_msg = msg
        if path_to_item:
            full_msg = "{0} at {1}".format(msg, render_path(path_to_item))
        super(ApiAttributeError, self).__init__(full_msg)


class ApiKeyError(OpenApiException, KeyError):
    def __init__(self, msg, path_to_item=None) -> None:
        """
        Args:
            msg (str): the exception message

        Keyword Args:
            path_to_item (None/list) the path to the exception in the
                received_data dict
        """
        self.path_to_item = path_to_item
        full_msg = msg
        if path_to_item:
            full_msg = "{0} at {1}".format(msg, render_path(path_to_item))
        super(ApiKeyError, self).__init__(full_msg)


class ApiException(OpenApiException):

    def __init__(
        self, 
        status=None, 
        reason=None, 
        http_resp=None,
        *,
        body: Optional[str] = None,
        data: Optional[Any] = None,
    ) -> None:
        self.status = status
        self.reason = reason
        self.body = body
        self.data = data
        self.headers = None

        if http_resp:
            if self.status is None:
                self.status = http_resp.status
            if self.reason is None:
                self.reason = http_resp.reason
            if self.body is None:
                try:
                    self.body = http_resp.data.decode('utf-8')
                except Exception:
                    pass
            self.headers = http_resp.getheaders()

    @classmethod
    def from_response(
        cls, 
        *, 
        http_resp, 
        body: Optional[str], 
        data: Optional[Any],
    ) -> Self:
        if http_resp.status == 400:
            raise BadRequestException(http_resp=http_resp, body=body, data=data)

        if http_resp.status == 401:
            raise UnauthorizedException(http_resp=http_resp, body=body, data=data)

        if http_resp.status == 403:
            raise ForbiddenException(http_resp=http_resp, body=body, data=data)

        if http_resp.status == 404:
            raise NotFoundException(http_resp=http_resp, body=body, data=data)

        # Added new conditions for 409 and 422
        if http_resp.status == 409:
            raise ConflictException(http_resp=http_resp, body=body, data=data)

        if http_resp.status == 422:
            raise UnprocessableEntityException(http_resp=http_resp, body=body, data=data)

        if 500 <= http_resp.status <= 599:
            raise ServiceException(http_resp=http_resp, body=body, data=data)
        raise ApiException(http_resp=http_resp, body=body, data=data)

    def __str__(self):
        """Custom error messages for exception"""
        error_message = "({0})\n"\
                        "Reason: {1}\n".format(self.status, self.reason)
        if self.headers:
            error_message += "HTTP response headers: {0}\n".format(
                self.headers)

        if self.data or self.body:
            error_message += "HTTP response body: {0}\n".format(self.data or self.body)

        return error_message


class BadRequestException(ApiException):
    pass


class NotFoundException(ApiException):
    pass


class UnauthorizedException(ApiException):
    pass


class ForbiddenException(ApiException):
    pass


class ServiceException(ApiException):
    pass


class ConflictException(ApiException):
    """Exception for HTTP 409 Conflict."""
    pass


class UnprocessableEntityException(ApiException):
    """Exception for HTTP 422 Unprocessable Entity."""
    pass


def render_path(path_to_item):
    """Returns a string representation of a path"""
    result = ""
    for pth in path_to_item:
        if isinstance(pth, int):
            result += "[{0}]".format(pth)
        else:
            result += "['{0}']".format(pth)
    return result

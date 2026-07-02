# coding: utf-8

"""
    EarthScope API (Beta) Documentation

    ![EarthScope Facility Logo](https://www.earthscope.org/app/uploads/2024/01/gage_sage_primary_color.svg)  Welcome to the EarthScope Consortium API documentation.   Our API is intended for programmatic access to NSF GAGE and SAGE Facilities' data and metadata. This API can be used with command line tools for automating data access, e.g., **cURL** and **Wget**, and can be directly incorporated into your programs to fetch data.   Our API also powers our online tools for data discovery and access. The dynamic OpenAPI documentation presented here allows you to easily try our API. However, the \"try it out\" forms in these docs are not intended as the primary interface for regular usage.  Authentication is required to use GAGE and SAGE services, please see the [Authentication](#authentication) section below.  ## <a id=\"versions\"></a> Versions The following versions of the EarthScope API have been released: - [beta](/beta/docs)  ##  <a id=\"authentication\"></a> Authentication Our API requires registration and authentication for reporting anonymized usage metrics to our sponsors.  1. [Register and login](https://www.earthscope.org/user/) - [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/user-profile.html). 2. Pass your authentication/access token in an Authorization header along with your API request. [See detailed instructions](https://www.unavco.org/data/gps-gnss/file-server/file-server-access-examples.html).  Please see [Authentication](https://www.earthscope.org/data/authentication).  ##  <a id=\"policies\"></a> Policies Access and use of EarthScope's NSF GAGE and NSF SAGE Facility data is governed by the following policies. ### <a id=\"data-policies\"></a> Data Policies - [GAGE Data Policy](https://www.unavco.org/data/policies_forms/data-policy/data-policy.html) - [SAGE Data Policy](https://ds.iris.edu/ds/docs/) - [EarthScope Privacy Policy](https://www.earthscope.org/privacy-policy/) - [EarthScope Terms of Service](https://www.earthscope.org/terms-of-service/)  ### <a id=\"versioning\"></a> Versioning The versioning protocol adopted by the NSF GAGE and SAGE Facilities, operated by EarthScope Consortium, applies to each release of a collection of individual web services, collectively referred to as the EarthScope API. An API version is identified by  the first node of the path following the host name, e.g.,  `api.earthscope.org/beta`, or `api.earthscope.org/v1`, where `beta` indicates a pre-production release and `v1` is the serialized production release version.  The EarthScope API uses [Semantic Versioning](https://semver.org/) to designate specific releases of an API. We increment the API major version whenever we introduce breaking changes. Internally, we use minor and patch versions whenever we add functionality and backward-compatible updates. When we release a new major version of the EarthScope API, clients can choose to either continue using a supported (see our [deprecation policy](#deprecation)) existing major version or migrate to the new one. Here forward, we simply use “version” to refer to our major version releases.  Versions will either be `beta` to indicate pre-production releases or `v1` for specific production version releases, where the number increments, e.g., `v1` to `v2` with each major release. Endpoints identified as `beta` are subject to change \"in place\" without notification and should not be used in critical production systems.  The following points describe what kinds of changes result in an updated version: - A URL path is never really changed; if such a modification is required, the original service path will be [deprecated](#deprecation) and a new one created with a version identifier of `beta` or it's version number incremented. - A change to the internal process of an existing web service will not result in an updated version. - A non-backward compatible change to the output produced by an existing web service will result in an updated version. - The addition of a new, optional, query parameter will not result in a new version and the default value of the query parameter will be set so that the web service will behave as previously if the new parameter is not specified. - The addition of a new, required parameter or a change in formatting of parameter values will result in an updated version.  ### <a id=\"deprecation\"></a> Deprecation   - API version deprecation (end of life) will be announced publicly via our [Data Announcements](https://groups.google.com/a/earthscope.org/g/data-announcements) email list.   - Deprecated services will be labelled “Deprecated” in the respective online API documentation.   - Deprecated services will be retired and removed from our documentation after a period of time to be determined in the deprecation announcement. The deprecation period is intended to allow users time to migrate to newer supported versions of our API. 

    The version of the OpenAPI document: beta
    Contact: data-help@earthscope.org
    Generated by OpenAPI Generator (https://openapi-generator.tech)

    Do not edit the class manually.
"""  # noqa: E501


import io
import json
import re
import ssl

import urllib3

from earthscope_client.exceptions import ApiException, ApiValueError

SUPPORTED_SOCKS_PROXIES = {"socks5", "socks5h", "socks4", "socks4a"}
RESTResponseType = urllib3.HTTPResponse


def is_socks_proxy_url(url):
    if url is None:
        return False
    split_section = url.split("://")
    if len(split_section) < 2:
        return False
    else:
        return split_section[0].lower() in SUPPORTED_SOCKS_PROXIES


class RESTResponse(io.IOBase):

    def __init__(self, resp) -> None:
        self.response = resp
        self.status = resp.status
        self.reason = resp.reason
        self.data = None

    def read(self):
        if self.data is None:
            self.data = self.response.data
        return self.data

    def getheaders(self):
        """Returns a dictionary of the response headers."""
        return self.response.headers

    def getheader(self, name, default=None):
        """Returns a given response header."""
        return self.response.headers.get(name, default)


class RESTClientObject:

    def __init__(self, configuration) -> None:
        # urllib3.PoolManager will pass all kw parameters to connectionpool
        # https://github.com/shazow/urllib3/blob/f9409436f83aeb79fbaf090181cd81b784f1b8ce/urllib3/poolmanager.py#L75  # noqa: E501
        # https://github.com/shazow/urllib3/blob/f9409436f83aeb79fbaf090181cd81b784f1b8ce/urllib3/connectionpool.py#L680  # noqa: E501
        # Custom SSL certificates and client certificates: http://urllib3.readthedocs.io/en/latest/advanced-usage.html  # noqa: E501

        # cert_reqs
        if configuration.verify_ssl:
            cert_reqs = ssl.CERT_REQUIRED
        else:
            cert_reqs = ssl.CERT_NONE

        pool_args = {
            "cert_reqs": cert_reqs,
            "ca_certs": configuration.ssl_ca_cert,
            "cert_file": configuration.cert_file,
            "key_file": configuration.key_file,
            "ca_cert_data": configuration.ca_cert_data,
        }
        if configuration.assert_hostname is not None:
            pool_args['assert_hostname'] = (
                configuration.assert_hostname
            )

        if configuration.retries is not None:
            pool_args['retries'] = configuration.retries

        if configuration.tls_server_name:
            pool_args['server_hostname'] = configuration.tls_server_name


        if configuration.socket_options is not None:
            pool_args['socket_options'] = configuration.socket_options

        if configuration.connection_pool_maxsize is not None:
            pool_args['maxsize'] = configuration.connection_pool_maxsize

        # https pool manager
        self.pool_manager: urllib3.PoolManager

        if configuration.proxy:
            if is_socks_proxy_url(configuration.proxy):
                from urllib3.contrib.socks import SOCKSProxyManager
                pool_args["proxy_url"] = configuration.proxy
                pool_args["headers"] = configuration.proxy_headers
                self.pool_manager = SOCKSProxyManager(**pool_args)
            else:
                pool_args["proxy_url"] = configuration.proxy
                pool_args["proxy_headers"] = configuration.proxy_headers
                self.pool_manager = urllib3.ProxyManager(**pool_args)
        else:
            self.pool_manager = urllib3.PoolManager(**pool_args)

    def request(
        self,
        method,
        url,
        headers=None,
        body=None,
        post_params=None,
        _request_timeout=None
    ):
        """Perform requests.

        :param method: http request method
        :param url: http request url
        :param headers: http request headers
        :param body: request json body, for `application/json`
        :param post_params: request post parameters,
                            `application/x-www-form-urlencoded`
                            and `multipart/form-data`
        :param _request_timeout: timeout setting for this request. If one
                                 number provided, it will be total request
                                 timeout. It can also be a pair (tuple) of
                                 (connection, read) timeouts.
        """
        method = method.upper()
        assert method in [
            'GET',
            'HEAD',
            'DELETE',
            'POST',
            'PUT',
            'PATCH',
            'OPTIONS'
        ]

        if post_params and body:
            raise ApiValueError(
                "body parameter cannot be used with post_params parameter."
            )

        post_params = post_params or {}
        headers = headers or {}

        timeout = None
        if _request_timeout:
            if isinstance(_request_timeout, (int, float)):
                timeout = urllib3.Timeout(total=_request_timeout)
            elif (
                    isinstance(_request_timeout, tuple)
                    and len(_request_timeout) == 2
                ):
                timeout = urllib3.Timeout(
                    connect=_request_timeout[0],
                    read=_request_timeout[1]
                )

        try:
            # For `POST`, `PUT`, `PATCH`, `OPTIONS`, `DELETE`
            if method in ['POST', 'PUT', 'PATCH', 'OPTIONS', 'DELETE']:

                # no content type provided or payload is json
                content_type = headers.get('Content-Type')
                if (
                    not content_type
                    or re.search('json', content_type, re.IGNORECASE)
                ):
                    request_body = None
                    if body is not None:
                        request_body = json.dumps(body)
                    r = self.pool_manager.request(
                        method,
                        url,
                        body=request_body,
                        timeout=timeout,
                        headers=headers,
                        preload_content=False
                    )
                elif content_type == 'application/x-www-form-urlencoded':
                    r = self.pool_manager.request(
                        method,
                        url,
                        fields=post_params,
                        encode_multipart=False,
                        timeout=timeout,
                        headers=headers,
                        preload_content=False
                    )
                elif content_type == 'multipart/form-data':
                    # must del headers['Content-Type'], or the correct
                    # Content-Type which generated by urllib3 will be
                    # overwritten.
                    del headers['Content-Type']
                    # Ensures that dict objects are serialized
                    post_params = [(a, json.dumps(b)) if isinstance(b, dict) else (a,b) for a, b in post_params]
                    r = self.pool_manager.request(
                        method,
                        url,
                        fields=post_params,
                        encode_multipart=True,
                        timeout=timeout,
                        headers=headers,
                        preload_content=False
                    )
                # Pass a `string` parameter directly in the body to support
                # other content types than JSON when `body` argument is
                # provided in serialized form.
                elif isinstance(body, str) or isinstance(body, bytes):
                    r = self.pool_manager.request(
                        method,
                        url,
                        body=body,
                        timeout=timeout,
                        headers=headers,
                        preload_content=False
                    )
                elif headers['Content-Type'].startswith('text/') and isinstance(body, bool):
                    request_body = "true" if body else "false"
                    r = self.pool_manager.request(
                        method,
                        url,
                        body=request_body,
                        preload_content=False,
                        timeout=timeout,
                        headers=headers)
                else:
                    # Cannot generate the request from given parameters
                    msg = """Cannot prepare a request message for provided
                             arguments. Please check that your arguments match
                             declared content type."""
                    raise ApiException(status=0, reason=msg)
            # For `GET`, `HEAD`
            else:
                r = self.pool_manager.request(
                    method,
                    url,
                    fields={},
                    timeout=timeout,
                    headers=headers,
                    preload_content=False
                )
        except urllib3.exceptions.SSLError as e:
            msg = "\n".join([type(e).__name__, str(e)])
            raise ApiException(status=0, reason=msg)

        return RESTResponse(r)

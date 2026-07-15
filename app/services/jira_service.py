# jira/service.py
from __future__ import annotations

# Libraries
import os
import json
import mimetypes
import urllib3
import logging

from typing import Any, Dict
from urllib.parse import urlencode
from urllib3.util.retry import Retry
from urllib3.util.timeout import Timeout

from app.services.jira_mappings import get_map


log = logging.getLogger(__name__)


class JiraService:

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the Jira service.

        Sets up configuration and creates a reusable Jira session
        for all subsequent API calls.
        """
        self._config = config
        self._session = self.create_jira_session()

    def success(self, data=None, status_code: int | None = None):
        return {
            "success": True,
            "status_code": status_code,
            "data": data,
            "error": None,
        }

    def failure(
        self,
        error: str,
        status_code: int | None = None,
        data=None,
    ):
        return {
            "success": False,
            "status_code": status_code,
            "data": data,
            "error": error,
        }

    def create_jira_session(self):
        """
        Initialize and return a reusable Jira HTTP session.

        Reads configuration values (such as base URL and token) from the
        service config and creates a urllib3 PoolManager configured with
        retry and timeout settings.

        Returns:
            dict: Session object containing the HTTP pool,
                  base URL, and request headers.
        """

        config = self._config

        base_url = config.get("JIRA_BASE_URL")
        token = config.get("JIRA_TOKEN")

        if not base_url:
            raise RuntimeError("Missing JIRA_BASE_URL in config")

        if not token:
            raise RuntimeError("Missing JIRA_TOKEN in config")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "DELETE"],
        )

        timeout = Timeout(
            connect=5.0,
            read=30.0,
        )

        http = urllib3.PoolManager(
            retries=retry_strategy,
            timeout=timeout,
            cert_reqs="CERT_REQUIRED",
        )

        return {
            "http": http,
            "base_url": base_url.rstrip("/"),
            "headers": headers,
        }

    def jira_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        payload: dict | None = None,
        raise_error: bool = True,
    ):
        """
        Execute a Jira REST API request.

        Always returns a structured response when no exception is raised.

        Returns:
            dict: {
                "success": bool,
                "status_code": int | None,
                "data": dict | list | None,
                "error": str | None,
            }
        """

        try:
            allowed_methods = {"GET", "POST", "PUT", "DELETE"}
            method = method.upper()

            if method not in allowed_methods:
                return self.failure(f"Unsupported HTTP method: {method}")

            base_url = self._session["base_url"]
            http = self._session["http"]
            headers = self._session["headers"]

            url = f"{base_url}{endpoint}"

            if params:
                url = f"{url}?{urlencode(params)}"

            request_kwargs = {
                "method": method,
                "url": url,
                "headers": headers,
            }

            if payload is not None:
                request_kwargs["body"] = json.dumps(payload).encode("utf-8")

            response = http.request(**request_kwargs)

            raw = response.data.decode("utf-8", errors="replace")

            if response.status < 200 or response.status >= 300:
                error_message = (
                    f"Jira {method} failed [{url}]: "
                    f"{response.status} - {raw}"
                )

                if raise_error:
                    raise RuntimeError(error_message)

                return {
                    "success": False,
                    "status_code": response.status,
                    "data": None,
                    "error": error_message,
                }

            if not raw:
                parsed_data = {}
            else:
                try:
                    parsed_data = json.loads(raw)
                except Exception:
                    error_message = (
                        f"Jira {method} returned non-JSON response "
                        f"[{url}]: {raw}"
                    )

                    if raise_error:
                        raise RuntimeError(error_message)

                    return {
                        "success": False,
                        "status_code": response.status,
                        "data": None,
                        "error": error_message,
                    }

                return {
                    "success": True,
                    "status_code": response.status,
                    "data": parsed_data,
                    "error": None,
                }

        except Exception as e:
            if raise_error:
                log.exception(f"Unexpected error during Jira {method} request")
                raise RuntimeError(
                    f"Jira {method} error [{endpoint}]: {e}"
                ) from e

            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": str(e),
            }

    def search_jira_issues(
        self,
        jql: str,
        output_fields: list[str] | None = None,
        max_records: int | None = None,
        map_fields: dict | None = None,
    ):
        """
        Search Jira issues using JQL with pagination support.

        Retrieves issues in batches and aggregates results until all
        matching issues or max_records are collected.

        Args:
            jql: Jira Query Language string.
            fields: Optional list of fields to retrieve.
            max_records: Optional maximum number of records to return.

        Returns:
            dict: Standard service response containing a list of
                Jira issue objects.
        """

        try:

            if not jql or not jql.strip():
                return self.failure("jql cannot be empty")

            if map_fields is not None:
                jira_fields = self._derive_fields(map_fields)
            else:
                jira_fields = self._derive_all_fields()

            all_issues = []
            start_at = 0
            page_size = int(self._config.get("PAGE_SIZE", 100))

            if page_size <= 0:
                return self.failure("PAGE_SIZE must be greater than 0")

            while True:

                if max_records is not None:
                    remaining = max_records - len(all_issues)

                    if remaining <= 0:
                        break

                    current_page_size = min(page_size, remaining)
                else:
                    current_page_size = page_size

                params = {
                    "jql": jql,
                    "fields": ",".join(jira_fields),
                    "startAt": start_at,
                    "maxResults": current_page_size,
                }
                
                result = self.jira_request(
                    method="get",
                    endpoint="/rest/api/2/search",
                    params=params,
                    raise_error=False,
                )

                if not result["success"]:
                    return result

                data = result["data"] or {}

                issues = data.get("issues", [])
                total = data.get("total", 0)

                if not issues:
                    break

                all_issues.extend(issues)
                start_at += len(issues)

                if start_at >= total:
                    break

            if map_fields is not None:
                mapped_issues = self.map_issues(all_issues, map_fields)
            else:
                mapped_issues = self.map_issues(all_issues)

            if output_fields is not None:
                mapped_issues = self._filter_output_fields(
                    mapped_issues,
                    output_fields,
                )

            return self.success(data=mapped_issues)

        except Exception as e:
            log.exception("Unexpected error during Jira issue search")
            return self.failure(str(e))

    def create_jira_issue(
        self,
        project_key: str,
        issue_type: str,
        summary: str,
        assignee: str,
        additional_fields: dict | None = None,
    ):
        """
        Create a new Jira issue.

        Constructs the required payload and sends a POST request to Jira.

        Args:
            project_key: Jira project key.
            issue_type: Issue type name.
            summary: Issue summary.
            description: Issue description.
            additional_fields: Optional dictionary of additional fields.

        Returns:
            dict: Standard service response containing the created Jira issue
            details.
        """

        try:
            fields = {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary,
            }

            if assignee:
                assignee_result = self.get_jira_user_identifier_by_email(
                    email_address=assignee,
                    identifier="name",
                )

                if not assignee_result["success"]:
                    return assignee_result

                fields["assignee"] = assignee_result["data"]

            if additional_fields:
                fields.update(additional_fields)

            payload = {"fields": fields}

            return self.jira_request(
                method="POST",
                endpoint="/rest/api/2/issue",
                payload=payload,
                raise_error=False,
            )

        except Exception as e:
            log.exception("Unexpected error during Jira issue creation")
            return self.failure(str(e))

    def add_jira_attachment(
        self,
        issue_key: str,
        file_path: str,
    ):
        """
        Attach a file to a Jira issue.

        Args:
            issue_key: Jira issue key.
            file_path: Path to the file to upload.

        Returns:
            dict: Standard service response containing attachment metadata.
        """

        try:
            if not os.path.exists(file_path):
                return self.failure(f"File not found: {file_path}")

            base_url = self._session["base_url"]
            http = self._session["http"]

            file_name = os.path.basename(file_path)
            content_type = (
                mimetypes.guess_type(file_path)[0]
                or "application/octet-stream"
            )

            url = (
                f"{base_url}/rest/api/2/issue/"
                f"{issue_key}/attachments"
            )

            headers = {
                "Authorization": self._session["headers"]["Authorization"],
                "Accept": "application/json",
                "X-Atlassian-Token": "nocheck",
            }

            with open(file_path, "rb") as file:
                response = http.request(
                    "POST",
                    url,
                    headers=headers,
                    fields={
                        "file": (
                            file_name,
                            file.read(),
                            content_type,
                        )
                    },
                    retries=False,
                )

            raw = response.data.decode("utf-8", errors="replace")

            if response.status < 200 or response.status >= 300:
                return self.failure(
                    error=(
                        f"Attachment upload failed: "
                        f"{response.status} - {raw}"
                    ),
                    status_code=response.status,
                )

            data = json.loads(raw) if raw else {}

            return self.success(
                data=data,
                status_code=response.status,
            )

        except Exception as e:
            log.exception("Unexpected error during Jira attachment upload")
            return self.failure(str(e))

    def add_jira_attachments(
        self,
        issue_key: str,
        file_paths: list[str],
    ):
        """
        Attach multiple files to a Jira issue.

        Args:
            issue_key: Jira issue key.
            file_paths: List of file paths.

        Returns:
            dict: Standard service response containing all attachment
            upload responses.
        """

        results = []

        for file_path in file_paths:
            result = self.add_jira_attachment(
                issue_key=issue_key,
                file_path=file_path,
            )

            results.append(result)

            if not result["success"]:
                return self.failure(
                    error=result["error"],
                    status_code=result["status_code"],
                    data=results,
                )

        return self.success(data=results)

    def get_jira_issue_detail(
        self,
        issue_key: str,
        fields: list[str] | None = None,
        expand: list[str] | None = None,
    ):
        """
        Fetch a single Jira issue with an explicit fields/expand selection.

        Used for on-demand tab data (comments, attachments, history) that
        the bulk /search endpoint used elsewhere in this service can't
        provide — history in particular requires expand=changelog, which
        /search does not support per-issue the way the single-issue GET does.

        Returns:
            dict: Standard service response containing the raw Jira issue
            payload (fields/changelog un-normalized).
        """

        params = {}

        if fields:
            params["fields"] = ",".join(fields)

        if expand:
            params["expand"] = ",".join(expand)

        return self.jira_request(
            method="GET",
            endpoint=f"/rest/api/2/issue/{issue_key}",
            params=params or None,
            raise_error=False,
        )

    def get_jira_issue_comments(self, issue_key: str):
        """
        Fetch and normalize comments for a single Jira issue.

        Returns:
            dict: Standard service response containing a list of
            {id, author, body, created, updated} comment objects.
        """

        result = self.get_jira_issue_detail(issue_key, fields=["comment"])

        if not result["success"]:
            return result

        fields = (result["data"] or {}).get("fields", {}) or {}
        raw_comments = ((fields.get("comment") or {}).get("comments")) or []

        comments = [
            {
                "id": c.get("id"),
                "author": self.get_jira_field_value({"author": c.get("author")}, "author"),
                "body": c.get("body", ""),
                "created": c.get("created"),
                "updated": c.get("updated"),
            }
            for c in raw_comments
        ]

        return self.success(data=comments, status_code=result.get("status_code"))

    def add_jira_comment(self, issue_key: str, comment: str) -> dict:
    """Post a new comment to an existing Jira issue."""
    return self.jira_request(
        method="POST",
        endpoint=f"/rest/api/2/issue/{issue_key}/comment",
        payload={"body": comment}
    )

    def get_jira_issue_attachments(self, issue_key: str):
        """
        Fetch and normalize attachment metadata for a single Jira issue.

        Note: does not return attachment bytes/content — only metadata
        (including the id used by download_attachment_content to stream
        the file separately).

        Returns:
            dict: Standard service response containing a list of
            {id, filename, author, created, size, mime_type} objects.
        """

        result = self.get_jira_issue_detail(issue_key, fields=["attachment"])

        if not result["success"]:
            return result

        fields = (result["data"] or {}).get("fields", {}) or {}
        raw_attachments = fields.get("attachment") or []

        attachments = [
            {
                "id": a.get("id"),
                "filename": a.get("filename"),
                "author": self.get_jira_field_value({"author": a.get("author")}, "author"),
                "created": a.get("created"),
                "size": a.get("size"),
                "mime_type": a.get("mimeType"),
            }
            for a in raw_attachments
        ]

        return self.success(data=attachments, status_code=result.get("status_code"))

    def get_jira_issue_history(self, issue_key: str):
        """
        Fetch and normalize the change history (changelog) for a single
        Jira issue.

        Requires expand=changelog on the single-issue GET — this is not
        available via the bulk /search endpoint, so history is always a
        dedicated per-issue call regardless of how the issue was originally
        listed.

        Returns:
            dict: Standard service response containing a list of
            {id, author, created, items: [{field, from, to}]} entries,
            most recent first.
        """

        result = self.get_jira_issue_detail(
            issue_key,
            fields=["created"],
            expand=["changelog"],
        )

        if not result["success"]:
            return result

        data = result["data"] or {}
        histories = ((data.get("changelog") or {}).get("histories")) or []

        history = [
            {
                "id": h.get("id"),
                "author": self.get_jira_field_value({"author": h.get("author")}, "author"),
                "created": h.get("created"),
                "items": [
                    {
                        "field": item.get("field"),
                        "from": item.get("fromString"),
                        "to": item.get("toString"),
                    }
                    for item in (h.get("items") or [])
                ],
            }
            for h in histories
        ]

        history.reverse()  # most recent change first

        return self.success(data=history, status_code=result.get("status_code"))

    def download_attachment_content(self, attachment_id: str):
        """
        Fetch raw attachment bytes from Jira by attachment id.

        Bypasses jira_request() (which always JSON-decodes the response
        body) since attachment content is binary — mirrors the raw-request
        pattern add_jira_attachment already uses for uploads. The route
        layer streams this back to the browser rather than exposing the
        Jira token or Jira's own attachment URL to the client.

        Returns:
            dict: Standard service response with data = {content: bytes,
            content_type: str} on success.
        """

        try:
            base_url = self._session["base_url"]
            http = self._session["http"]

            url = f"{base_url}/rest/api/2/attachment/content/{attachment_id}"

            headers = {
                "Authorization": self._session["headers"]["Authorization"],
                "Accept": "*/*",
            }

            response = http.request(
                "GET",
                url,
                headers=headers,
                retries=False,
            )

            if response.status < 200 or response.status >= 300:
                return self.failure(
                    error=f"Attachment download failed: {response.status}",
                    status_code=response.status,
                )

            content_type = response.headers.get("Content-Type", "application/octet-stream")

            return self.success(
                data={"content": response.data, "content_type": content_type},
                status_code=response.status,
            )

        except Exception as e:
            log.exception("Unexpected error during Jira attachment download")
            return self.failure(str(e))

    def get_jira_field_value(
        self,
        fields: dict,
        field_name: str,
        pick: str | None = None,
        default="",
        list_separator=" | ",
    ):
        """
        Extract and normalize a Jira field value.

        Handles simple values, nested objects, and lists. Optionally
        selects a specific attribute (e.g., displayName, name).

        Args:
            fields: Jira issue fields dictionary.
            field_name: Field name to retrieve.
            pick: Optional attribute to extract.
            default: Default value if field is missing.
            list_separator: Separator for list values.

        Returns:
            Any: Normalized field value.

        Raises:
            ValueError: If an invalid pick value is provided.
        """

        value = fields.get(field_name)

        if value is None:
            return default

        allowed_pick_keys = {
            "displayName",
            "emailAddress",
            "name",
            "value",
            "key",
            "id",
        }

        if pick is not None and pick not in allowed_pick_keys:
            raise ValueError(
                f"Invalid pick value: {pick}. "
                f"Allowed values are: {', '.join(sorted(allowed_pick_keys))}"
            )

        default_priority = [
            "displayName",
            "value",
            "name",
            "key",
            "id",
            "emailAddress",
        ]

        def extract_from_dict(item: dict):
            if pick:
                return item.get(pick, default)

            for key in default_priority:
                if item.get(key) is not None:
                    return item.get(key)

            return default

        if isinstance(value, dict):
            return extract_from_dict(value)

        if isinstance(value, list):
            values = []

            for item in value:
                if isinstance(item, dict):
                    item_value = extract_from_dict(item)
                else:
                    item_value = item

                if item_value is not None and item_value != "":
                    values.append(str(item_value))

            return values

        return value

    def map_issue(
        self,
        issue: dict,
        field_map: dict | None = None,
    ) -> dict:
        fields = issue.get("fields", {})

        if field_map is None:
            issue_type = (fields.get("issuetype") or {}).get("name")
            field_map = get_map(issue_type)

        result = {
            "key": issue.get("key")
        }

        for out_field, (jira_field, pick) in field_map.items():

            if jira_field == "issuelinks":
                result[out_field] = self.get_jira_issue_links(fields)
                continue

            result[out_field] = self.get_jira_field_value(
                fields=fields,
                field_name=jira_field,
                pick=pick,
            )

        return result

    def map_issues(
        self,
        issues: list[dict],
        field_map: dict | None = None,
    ) -> list[dict]:
        return [
            self.map_issue(issue, field_map)
            for issue in issues
        ]

    def _derive_fields(self, field_map: dict) -> list[str]:
        fields = {
            jira_field
            for jira_field, _ in field_map.values()
        }

        fields.add("issuetype")

        return list(fields)

    def _derive_all_fields(self) -> list[str]:
        from app.services.jira_mappings import (
            BASE_ISSUE_MAP,
            ISSUE_TYPE_MAPS,
        )

        fields = {
            jira_field
            for jira_field, _ in BASE_ISSUE_MAP.values()
        }

        for issue_map in ISSUE_TYPE_MAPS.values():
            for jira_field, _ in issue_map.values():
                fields.add(jira_field)

        fields.add("issuetype")

        return list(fields)

    def _filter_output_fields(
        self,
        issues: list[dict],
        output_fields: list[str],
    ) -> list[dict]:
        return [
            {
                field: issue.get(field, "")
                for field in output_fields
            }
            for issue in issues
        ]

    def get_jira_issue_links(
        self,
        fields: dict,
    ) -> list[dict]:
        """
        Extract linked Jira issues from the issuelinks field.

        Returns a normalized list of linked issue objects.
        """

        links = fields.get("issuelinks") or []

        results = []

        for link in links:
            link_type = link.get("type") or {}

            linked_issue = (
                link.get("outwardIssue")
                or link.get("inwardIssue")
            )

            if not linked_issue:
                continue

            linked_fields = linked_issue.get("fields", {}) or {}

            results.append({
                "id": linked_issue.get("id"),
                "key": linked_issue.get("key"),
                # RD "self": linked_issue.get("self"),
                "direction": (
                    "outward"
                    if link.get("outwardIssue")
                    else "inward"
                ),
                # RD "link_type": link_type.get("name"),
                "relationship": (
                    link_type.get("outward")
                    if link.get("outwardIssue")
                    else link_type.get("inward")
                ),
                # RD "summary": linked_fields.get("summary", ""),
                "status": self.get_jira_field_value(
                    linked_fields,
                    field_name="status",
                    pick="name",
                ),
                "issue_type": self.get_jira_field_value(
                    linked_fields,
                    field_name="issuetype",
                    pick="name",
                ),
            })

        return results

    def get_jira_userobject_using_email(
        self,
        email_address: str,
        max_results: int = 50,
    ):
        """
        Search Jira user object by email address.

        Returns:
            dict: Standard service response containing one Jira user object.
        """

        try:
            if not email_address or not email_address.strip():
                return self.failure("email_address cannot be empty")

            email_address = email_address.strip().lower()

            result = self.jira_request(
                method="GET",
                endpoint="/rest/api/2/user/search",
                params={
                    "username": email_address,
                    "maxResults": max_results,
                    "includeActive": "true",
                },
                raise_error=False,
            )

            if not result["success"]:
                return result

            users = result["data"] or []
            if not isinstance(users, list):
                return self.failure(
                    error="Unexpected Jira user search response",
                    status_code=result.get("status_code"),
                    data=users,
                )

            exact_user = next(
                (
                    user
                    for user in users
                    if (user.get("emailAddress") or "").lower()
                    == email_address
                ),
                None,
            )

            if exact_user:
                return self.success(
                    data=exact_user,
                    status_code=result.get("status_code"),
                )

            if len(users) == 1:
                return self.success(
                    data=users[0],
                    status_code=result.get("status_code"),
                )

            return self.failure(
                error=f"No exact Jira user found for emailAddress: {email_address}",
                status_code=result.get("status_code"),
                data=users,
            )

        except Exception as e:
            log.exception("Unexpected error during Jira user lookup")
            return self.failure(str(e))

    def get_jira_user_identifier_by_email(
        self,
        email_address: str,
        identifier: str = "name",
    ):
        """
        Get a reusable Jira user identifier object by email address.

        Example returns:
            {"name": "abc123"}
            {"accountId": "abc123"}
            {"key": "abc123"}

        Args:
            email_address: User email address.
            identifier: Jira user identifier to return.
                        Usually name, key, or accountId.

        Returns:
            dict: Standard service response containing a Jira user
                  identifier object.
        """

        try:
            allowed_identifiers = {
                "name",
                "key",
                "accountId",
            }

            if identifier not in allowed_identifiers:
                return self.failure(
                    f"Invalid identifier: {identifier}. "
                    f"Allowed values are: "
                    f"{', '.join(sorted(allowed_identifiers))}"
                )

            user_result = self.get_jira_userobject_using_email(
                email_address
            )

            if not user_result["success"]:
                return user_result

            user = user_result["data"] or {}

            if not user.get(identifier):
                return self.failure(
                    error=(
                        f"Jira user found, but "
                        f"'{identifier}' was not available"
                    ),
                    data=user,
                )

            return self.success(
                data={identifier: user[identifier]},
                status_code=user_result.get("status_code"),
            )

        except Exception as e:
            log.exception("Unexpected error while building Jira user identifier")
            return self.failure(str(e))

    # Helpers to format any text to Jira markup, I might need the following in the future.

    def escape_jira_markup(self, value) -> str:
        """
        Escapes user/data values so they don't accidentally break Jira wiki markup.
        Use this for dynamic values, not for the markup you intentionally create.
        """

        if value is None:
            return ""

        text = str(value)

        chars_to_escape = [
            "\\", "*", "_", "-", "+", "^", "~",
            "{", "}", "[", "]", "|", "!"
        ]

        for ch in chars_to_escape:
            text = text.replace(ch, f"\\{ch}")

        return text

    def jira_bold(self, value) -> str:
        return f"*{self.escape_jira_markup(value)}*"

    def jira_italic(self, value) -> str:
        return f"_{self.escape_jira_markup(value)}_"

    def jira_heading(self, level: int, text: str) -> str:
        level = max(1, min(level, 6))
        return f"h{level}. {self.escape_jira_markup(text)}"

    def jira_bullet(self, value) -> str:
        return f"* {self.escape_jira_markup(value)}"

    def jira_link(self, label: str, url: str) -> str:
        return (
            f"[{self.escape_jira_markup(label)}|"
            f"{self.escape_jira_markup(url)}]"
        )

    def jira_code_block(
        self,
        value: str,
        language: str | None = None,
    ) -> str:
        lang = f"{{{language}}}" if language else ""
        return f"{{code:{lang}}}\n{value or ''}\n{{code}}"

    def build_jira_description(self, data: dict) -> str:
        """
        Description is already converted to Jira wiki markup by the frontend.
        Do not escape it here.
        """

        if not data:
            return ""

        return self.normalize_jira_markup(
            data.get("description")
        )

    def build_jira_acceptancecriteria(self, data: dict) -> str:
        """
        Acceptance criteria is already converted to Jira wiki markup
        by the frontend.
        Do not escape it here.
        """

        if not data:
            return ""

        return self.normalize_jira_markup(
            data.get("acceptancecriteria")
        )

    def normalize_jira_markup(self, value) -> str:
        """
        Normalizes Jira wiki markup generated by the UI.

        Important:
        - This does not escape markup.
        - This keeps intentional Jira formatting like *, _, #,
          and bullet lists.
        - This helps prevent list markup from being glued to
          previous text.
        """

        if value is None:
            return ""

        text = (
            str(value)
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )

        # Fix common issue where a numbered/bullet list gets glued
        # to prior text.
        #
        # Example: *This is BOLD:*# One
        # Becomes:
        # *This is BOLD:*
        #
        # # One

        text = text.replace("*#", "*\n\n#")
        text = text.replace("**#", "**\n\n#")

        # Normalize excessive blank lines
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")

        return text.strip()

    def get_jira_issue_transitions(
        self,
        issue_key: str,
    ):
        """
        Get available workflow transitions for a Jira issue.
        """

        return self.jira_request(
            method="GET",
            endpoint=f"/rest/api/2/issue/{issue_key}/transitions",
            raise_error=False,
        )

    def transition_jira_issue_by_name(
        self,
        issue_key: str,
        transition_names: list[str],
        comment: str | None = None,
    ):
        """
        Transition a Jira issue using the first matching transition name.

        Example transition names:
            ["Cancel", "Cancelled", "Canceled", "Close", "Done"]
        """

        transitions_result = self.get_jira_issue_transitions(issue_key)

        if not transitions_result["success"]:
            return transitions_result

        transitions = (
            transitions_result.get("data", {})
            .get("transitions", [])
        )

        transition_match = None
        transition_names_lower = {
            name.lower()
            for name in transition_names
        }

        for transition in transitions:
            transition_name = str(
                transition.get("name", "")
            ).lower()

            if transition_name in transition_names_lower:
                transition_match = transition
                break

        if not transition_match:
            available = [
                t.get("name")
                for t in transitions
            ]

            return self.failure(
                error=(
                    f"No matching Jira transition found for "
                    f"{issue_key}. "
                    f"Requested={transition_names}. "
                    f"Available={available}"
                ),
                data={
                    "available_transitions": available,
                },
            )

        payload = {
            "transition": {
                "id": transition_match["id"],
            }
        }

        if comment:
            payload["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": comment,
                        }
                    }
                ]
            }

        return self.jira_request(
            method="POST",
            endpoint=f"/rest/api/2/issue/{issue_key}/transitions",
            payload=payload,
            raise_error=False,
        )

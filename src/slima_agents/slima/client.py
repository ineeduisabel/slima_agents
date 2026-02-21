"""Async HTTP client for the Slima REST API."""

from __future__ import annotations

from typing import Any

import httpx

from .types import (
    Book,
    Commit,
    McpFileAppendResponse,
    McpFileCreateResponse,
    McpFileDeleteResponse,
    McpFileReadResponse,
    McpFileUpdateResponse,
    McpSearchResponse,
)


class SlimaApiError(Exception):
    def __init__(self, status: int, code: str | None = None, message: str | None = None):
        self.status = status
        self.code = code
        super().__init__(message or f"Slima API error {status}")


class AuthenticationError(SlimaApiError):
    pass


class NotFoundError(SlimaApiError):
    pass


class SlimaClient:
    """Async client for Slima REST API, mirroring the TypeScript SlimaApiClient."""

    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "slima-agents/0.1.0",
            },
            timeout=60.0,
        )

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        resp = await self._client.request(method, path, json=body)
        if not resp.is_success:
            await self._handle_error(resp)
        data = resp.json()
        return data.get("data", data)

    async def _handle_error(self, resp: httpx.Response) -> None:
        try:
            error_data = resp.json()
            code = error_data.get("error", {}).get("code")
            message = error_data.get("error", {}).get("message")
        except Exception:
            code, message = None, None

        if resp.status_code == 401:
            raise AuthenticationError(resp.status_code, code, message or "Authentication failed")
        if resp.status_code == 404:
            raise NotFoundError(resp.status_code, code, message or "Not found")
        raise SlimaApiError(resp.status_code, code, message)

    # === Book Operations ===

    async def list_books(self) -> list[Book]:
        data = await self._request("GET", "/api/v1/books")
        return [Book.model_validate(b) for b in data]

    async def get_book(self, token: str) -> Book:
        data = await self._request("GET", f"/api/v1/books/{token}")
        return Book.model_validate(data)

    async def create_book(
        self,
        title: str,
        author_name: str | None = None,
        description: str | None = None,
    ) -> Book:
        data = await self._request(
            "POST",
            "/api/v1/books",
            {"book": {"title": title, "author_name": author_name, "description": description}},
        )
        return Book.model_validate(data)

    # === Version Control ===

    async def list_commits(self, book_token: str, limit: int = 10) -> list[Commit]:
        data = await self._request("GET", f"/api/v1/books/{book_token}/commits?limit={limit}")
        commits = data.get("commits", data) if isinstance(data, dict) else data
        return [Commit.model_validate(c) for c in commits]

    # === MCP File Operations ===

    async def create_file(
        self,
        book_token: str,
        path: str,
        content: str = "",
        commit_message: str | None = None,
    ) -> McpFileCreateResponse:
        data = await self._request(
            "POST",
            f"/api/v1/books/{book_token}/mcp/files/create",
            {"path": path, "content": content, "commit_message": commit_message},
        )
        return McpFileCreateResponse.model_validate(data)

    async def read_file(self, book_token: str, path: str) -> McpFileReadResponse:
        data = await self._request(
            "POST",
            f"/api/v1/books/{book_token}/mcp/files/read",
            {"path": path},
        )
        return McpFileReadResponse.model_validate(data)

    async def write_file(
        self,
        book_token: str,
        path: str,
        content: str,
        commit_message: str | None = None,
    ) -> McpFileUpdateResponse:
        data = await self._request(
            "POST",
            f"/api/v1/books/{book_token}/mcp/files/update",
            {"path": path, "content": content, "commit_message": commit_message},
        )
        return McpFileUpdateResponse.model_validate(data)

    async def delete_file(
        self,
        book_token: str,
        path: str,
        commit_message: str | None = None,
    ) -> McpFileDeleteResponse:
        data = await self._request(
            "POST",
            f"/api/v1/books/{book_token}/mcp/files/delete",
            {"path": path, "commit_message": commit_message},
        )
        return McpFileDeleteResponse.model_validate(data)

    async def append_to_file(
        self,
        book_token: str,
        path: str,
        content: str,
        commit_message: str | None = None,
    ) -> McpFileAppendResponse:
        data = await self._request(
            "POST",
            f"/api/v1/books/{book_token}/mcp/files/append",
            {"path": path, "content": content, "commit_message": commit_message},
        )
        return McpFileAppendResponse.model_validate(data)

    async def search_files(
        self,
        book_token: str,
        query: str,
        file_types: list[str] | None = None,
        limit: int | None = None,
    ) -> McpSearchResponse:
        body: dict[str, Any] = {"query": query}
        if file_types:
            body["file_types"] = file_types
        if limit:
            body["limit"] = limit
        data = await self._request(
            "POST",
            f"/api/v1/books/{book_token}/mcp/files/search",
            body,
        )
        return McpSearchResponse.model_validate(data)

    async def get_book_structure(self, book_token: str) -> list[dict]:
        """Get the file/folder tree of a book via the latest commit's filesSnapshot."""
        commits = await self.list_commits(book_token, limit=1)
        if not commits:
            return []
        return [fs.model_dump() for fs in commits[0].files_snapshot]

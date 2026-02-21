"""Tests for the Slima API client using respx to mock HTTP."""

from __future__ import annotations

import pytest
import httpx
import respx

from slima_agents.slima.client import SlimaClient, AuthenticationError, NotFoundError


BASE_URL = "https://test.slima.app"
TOKEN = "test-token-123"


@pytest.fixture
def client():
    return SlimaClient(BASE_URL, TOKEN)


@respx.mock
@pytest.mark.asyncio
async def test_list_books(client: SlimaClient):
    respx.get(f"{BASE_URL}/api/v1/books").mock(
        return_value=httpx.Response(200, json={
            "data": [
                {
                    "token": "bk_1",
                    "title": "Test Book",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "updatedAt": "2024-01-01T00:00:00Z",
                }
            ]
        })
    )

    books = await client.list_books()
    assert len(books) == 1
    assert books[0].token == "bk_1"
    assert books[0].title == "Test Book"


@respx.mock
@pytest.mark.asyncio
async def test_create_book(client: SlimaClient):
    respx.post(f"{BASE_URL}/api/v1/books").mock(
        return_value=httpx.Response(200, json={
            "data": {
                "token": "bk_new",
                "title": "New Book",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
            }
        })
    )

    book = await client.create_book("New Book", description="A test book")
    assert book.token == "bk_new"
    assert book.title == "New Book"


@respx.mock
@pytest.mark.asyncio
async def test_create_file(client: SlimaClient):
    respx.post(f"{BASE_URL}/api/v1/books/bk_1/mcp/files/create").mock(
        return_value=httpx.Response(200, json={
            "data": {
                "commit": {
                    "token": "cm_1",
                    "name": "commit-1",
                    "commitType": "auto",
                    "fileCount": 1,
                    "totalWordCount": 10,
                    "manuscriptWordCount": 10,
                    "createdAt": "2024-01-01T00:00:00Z",
                    "filesSnapshot": [],
                },
                "fileToken": "fl_1",
            }
        })
    )

    resp = await client.create_file("bk_1", "test.md", "# Hello", "Initial commit")
    assert resp.file_token == "fl_1"
    assert resp.commit.token == "cm_1"


@respx.mock
@pytest.mark.asyncio
async def test_read_file(client: SlimaClient):
    respx.post(f"{BASE_URL}/api/v1/books/bk_1/mcp/files/read").mock(
        return_value=httpx.Response(200, json={
            "data": {
                "file": {
                    "token": "fl_1",
                    "name": "test.md",
                    "path": "test.md",
                    "kind": "file",
                    "wordCount": 5,
                },
                "content": "# Hello World",
            }
        })
    )

    resp = await client.read_file("bk_1", "test.md")
    assert resp.content == "# Hello World"
    assert resp.file.name == "test.md"


@respx.mock
@pytest.mark.asyncio
async def test_auth_error(client: SlimaClient):
    respx.get(f"{BASE_URL}/api/v1/books").mock(
        return_value=httpx.Response(401, json={
            "error": {"code": "unauthorized", "message": "Invalid token"}
        })
    )

    with pytest.raises(AuthenticationError):
        await client.list_books()


@respx.mock
@pytest.mark.asyncio
async def test_not_found_error(client: SlimaClient):
    respx.get(f"{BASE_URL}/api/v1/books/bk_missing").mock(
        return_value=httpx.Response(404, json={
            "error": {"code": "not_found", "message": "Book not found"}
        })
    )

    with pytest.raises(NotFoundError):
        await client.get_book("bk_missing")


@respx.mock
@pytest.mark.asyncio
async def test_search_files(client: SlimaClient):
    respx.post(f"{BASE_URL}/api/v1/books/bk_1/mcp/files/search").mock(
        return_value=httpx.Response(200, json={
            "data": {
                "matches": [
                    {
                        "file": {
                            "token": "fl_1",
                            "name": "test.md",
                            "path": "test.md",
                            "kind": "file",
                            "wordCount": 5,
                        },
                        "snippets": [{"text": "hello", "highlightStart": 0, "highlightEnd": 5}],
                        "matchCount": 1,
                    }
                ],
                "query": "hello",
            }
        })
    )

    resp = await client.search_files("bk_1", "hello")
    assert len(resp.matches) == 1
    assert resp.query == "hello"

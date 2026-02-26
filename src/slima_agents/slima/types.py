"""Pydantic models for Slima API responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Book(BaseModel):
    token: str
    title: str
    author_name: str | None = Field(None, alias="authorName")
    description: str | None = None
    language: str | None = None
    total_word_count: int | None = Field(None, alias="totalWordCount")
    manuscript_word_count: int | None = Field(None, alias="manuscriptWordCount")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    deleted_at: str | None = Field(None, alias="deletedAt")

    model_config = {"populate_by_name": True}


class FileSnapshot(BaseModel):
    token: str
    name: str
    kind: str
    blob_hash: str | None = Field(None, alias="blobHash")
    word_count: int | None = Field(None, alias="wordCount")
    is_manuscript: bool | None = Field(None, alias="isManuscript")
    parent_token: str | None = Field(None, alias="parentToken")
    position: int
    children: list[FileSnapshot] | None = None

    model_config = {"populate_by_name": True}


class Commit(BaseModel):
    token: str
    parent_token: str | None = Field(None, alias="parentToken")
    name: str
    message: str | None = None
    commit_type: str = Field(alias="commitType")
    file_count: int = Field(alias="fileCount")
    total_word_count: int = Field(alias="totalWordCount")
    manuscript_word_count: int = Field(alias="manuscriptWordCount")
    created_at: str = Field(alias="createdAt")
    files_snapshot: list[FileSnapshot] = Field(default_factory=list, alias="filesSnapshot")

    model_config = {"populate_by_name": True}


class McpFile(BaseModel):
    token: str
    name: str
    path: str
    kind: str
    file_type: str | None = Field(None, alias="fileType")
    word_count: int = Field(alias="wordCount")
    blob_hash: str | None = Field(None, alias="blobHash")

    model_config = {"populate_by_name": True}


class McpFileReadResponse(BaseModel):
    file: McpFile
    content: str


class McpFileCreateResponse(BaseModel):
    commit: Commit
    file_token: str = Field(alias="fileToken")

    model_config = {"populate_by_name": True}


class McpFileUpdateResponse(BaseModel):
    commit: Commit


class McpFileDeleteResponse(BaseModel):
    commit: Commit


class McpFileAppendResponse(BaseModel):
    commit: Commit


class McpSearchMatch(BaseModel):
    file: McpFile
    snippets: list[dict]
    match_count: int = Field(alias="matchCount")

    model_config = {"populate_by_name": True}


class McpSearchResponse(BaseModel):
    matches: list[McpSearchMatch]
    query: str

"""Types for the subset of LINE Flex components emitted by this library."""

from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict


class _SpanRequired(TypedDict):
    type: Literal["span"]
    text: str


class FlexSpan(_SpanRequired, total=False):
    color: str
    size: str
    weight: Literal["regular", "bold"]
    style: Literal["normal", "italic"]
    decoration: Literal["none", "underline", "line-through"]


class URIAction(TypedDict):
    type: Literal["uri"]
    uri: str


class _TextRequired(TypedDict):
    type: Literal["text"]


class FlexText(_TextRequired, total=False):
    text: str
    contents: list[FlexSpan]
    wrap: bool
    margin: str
    size: str
    weight: Literal["regular", "bold"]
    color: str
    align: Literal["start", "end", "center"]
    gravity: Literal["top", "bottom", "center"]
    flex: int
    action: URIAction


class _BoxRequired(TypedDict):
    type: Literal["box"]
    layout: Literal["vertical", "horizontal", "baseline"]
    contents: list[FlexComponent]


class FlexBox(_BoxRequired, total=False):
    spacing: str
    margin: str
    paddingAll: str
    paddingStart: str
    backgroundColor: str
    cornerRadius: str
    width: str
    flex: int
    alignItems: Literal["flex-start", "flex-end", "center"]


FlexComponent: TypeAlias = FlexBox | FlexText


class FlexBubble(TypedDict):
    type: Literal["bubble"]
    size: Literal["giga"]
    body: FlexBox


class FlexMessage(TypedDict):
    type: Literal["flex"]
    altText: str
    contents: FlexBubble

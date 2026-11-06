"""
A helper for GraphQL connection

---

MIT License

Copyright (c) 2019-2022 naoTimesdev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import inspect
import logging
import traceback
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, cast

import aiohttp

from ..utils import AttributeDict, complex_walk
from ..version import __version__

__all__ = ("GraphQLClient", "GraphQLPaginationInfo", "GraphQLResult")
ResultT = TypeVar("ResultT", bound="AttributeDict")
PredicateReturn = tuple[bool, Any | None, str | None]
PredicateFunc = Callable[[ResultT | None], PredicateReturn | Awaitable[PredicateReturn]]


@dataclass
class GraphQLErrorLocation:
    line: int
    column: int


@dataclass
class GraphQLError:
    message: str
    location: GraphQLErrorLocation | None = None
    code: str | None = None


@dataclass
class GraphQLResult(Generic[ResultT]):
    query: str
    operationName: str | None
    data: ResultT | None = None
    errors: list[GraphQLError] = field(default_factory=list)
    httpcode: int | None = None


@dataclass
class GraphQLPaginationInfo:
    hasMore: bool = False
    nextCursor: Any | None = None


class GraphQLClient(Generic[ResultT]):
    def __init__(self, endpoint: str, session: aiohttp.ClientSession | None = None):
        self.endpoint = endpoint
        self.logger = logging.getLogger("http.GraphQLClient")

        self._outside_session = True
        if session is None:
            self._outside_session = False
            self._sesi = aiohttp.ClientSession(
                headers={"User-Agent": f"naoTimes/v{__version__} (https://github.com/naoTimesdev/naoTimes)"}
            )
        else:
            self._sesi = session

    def _convert_data(self, data: Any) -> ResultT | None:
        if not isinstance(data, dict):
            return None
        return cast(ResultT, AttributeDict(data))

    async def query(
        self, query: str, variables: dict = {}, operation_name: str | None = None
    ) -> GraphQLResult[ResultT]:
        """Send query to the GraphQL API and get the result

        :param query: The query
        :type query: str
        :param variables: The variables, defaults to {}
        :type variables: dict, optional
        :param operation_name: The operation name, defaults to None
        :type operation_name: str, optional
        :return: The request result
        :rtype: GraphQLResult
        """
        query_send: dict[str, Any] = {"query": query}
        if len(variables.keys()) > 0:
            query_send["variables"] = variables
        if isinstance(operation_name, str) and len(operation_name.strip()) > 0:
            query_send["operationName"] = operation_name
        async with self._sesi.post(self.endpoint, json=query_send) as resp:
            try:
                json_data = await resp.json()
                get_data = complex_walk(json_data, "data")
                errors = complex_walk(json_data, "errors")
                if not isinstance(errors, list):
                    errors = []
                all_errors = []
                for error in errors:
                    if not isinstance(error, dict):
                        continue
                    raw_message = error.get("message", "")
                    msg = raw_message if isinstance(raw_message, str) else ""
                    error_loc = complex_walk(error, "locations.0")
                    if error_loc is not None:
                        location_data = error_loc if isinstance(error_loc, dict) else {}
                        raw_line = location_data.get("line", -1)
                        raw_column = location_data.get("column", -1)
                        line = raw_line if isinstance(raw_line, int) else -1
                        column = raw_column if isinstance(raw_column, int) else -1
                        error_loc = GraphQLErrorLocation(line, column)
                    stack_code = complex_walk(error, "extensions.code")
                    code = stack_code if isinstance(stack_code, str) else None
                    all_errors.append(GraphQLError(msg, error_loc, code))
                return GraphQLResult(query, operation_name, self._convert_data(get_data), all_errors, resp.status)
            except Exception:
                self.logger.error("An exception occured!\n%s", traceback.format_exc())
                return GraphQLResult(
                    query, operation_name, None, [GraphQLError("Failed to parse JSON file", code="50000")]
                )

    async def _execute_predicate(self, predicate: PredicateFunc, content: ResultT | None = None) -> PredicateReturn:
        """Execute the predicate function and return the result"""
        result = predicate(content)
        if inspect.isawaitable(result):
            return await cast(Awaitable[PredicateReturn], result)
        return result

    async def paginate(
        self, query: str, predicate: PredicateFunc, variables: dict = {}, operation_name: str | None = None
    ) -> AsyncGenerator[tuple[GraphQLResult[ResultT], GraphQLPaginationInfo]]:
        has_more, next_cursor, cursor_var = await self._execute_predicate(predicate, None)
        has_more = True
        while has_more:
            if next_cursor is not None and cursor_var is not None:
                variables[cursor_var] = next_cursor
            query_request = await self.query(query, variables, operation_name)
            if query_request.data is None:
                has_more = False
            else:
                has_more, next_cursor, _ = await self._execute_predicate(predicate, query_request.data)
            page_info = GraphQLPaginationInfo(has_more, next_cursor)
            yield query_request, page_info

    async def close(self):
        if not self._outside_session:
            await self._sesi.close()

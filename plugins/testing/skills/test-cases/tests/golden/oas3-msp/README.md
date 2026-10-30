# Test cases

4 entities · 10 operations · 416 cases (P1 68 / P2 216 / P3 132)

## health

| Kind | P1 | P2 | P3 |
|---|---|---|---|
| HAPPY_FULL | 1 | 0 | 0 |
| PUBLIC_REACHABLE | 1 | 0 | 0 |

## shapes

| Kind | P1 | P2 | P3 |
|---|---|---|---|
| HAPPY_FULL | 1 | 0 | 0 |
| MALFORMED_BODY | 0 | 2 | 0 |
| EMPTY_BODY | 0 | 1 | 0 |
| NOT_FOUND | 0 | 1 | 0 |
| AUTH_MISSING | 1 | 0 | 0 |
| AUTH_INVALID | 1 | 0 | 0 |
| WRONG_CONTENT_TYPE | 0 | 1 | 0 |

### Unsupported

- `createShape`: oneOf at #/components/schemas/Shape

## widgets

| Kind | P1 | P2 | P3 |
|---|---|---|---|
| HAPPY_FULL | 6 | 0 | 0 |
| HAPPY_MIN | 0 | 2 | 0 |
| OPTIONAL_ABSENT | 2 | 0 | 30 |
| REQUIRED_MISSING | 0 | 20 | 0 |
| LENGTH_INVALID | 0 | 4 | 0 |
| LENGTH_BOUNDARY_VALID | 0 | 0 | 12 |
| PATTERN_INVALID | 0 | 12 | 0 |
| RANGE_INVALID | 6 | 6 | 0 |
| RANGE_BOUNDARY_VALID | 10 | 0 | 14 |
| ENUM_INVALID | 0 | 6 | 0 |
| ENUM_EACH_VALID | 0 | 0 | 4 |
| ARRAY_BOUNDS | 0 | 6 | 4 |
| MALFORMED_BODY | 0 | 4 | 0 |
| EMPTY_BODY | 0 | 2 | 0 |
| NOT_FOUND | 0 | 10 | 0 |
| INVALID_ID_FORMAT | 0 | 4 | 0 |
| AUTH_MISSING | 6 | 0 | 0 |
| AUTH_INVALID | 6 | 0 | 0 |
| CROSS_TENANT | 4 | 0 | 0 |
| PAGINATION | 0 | 1 | 0 |
| INVALID_QUERY_PARAM | 0 | 7 | 0 |
| FORMAT_INVALID | 0 | 46 | 4 |
| TYPE_INVALID | 6 | 54 | 36 |
| UNKNOWN_FIELD | 0 | 2 | 0 |
| READONLY_SENT | 2 | 0 | 0 |
| WRONG_CONTENT_TYPE | 0 | 2 | 0 |
| RESOURCE_LIMIT | 0 | 2 | 24 |
| LIFECYCLE | 1 | 0 | 0 |
| DELETE_TWICE | 0 | 1 | 0 |

## parts

| Kind | P1 | P2 | P3 |
|---|---|---|---|
| HAPPY_FULL | 2 | 0 | 0 |
| REQUIRED_MISSING | 0 | 7 | 0 |
| LENGTH_INVALID | 0 | 1 | 0 |
| LENGTH_BOUNDARY_VALID | 0 | 0 | 2 |
| MALFORMED_BODY | 0 | 2 | 0 |
| EMPTY_BODY | 0 | 1 | 0 |
| NOT_FOUND | 0 | 3 | 0 |
| AUTH_MISSING | 2 | 0 | 0 |
| AUTH_INVALID | 2 | 0 | 0 |
| CROSS_TENANT | 1 | 0 | 0 |
| FORMAT_INVALID | 0 | 3 | 1 |
| TYPE_INVALID | 0 | 2 | 0 |
| MASS_ASSIGNMENT | 6 | 0 | 0 |
| WRONG_CONTENT_TYPE | 0 | 1 | 0 |
| RESOURCE_LIMIT | 0 | 0 | 1 |
| LIFECYCLE | 1 | 0 | 0 |

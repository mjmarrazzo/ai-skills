# Test cases

2 entities · 4 operations · 96 cases (P1 26 / P2 49 / P3 21)

## accounts

| Kind | P1 | P2 | P3 |
|---|---|---|---|
| HAPPY_FULL | 3 | 0 | 0 |
| HAPPY_MIN | 0 | 1 | 0 |
| OPTIONAL_ABSENT | 0 | 0 | 5 |
| REQUIRED_MISSING | 0 | 13 | 0 |
| LENGTH_INVALID | 0 | 2 | 0 |
| LENGTH_BOUNDARY_VALID | 0 | 0 | 4 |
| RANGE_INVALID | 0 | 1 | 0 |
| RANGE_BOUNDARY_VALID | 0 | 0 | 1 |
| MALFORMED_BODY | 0 | 4 | 0 |
| EMPTY_BODY | 0 | 2 | 0 |
| NOT_FOUND | 0 | 2 | 0 |
| INVALID_ID_FORMAT | 0 | 1 | 0 |
| AUTH_MISSING | 3 | 0 | 0 |
| AUTH_INVALID | 3 | 0 | 0 |
| FORMAT_INVALID | 0 | 8 | 0 |
| TYPE_INVALID | 0 | 12 | 7 |
| MASS_ASSIGNMENT | 11 | 0 | 0 |
| READONLY_SENT | 2 | 0 | 0 |
| WRONG_CONTENT_TYPE | 0 | 2 | 0 |
| RESOURCE_LIMIT | 0 | 0 | 4 |
| LIFECYCLE | 1 | 0 | 0 |

### Unsupported

- `postAccounts`: recursion at #/definitions/Node/properties/children/items

## accounts-notes

| Kind | P1 | P2 | P3 |
|---|---|---|---|
| HAPPY_FULL | 1 | 0 | 0 |
| NOT_FOUND | 0 | 1 | 0 |
| AUTH_MISSING | 1 | 0 | 0 |
| AUTH_INVALID | 1 | 0 | 0 |

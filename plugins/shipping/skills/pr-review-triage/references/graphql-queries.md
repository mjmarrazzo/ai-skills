# GraphQL queries and mutations for pr-review-triage

GitHub's REST API doesn't expose review-thread resolution state, and inline comments can't be resolved over REST. These GraphQL queries and mutations cover the gap. All run via `gh api graphql`.

## Fetch unresolved review threads + comments

```graphql
query ListReviewThreads($owner: String!, $name: String!, $num: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $num) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          isCollapsed
          path
          line
          originalLine
          comments(first: 50) {
            nodes {
              id
              databaseId
              author {
                login
                __typename
              }
              body
              path
              originalLine
              diffHunk
              url
              createdAt
              outdated
            }
          }
        }
      }
    }
  }
}
```

Invocation:

```bash
gh api graphql \
  -f query="$(cat list-threads.graphql)" \
  -F owner="$OWNER" -F name="$REPO" -F num=$PR_NUMBER
```

Field notes:
- `id` on `reviewThread` is the GraphQL node ID — needed for `resolveReviewThread`.
- `databaseId` on comment is the REST integer ID — needed for `POST /pulls/{num}/comments/{id}/replies`.
- `author.__typename == "Bot"` is the most reliable bot indicator (login-suffix `[bot]` is a convention, not enforced).
- `isOutdated` on the thread or `outdated` on the comment indicates the anchor line has moved; treat as stale.

## Resolve a review thread

```graphql
mutation ResolveThread($id: ID!) {
  resolveReviewThread(input: { threadId: $id }) {
    thread {
      id
      isResolved
    }
  }
}
```

Invocation:

```bash
gh api graphql \
  -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' \
  -F id="$THREAD_ID"
```

Returns `isResolved: true` on success. On failure (already resolved, insufficient permissions, thread not found), `gh api` exits non-zero — capture stderr and surface to user.

## Unresolve a review thread

Provided for completeness; not invoked by default.

```graphql
mutation UnresolveThread($id: ID!) {
  unresolveReviewThread(input: { threadId: $id }) {
    thread {
      id
      isResolved
    }
  }
}
```

## Add reply to an inline review thread (REST)

GraphQL has `addPullRequestReviewThreadReply`, but the REST equivalent is simpler and integrates with `gh api` more cleanly:

```bash
gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments/$COMMENT_DATABASE_ID/replies" \
  -f body="Fixed in $SHORT_SHA. <description>."
```

`$COMMENT_DATABASE_ID` is the `databaseId` from the GraphQL query above (or `id` from the REST `/pulls/{num}/comments` endpoint — same integer). Replies attach to the same thread as the original comment.

## Post a top-level PR conversation comment

For PR-conversation (issue-style) comments — these have no thread structure on GitHub:

```bash
gh api "repos/$OWNER/$REPO/issues/$PR_NUMBER/comments" \
  -f body="Re: @$ORIG_AUTHOR — fixed in $SHORT_SHA. <description>."
```

These can't be "resolved" — there's no thread state. The mention by `@login` is the back-reference.

## Get PR metadata for owner/repo/number

```bash
gh pr view --json url,number,state,headRefName,baseRefName,headRepository,headRepositoryOwner
```

Owner and repo for API URLs come from `headRepositoryOwner.login` and `headRepository.name`. For PRs from a fork, those differ from the base; review comments live on the **base** repo, so use:

```bash
gh repo view --json owner,name
```

for `$OWNER` / `$REPO` in the API calls above.

## Rate limiting

`gh api` respects the auth'd user's rate limit (5000/hour for typical users). A full triage cycle on a large PR uses roughly:
- 1 `gh pr view`
- 2 paginated REST list calls (inline + conversation comments)
- 1 GraphQL list query
- N reply POSTs (one per comment with a reply)
- M GraphQL resolve mutations (one per resolved thread)

For a PR with 30 comments, that's ~70 calls — well under the limit. No retry-with-backoff machinery needed; if a single call fails, surface and stop.

#!/bin/bash
# linear.sh status <ISSUE-ID> "<State name>" | comment <ISSUE-ID> "<text>" | list [project]
#           | create <project> "<title>" <description-file> [state]
#
# Zalo's Linear content board: one team, projects "Whiteboard YouTube" and "Reels",
# one issue per video. Team key: LINEAR_TEAM_KEY, else ~/.config/linear/team-key.
# States: Idea, Planned, Boards ready, Filmed, Editing, Scheduled, Published, Canceled.
# Ids and the issue per video: memory linear-content-board.md.
#
#   status  ABC-4 "Filmed"        move an issue to a state (name match ignores case)
#   comment ABC-4 "Board printed"  add a comment to an issue
#   list    [project]              the team's issues as id, state, project, title;
#                                  project filter is a case-insensitive substring
#   create  whiteboard "LF7: x" desc.md [Idea]
#                                  new team issue in the project matching the
#                                  substring, markdown description read from a
#                                  file, state by name (default: team default)
#
# The personal API key lives ONLY in ~/.config/linear/api-key (mode 600). It is
# read into a variable and handed to curl through a process substitution config
# (printf is a builtin), so it never appears in argv, in output or in a file.
# Exit: 0 ok, 1 API or network error, 2 usage or unknown issue/state.
set -uo pipefail

KEY_FILE="$HOME/.config/linear/api-key"
TEAM_FILE="$HOME/.config/linear/team-key"
API="https://api.linear.app/graphql"
TEAM_KEY=${LINEAR_TEAM_KEY:-$(tr -d '[:space:]' 2>/dev/null < "$TEAM_FILE")}

die() { echo "linear.sh: $*" >&2; exit "${2:-1}"; }
usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
need_team() { [ -n "$TEAM_KEY" ] || die "no team key: set LINEAR_TEAM_KEY or write it to $TEAM_FILE" 2; }

# gql <query> [variables-json]: prints the response body, or exits 1 on any error.
gql() {
  local key vars r
  vars=${2:-'{}'}
  [ -r "$KEY_FILE" ] || die "no key at $KEY_FILE"
  key=$(tr -d '\n' < "$KEY_FILE")
  r=$(jq -n --arg q "$1" --argjson v "$vars" '{query:$q, variables:$v}' |
    curl -sS --max-time 30 "$API" \
      -H 'Content-Type: application/json' \
      -K <(printf 'header = "Authorization: %s"\n' "$key") \
      --data-binary @-) || die "request to Linear failed"
  if ! printf '%s' "$r" | jq -e . >/dev/null 2>&1; then
    die "Linear returned a non JSON response"
  fi
  if printf '%s' "$r" | jq -e '.errors' >/dev/null; then
    printf '%s' "$r" | jq -r '.errors[] | "linear.sh: " + .message' >&2
    exit 1
  fi
  printf '%s' "$r"
}

cmd_status() {
  [ $# -eq 2 ] || usage
  local r state_id from to
  r=$(gql 'query($id: String!) { issue(id: $id) { id identifier state { name } team { states { nodes { id name type position } } } } }' \
    "$(jq -n --arg id "$1" '{id:$id}')") || exit 1
  state_id=$(printf '%s' "$r" | jq -r --arg s "$2" \
    '[.data.issue.team.states.nodes[] | select((.name | ascii_downcase) == ($s | ascii_downcase)) | .id][0] // empty')
  if [ -z "$state_id" ]; then
    echo "linear.sh: no state \"$2\" on $1's team. States:" >&2
    printf '%s' "$r" | jq -r '.data.issue.team.states.nodes
      | sort_by((.type as $t | ["triage","backlog","unstarted","started","completed","canceled","duplicate"] | index($t)), .position)[]
      | "  " + .name' >&2
    exit 2
  fi
  from=$(printf '%s' "$r" | jq -r '.data.issue.state.name')
  r=$(gql 'mutation($id: String!, $s: String!) { issueUpdate(id: $id, input: {stateId: $s}) { success issue { identifier state { name } } } }' \
    "$(jq -n --arg id "$1" --arg s "$state_id" '{id:$id, s:$s}')") || exit 1
  to=$(printf '%s' "$r" | jq -r '.data.issueUpdate.issue.state.name')
  printf '%s' "$r" | jq -e '.data.issueUpdate.success' >/dev/null || die "update not confirmed for $1"
  printf '%s: %s -> %s\n' "$(printf '%s' "$r" | jq -r '.data.issueUpdate.issue.identifier')" "$from" "$to"
}

cmd_comment() {
  [ $# -eq 2 ] || usage
  [ -n "$2" ] || die "empty comment" 2
  local r
  r=$(gql 'mutation($id: String!, $b: String!) { commentCreate(input: {issueId: $id, body: $b}) { success comment { url issue { identifier } } } }' \
    "$(jq -n --arg id "$1" --arg b "$2" '{id:$id, b:$b}')") || exit 1
  printf '%s' "$r" | jq -e '.data.commentCreate.success' >/dev/null || die "comment not confirmed for $1"
  printf '%s' "$r" | jq -r '.data.commentCreate.comment | "\(.issue.identifier): comment added \(.url)"'
}

cmd_list() {
  [ $# -le 1 ] || usage
  need_team
  local filter r after="" all='[]' page
  if [ $# -eq 1 ]; then
    filter=$(jq -n --arg t "$TEAM_KEY" --arg p "$1" '{team:{key:{eq:$t}}, project:{name:{containsIgnoreCase:$p}}}')
  else
    filter=$(jq -n --arg t "$TEAM_KEY" '{team:{key:{eq:$t}}}')
  fi
  while :; do
    r=$(gql 'query($f: IssueFilter, $a: String) { issues(filter: $f, first: 100, after: $a) { nodes { identifier number title state { name } project { name } } pageInfo { hasNextPage endCursor } } }' \
      "$(jq -n --argjson f "$filter" --arg a "$after" '{f:$f, a:(if $a == "" then null else $a end)}')") || exit 1
    page=$(printf '%s' "$r" | jq -c '.data.issues.nodes')
    all=$(jq -n --argjson a "$all" --argjson b "$page" '$a + $b')
    [ "$(printf '%s' "$r" | jq -r '.data.issues.pageInfo.hasNextPage')" = "true" ] || break
    after=$(printf '%s' "$r" | jq -r '.data.issues.pageInfo.endCursor')
  done
  printf '%s' "$all" | jq -r 'sort_by(.number)[] | [.identifier, .state.name, (.project.name // "-"), .title] | @tsv' |
    awk -F'\t' '{ printf "%-7s %-13s %-19s %s\n", $1, $2, $3, $4 }'
  [ "$(printf '%s' "$all" | jq 'length')" -gt 0 ] || echo "linear.sh: no issues matched" >&2
}

cmd_create() {
  [ $# -ge 3 ] && [ $# -le 4 ] || usage
  need_team
  [ -r "$3" ] || die "no description file at $3" 2
  local r team_id project_id state_id="" input
  r=$(gql 'query($t: String!, $p: String!) { teams(filter: {key: {eq: $t}}) { nodes { id states { nodes { id name } } } } projects(filter: {name: {containsIgnoreCase: $p}}) { nodes { id name } } }' \
    "$(jq -n --arg t "$TEAM_KEY" --arg p "$1" '{t:$t, p:$p}')") || exit 1
  team_id=$(printf '%s' "$r" | jq -r '.data.teams.nodes[0].id // empty')
  [ -n "$team_id" ] || die "team $TEAM_KEY not found" 2
  [ "$(printf '%s' "$r" | jq '.data.projects.nodes | length')" = "1" ] ||
    die "project \"$1\" must match exactly one project, matched: $(printf '%s' "$r" | jq -r '[.data.projects.nodes[].name] | join(", ")')" 2
  project_id=$(printf '%s' "$r" | jq -r '.data.projects.nodes[0].id')
  if [ $# -eq 4 ]; then
    state_id=$(printf '%s' "$r" | jq -r --arg s "$4" \
      '[.data.teams.nodes[0].states.nodes[] | select((.name | ascii_downcase) == ($s | ascii_downcase)) | .id][0] // empty')
    [ -n "$state_id" ] || die "no state \"$4\" on team $TEAM_KEY" 2
  fi
  input=$(jq -n --arg team "$team_id" --arg proj "$project_id" --arg title "$2" --rawfile d "$3" --arg st "$state_id" \
    '{teamId:$team, projectId:$proj, title:$title, description:$d} + (if $st == "" then {} else {stateId:$st} end)')
  r=$(gql 'mutation($i: IssueCreateInput!) { issueCreate(input: $i) { success issue { identifier url state { name } project { name } } } }' \
    "$(jq -n --argjson i "$input" '{i:$i}')") || exit 1
  printf '%s' "$r" | jq -e '.data.issueCreate.success' >/dev/null || die "create not confirmed for \"$2\""
  printf '%s' "$r" | jq -r '.data.issueCreate.issue | "\(.identifier)\t\(.state.name)\t\(.project.name)\t\(.url)"'
}

[ $# -ge 1 ] || usage
sub=$1; shift
case "$sub" in
  status)  cmd_status "$@" ;;
  comment) cmd_comment "$@" ;;
  list)    cmd_list "$@" ;;
  create)  cmd_create "$@" ;;
  *)       usage ;;
esac

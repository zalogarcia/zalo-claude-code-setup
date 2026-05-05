"use strict";

const fs = require("fs");
const path = require("path");

const ORCHESTRATOR_ROOT = path.resolve(__dirname, "..", "..");
const CONFIG_PATH = path.join(ORCHESTRATOR_ROOT, "config.json");
const LINEAR_ENDPOINT = "https://api.linear.app/graphql";

let _configCache = null;
let _stateCacheByTeam = Object.create(null); // teamId -> { name -> id, _all: [{id,name,type}] }
let _labelCacheByTeam = Object.create(null); // teamId -> { name -> id }

function loadConfig() {
  if (_configCache) return _configCache;
  let raw;
  try {
    raw = fs.readFileSync(CONFIG_PATH, "utf8");
  } catch (err) {
    // No config file — treat as no key.
    _configCache = {};
    return _configCache;
  }
  try {
    _configCache = JSON.parse(raw);
  } catch (err) {
    _configCache = {};
  }
  return _configCache;
}

function getEndpoint() {
  if (process.env.LINEAR_TEST_ENDPOINT) return process.env.LINEAR_TEST_ENDPOINT;
  return LINEAR_ENDPOINT;
}

function requireKey(cfg) {
  if (!cfg || !cfg.linear || !cfg.linear.apiKey) {
    throw new Error(
      "LINEAR_API_KEY not configured in config.json — Symphony idle",
    );
  }
}

function requireTeamId(cfg) {
  if (!cfg.linear.teamId) {
    throw new Error(
      "LINEAR_API_KEY not configured in config.json — Symphony idle",
    );
  }
  return cfg.linear.teamId;
}

async function gql(query, variables = {}) {
  const cfg = loadConfig();
  requireKey(cfg);
  const res = await fetch(getEndpoint(), {
    method: "POST",
    headers: {
      Authorization: cfg.linear.apiKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Linear API ${res.status}: ${text}`);
  }
  const json = await res.json();
  if (json.errors) {
    throw new Error("Linear: " + JSON.stringify(json.errors));
  }
  return json.data;
}

async function poll(label) {
  const cfg = loadConfig();
  requireKey(cfg);
  const teamId = requireTeamId(cfg);
  const query = `query Issues($filter: IssueFilter) {
  issues(filter: $filter, first: 50) {
    nodes {
      id
      title
      description
      state { name }
      project { name }
      team { id }
    }
  }
}`;
  const variables = {
    filter: {
      team: { id: { eq: teamId } },
      labels: { name: { eq: label } },
    },
  };
  const data = await gql(query, variables);
  const nodes = (data && data.issues && data.issues.nodes) || [];
  return nodes;
}

async function getTicket(ticketId) {
  const cfg = loadConfig();
  requireKey(cfg);
  const query = `query Issue($id: String!) {
  issue(id: $id) {
    id
    title
    description
    state { name }
    project { name }
    team { id }
  }
}`;
  const data = await gql(query, { id: ticketId });
  return data && data.issue;
}

async function getTeamWorkflowStates() {
  const cfg = loadConfig();
  requireKey(cfg);
  const teamId = requireTeamId(cfg);
  if (_stateCacheByTeam[teamId]) {
    return _stateCacheByTeam[teamId]._all;
  }
  const query = `query TeamStates($teamId: ID!) {
  workflowStates(filter: { team: { id: { eq: $teamId } } }, first: 100) {
    nodes { id name type }
  }
}`;
  const data = await gql(query, { teamId });
  const nodes =
    (data && data.workflowStates && data.workflowStates.nodes) || [];
  const map = Object.create(null);
  for (const n of nodes) map[n.name] = n.id;
  _stateCacheByTeam[teamId] = { _all: nodes };
  // attach name->id index alongside _all
  for (const k of Object.keys(map)) _stateCacheByTeam[teamId][k] = map[k];
  return nodes;
}

async function _resolveStateId(statusName) {
  const cfg = loadConfig();
  const teamId = requireTeamId(cfg);
  let cache = _stateCacheByTeam[teamId];
  if (!cache || !cache[statusName]) {
    delete _stateCacheByTeam[teamId];
    await getTeamWorkflowStates();
    cache = _stateCacheByTeam[teamId];
  }
  if (!cache || !cache[statusName]) {
    throw new Error(
      `Linear: workflow state not found for name "${statusName}"`,
    );
  }
  return cache[statusName];
}

async function transition(ticketId, statusName) {
  const cfg = loadConfig();
  requireKey(cfg);
  const stateId = await _resolveStateId(statusName);
  const mutation = `mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) { success }
}`;
  await gql(mutation, { id: ticketId, input: { stateId } });
}

async function commentPlan(ticketId, planMarkdown) {
  const cfg = loadConfig();
  requireKey(cfg);
  const mutation = `mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) { success comment { id url } }
}`;
  const data = await gql(mutation, {
    input: { issueId: ticketId, body: planMarkdown },
  });
  const url =
    data &&
    data.commentCreate &&
    data.commentCreate.comment &&
    data.commentCreate.comment.url;
  return { commentUrl: url };
}

async function comment(ticketId, text) {
  await commentPlan(ticketId, text);
}

async function _getLabelIdByName(labelName) {
  const cfg = loadConfig();
  const teamId = requireTeamId(cfg);
  let cache = _labelCacheByTeam[teamId];
  if (cache && Object.prototype.hasOwnProperty.call(cache, labelName)) {
    return cache[labelName];
  }
  const query = `query TeamLabels($teamId: ID!) {
  issueLabels(filter: { team: { id: { eq: $teamId } } }, first: 200) {
    nodes { id name }
  }
}`;
  const data = await gql(query, { teamId });
  const nodes = (data && data.issueLabels && data.issueLabels.nodes) || [];
  if (!_labelCacheByTeam[teamId])
    _labelCacheByTeam[teamId] = Object.create(null);
  for (const n of nodes) _labelCacheByTeam[teamId][n.name] = n.id;
  return _labelCacheByTeam[teamId][labelName];
}

async function label(ticketId, labelName) {
  const cfg = loadConfig();
  requireKey(cfg);
  const newId = await _getLabelIdByName(labelName);
  if (!newId) {
    process.stderr.write(
      `linear.label: label "${labelName}" not found — skipping\n`,
    );
    return;
  }
  // Fetch current labelIds on the issue
  const q = `query IssueLabels($id: String!) {
  issue(id: $id) { id labels { nodes { id } } }
}`;
  const data = await gql(q, { id: ticketId });
  const existing =
    (data && data.issue && data.issue.labels && data.issue.labels.nodes) || [];
  const ids = existing.map((n) => n.id);
  if (!ids.includes(newId)) ids.push(newId);
  const mutation = `mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) { success }
}`;
  await gql(mutation, { id: ticketId, input: { labelIds: ids } });
}

// Test-only: clear caches between scenarios.
function _resetCachesForTests() {
  _configCache = null;
  _stateCacheByTeam = Object.create(null);
  _labelCacheByTeam = Object.create(null);
}

module.exports = {
  poll,
  transition,
  commentPlan,
  comment,
  label,
  getTeamWorkflowStates,
  getTicket,
  _resetCachesForTests,
};

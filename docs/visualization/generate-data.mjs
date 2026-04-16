#!/usr/bin/env node
// Scanner: walks the repo and emits data.json + flows.json for the visualization.
// Usage:
//   node docs/visualization/generate-data.mjs          # regenerate data.json + flows.json
//   node docs/visualization/generate-data.mjs --inline # also inline data into index.html

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const OUT_DIR = __dirname;

const AGENT_NAMES = new Set([
  'brainstorm',
  'bug-fix',
  'frontend-specialist',
  'image-craft-expert',
  'live-test',
  'qa-agent',
  'safe-planner',
]);

// Hand-authored canonical flows for the primary orchestrator commands.
// Steps reference node IDs that must exist in data.json (validated below).
const CANONICAL_FLOWS = {
  'command.ship': {
    label: '/ship — Full Feature Delivery',
    description: 'Plan → Implement → Verify → Audit → Human push-gate',
    steps: [
      { node: 'command.ship', caption: 'User invokes /ship with a feature description' },
      { node: 'rule.questioning', caption: 'Orchestrator consults questioning.md to sharpen scope', via: 'include' },
      { node: 'agent.safe-planner', caption: 'Dispatch safe-planner for a rollback-ready plan', via: 'dispatch', marker: '## PLAN READY' },
      { node: 'agent.frontend-specialist', caption: 'Dispatch frontend-specialist to implement', via: 'dispatch', marker: '## IMPLEMENTATION COMPLETE' },
      { node: 'agent.live-test', caption: 'live-test verifies UI in browser', via: 'dispatch', marker: '## UI VERIFIED' },
      { node: 'agent.qa-agent', caption: 'qa-agent audits for real bugs', via: 'dispatch', marker: '## VERIFICATION PASSED' },
      { node: 'rule.checkpoints', caption: 'Emit human push-gate checkpoint — nothing ships until approval', via: 'include' },
    ],
  },
  'command.tdd': {
    label: '/tdd — Test-Driven Development',
    description: 'Red → Green → Refactor, with the Iron Law of "test first"',
    steps: [
      { node: 'command.tdd', caption: 'User invokes /tdd for a new behavior' },
      { node: 'rule.gates', caption: '@-includes gates.md (Iron Law: no code before a failing test)', via: 'include' },
      { node: 'agent.safe-planner', caption: 'Plan the test surface and rollback', via: 'dispatch', marker: '## PLAN READY' },
      { node: 'agent.frontend-specialist', caption: 'Write failing test → minimal impl → refactor', via: 'dispatch', marker: '## IMPLEMENTATION COMPLETE' },
      { node: 'agent.qa-agent', caption: 'qa-agent confirms coverage and no regressions', via: 'dispatch', marker: '## VERIFICATION PASSED' },
    ],
  },
  'command.bug': {
    label: '/bug — Trace, Diagnose, Fix, Validate',
    description: '4-phase systematic debugging, stops at 3+ failed fixes',
    steps: [
      { node: 'command.bug', caption: 'User reports symptom' },
      { node: 'rule.problem-solving', caption: '@-includes problem-solving.md (symptom→technique dispatch)', via: 'include' },
      { node: 'agent.bug-fix', caption: 'Dispatch bug-fix: trace flow → identify root cause', via: 'dispatch', marker: '## ROOT CAUSE FOUND' },
      { node: 'agent.frontend-specialist', caption: 'Apply narrow fix at root cause', via: 'dispatch', marker: '## IMPLEMENTATION COMPLETE' },
      { node: 'agent.qa-agent', caption: 'qa-agent confirms symptom gone, no regressions', via: 'dispatch', marker: '## VERIFICATION PASSED' },
    ],
  },
  'command.qa-loop': {
    label: '/qa-loop — Iterative Audit-and-Fix',
    description: 'Revision gate: audit → fix → re-audit until clean (max 3 iterations)',
    steps: [
      { node: 'command.qa-loop', caption: 'User triggers /qa-loop on recent changes' },
      { node: 'agent.qa-agent', caption: 'qa-agent finds bugs', via: 'dispatch', marker: '## ISSUES FOUND' },
      { node: 'agent.frontend-specialist', caption: 'Fix CRITICAL/HIGH findings', via: 'dispatch', marker: '## IMPLEMENTATION COMPLETE' },
      { node: 'agent.qa-agent', caption: 'Re-audit until PASSED or max-iterations', via: 'dispatch', marker: '## VERIFICATION PASSED' },
      { node: 'rule.gates', caption: 'Revision gate: loop or escalate per gates.md', via: 'include' },
    ],
  },
  'command.deploy-validate': {
    label: '/deploy-validate — Self-Healing Deployment',
    description: 'Pre-deploy QA → deploy → smoke test → human prod approval',
    steps: [
      { node: 'command.deploy-validate', caption: 'User runs /deploy-validate' },
      { node: 'agent.qa-agent', caption: 'Pre-deploy audit', via: 'dispatch', marker: '## VERIFICATION PASSED' },
      { node: 'rule.checkpoints', caption: 'checkpoint:human-action for the live deploy', via: 'include' },
      { node: 'agent.live-test', caption: 'Post-deploy smoke test on prod URL', via: 'dispatch', marker: '## UI VERIFIED' },
      { node: 'rule.checkpoints', caption: 'Final human approval before marking success', via: 'include' },
    ],
  },
  'command.redesign': {
    label: '/redesign — Collaborative UI Redesign',
    description: 'Capture → brainstorm → generate mockups → implement → verify',
    steps: [
      { node: 'command.redesign', caption: 'User requests a UI redesign' },
      { node: 'agent.live-test', caption: 'Capture current state screenshots', via: 'dispatch', marker: '## UI VERIFIED' },
      { node: 'agent.brainstorm', caption: '2+ loops: challenge assumptions, propose directions', via: 'dispatch', marker: '## EXPLORATION COMPLETE' },
      { node: 'agent.image-craft-expert', caption: '3 options × 2 generators = 6 mockups in parallel', via: 'dispatch', marker: '## IMAGE GENERATED' },
      { node: 'agent.frontend-specialist', caption: 'Implement chosen direction', via: 'dispatch', marker: '## IMPLEMENTATION COMPLETE' },
      { node: 'agent.live-test', caption: 'Verify against mockup', via: 'dispatch', marker: '## UI VERIFIED' },
    ],
  },
};

// ---------- utilities ----------

function readIfExists(p) {
  try {
    return fs.readFileSync(p, 'utf8');
  } catch {
    return null;
  }
}

function listMdFiles(dir) {
  try {
    return fs
      .readdirSync(dir, { withFileTypes: true })
      .filter((d) => d.isFile() && d.name.endsWith('.md'))
      .map((d) => path.join(dir, d.name))
      .sort();
  } catch {
    return [];
  }
}

function firstParagraph(text) {
  if (!text) return '';
  const withoutFrontmatter = text.replace(/^---\n[\s\S]*?\n---\n/, '');
  const withoutHeadings = withoutFrontmatter
    .split('\n')
    .filter((l) => !l.startsWith('#'))
    .join('\n')
    .trim();
  const para = withoutHeadings.split(/\n\n+/)[0] || '';
  return para.replace(/\s+/g, ' ').slice(0, 280);
}

function extractFrontmatter(text) {
  const m = text.match(/^---\n([\s\S]*?)\n---\n/);
  if (!m) return {};
  const fm = {};
  for (const line of m[1].split('\n')) {
    const kv = line.match(/^([a-zA-Z0-9_-]+):\s*(.*)$/);
    if (kv) fm[kv[1]] = kv[2].replace(/^['"]|['"]$/g, '');
  }
  return fm;
}

function extractAtIncludes(text) {
  const hits = new Set();
  const re = /@~\/\.claude\/(rules|agents)\/([a-z0-9_-]+)\.md/g;
  let m;
  while ((m = re.exec(text))) {
    hits.add(`${m[1] === 'rules' ? 'rule' : 'agent'}.${m[2]}`);
  }
  return [...hits];
}

function extractAgentMentions(text) {
  const hits = new Set();
  for (const name of AGENT_NAMES) {
    const re = new RegExp(`(?<![a-z])${name}(?![a-z])`, 'i');
    if (re.test(text)) hits.add(`agent.${name}`);
  }
  return [...hits];
}

function firstOccurrenceIndex(text, needle) {
  const i = text.toLowerCase().indexOf(needle.toLowerCase());
  return i === -1 ? Infinity : i;
}

function extractAgentMentionsOrdered(text) {
  return [...AGENT_NAMES]
    .map((name) => ({ name, idx: firstOccurrenceIndex(text, name) }))
    .filter((x) => x.idx !== Infinity)
    .sort((a, b) => a.idx - b.idx)
    .map((x) => `agent.${x.name}`);
}

// Parse the marker table in rules/agent-contracts.md
function parseAgentMarkers() {
  const contractsText = readIfExists(path.join(REPO_ROOT, 'rules', 'agent-contracts.md'));
  const markers = {};
  if (!contractsText) return markers;
  const lines = contractsText.split('\n');
  for (const line of lines) {
    const m = line.match(/^\|\s*`([a-z-]+)`\s*\|\s*(.+?)\s*\|$/);
    if (!m) continue;
    const agent = m[1];
    if (!AGENT_NAMES.has(agent)) continue;
    const markerCell = m[2];
    const markerList = [...markerCell.matchAll(/`(## [A-Z_][A-Z_ ]*)`/g)].map((x) => x[1]);
    if (markerList.length) markers[agent] = markerList;
  }
  return markers;
}

// ---------- scan ----------

function scanAgents() {
  const out = [];
  const markers = parseAgentMarkers();
  for (const file of listMdFiles(path.join(REPO_ROOT, 'agents'))) {
    const name = path.basename(file, '.md');
    const text = fs.readFileSync(file, 'utf8');
    const fm = extractFrontmatter(text);
    out.push({
      id: `agent.${name}`,
      kind: 'agent',
      label: name,
      path: path.relative(REPO_ROOT, file),
      summary: fm.description || firstParagraph(text),
      markers: markers[name] || [],
      includes: extractAtIncludes(text),
    });
  }
  return out;
}

function scanAgentTemplates() {
  const out = [];
  const dir = path.join(REPO_ROOT, 'agents', 'templates');
  for (const file of listMdFiles(dir)) {
    const name = path.basename(file, '.md');
    const text = fs.readFileSync(file, 'utf8');
    out.push({
      id: `agent-template.${name}`,
      kind: 'agent-template',
      label: name,
      path: path.relative(REPO_ROOT, file),
      summary: firstParagraph(text),
      includes: extractAtIncludes(text),
    });
  }
  return out;
}

function scanRules() {
  const out = [];
  for (const file of listMdFiles(path.join(REPO_ROOT, 'rules'))) {
    const name = path.basename(file, '.md');
    const text = fs.readFileSync(file, 'utf8');
    out.push({
      id: `rule.${name}`,
      kind: 'rule',
      label: name,
      path: path.relative(REPO_ROOT, file),
      summary: firstParagraph(text),
    });
  }
  return out;
}

function scanCommands() {
  const out = [];
  const dir = path.join(REPO_ROOT, 'commands');
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    if (!entry.name.endsWith('.md') && !entry.name.endsWith('.sh')) continue;
    const name = path.basename(entry.name, path.extname(entry.name));
    const file = path.join(dir, entry.name);
    const text = fs.readFileSync(file, 'utf8');
    const fm = extractFrontmatter(text);
    out.push({
      id: `command.${name}`,
      kind: 'command',
      label: `/${name}`,
      path: path.relative(REPO_ROOT, file),
      summary: fm.description || firstParagraph(text),
      includes: extractAtIncludes(text),
      dispatches: extractAgentMentionsOrdered(text),
    });
  }
  return out.sort((a, b) => a.label.localeCompare(b.label));
}

function scanSkills() {
  const out = [];
  const dir = path.join(REPO_ROOT, 'skills');
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const name = entry.name;
    const skillMd =
      readIfExists(path.join(dir, name, 'SKILL.md')) ||
      readIfExists(path.join(dir, name, `${name}.md`)) ||
      '';
    const fm = extractFrontmatter(skillMd);
    out.push({
      id: `skill.${name}`,
      kind: 'skill',
      label: name,
      path: path.relative(REPO_ROOT, path.join(dir, name)),
      summary: fm.description || firstParagraph(skillMd),
    });
  }
  return out.sort((a, b) => a.label.localeCompare(b.label));
}

function scanMcp() {
  const out = [];
  const jsonText = readIfExists(path.join(REPO_ROOT, 'mcp', 'mcp-servers.json'));
  if (!jsonText) return out;
  const data = JSON.parse(jsonText);
  for (const [name, cfg] of Object.entries(data)) {
    out.push({
      id: `mcp.${name}`,
      kind: 'mcp',
      label: name,
      path: 'mcp/mcp-servers.json',
      summary: cfg.type === 'http' ? `HTTP endpoint: ${cfg.url}` : `stdio: ${cfg.command} ${(cfg.args || []).join(' ')}`.slice(0, 280),
      transport: cfg.type || 'stdio',
    });
  }
  return out;
}

function scanHooks() {
  const out = [];
  const jsonText = readIfExists(path.join(REPO_ROOT, 'hooks', 'settings.json'));
  if (!jsonText) return out;
  const data = JSON.parse(jsonText);
  const hookEvents = data.hooks || {};
  for (const [event, entries] of Object.entries(hookEvents)) {
    entries.forEach((entry, idx) => {
      const matcher = entry.matcher || '*';
      const cmds = (entry.hooks || []).map((h) => h.command || '').filter(Boolean);
      const firstCmd = cmds[0] || '';
      const label = `${event}${matcher !== '*' ? ` [${matcher}]` : ''}`;
      out.push({
        id: `hook.${event}.${idx}`,
        kind: 'hook',
        label,
        event,
        matcher,
        path: 'hooks/settings.json',
        summary: firstCmd.slice(0, 280),
      });
    });
  }
  return out;
}

function scanMeta() {
  const out = [];
  const metaText = readIfExists(path.join(REPO_ROOT, 'META_RULE.md'));
  if (metaText) {
    out.push({
      id: 'meta.META_RULE',
      kind: 'meta',
      label: 'META_RULE.md',
      path: 'META_RULE.md',
      summary: firstParagraph(metaText),
    });
  }
  const claudeMd = readIfExists(path.join(REPO_ROOT, 'claude-md', 'CLAUDE.md'));
  if (claudeMd) {
    out.push({
      id: 'meta.CLAUDE',
      kind: 'meta',
      label: 'CLAUDE.md',
      path: 'claude-md/CLAUDE.md',
      summary: firstParagraph(claudeMd),
    });
  }
  out.push({
    id: 'meta.orchestrator',
    kind: 'meta',
    label: 'Main Thread (Orchestrator)',
    path: '',
    summary:
      'The main conversation thread. Routes requests, reads rules, dispatches fresh-context subagents, and owns the user relationship. Never does heavy lifting itself.',
  });
  return out;
}

// ---------- build ----------

function buildGraph() {
  const nodes = [
    ...scanMeta(),
    ...scanRules(),
    ...scanCommands(),
    ...scanAgents(),
    ...scanAgentTemplates(),
    ...scanSkills(),
    ...scanMcp(),
    ...scanHooks(),
  ];
  const nodeIds = new Set(nodes.map((n) => n.id));

  const edges = [];
  function addEdge(source, target, type) {
    if (!nodeIds.has(source) || !nodeIds.has(target)) return;
    edges.push({ source, target, type });
  }

  // meta anchors
  addEdge('meta.orchestrator', 'meta.CLAUDE', 'include');
  addEdge('meta.orchestrator', 'meta.META_RULE', 'include');

  // Session-start-like hook that emits META_RULE: represent as trigger
  for (const n of nodes.filter((x) => x.kind === 'hook' && x.event === 'SessionStart')) {
    addEdge(n.id, 'meta.META_RULE', 'trigger');
  }

  // commands: include edges + dispatch edges
  for (const n of nodes.filter((x) => x.kind === 'command')) {
    for (const inc of n.includes || []) addEdge(n.id, inc, 'include');
    for (const d of n.dispatches || []) addEdge(n.id, d, 'dispatch');
    addEdge('meta.orchestrator', n.id, 'routes');
  }

  // agents: orchestrator routes to them directly
  for (const n of nodes.filter((x) => x.kind === 'agent')) {
    addEdge('meta.orchestrator', n.id, 'routes');
    for (const inc of n.includes || []) addEdge(n.id, inc, 'include');
  }

  // agent-templates
  for (const n of nodes.filter((x) => x.kind === 'agent-template')) {
    for (const inc of n.includes || []) addEdge(n.id, inc, 'include');
  }

  return {
    meta: {
      generatedAt: new Date().toISOString(),
      repo: 'zalo-claude-code-setup',
    },
    nodes,
    edges,
  };
}

function buildFlows(graph) {
  const flows = {};
  const nodeIds = new Set(graph.nodes.map((n) => n.id));

  // Canonical flows first (validated against node IDs)
  for (const [id, flow] of Object.entries(CANONICAL_FLOWS)) {
    if (!nodeIds.has(id)) {
      throw new Error(`Canonical flow refers to missing command node: ${id}`);
    }
    for (const step of flow.steps) {
      if (!nodeIds.has(step.node)) {
        throw new Error(`Canonical flow ${id} references missing node: ${step.node}`);
      }
    }
    flows[id] = { ...flow, canonical: true };
  }

  // Auto-generated simple flows for remaining commands
  for (const cmd of graph.nodes.filter((n) => n.kind === 'command')) {
    if (flows[cmd.id]) continue;
    const steps = [{ node: cmd.id, caption: `User invokes ${cmd.label}` }];
    for (const agentId of cmd.dispatches || []) {
      const agent = graph.nodes.find((n) => n.id === agentId);
      const marker = agent && agent.markers && agent.markers[0];
      steps.push({
        node: agentId,
        via: 'dispatch',
        caption: `Dispatch ${agent ? agent.label : agentId}`,
        marker: marker || undefined,
      });
    }
    for (const inc of cmd.includes || []) {
      steps.push({
        node: inc,
        via: 'include',
        caption: `@-includes ${inc.split('.').pop()}`,
      });
    }
    if (steps.length === 1) {
      steps.push({
        node: cmd.id,
        caption: 'Standalone skill/utility — no subagent dispatch in the core path',
      });
    }
    flows[cmd.id] = {
      label: `${cmd.label} — ${(cmd.summary || '').slice(0, 80)}`,
      description: cmd.summary || '',
      steps,
      canonical: false,
    };
  }

  return flows;
}

// ---------- stats ----------

function printStats(graph, flows) {
  const byKind = {};
  for (const n of graph.nodes) byKind[n.kind] = (byKind[n.kind] || 0) + 1;
  const canonicalCount = Object.values(flows).filter((f) => f.canonical).length;
  console.log('Graph:');
  for (const [k, v] of Object.entries(byKind).sort()) {
    console.log(`  ${k.padEnd(16)} ${v}`);
  }
  console.log(`  edges            ${graph.edges.length}`);
  console.log(`Flows: ${Object.keys(flows).length} total (${canonicalCount} canonical, ${Object.keys(flows).length - canonicalCount} auto)`);
}

// ---------- write ----------

function writeOutputs(graph, flows) {
  fs.writeFileSync(path.join(OUT_DIR, 'data.json'), JSON.stringify(graph, null, 2) + '\n');
  fs.writeFileSync(path.join(OUT_DIR, 'flows.json'), JSON.stringify(flows, null, 2) + '\n');
}

function inlineIntoHtml(graph, flows) {
  const htmlPath = path.join(OUT_DIR, 'index.html');
  if (!fs.existsSync(htmlPath)) {
    console.warn('index.html not found — skipping --inline (run after Step 2)');
    return;
  }
  let html = fs.readFileSync(htmlPath, 'utf8');

  function replaceSentinel(haystack, id, payload) {
    const startTag = `<script type="application/json" id="${id}">`;
    const endTag = '</script>';
    const startIdx = haystack.indexOf(startTag);
    const endIdx = startIdx === -1 ? -1 : haystack.indexOf(endTag, startIdx);
    if (startIdx === -1 || endIdx === -1) {
      console.warn(`sentinel #${id} not found — skipping`);
      return haystack;
    }
    return (
      haystack.slice(0, startIdx + startTag.length) +
      '\n' +
      payload +
      '\n' +
      haystack.slice(endIdx)
    );
  }

  html = replaceSentinel(html, 'graph-data', JSON.stringify(graph));
  html = replaceSentinel(html, 'flow-data', JSON.stringify(flows));
  fs.writeFileSync(htmlPath, html);
  console.log('Inlined graph → #graph-data, flows → #flow-data');
}

// ---------- main ----------

function main() {
  const inline = process.argv.includes('--inline');
  const graph = buildGraph();
  const flows = buildFlows(graph);

  // Acceptance criteria (fail loud if tree looks wrong)
  const counts = {
    agent: graph.nodes.filter((n) => n.kind === 'agent').length,
    rule: graph.nodes.filter((n) => n.kind === 'rule').length,
    command: graph.nodes.filter((n) => n.kind === 'command').length,
    hook: graph.nodes.filter((n) => n.kind === 'hook').length,
    mcp: graph.nodes.filter((n) => n.kind === 'mcp').length,
    skill: graph.nodes.filter((n) => n.kind === 'skill').length,
  };
  const minimums = { agent: 7, rule: 11, command: 22, hook: 6, mcp: 8, skill: 4 };
  const failures = [];
  for (const [k, min] of Object.entries(minimums)) {
    if (counts[k] < min) failures.push(`${k}: ${counts[k]} < ${min}`);
  }
  // Edge integrity
  const nodeIds = new Set(graph.nodes.map((n) => n.id));
  for (const e of graph.edges) {
    if (!nodeIds.has(e.source)) failures.push(`edge source missing: ${e.source}`);
    if (!nodeIds.has(e.target)) failures.push(`edge target missing: ${e.target}`);
  }
  if (failures.length) {
    console.error('Scanner failed acceptance checks:');
    for (const f of failures) console.error('  - ' + f);
    process.exit(1);
  }

  writeOutputs(graph, flows);
  printStats(graph, flows);
  if (inline) inlineIntoHtml(graph, flows);
}

main();

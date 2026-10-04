#!/usr/bin/env node
// Scanner: walks the repo and emits data.json + flows.json for the visualization.
// Usage:
//   node docs/visualization/generate-data.mjs          # regenerate data.json + flows.json
//   node docs/visualization/generate-data.mjs --inline # also inline data into index.html

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const OUT_DIR = __dirname;

// Only files git tracks may reach the published graph. A fresh clone of the public repo is
// the main guard against private primitives; this is the second one: an untracked skill,
// rule, command or agent in a working copy is never read. Refuses to run outside a git
// checkout rather than fall back to reading everything.
function loadTrackedFiles() {
  try {
    const out = execFileSync('git', ['ls-files', '-z'], {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      maxBuffer: 64 * 1024 * 1024,
    });
    return new Set(out.split('\0').filter(Boolean));
  } catch (err) {
    console.error(`generate-data: \`git ls-files\` failed in ${REPO_ROOT}: ${err.message.split('\n')[0]}`);
    console.error('Run it inside a git clone of the setup repo: it only reads tracked files.');
    process.exit(1);
  }
}
const TRACKED = loadTrackedFiles();
if (!TRACKED.has('docs/visualization/generate-data.mjs')) {
  // e.g. an untracked copy of the tree sitting inside some other repository
  console.error(`generate-data: ${REPO_ROOT} is not a checkout of the setup repo (this script is not tracked in it).`);
  console.error('Run it inside a git clone of the setup repo: it only reads tracked files.');
  process.exit(1);
}

function isTracked(absPath) {
  return TRACKED.has(path.relative(REPO_ROOT, absPath).split(path.sep).join('/'));
}

const AGENT_NAMES = new Set([
  'brainstorm',
  'bug-fix',
  'frontend-specialist',
  'live-test',
  'outcomes-grader',
  'qa-agent',
  'safe-planner',
]);

// Hand-authored canonical flows for the primary orchestrator commands.
// Steps reference node IDs that must exist in data.json (validated below).
// Flow IDs starting with `workflow.` are narrative/meta flows that do not
// correspond to a single command node; the validator skips the top-level
// node check for them but still validates each step's node ID.
const CANONICAL_FLOWS = {
  'workflow.daily-use': {
    label: 'Daily Workflow — /plan → /autopilot → verify → /compact',
    description: 'How you actually work: one terminal orchestrates with /plan, a second terminal runs /autopilot, then back to the first to verify and merge',
    steps: [
      { node: 'meta.orchestrator', caption: 'Open your first terminal. Tell Claude what you want to build, in plain English.' },
      { node: 'command.plan', caption: 'Run /plan. Claude breaks your task down before writing any code.', via: 'dispatch' },
      { node: 'agent.safe-planner', caption: 'A specialist sub-task figures out every file to change, in what order, and how to undo it if something goes wrong.', via: 'dispatch', marker: '## PLAN READY' },
      { node: 'rule.plan-verification', caption: 'Two more sub-tasks pressure-test the plan — one challenges the assumptions, one grades it against engineering rules. The plan is revised until both pass.', via: 'include' },
      { node: 'command.autopilot', caption: 'Open a second terminal. Paste the /autopilot command /plan handed you. It runs the plan on its own while you do other things.' },
      { node: 'agent.qa-agent', caption: 'A QA sub-task audits every change and re-checks until the work is clean. No "should work" — only verified.', via: 'dispatch', marker: '## VERIFICATION PASSED' },
      { node: 'rule.checkpoints', caption: 'Switch back to your first terminal. Claude waits for you to confirm before pushing anything.', via: 'include' },
      { node: 'meta.orchestrator', caption: "When you're done, run /compact. It throws away the noise and keeps your next conversation lean." },
    ],
  },
  'command.autopilot': {
    label: '/autopilot — Autonomous Multi-Phase Orchestrator',
    description: 'Plan → Implement → QA → Commit, end-to-end with API retry + circuit breaker',
    steps: [
      { node: 'command.autopilot', caption: 'User invokes /autopilot with a task description' },
      { node: 'agent.safe-planner', caption: 'Phase 1: dispatch safe-planner for work-unit plan', via: 'dispatch', marker: '## PLAN READY' },
      { node: 'agent.brainstorm', caption: 'Plan verification gate: brainstorm-vet critique', via: 'dispatch', marker: '## EXPLORATION COMPLETE' },
      { node: 'agent.outcomes-grader', caption: 'Plan verification gate: rubric grading', via: 'dispatch', marker: '## OUTCOMES PASSED' },
      { node: 'agent.frontend-specialist', caption: 'Phase 2: implementation work units in parallel where safe', via: 'dispatch', marker: '## IMPLEMENTATION COMPLETE' },
      { node: 'agent.qa-agent', caption: 'Phase 3: QA loop — audit + fix until clean', via: 'dispatch', marker: '## VERIFICATION PASSED' },
      { node: 'rule.checkpoints', caption: 'Final commit phase + human push-gate', via: 'include' },
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
  'command.plan': {
    label: '/plan — Plan with Brainstorm + Principles Verification',
    description: 'safe-planner → brainstorm critique → rubric grading → revision loop',
    steps: [
      { node: 'command.plan', caption: 'User invokes /plan with a task' },
      { node: 'agent.safe-planner', caption: 'Generate work-unit plan with rollback', via: 'dispatch', marker: '## PLAN READY' },
      { node: 'agent.brainstorm', caption: 'Critical-thinking pass: inversion + scale-game + meta-pattern', via: 'dispatch', marker: '## EXPLORATION COMPLETE' },
      { node: 'agent.outcomes-grader', caption: 'Grade plan against engineering-principles.md rubric', via: 'dispatch', marker: '## OUTCOMES PASSED' },
      { node: 'rule.gates', caption: 'Revision gate: one retry pass if either critique flags issues', via: 'include' },
    ],
  },
};

// ---------- utilities ----------

// Reads a file only when git tracks it (see isTracked).
function readIfExists(p) {
  if (!isTracked(p)) return null;
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
      .filter((p) => isTracked(p))
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
  const lines = m[1].split('\n');
  for (let i = 0; i < lines.length; i++) {
    const kv = lines[i].match(/^([a-zA-Z0-9_-]+):\s*(.*)$/);
    if (!kv) continue;
    // YAML block scalar (`key: >` or `key: |`): the value is the indented lines below it.
    if (/^[>|][-+]?$/.test(kv[2].trim())) {
      const block = [];
      while (i + 1 < lines.length && /^(\s+\S|\s*$)/.test(lines[i + 1])) block.push(lines[++i].trim());
      fm[kv[1]] = block.filter(Boolean).join(' ');
      continue;
    }
    fm[kv[1]] = kv[2].replace(/^['"]|['"]$/g, '');
  }
  return fm;
}

function extractAtIncludes(text) {
  const hits = new Set();
  const re = /@~\/\.claude\/(rules|rules-ref|agents)\/([a-z0-9_-]+)\.md/g;
  let m;
  while ((m = re.exec(text))) {
    hits.add(`${m[1] === 'agents' ? 'agent' : 'rule'}.${m[2]}`);
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

// ---------- changelog ----------

// Cap the shipped log; the panel is a highlight reel, not the full history.
const CHANGELOG_MAX_ENTRIES = 60;
// Drop bookkeeping/noise subjects — regenerated-data commits, merges, releases.
const CHANGELOG_NOISE_RE = /^(Sync|Regenerate|Merge|chore\(release\)|docs: regenerate)/i;

// Extract a self-maintaining "Setup Log" from the repo's own git history.
// Reads first-parent main, filters noise, dedupes identical subjects, and
// groups by date (reverse-chronological). Degrades to [] if git is unavailable.
function buildChangelog() {
  let raw;
  try {
    raw = execFileSync(
      'git',
      ['log', '--first-parent', '--date=short', '--pretty=format:%ad%x09%s', '-n', '400'],
      { cwd: REPO_ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
    );
  } catch (err) {
    console.warn('changelog: `git log` failed — emitting empty changelog:', err.message);
    return [];
  }

  const seen = new Set();
  const flat = []; // { date, subject } in reverse-chronological order
  for (const line of raw.split('\n')) {
    if (!line) continue;
    const tab = line.indexOf('\t');
    if (tab === -1) continue;
    const date = line.slice(0, tab).trim();
    const subject = line.slice(tab + 1).trim();
    if (!date || !subject) continue;
    if (CHANGELOG_NOISE_RE.test(subject)) continue;
    const key = subject.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    flat.push({ date, subject });
  }

  const truncated = flat.length > CHANGELOG_MAX_ENTRIES;
  const capped = flat.slice(0, CHANGELOG_MAX_ENTRIES);
  if (truncated) {
    console.log(
      `changelog: truncated to ${CHANGELOG_MAX_ENTRIES} of ${flat.length} meaningful entries`,
    );
  }

  // Group by date, preserving reverse-chronological order of first appearance.
  const groups = [];
  const byDate = new Map();
  for (const { date, subject } of capped) {
    let group = byDate.get(date);
    if (!group) {
      group = { date, entries: [] };
      byDate.set(date, group);
      groups.push(group);
    }
    group.entries.push(subject);
  }
  return groups;
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

function scanRules() {
  const out = [];
  const files = [
    ...listMdFiles(path.join(REPO_ROOT, 'rules')),
    ...listMdFiles(path.join(REPO_ROOT, 'rules-ref')),
  ];
  for (const file of files) {
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
    if (!isTracked(file)) continue;
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
    if (!skillMd) continue; // no tracked SKILL.md: not a published skill
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
  const claudeMd = readIfExists(path.join(REPO_ROOT, 'CLAUDE.md'));
  if (claudeMd) {
    out.push({
      id: 'meta.CLAUDE',
      kind: 'meta',
      label: 'CLAUDE.md',
      path: 'CLAUDE.md',
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

// ---------- count text ----------

// The title, the hero and the List label in index.html carry data-count-text and
// data-count-aria templates such as "{agent:Word} Agents" or "{total} pieces". --inline
// fills them from the graph it just built, and the page fills them again at render time
// from the data it loaded, so no count in the copy can go stale. Keep these helpers in
// step with fillCountTemplate() in index.html.
const NUMBER_WORDS = [
  'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
  'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen',
  'nineteen',
];
const TENS_WORDS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];

function numberWord(n) {
  if (n < 20) return NUMBER_WORDS[n];
  if (n < 100) return TENS_WORDS[Math.floor(n / 10)] + (n % 10 ? '-' + NUMBER_WORDS[n % 10] : '');
  return String(n);
}

function fillCountTemplate(template, graph) {
  const counts = { total: graph.nodes.length };
  for (const n of graph.nodes) counts[n.kind] = (counts[n.kind] || 0) + 1;
  return template.replace(/\{([a-z-]+)(?::(word|Word))?\}/g, (m, key, form) => {
    const n = counts[key] || 0;
    if (!form) return String(n);
    const w = numberWord(n);
    return form === 'Word' ? w.charAt(0).toUpperCase() + w.slice(1) : w;
  });
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
}

function applyCountTemplates(html, graph) {
  const expected = (html.match(/\sdata-count-(?:text|aria)="/g) || []).length;
  let filled = 0;
  html = html.replace(
    /<([a-z0-9]+)(\s[^>]*?\bdata-count-text="([^"]*)"[^>]*)>([^<]*)<\/\1\s*>/g,
    (m, tag, attrs, tpl) => {
      filled++;
      return `<${tag}${attrs}>${escapeHtml(fillCountTemplate(tpl, graph))}</${tag}>`;
    },
  );
  html = html.replace(/<[a-z0-9]+\s[^>]*\bdata-count-aria="([^"]*)"[^>]*>/g, (tag, tpl) => {
    filled++;
    return tag.replace(/\baria-label="[^"]*"/, `aria-label="${escapeHtml(fillCountTemplate(tpl, graph))}"`);
  });
  if (filled !== expected) {
    // A template the patterns above cannot fill would keep a stale count in the copy.
    console.error(`generate-data: count text: filled ${filled} of ${expected} data-count templates in index.html.`);
    console.error('A data-count element must hold plain text only. Nothing was written.');
    process.exit(1);
  }
  if (!filled) console.warn('count text: no data-count templates found in index.html');
  else console.log(`count text: filled ${filled} of ${expected} templates`);
  return html;
}

// ---------- build ----------

function buildGraph() {
  const nodes = [
    ...scanMeta(),
    ...scanRules(),
    ...scanCommands(),
    ...scanAgents(),
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

  return {
    meta: {
      generatedAt: new Date().toISOString(),
      repo: 'zalo-claude-code-setup',
      changelog: buildChangelog(),
    },
    nodes,
    edges,
  };
}

function buildFlows(graph) {
  const flows = {};
  const nodeIds = new Set(graph.nodes.map((n) => n.id));

  // Canonical flows first (validated against node IDs).
  // `workflow.*` flow IDs are narrative/meta flows that don't correspond to
  // a single command node — skip the top-level node check for them. Steps
  // are still validated below.
  for (const [id, flow] of Object.entries(CANONICAL_FLOWS)) {
    if (!id.startsWith('workflow.') && !nodeIds.has(id)) {
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

// Builds the inlined page without writing it, so a refusal (an unfillable count template)
// happens before any output file is touched.
function buildInlinedHtml(graph, flows) {
  const htmlPath = path.join(OUT_DIR, 'index.html');
  if (!fs.existsSync(htmlPath)) {
    console.warn('index.html not found — skipping --inline (run after Step 2)');
    return null;
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

  html = applyCountTemplates(html, graph);
  html = replaceSentinel(html, 'graph-data', JSON.stringify(graph));
  html = replaceSentinel(html, 'flow-data', JSON.stringify(flows));
  return { htmlPath, html };
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
  const minimums = { agent: 6, rule: 11, command: 5, hook: 2, mcp: 4, skill: 8 };
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

  const inlined = inline ? buildInlinedHtml(graph, flows) : null;
  writeOutputs(graph, flows);
  printStats(graph, flows);
  if (inlined) {
    fs.writeFileSync(inlined.htmlPath, inlined.html);
    console.log('Inlined graph → #graph-data, flows → #flow-data');
  }
}

main();

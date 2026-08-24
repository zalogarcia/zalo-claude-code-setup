---
name: voice-agent-forge
description: Generate production-ready Retell-style voice/chat agent system prompts in the Operator Base "house format" — the same structure the game-app's Prompt Forge (Prompt Studio) and demo-retell-setup templates produce. Use when the user says "write a voice agent prompt", "build a Retell agent", "make an orchestrator bot", "create the sub-agents", "forge a prompt for [client]", "draft the AI receptionist prompt", or asks for a multi-bot routing setup (orchestrator + specialized agents). Produces the full <identity>/<company_identity>/<goal>/<context>/<important_information>/<conversational_style_guideline>/<conversation_steps>/<selling_method>/<objection_handling_database>/<knowledge_database> skeleton with the voice-specific rules and the Selling Method block baked in, so every client bot comes out consistent instead of re-derived from scratch each time.
---

Forge voice (Retell) and chat (ADRS) agent system prompts in Operator Base house format. One client = an orchestrator bot plus N specialized sub-agents the orchestrator transfers to. This skill gives you the exact section taxonomy, the voice-specific rules, and the generation discipline so every bot comes out in the same shape.

## When to invoke

- "Write/forge a voice agent prompt for [client]" / "build a Retell agent" / "make the AI receptionist"
- "Create the orchestrator + sub-agents" / "I need 4 bots for this client" / "route callers to the right department"
- "Turn this onboarding submission into a chatbot prompt" (the Client Onboarding → Forge seed flow)
- Any time you're producing the `<identity>`-tagged prompt that goes into Retell, Prompt Studio, or an n8n ADRS workflow

Skip for: editing an existing prompt's wording (just edit the file), one-line tone tweaks, or non-conversational LLM prompts (summarizers, classifiers).

## Origin

This is the game-app "Prompt Forge" promoted into Claude Code. Canonical references (read them if present, they are the source of truth for wording):

- House structure & voice rules: `~/dev/90-day-cmaa-game-app/supabase/functions/demo-retell-setup/templates.ts` (`ORCHESTRATOR_GLOBAL_PROMPT`, `ENG_LLM_PROMPT`, `ESP_LLM_PROMPT`)
- The in-app Forge system prompt (repo-tracked source of truth for the `prompt_forge_system_prompt` app_settings row — the code `DEFAULT_SYSTEM_PROMPT` in useAnthropicChat.js is only a minimal fallback): `~/dev/90-day-cmaa-game-app/docs/prompt-forge/system-prompt.md`
- **The Selling Method block (canonical, paste-verbatim artifact):** `~/Documents/Zalo Content/Sales System/agent-prompt-block/SELLING-METHOD.block.md` — 530-conversation-measured; its README documents the evidence and deploy gates
- Onboarding → Forge seed contract: `~/dev/90-day-cmaa-game-app/src/components/Toolkit/ClientOnboarding/buildForgeSeedFromSubmission.js`

If those files aren't on disk, this skill is self-contained — the skeleton and rules below are the full spec.

## Generation discipline (the Forge contract)

1. **Ground everything in supplied context.** Pull company identity, services, hours, regions, pricing, FAQs from what the user gave you (onboarding submission, website scrape, email brief, transcript).
2. **Never invent prices, commitments, dates, or policies** not grounded in the context. If a value is unknown, the bot _collects the lead and sends a link / hands off_ — it does not fabricate. (e.g., unknown exhibitor rates → "I'll text you the exhibitor info" via the SMS tool, not a made-up number.)
3. **Every prompt includes:** Identity, Voice/Tone, the Offering/Services, qualification criteria, FAQs/knowledge, and Guardrails (out-of-scope → human handoff).
4. **Tools are external.** Never write real URLs or phone numbers as links. Reference _using_ a tool ("I'll send you the calendar link now") — the platform owns the actual send. Booking, SMS, email, agent-transfer, and human-handoff tools are configured in Retell/the platform, not in the prompt.
5. **Out-of-scope → hand off, don't guess.** When a question falls outside the grounded context, escalate to the human team.
6. **Sales-mission bots get the Selling Method block VERBATIM.** A sales-mission bot is any bot whose job moves someone toward a purchase — outbound sales, inbound lead qualification, revival/re-engagement, and appointment-setters whose booking IS the sales next step. Insert `~/Documents/Zalo Content/Sales System/agent-prompt-block/SELLING-METHOD.block.md` word-for-word as the `<selling_method>` section (client bots get the FULL block, fact-sourcing rules included — those rules only get adapted in demo contexts). Exactly two permitted adaptations: (a) `set_dnd` — Delta Agents platform bots HAVE the tool, keep those sentences exactly; only swap for the platform's real opt-out mechanism when the target platform genuinely lacks one; (b) voice bots — adapt the handful of text-channel phrases to speech ("in writing" → "on a call", "scroll up and reread" → "remembers what you said", "block a number" → "hang up and block a number"). Pure support bots, receptionists/after-hours catch-alls, and post-purchase bots do NOT get the block or an objection database — on those it is pure cost and distorts behavior. A routing-only orchestrator does not get it; an orchestrator that itself sells does.
7. **Objection handlers are generated per client, never canned.** After the block, write `<objection_handling_database>` as 8-15 objections this client's prospects actually raise — composed from the block's ten patterns + the client's niche, offer, pricing, and stated objections — each response following the four-step move (accept briefly → exit out loud → one diagnostic question → concrete answer + next step) and obeying the block's "Never do these". No stock script libraries, no invented statistics/success rates/social proof.

## The house format (section order is fixed)

Emit sections in this exact order. Orchestrators and sub-agents share the skeleton; the differences are noted.

```
<identity>            Named persona, role, default tone, 2 good/bad response examples. Tone tuned to caller type.
<company_identity>    Shared block — repeat verbatim in EVERY bot so each is self-contained (name, founder, phone spelled in words, email "at … dot …", website, what the company does, signature programs).
<goal>                Primary objective + "Success looks like" bullets + strategic approach.
                      • Orchestrator: identify intent → route to the right sub-agent (list the categories).
                      • Sub-agent: the qualification criteria + actions for THIS caller type.
<context>             {{contact_first_name}}, {{contact_id}}, {{date_context}}; business hours + timezone;
                      for sub-agents: note they can transfer BACK to the orchestrator or sideways to another sub-agent.
<important_information>
                      Concise rule; match energy. AI DISCLOSURE (tell the truth if asked, offer human).
                      CONVERSATION ENERGY MANAGEMENT (5 energy types).
                      <conversation_flow_flexibility> … adaptive-framework block …
                      MAXIMUM ATTEMPT RULES (same question 3× → human handoff; routing 2× max;
                      objections defer to the Selling Method three-attempt budget — never a separate "price 2× max" rule).
                      TOOLS ARE EXTERNAL (no raw URLs; reference using the tool).
                      CRITICAL GUIDELINES (never break character; redirect off-scope).
<conversational_style_guideline>
                      VOICE-SPECIFIC RULES (verbatim block below) + the Words-to-Avoid list.
<conversation_steps>  Numbered flow. Sub-agents: warm pickup (acknowledge the transfer, don't re-greet from scratch)
                      → qualification (one question at a time) → send links/info via tools → booking sequence
                      → CRM add / reminder offer → confirm. Orchestrator: greeting → identify intent → route.
<selling_method>      SALES-MISSION BOTS ONLY (see discipline #6): the Selling Method block, verbatim, with only the
                      two permitted adaptations. Omit entirely for support/receptionist/routing-only/post-purchase bots.
<objection_handling_database>
                      SALES-MISSION BOTS ONLY: 8-15 niche-specific handlers generated per discipline #7 —
                      the client's real objections in the four-step move shape. Never a canned library.
<knowledge_database>  Grounded facts: schedule, programs, regions, rates-by-link, etc. Spell dates/numbers in words.
```

### Verbatim voice block (drop into every `<conversational_style_guideline>`)

```
Ask only one question at a time and wait for response — never bundle questions.
Use natural filler words ("umm", "so") very sparingly, max once every two interactions.
Keep interactions brief with short sentences.
Write symbols as words: "three dollars" not "$3", "at" not "@".
Read phone numbers in natural 3-3-4 groupings, in full words: "five five five - one two three - four five six seven".
When spelling names: "First name is Jane, spelled J A N E."
Read dates naturally in full words: "Tuesday the eighteenth at ten am".
Never use em dashes when speaking.
Acknowledge info the caller already shared; never ask for it twice.
```

### Words to Avoid (paste into the style block)

Accordingly, Additionally, Arguably, Certainly, Consequently, Hence, However, Indeed, Moreover, Nevertheless, Nonetheless, Notwithstanding, Thus, Undoubtedly, Adept, Commendable, Dynamic, Efficient, Ever-evolving, Exciting, Exemplary, Innovative, Invaluable, Robust, Seamless, Synergistic, Thought-provoking, Transformative, Utmost, Vibrant, Vital, Efficiency, Innovation, Institution, Integration, Implementation, Landscape, Optimization, Realm, Tapestry, Transformation, Aligns, Augment, Delve, Embark, Facilitate, Maximize, Underscores, Utilize, A testament to…, In conclusion…, In summary…, It's important to note/consider…, It's worth noting that…, On the contrary.

## Orchestrator + sub-agent architecture

- **No IVR.** Never tell callers to "press 1." The orchestrator asks one open question, infers intent, and transfers. (Per client preference — IVR is outdated.)
- **Seamless handoff both ways.** Sub-agents can transfer back to the orchestrator or sideways to a sibling sub-agent if the caller's need changes. State this in each sub-agent's `<context>` and `<conversation_steps>`.
- **One persona per bot, consistent across the set.** Give each bot a distinct, on-brand first name; the orchestrator says "let me connect you with someone who specializes in…". Pick voices/names that fit the brand.
- **Shared blocks stay identical.** `<company_identity>`, the voice block, and the Words-to-Avoid list must be byte-identical across all bots in a set — define once, paste everywhere. Divergence here is the #1 quality bug.
- **Add-on tools** (lead scoring, CRM push, reminder-text scheduling) are referenced as external tools the same way booking/SMS are — describe WHEN to fire them, never implement them in-prompt.

## Output shape

- Write each bot to its own file: `<client>/voice-agents/<NN>-<agent-name>.md`. Add a `00-orchestrator.md` and a `README.md` mapping the routing.
- After writing, report a one-line manifest: `Forged N bots: orchestrator + [list]. Shared blocks verified identical.`
- Do NOT paste full 250-line prompts back into chat — point to the files and summarize each bot's qualification criteria in 1-2 lines.

## Anti-patterns

- ❌ Inventing prices/rates/dates to fill a section — collect the lead and send a link via the SMS tool instead.
- ❌ Canned objection scripts (the old "Common objections" / stock objection database) — superseded 2026-08-24 by the Selling Method block + per-client handlers. If you find yourself pasting an objection response you didn't derive from THIS client's context, stop.
- ❌ Pasting `<selling_method>` into a support, receptionist, or routing-only bot — the block itself documents this as pure cost that distorts behavior.
- ❌ Paraphrasing or trimming the Selling Method block — it is a measured artifact; verbatim or absent, nothing in between (the two platform adaptations in discipline #6 are the only exceptions).
- ❌ Writing real URLs or phone numbers as clickable links inside the prompt — tools are external; reference using them.
- ❌ IVR "press 1 for…" menus — the client wants natural conversation.
- ❌ Letting `<company_identity>` or the voice block drift between bots in the same set — paste identical.
- ❌ Sub-agent that re-greets with the full "Thank you for calling…" after a transfer — it should warmly pick up mid-conversation.
- ❌ Using any word from the Words-to-Avoid list in the prompt's own example lines.
- ❌ Fanning out one parallel subagent per bot when consistency matters — the shared blocks will diverge. Write the set in one pass, or define shared blocks first and pass them verbatim to each writer.

## Edge cases

- **Bilingual client** → mirror each bot into a second language agent (the templates ship `ENG_LLM_PROMPT` + `ESP_LLM_PROMPT`); keep the structure identical, translate the spoken lines, keep variables and tool references in place.
- **Onboarding submission as input** → follow the `buildForgeSeedFromSubmission` contract: treat uploaded docs as primary source for tone/FAQs/services; never invent beyond them.
- **Unknown qualification answer matters for routing** → ask one clarifying question, cap at two, then hand to the human team.
- **Single-bot client (no routing)** → produce just the one agent in the same house format; skip the orchestrator.

## Pair with

- `commit-with-heredoc` — commit the forged prompt set following convention.
- The game-app Prompt Studio / Conversation Bench — paste a forged prompt there to bench-test it against generated personas before shipping to the client.
- `/brainstorm` — when the qualification criteria or routing logic for a complex client isn't obvious yet.

# Writing card: STE-lite (80% of the way to ASD-STE100)

ASD-STE100 (Simplified Technical English) is a controlled English for aircraft maintenance
manuals. It makes text easy to read fast. This card is our own short version of the parts that
matter. It is the default for everything that reaches Zalo: Telegram replies, reports, summaries.

Check a draft: `python3 ~/.claude/skills/digest/scripts/ste-lint.py <file>` (or pipe it in).
Exit 0 is clean. Exit 1 lists each problem with its line. `--json` gives machine output.

## Sentences
- An instruction (it starts with a verb: "Open", "Run", "Send") has 20 words or fewer.
- A description has 25 words or fewer.
- Put one idea in each sentence. Two actions by two actors make two sentences.
- Use the active voice. Say who does the action: "The cron job sends the event", not "The event is sent".
- Use simple tenses: present, simple past, "will" for the future.
- Write instructions as commands: "Open the page." Not "You should open the page."

## Words
- Use one word for one thing, every time. If it is a "session", do not also call it a "run".
- Use the plain word: "use" not "utilize", "start" not "initiate", "help" not "facilitate".
- Use a plain verb, not a phrasal verb or an idiom: "start" not "kick off", "check" not "look into".
- Keep the articles ("a", "an", "the"). Do not write "Send event to GHL".
- Write ids, file names and event names exactly. Put them in `code` where the channel shows it.
- Write numbers as digits: "3 events", "49.2 s".
- Prefer words under 14 letters. A long technical term with no plain word (authentication, infrastructure) is fine.

## Layout
- Put the answer or the decision needed in the first line.
- Use a numbered list for steps in order. Use bullets for items in no order.
- Keep a paragraph or a list item to 4 sentences and 60 words or fewer.
- Use short headings in plain words.

## Zalo's rules on top
- No em dashes and no en dashes. Use a comma, a colon, a period, parentheses or "to".
- Make it phone readable: short lines, short paragraphs, no wide tables in Telegram.
- A status is a few lines, not a report. This card makes text clearer; it does not make it longer.

## The 80% part
The full spec also has a fixed dictionary of approved words and meanings. We do not enforce it.
Technical names stay as they are. An occasional sentence a little over the limit is fine when
splitting it would hurt the meaning: the lint flags it, and you decide.

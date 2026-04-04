---
name: Fine-tuning response style
description: Training data for setter/sales LLM must have varied lengths (single words to 2-3 sentences) like real SMS, and be vertical-agnostic
type: feedback
---

Responses in training data must be varied in length -- can be as short as a single word, a few words, or a couple sentences. Like a real human over SMS/DM. Not every response needs to be 2-4 sentences.

The fine-tuned LLM will be used as a general setter/sales/support agent for ANY business vertical, not just Black Umbrella's specific products. Training data must be universal and cover many different industries.

**Why:** The model needs to learn natural conversational cadence and adapt to any business, not just mimic one company's prompt.
**How to apply:** When creating training data, vary response lengths dramatically, cover diverse verticals, and keep the system prompt generic enough to be reusable across businesses.

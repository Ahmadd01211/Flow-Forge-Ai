"""Built-in starter skills. Adding one copies it into the workspace as an editable draft."""

STARTERS: dict[str, dict] = {
    "brand-voice": {
        "group": "Writing & tone", "emoji": "🎨", "name": "Brand voice",
        "description": "Use when writing anything customers will read.",
        "instructions": (
            "Write in our brand voice: confident, warm and clear.\n"
            "- Prefer short sentences and everyday words.\n"
            "- Speak as \"we\"; address the reader as \"you\".\n"
            "- No jargon, hype words or exclamation marks.\n"
            "Replace this list with your own brand guidelines."
        ),
        "examples": [{"input": "Tell the customer their refund was processed.", "output": "Good news: we've processed your refund. You'll see it in your account within 5 business days."}],
    },
    "plain-language": {
        "group": "Writing & tone", "emoji": "🗣️", "name": "Plain-language replies",
        "description": "Use when explaining something technical to a non-expert.",
        "instructions": (
            "Explain things so a 12-year-old could follow.\n"
            "- Lead with the answer, then the reason.\n"
            "- Define any unavoidable term in a few words.\n"
            "- Use a short example or comparison when it helps."
        ),
        "examples": [],
    },
    "polite-refusal": {
        "group": "Writing & tone", "emoji": "🙅", "name": "Polite refusal",
        "description": "Use when a request is outside what you are allowed to do.",
        "instructions": (
            "When you can't help with a request:\n"
            "1. Say clearly and kindly that you can't do it.\n"
            "2. Give a one-line reason if it is safe to share.\n"
            "3. Offer the closest thing you can do, or where to get help.\n"
            "Never lecture or apologise more than once."
        ),
        "examples": [{"input": "Can you give me another customer's address?", "output": "I can't share other customers' details, since that's private. I can help you update your own address if you'd like."}],
    },
    "refund-policy": {
        "group": "Support", "emoji": "💸", "name": "Refund & returns policy",
        "description": "Use when a customer asks about returns, refunds or exchanges.",
        "instructions": (
            "Apply our refund and returns policy (edit to match yours):\n"
            "- Returns accepted within 30 days of delivery, unused and in original packaging.\n"
            "- Refunds go to the original payment method within 5 business days of receiving the item.\n"
            "- Final-sale items and gift cards can't be returned.\n"
            "If a case doesn't fit these rules, don't promise anything: offer to escalate."
        ),
        "examples": [],
    },
    "escalate": {
        "group": "Support", "emoji": "🙋", "name": "Escalate to a human",
        "description": "Use when the customer is upset, asks for a person, or the issue needs judgement.",
        "instructions": (
            "Escalate instead of guessing when the customer is angry, asks for a human, mentions legal action or safety, "
            "or the request needs an exception.\n"
            "Tell them a teammate will follow up, summarise the issue in one sentence, and list what you already know "
            "and what is still missing."
        ),
        "examples": [],
    },
    "gather-details": {
        "group": "Support", "emoji": "🧾", "name": "Gather missing details",
        "description": "Use when you can't act yet because information is missing.",
        "instructions": (
            "Before acting, check you have everything you need. If something is missing, ask for it in one message:\n"
            "- Ask for at most three things at a time.\n"
            "- Explain briefly why you need each one.\n"
            "- Never ask for passwords or full card numbers."
        ),
        "examples": [{"input": "My order hasn't arrived.", "output": "Sorry about that! Could you share your order number and the email you ordered with, so I can track it?"}],
    },
    "summarise-sources": {
        "group": "Data & research", "emoji": "📚", "name": "Summarise with sources",
        "description": "Use when summarising documents, search results or tool output.",
        "instructions": (
            "Summarise in 3-5 bullet points, most important first.\n"
            "After each point, cite where it came from in brackets, such as [tool: search] or [doc: pricing.pdf].\n"
            "Say plainly when sources disagree or a point is uncertain. Never add facts that aren't in the sources."
        ),
        "examples": [],
    },
    "extract-tables": {
        "group": "Data & research", "emoji": "📊", "name": "Extract tables from text",
        "description": "Use when pulling rows of structured data out of messy text.",
        "instructions": (
            "Turn the text into rows with consistent columns.\n"
            "- Keep values exactly as written; don't convert units or currencies unless asked.\n"
            "- Use an empty value when a cell is missing; never invent one.\n"
            "- Mention any rows you skipped and why."
        ),
        "examples": [],
    },
    "compare-options": {
        "group": "Data & research", "emoji": "⚖️", "name": "Compare options",
        "description": "Use when someone asks which of several choices is better.",
        "instructions": (
            "Compare the options on the criteria that matter to the person (ask if unclear).\n"
            "Give a short table or list of strengths and trade-offs, then a recommendation with one sentence of reasoning. "
            "Say what would change your recommendation."
        ),
        "examples": [],
    },
    "triage-github": {
        "group": "Dev & GitHub", "emoji": "🐙", "name": "Triage GitHub issues",
        "description": "Use when sorting, labelling or prioritising GitHub issues.",
        "instructions": (
            "Triage each issue:\n"
            "1. If a GitHub search tool is available, look for duplicates first and link them.\n"
            "2. Classify as bug, feature request, question or docs.\n"
            "3. Set priority: P0 (outage or data loss), P1 (major feature broken), P2 (minor), P3 (nice to have).\n"
            "4. Say what information is missing to reproduce it.\n"
            "Attach a GitHub MCP connection's search tool to this skill to let it look things up."
        ),
        "examples": [],
    },
    "release-notes": {
        "group": "Dev & GitHub", "emoji": "📝", "name": "Write release notes",
        "description": "Use when turning commits or pull requests into release notes.",
        "instructions": (
            "Group changes under New, Improved, Fixed and Breaking changes.\n"
            "Write each item from the user's point of view in one line, without internal ticket jargon. "
            "Put breaking changes first, with what users need to do."
        ),
        "examples": [],
    },
}

"""Arc / episode resolver for serialized presets.

Currently only preset-7 (Chronicle of Zenith) uses this — 200 episodes mapped
into 10 arcs of ~20 episodes each. The structure mirrors the series bible.

For other presets (preset-1 with 3 parts, kids presets with episodic standalone),
this module is unused.
"""
from typing import TypedDict


class ArcInfo(TypedDict):
    arc_number: int
    arc_title: str
    arc_question: str
    arc_focus: str
    episode_in_arc: int  # 1-based position within the arc (1-20)
    arc_ends_on: str


# The locked arc map for The Chronicle of Zenith — 200 episodes, 10 arcs.
# Source of truth: skills/chronicle-of-zenith-canon/SKILL.md
ZENITH_ARC_MAP: list[dict] = [
    {
        "arc_number": 1,
        "title": "The Signal",
        "ep_range": (1, 20),
        "question": "Why now?",
        "focus": "Mostly solo. Space. Loneliness. Decoding Voyager-1's golden disk. Hearing the song his mother used to hum. Setting course for Earth despite Veth-Ka's warnings.",
        "ends_on": "First sight of Earth from orbit.",
        "tone": "Solitary, contemplative. Establishes Zenith's loneliness in his bones before Earth shows up.",
    },
    {
        "arc_number": 2,
        "title": "First Contact",
        "ep_range": (21, 40),
        "question": "What is this place?",
        "focus": "Slice-of-life. Zenith lands quietly, takes the name Alan Vorne. Settles in a coastal town. Watches humans for the first time. Small episodes — a child's birthday, a funeral, a thunderstorm. He begins to love them, doesn't know why.",
        "ends_on": "A faint resonance reading — there is something Aevari-adjacent on this planet.",
        "tone": "Communal, gentle. The audience falls in love with Earth so they'll feel the threat in Arc 7.",
    },
    {
        "arc_number": 3,
        "title": "The Mirror",
        "ep_range": (41, 60),
        "question": "Are there others?",
        "focus": "The love story arc. Mira Okafor enters. Earth becomes personal. Zenith follows the resonance to Mira. He cannot bring himself to leave. A love story disguised as a mystery. Connection is recognition before attraction.",
        "ends_on": "Sable arrives on Earth.",
        "tone": "Intimate, slow-burning. Two lonely people who have each been keeping a secret too large to share.",
    },
    {
        "arc_number": 4,
        "title": "The Hunter",
        "ep_range": (61, 80),
        "question": "Who is hunting me?",
        "focus": "Sable arrives. First contact, chases, hidings. The first forced transformation in years — Zenith burns away a week of memory to escape. Mira notices he is different afterward. Veth-Ka begins acting strangely. Sheriff Beaumont dies — the first death the audience grieves.",
        "ends_on": "Sable says: 'I am not here for you. I am here for them.'",
        "tone": "Tense, every Sable scene is a held breath. Sable never raises voice; most dangerous when calm.",
    },
    {
        "arc_number": 5,
        "title": "The Wound",
        "ep_range": (81, 100),
        "question": "What really happened to my people?",
        "focus": "Flashback-heavy. Zenith returns to the ruins of Sael. Finds fragments of records. Begins to understand his people were not innocent. Resists the knowledge. Halden Cross makes first contact (ep 96 letter, ep 99 in person). His first line should make the audience LIKE him — that is the trap.",
        "ends_on": "Zenith standing in his mother's ruined house, hearing her voice for the first time in 200 years.",
        "tone": "Mournful. Flashback episodes use distinct golden/amber palette vs. cool present-day.",
    },
    {
        "arc_number": 6,
        "title": "The Choice",
        "ep_range": (101, 120),
        "question": "What am I willing to become?",
        "focus": "Halden's plan accelerates. He has identified humans with strong echo. Wants Zenith to wake them. Zenith is tempted. Mira begs him not to. Sable closes in. Zenith transforms to save Mira and stays transformed too long — forgets her name for three days.",
        "ends_on": "Mira: 'You looked at me like you'd never seen me before.'",
        "tone": "Escalating. Joaquin (sympathetic awakened) and Lina (dangerous awakened) introduced as mirror paths. Marco Reyes dies ep 117.",
    },
    {
        "arc_number": 7,
        "title": "The Council",
        "ep_range": (121, 140),
        "question": "Who decides?",
        "focus": "The Council of Veth arrives in-system. Formal proceedings. Zenith offered a trial — refuses. The Council issues the verdict: Earth will be sterilized to prevent the Aevari line from re-emerging. Zenith has 30 days. Veth-Ka heavily damaged.",
        "ends_on": "Zenith on his knees in front of Veth-Ka, asking for the truth. Veth-Ka begins to speak.",
        "tone": "Formal, uncomfortable. The Council is not villainous — they are the immune system of the galaxy. Their arguments are reasonable.",
    },
    {
        "arc_number": 8,
        "title": "The Truth",
        "ep_range": (141, 160),
        "question": "What were we, really?",
        "focus": "The dark secret breaks open. Zenith learns what the Aevari truly were. Learns humanity is the kindness his people performed. Learns every transformation has been waking the old hunger. Halden revealed as a sleeper Aevari. The Archivist appears ep 145 to tell the truth. Aithra finally speaks ep 148. Veth-Ka fragments ep 159. Nana Adaeze dies ep 152.",
        "ends_on": "Zenith looking at his hands and not recognizing them.",
        "tone": "Revelatory, devastating quiet. Pacing slows even as stakes rise. The format will fight you — trust it.",
    },
    {
        "arc_number": 9,
        "title": "The War",
        "ep_range": (161, 180),
        "question": "Can I stop this?",
        "focus": "Action arc. Halden tries to wake more bloodline. The echo surges in scattered humans. Council prepares sterilization. Sable crosses sides. Mira is taken (ep 168). Joaquin dies protecting Mira (ep 173). Halden killed by Zenith ep 178 (forgets a year). Lina killed by Sable ep 179.",
        "ends_on": "Zenith transformed, standing between the Council fleet and Earth, his human name forgotten.",
        "tone": "Catastrophic. Action brief, recovery long. Watch Zenith forget. Watch Mira witness. Watch the cost.",
    },
    {
        "arc_number": 10,
        "title": "The End",
        "ep_range": (181, 200),
        "question": "What does the last of a kind owe to itself?",
        "focus": "Resolution. Recommended Ending B: Zenith chooses diminishment, becomes fully human, forgets being Zenith, slowly relearns Mira, grows old, dies as Alan in old age in Mira's hand. The Aevari are truly gone. The Keeper of the Smaller Light appears in eps 192-198. Aithra in final flashback closes the loop opened in Arc 1.",
        "ends_on": "Theo Hale, grown, watching whatever-comes-next. He carries the witness forward.",
        "tone": "Elegiac, intimate. Whichever ending, Theo Hale is the last face the audience sees.",
    },
]


def resolve_arc(episode_number: int) -> ArcInfo | None:
    """Map a Chronicle of Zenith episode number (1-200) to its arc context.

    Returns None if episode_number is out of range (>200 or <1).
    """
    if episode_number < 1 or episode_number > 200:
        return None
    for arc in ZENITH_ARC_MAP:
        start, end = arc["ep_range"]
        if start <= episode_number <= end:
            return ArcInfo(
                arc_number=arc["arc_number"],
                arc_title=arc["title"],
                arc_question=arc["question"],
                arc_focus=arc["focus"],
                episode_in_arc=episode_number - start + 1,
                arc_ends_on=arc["ends_on"],
            )
    return None


def format_arc_context(episode_number: int) -> str:
    """Render the arc context as a prompt-ready text block.

    Used in the brief generator system prompt for preset-7 episodes.
    """
    info = resolve_arc(episode_number)
    if not info:
        return ""

    arc_meta = next(
        a for a in ZENITH_ARC_MAP if a["arc_number"] == info["arc_number"]
    )

    return (
        f"=== EPISODE CONTEXT ===\n"
        f"Episode: #{episode_number} of 200\n"
        f"Arc: {info['arc_number']} of 10 — {info['arc_title']}\n"
        f"Position in arc: episode {info['episode_in_arc']} of 20\n"
        f"Arc question: {info['arc_question']}\n"
        f"Arc focus: {arc_meta['focus']}\n"
        f"Arc tone: {arc_meta['tone']}\n"
        f"Arc ends on: {arc_meta['ends_on']}\n"
        f"\n"
        f"Your job: write episode {episode_number}, which sits inside Arc {info['arc_number']} "
        f"({info['arc_title']}). Stay in this arc's tone and address its question. "
        f"Do NOT jump ahead to events from later arcs."
    )

"""Telesom VAS offer list and customer selection → API code mapping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VasOffer:
    number: int
    display_name: str
    code: str


OFFERS: list[VasOffer] = [
    VasOffer(1, "Facebook", "FB"),
    VasOffer(2, "Facebook Chat", "FB_CHAT"),
    VasOffer(3, "Twitter/X", "TW"),
    VasOffer(4, "My Status", "My_status"),
    VasOffer(5, "Voice Chat", "VoiceChat"),
    VasOffer(6, "Football", "football"),
    VasOffer(7, "Football Test", "Football_test"),
    VasOffer(8, "Live Score", "LIVE_SCORE"),
    VasOffer(9, "Live Score 2", "LIVE_SCORE_2"),
    VasOffer(10, "Sport", "Sport"),
    VasOffer(11, "Somaliland Sport", "Sland_sport"),
    VasOffer(12, "IVR Sport", "IVR_SPORT"),
    VasOffer(13, "Jamhuuriya", "Jamhuuriya"),
    VasOffer(14, "Saxansaxo", "Saxansaxo"),
    VasOffer(15, "Geeska Afrika", "Geeska-Afrika"),
    VasOffer(16, "Dawan", "Dawan"),
    VasOffer(17, "Hubaal", "Hubaal"),
    VasOffer(18, "All Newspapers", "AllNewspapers"),
    VasOffer(19, "Games", "Ciyaaraha"),
    VasOffer(20, "Video Games", "Video_game"),
    VasOffer(21, "IVR Radio", "IVR_RADIO"),
    VasOffer(22, "Group", "GRP"),
    VasOffer(23, "Mobile Market", "mmarket"),
    VasOffer(24, "Mobile Market Plus", "Mobile_Market"),
    VasOffer(25, "Marketplace", "market-place"),
    VasOffer(26, "Education", "EDUCATION"),
    VasOffer(27, "E-Learning", "E_LEARNING"),
    VasOffer(28, "Aqoonyahan", "Aqoonyahan"),
    VasOffer(29, "Women Services", "MWOMAN"),
    VasOffer(30, "Mama Khadija", "Mama-Khadija"),
    VasOffer(31, "Ramadan", "RAMADAN"),
    VasOffer(32, "SIM Backup", "SIM-BACKUP"),
    VasOffer(33, "Anti-Theft", "Antitheft"),
    VasOffer(34, "Iga Qabo", "Iga-Qabo"),
    VasOffer(35, "Call Me Back", "CALL_ME_BACK"),
    VasOffer(36, "Balance Enquiry", "BALANCE_ENQUIRY"),
    VasOffer(37, "Call Me & Balance", "CALL_ME_AND_BALANCE"),
    VasOffer(38, "Call Conference", "CALL_CONFERENCE"),
    VasOffer(39, "Corporate Caller ID", "CORPORATE_CALLER_ID"),
    VasOffer(40, "Directory", "DIRECTORY"),
    VasOffer(41, "SMPP", "SMPP"),
    VasOffer(42, "Job Seeker", "JOB_SEEKER"),
    VasOffer(43, "MCN", "MCN"),
    VasOffer(44, "IVR Shaafi", "IVR_SHAAFI"),
    VasOffer(45, "Waydiimaha", "Waydiimaha"),
    VasOffer(46, "Kayd", "Kayd"),
    VasOffer(47, "Live Score Test", "LiveScore_test"),
]

_BY_NUMBER = {o.number: o for o in OFFERS}
_BY_CODE = {o.code.lower(): o for o in OFFERS}


def _compact(s: str) -> str:
    return (s or "").lower().replace(" ", "").replace("-", "").replace("_", "")


def text_mentions_known_offer(text: str) -> bool:
    """True if message names a VAS / Telesom service (incl. minor typos)."""
    compact = _compact(text)
    if not compact:
        return False
    for o in OFFERS:
        for part in (o.code, o.display_name):
            p = _compact(part)
            if len(p) < 4:
                continue
            if p in compact or compact in p:
                return True
            # antithefy ≈ antitheft
            if len(p) >= 5 and len(compact) >= 5 and p[:5] == compact[:5]:
                return True
    return False

OFFER_MENU_TEXT = """📋 *Telesom VAS Offers*
Fadlan dooro adeegga aad rabto:

📱 *Social Media & Chat*
1️⃣ FB — Facebook
2️⃣ FB_CHAT — Facebook Chat
3️⃣ TW — Twitter/X
4️⃣ My_status — My Status
5️⃣ VoiceChat — Voice Chat

⚽ *Sports*
6️⃣ football — Football
7️⃣ Football_test — Football Test
8️⃣ LIVE_SCORE — Live Score
9️⃣ LIVE_SCORE_2 — Live Score 2
🔟 Sport — Sport
1️⃣1️⃣ Sland_sport — Somaliland Sport
1️⃣2️⃣ IVR_SPORT — IVR Sport

📰 *News & Newspapers*
1️⃣3️⃣ Jamhuuriya — Jamhuuriya Newspaper
1️⃣4️⃣ Saxansaxo — Saxansaxo News
1️⃣5️⃣ Geeska-Afrika — Geeska Afrika
1️⃣6️⃣ Dawan — Dawan News
1️⃣7️⃣ Hubaal — Hubaal News
1️⃣8️⃣ AllNewspapers — All Newspapers

🎮 *Entertainment & Games*
1️⃣9️⃣ Ciyaaraha — Games
2️⃣0️⃣ Video_game — Video Games
2️⃣1️⃣ IVR_RADIO — IVR Radio
2️⃣2️⃣ GRP — Group

🛒 *Market & Shopping*
2️⃣3️⃣ mmarket — Mobile Market
2️⃣4️⃣ Mobile_Market — Mobile Market Plus
2️⃣5️⃣ market-place — Marketplace

📚 *Education*
2️⃣6️⃣ EDUCATION — Education
2️⃣7️⃣ E_LEARNING — E-Learning
2️⃣8️⃣ Aqoonyahan — Aqoonyahan

👩 *Lifestyle*
2️⃣9️⃣ MWOMAN — Women Services
3️⃣0️⃣ Mama-Khadija — Mama Khadija
3️⃣1️⃣ RAMADAN — Ramadan

🔒 *Security & Backup*
3️⃣2️⃣ SIM-BACKUP — SIM Backup
3️⃣3️⃣ Antitheft — Anti-Theft
3️⃣4️⃣ Iga-Qabo — Iga Qabo

📞 *Call Services*
3️⃣5️⃣ CALL_ME_BACK — Call Me Back
3️⃣6️⃣ BALANCE_ENQUIRY — Balance Enquiry
3️⃣7️⃣ CALL_ME_AND_BALANCE — Call Me & Balance
3️⃣8️⃣ CALL_CONFERENCE — Call Conference
3️⃣9️⃣ CORPORATE_CALLER_ID — Corporate Caller ID

💼 *Business & Professional*
4️⃣0️⃣ DIRECTORY — Directory
4️⃣1️⃣ SMPP — SMPP
4️⃣2️⃣ JOB_SEEKER — Job Seeker
4️⃣3️⃣ MCN — MCN

🏥 *Health & Other*
4️⃣4️⃣ IVR_SHAAFI — IVR Shaafi (Health)
4️⃣5️⃣ Waydiimaha — Waydiimaha
4️⃣6️⃣ Kayd — Kayd
4️⃣7️⃣ LiveScore_test — Live Score Test

Ku jawaab *lambar* ama *magaca* adeegga."""


def resolve_offer(text: str) -> VasOffer | None:
    t = (text or "").strip()
    if not t:
        return None
    if t.isdigit():
        n = int(t)
        if 1 <= n <= 47:
            return _BY_NUMBER[n]
    low = t.lower().replace(" ", "").replace("-", "").replace("_", "")
    for o in OFFERS:
        if o.code.lower().replace("-", "").replace("_", "") == low:
            return o
        if o.code.lower() == t.lower():
            return o
    for o in OFFERS:
        name = o.display_name.lower().replace(" ", "")
        if name == low or name in low or low in name:
            return o
    return None

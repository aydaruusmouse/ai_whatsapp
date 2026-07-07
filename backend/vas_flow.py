"""Telesom VAS + service API conversation flows (WhatsApp-style)."""

from __future__ import annotations

import re
from typing import Any

from flow_state import get_meta, reset_flow, set_meta
from telesom_api import (
    TelesomAPIError,
    _friendly_api_error,
    block_wrong_transaction,
    check_subscription,
    get_exchange_rate,
    new_fiber_installation,
    subscribe,
    unsubscribe,
)
from vas_offers import OFFER_MENU_TEXT, VasOffer, resolve_offer

MAIN_MENU = """Ku soo dhawoow Telesom! Sideen kuu caawin karaa?

1️⃣ *VAS Offers* — subscribe / unsubscribe adeegyo
2️⃣ *Sarifka* — exchange rate maanta
3️⃣ *Xannib lacag khaldan* — block wrong transaction
4️⃣ *Fiber cusub* — dalab rakibid fiber internet
5️⃣ *Su'aal guud* — weydii wax kale oo Telesom ah

Ku jawaab lambar ama qor waxa aad rabto (tusaale: *VAS*, *subscribe*, *exchange*, *lacag qaldan*)."""


BLOCK_GUIDE_INTRO = """Waan fahmay — waxaad cabanaysaa *lacag qaldan* / lacag loo diray lambarka khaldan.

Waxaan kaa caawinayaa *in la xannibo* (block) lacag-bixintaas haddii ay suurtogal tahay.

Waxaad u baahan tahay:
• *Tixraaca lacag-bixinta* (SMS tixraac — tusaale TXN123456, **ma aha** lambarka taleefanka)
• *Lambarka khaldan* ee lacagta loo diray
• *Lacagta*: Dollar ama Shilling

Lambarkaaga waan haynaa — bilow tixraaca:"""


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _is_yes(s: str) -> bool:
    t = _norm(s)
    return t in {"yes", "y", "haa", "h", "ok", "okay", "confirm", "proceed", "waa", "waa haa"}


def _is_no(s: str) -> bool:
    t = _norm(s)
    return t in {"no", "n", "maya", "cancel", "stop", "iska daa"}


def _is_subscribe(s: str) -> bool:
    t = _norm(s)
    return t in {"1", "subscribe", "is diiwaan geli", "diiwaangeli", "ku biir", "subscribe 1"}


def _is_unsubscribe(s: str) -> bool:
    t = _norm(s)
    return t in {"2", "unsubscribe", "ka bax", "jooji", "unsubscribe 2"}


def _phone_required() -> str:
    return (
        "Lambarkaaga WhatsApp lama helin. Fadlan WhatsApp ka isticmaal ama "
        "(tijaabo web) geli lambarkaaga sidebar-ka."
    )


def _save_phone(session_id: str, phone: str | None) -> str | None:
    if not phone or not phone.strip():
        return None
    set_meta(session_id, customer_phone=phone.strip())
    return phone.strip()


def _get_phone(session_id: str, customer_phone: str | None) -> str | None:
    if customer_phone and customer_phone.strip():
        _save_phone(session_id, customer_phone)
    meta = get_meta(session_id)
    p = meta.get("customer_phone")
    return p.strip() if p else None


def _is_general_telesom_info_query(text: str) -> bool:
    """Macmiil wuxuu rabaa macluumaad guud oo Telesom ah — ma aha VAS subscribe."""
    t = _norm(text)
    if "vas" in t and any(k in t for k in ("subscribe", "unsubscribe", "offer", "diiwaan", "ku biir", "ka bax")):
        return False
    if "telesom" not in t:
        return False
    if any(
        p in t
        for p in (
            "maxay telesom qabataa",
            "maxay telesom qabato",
            "waxa telesom qabato",
            "waxa telesom sameyso",
            "waxa ay telesom qabato",
            "adeegyada telesom",
            "adeegyada shirkadda",
            "what does telesom",
            "what is telesom",
            "telesom services",
            "about telesom",
        )
    ):
        return True
    if "adeeg" in t or "adeegyada" in t or "service" in t or "services" in t:
        return True
    if any(w in t for w in ("qabataa", "qabato", "qabtaa", "sameyso", "sameysaa", "bixisaa", "bixiyo")):
        return True
    return False


def _wants_vas_menu(text: str) -> bool:
    """Kaliya marka macmiilku si cad u weydiiyo VAS subscribe/unsubscribe."""
    t = _norm(text)
    if t in {"1", "vas", "subscribe", "unsubscribe", "vas offers", "vas offer"}:
        return True
    explicit = (
        "vas offers",
        "vas offer",
        "vas subscribe",
        "vas unsubscribe",
        "subscribe vas",
        "unsubscribe vas",
        "is diiwaan geli",
        "diiwaangeli",
        "ku biir",
        "ka bax adeeg",
        "unsubscribe garee",
        "dooro adeeg",
        "dooro vas",
    )
    return any(k in t for k in explicit)


def _wants_exchange(text: str) -> bool:
    t = _norm(text)
    return any(
        k in t
        for k in ("exchange", "sarif", "rate", "dollar", "shilling", "2", "qiimaha sarifka")
    )


def _wants_block(text: str) -> bool:
    """Detect wrong-money complaints / block-transaction intent (Somali + English)."""
    t = _norm(text)
    if t in {"3", "block", "xannib"}:
        return True

    phrases = (
        # Somali — lacag qaldan / cabasho
        "lacagba iga qaldantey",
        "lacagba iga qaldantay",
        "lacag iga qaldantey",
        "lacag iga qaldantay",
        "lacag iga qaldamay",
        "lacag ii qaldantay",
        "lacag i qaldantay",
        "lacag qaldantey",
        "lacag qaldantay",
        "lacag qaldan",
        "lacag khaldan",
        "lacag khalad",
        "lacag khalday",
        "lacag qaldan tahay",
        "lacag khaldan tahay",
        "lacag i xayir",
        "lacag ii xayir",
        "lacag xayir",
        "lacag i xannib",
        "lacag xannib",
        "lacag xanniba",
        "iga qaldantey",
        "iga qaldantay",
        "waxaan u diray qaldan",
        "waxaan u diray khaldan",
        "waxaan diray qaldan",
        "lacag u diray qaldan",
        "loo diray qaldan",
        "tixraac khaldan",
        "tixraac qaldan",
        "cabasho lacag",
        "lacag cabasho",
        "cabashada lacag",
        "cabasho ku saabsan lacag",
        "wax ku saabsan cabasho lacag",
        "wax ku saabsan lacag qaldan",
        "lacag qaldan ah",
        "lacag khaldan ah",
        # English
        "block wrong transaction",
        "wrong transaction",
        "wrong money",
        "sent to wrong number",
        "sent money wrong",
        "money to wrong number",
        "block transaction",
        "block my money",
        "wrong transfer",
        "mistaken transfer",
    )
    if any(p in t for p in phrases):
        return True

    money = ("lacag", "lacagta", "money", "zaad", "evc", "tixraac", "transfer")
    wrong = ("qaldan", "khaldan", "qaldantey", "qaldantay", "qaldamay", "khaldamay", "khalad", "wrong", "mistake")
    block = ("xayir", "xannib", "xanniba", "block", "jooji", "stop", "hold")
    complaint = ("cabasho", "cabashada", "complaint", "caban", "cabsi")

    has_money = any(w in t for w in money)
    has_wrong = any(w in t for w in wrong)
    has_block = any(w in t for w in block)
    has_complaint = any(w in t for w in complaint)

    if has_money and has_wrong:
        return True
    if has_money and has_block:
        return True
    if has_complaint and has_money:
        return True
    if has_complaint and has_wrong:
        return True
    if "block" in t or "xannib" in t:
        if has_money or "transaction" in t:
            return True
    return False


def _start_block_flow(session_id: str) -> str:
    set_meta(session_id, flow_state="block_await_txn", flow_data={})
    return f"{BLOCK_GUIDE_INTRO}\n\n1️⃣ Geli *tixraaca lacag-bixinta*:"


def _wants_fiber(text: str) -> bool:
    t = _norm(text)
    phrases = (
        "internet ma i xidhi kartaa",
        "internet ii xidh",
        "internet i xidh",
        "fiber cusub",
        "rakib internet",
        "rakibid internet",
        "fiber rakib",
        "new fiber",
        "fiber installation",
        "install fiber",
        "broadband",
    )
    if any(p in t for p in phrases):
        return True
    if t in {"4", "fiber"}:
        return True
    if "fiber" in t or "rakib" in t or "rakibid" in t:
        return True
    if "internet" in t and any(k in t for k in ("xidh", "xir", "rakib", "install", "cusub", "fiber")):
        return True
    return False


def _fiber_confirm_prompt(data: dict[str, Any]) -> str:
    return (
        "⚠️ *Xaqiiji dalabka rakibidda fiber:*\n"
        f"📍 Cinwaan: {data.get('address', '')}\n"
        f"⚡ Xawaare: {data.get('speed', '')}\n"
        f"💳 Lacag bixin: {data.get('payment_method', '')}\n"
        f"💵 Nooca lacagta: {data.get('tran_type', '')}\n\n"
        "Ma sax baa? (Haa / Maya)"
    )


def _fiber_missing_fields(data: dict[str, Any]) -> list[str]:
    missing = []
    if not (data.get("address") or "").strip():
        missing.append("cinwaan")
    if not (data.get("speed") or "").strip():
        missing.append("xawaare")
    if not (data.get("payment_method") or "").strip():
        missing.append("habka lacag bixinta")
    if not (data.get("tran_type") or "").strip():
        missing.append("Dollar/Shilling")
    return missing


def _fiber_api_user_message(res: dict[str, Any]) -> str:
    msg = str(res.get("message") or "").strip()
    low = msg.lower()
    if str(res.get("status")) == "1":
        return f"✅ {msg or 'Dalabka rakibidda fiber waa la gudbiyey.'}"
    if "balance" in low and "sufficient" in low:
        return (
            "⚠️ Lacagta koontadaadu kugu filna ma aha. "
            "Fadlan ku shubi Zaad kadibna isku day mar kale."
        )
    if "pin" in low or "rejected" in low:
        return "Lama xaqiijin karin akoonkaaga. Fadlan la xiriir taageerada Telesom *151#."
    if msg:
        return f"⚠️ {msg}"
    return "Codsiga lama gudbin karin. Fadlan isku day mar kale."


def _submit_fiber(session_id: str, phone: str, data: dict[str, Any]) -> str:
    missing = _fiber_missing_fields(data)
    if missing:
        reset_flow(session_id)
        return f"Waxaa ka maqan: {', '.join(missing)}. Fadlan bilow mar kale 'fiber' ama 'internet'."
    try:
        res = new_fiber_installation(
            phone,
            address=data["address"],
            speed=data["speed"],
            payment_method=data["payment_method"],
            tran_type=data["tran_type"],
            contact_number=phone,
        )
    except TelesomAPIError as e:
        reset_flow(session_id)
        return _api_fail(e)
    reset_flow(session_id)
    return _fiber_api_user_message(res)


def _start_fiber_flow(session_id: str) -> str:
    set_meta(session_id, flow_state="fiber_await_address", flow_data={})
    return (
        "Si aan u gudbino dalabka *rakibidda fiber internet*, fadlan bixi:\n\n"
        "1️⃣ *Cinwaanka rakibidda* (address) — tusaale: Hargeisa, 26 June"
    )


def _format_exchange(data: dict[str, Any]) -> str:
    try:
        rate = int(data.get("ExchangeRate", 0))
        modified = str(data.get("ModifiedDate", ""))[:10]
        return (
            f"💱 *Today's Exchange Rate*\n"
            f"💵 1 USD = {rate:,} Somali Shillings\n"
            f"🗓 Last updated: {modified}"
        )
    except (TypeError, ValueError):
        return f"💱 *Exchange Rate*\n{data}"


def _sub_unsub_prompt(offer: VasOffer) -> str:
    return (
        f"Waxaad dooratay *{offer.display_name}* ({offer.code}).\n"
        "Maxaad rabtaa?\n"
        "1️⃣ Subscribe\n"
        "2️⃣ Unsubscribe"
    )


def _api_fail(exc: TelesomAPIError) -> str:
    return _friendly_api_error(exc)


def _normalize_somali_phone(s: str) -> str:
    """252XXXXXXXXX for API wrongnumber (API also cleans msisdn)."""
    digits = re.sub(r"\D", "", s or "")
    if digits.startswith("252"):
        return digits
    if len(digits) == 9 and digits.startswith("6"):
        return "252" + digits
    return (s or "").strip()


def _handle_subscribe(phone: str, offer: VasOffer) -> str:
    try:
        chk = check_subscription(phone, offer.code)
    except TelesomAPIError as e:
        return _api_fail(e)
    subscribed = chk.get("data") is True
    if subscribed:
        return (
            f"⚠️ Waxaad horey ugu diiwaangashan tahay *{offer.display_name}* ({offer.code}).\n"
            "Ma rabtaa inaad ka baxdo? (Haa/Maya)"
        )
    try:
        res = subscribe(phone, offer.code)
    except TelesomAPIError as e:
        return _api_fail(e)
    if res.get("success") is True:
        msg = res.get("message") or "Subscribed successfully."
        return f"✅ {msg}\n*{offer.display_name}* ({offer.code})"
    msg = res.get("message") or "Lama diiwaan gelin karin. Fadlan isku day mar kale."
    return f"⚠️ {msg}"


def _handle_unsubscribe(phone: str, offer: VasOffer) -> str:
    try:
        chk = check_subscription(phone, offer.code)
    except TelesomAPIError as e:
        return _api_fail(e)
    subscribed = chk.get("data") is True
    if not subscribed:
        return f"Ma aadan ku diiwaangashanayn *{offer.display_name}* ({offer.code})."
    try:
        res = unsubscribe(phone, offer.code)
    except TelesomAPIError as e:
        return _api_fail(e)
    if res.get("result") == "ok":
        msg = res.get("message") or "Unsubscribed successfully."
        return f"✅ {msg}\n*{offer.display_name}*"
    msg = res.get("message") or "Lama joojin karin. Fadlan isku day mar kale."
    return f"⚠️ {msg}"


def _parse_currency(text: str) -> str | None:
    t = _norm(text)
    if "dollar" in t or "usd" in t:
        return "Dollar"
    if "shilling" in t or "shilin" in t or "sl" in t:
        return "Shilling"
    return None


def _parse_speed(text: str) -> str | None:
    t = text.upper().replace(" ", "")
    for s in ("10MB", "20MB", "50MB"):
        if s in t:
            return s
    m = re.search(r"(10|20|50)\s*mb", text, re.I)
    if m:
        return f"{m.group(1)}MB"
    return None


def _parse_payment(text: str) -> str | None:
    t = _norm(text)
    if "zaad" in t:
        return "Zaad"
    if "cash" in t:
        return "Cash"
    return None


def handle_vas_flow(
    session_id: str,
    user_message: str,
    customer_phone: str | None,
    *,
    skip_vas_menu: bool = False,
) -> str | None:
    """
    Run Telesom API flows. Returns reply text if handled, else None (fall through to LLM).
    """
    text = (user_message or "").strip()
    if not text:
        return None

    phone = _get_phone(session_id, customer_phone)
    meta = get_meta(session_id)
    state = meta["flow_state"]
    data: dict[str, Any] = dict(meta["flow_data"])

    # --- Active flows ---
    if state == "await_offer":
        if skip_vas_menu and _is_general_telesom_info_query(text):
            reset_flow(session_id)
            return None
        offer = resolve_offer(text)
        if not offer:
            return (
                "Lama aqoonsan doorashadaada. Fadlan ku jawaab lambar (1–47) ama magaca adeegga.\n\n"
                + OFFER_MENU_TEXT
            )
        data["offer_code"] = offer.code
        data["offer_name"] = offer.display_name
        set_meta(session_id, flow_state="await_sub_unsub", flow_data=data)
        return _sub_unsub_prompt(offer)

    if state == "await_sub_unsub":
        offer = VasOffer(0, data.get("offer_name", ""), data.get("offer_code", ""))
        if not offer.code:
            reset_flow(session_id)
            return OFFER_MENU_TEXT
        if not phone:
            reset_flow(session_id)
            return _phone_required()
        if _is_subscribe(text):
            reply = _handle_subscribe(phone, offer)
            if "Ma rabtaa inaad ka baxdo" in reply:
                set_meta(session_id, flow_state="await_unsub_after_subscribed", flow_data=data)
            else:
                reset_flow(session_id)
            return reply
        if _is_unsubscribe(text):
            try:
                chk = check_subscription(phone, offer.code)
            except TelesomAPIError as e:
                return _api_fail(e)
            if chk.get("data") is not True:
                reset_flow(session_id)
                return f"Ma aadan ku diiwaangashanayn *{offer.display_name}* ({offer.code})."
            set_meta(session_id, flow_state="await_unsub_confirm", flow_data=data)
            return f"⚠️ Ma hubtaa inaad ka baxdo *{offer.display_name}*? (Haa/Maya)"
        return "Fadlan dooro:\n1️⃣ Subscribe\n2️⃣ Unsubscribe"

    if state == "await_unsub_confirm":
        offer = VasOffer(0, data.get("offer_name", ""), data.get("offer_code", ""))
        if _is_yes(text):
            reply = _handle_unsubscribe(phone or "", offer)
            reset_flow(session_id)
            return reply
        if _is_no(text):
            reset_flow(session_id)
            return "Waa la joojiyey. Ma jiraan wax kale oo aan kuu qaban karo?"
        return "Fadlan ku jawaab *Haa* ama *Maya*."

    if state == "await_unsub_after_subscribed":
        offer = VasOffer(0, data.get("offer_name", ""), data.get("offer_code", ""))
        if _is_yes(text):
            set_meta(session_id, flow_state="await_unsub_confirm", flow_data=data)
            return f"⚠️ Ma hubtaa inaad ka baxdo *{offer.display_name}*? (Haa/Maya)"
        reset_flow(session_id)
        return "Waa hagaag. Ma jiraan wax kale oo aan kuu qaban karo?"

    if state == "block_await_txn":
        data["transactionnumber"] = text.strip()
        set_meta(session_id, flow_state="block_await_wrong", flow_data=data)
        return (
            "2️⃣ Geli lambarka *khaldan* ee aad lacagta u dirtay "
            "(tusaale 634XXXXXX ama 25263XXXXXXX):"
        )

    if state == "block_await_wrong":
        data["wrongnumber"] = text.strip()
        set_meta(session_id, flow_state="block_await_currency", flow_data=data)
        return "3️⃣ Dooro lacagta: *Dollar* ama *Shilling*"

    if state == "block_await_currency":
        cur = _parse_currency(text)
        if not cur:
            return "Fadlan qor *Dollar* ama *Shilling*."
        data["currency_code"] = cur
        set_meta(session_id, flow_state="block_confirm", flow_data=data)
        return (
            "⚠️ *Xaqiiji xannibaadda:*\n"
            f"📋 Transaction: {data.get('transactionnumber')}\n"
            f"📱 Wrong number: {data.get('wrongnumber')}\n"
            f"💵 Currency: {cur}\n"
            "Proceed? (Haa/Maya)"
        )

    if state == "block_confirm":
        if _is_no(text):
            reset_flow(session_id)
            return "Waa la joojiyey."
        if not _is_yes(text):
            return "Fadlan ku jawaab *Haa* ama *Maya*."
        if not phone:
            reset_flow(session_id)
            return _phone_required()
        try:
            res = block_wrong_transaction(
                phone,
                data["transactionnumber"].strip(),
                _normalize_somali_phone(data["wrongnumber"]),
                data["currency_code"],
            )
        except TelesomAPIError as e:
            reset_flow(session_id)
            return _api_fail(e)
        reset_flow(session_id)
        if str(res.get("status")) == "1":
            return res.get("message") or "Transaction blocked successfully."
        msg = res.get("message") or "Lama xannibi karin."
        if "khadlan" in msg.lower() or "invalid" in msg.lower():
            return (
                "Tixraaca lacag-bixinta waa khalad. Fadlan hubi oo mar kale isku day.\n"
                f"({msg})"
            )
        return f"⚠️ {msg}"

    if state == "fiber_await_address":
        data["address"] = text.strip()
        set_meta(session_id, flow_state="fiber_await_speed", flow_data=data)
        return "2️⃣ Dooro xawaaraha: *10MB* / *20MB* / *50MB*"

    if state == "fiber_await_speed":
        speed = _parse_speed(text)
        if not speed:
            return "Fadlan dooro: 10MB, 20MB, ama 50MB."
        data["speed"] = speed
        set_meta(session_id, flow_state="fiber_await_payment", flow_data=data)
        return "3️⃣ Habka lacag bixinta: *Cash* / *Zaad*"

    if state == "fiber_await_payment":
        pay = _parse_payment(text)
        if not pay:
            return "Fadlan qor: Cash ama Zaad."
        data["payment_method"] = pay
        set_meta(session_id, flow_state="fiber_await_currency", flow_data=data)
        return "4️⃣ Lacagta: *Dollar* ama *Shilling*"

    if state == "fiber_await_currency":
        cur = _parse_currency(text)
        if not cur:
            return "Fadlan qor *Dollar* ama *Shilling*."
        data["tran_type"] = cur
        if not phone:
            return _phone_required()
        missing = _fiber_missing_fields(data)
        if missing:
            return f"Waxaa ka maqan: {', '.join(missing)}. Fadlan bilow mar kale."
        set_meta(session_id, flow_state="fiber_confirm", flow_data=data)
        return _fiber_confirm_prompt(data)

    if state == "fiber_confirm":
        if _is_no(text):
            reset_flow(session_id)
            return "Waa la joojiyey dalabka fiber."
        if not _is_yes(text):
            return "Fadlan ku jawaab *Haa* ama *Maya*."
        if not phone:
            reset_flow(session_id)
            return _phone_required()
        return _submit_fiber(session_id, phone, data)

    # --- Idle: route new intents ---
    if state != "idle":
        reset_flow(session_id)

    t = _norm(text)
    if t in {"menu", "help", "caawi", "start", "bilow"}:
        return MAIN_MENU

    if _wants_exchange(text):
        try:
            res = get_exchange_rate()
            return _format_exchange(res)
        except TelesomAPIError as e:
            return _api_fail(e)

    if _wants_block(text):
        if not phone:
            return _phone_required()
        return _start_block_flow(session_id)

    if _wants_fiber(text):
        if not phone:
            return _phone_required()
        return _start_fiber_flow(session_id)

    if skip_vas_menu or _is_general_telesom_info_query(text):
        return None

    if _wants_vas_menu(text):
        set_meta(session_id, flow_state="await_offer", flow_data={})
        return OFFER_MENU_TEXT

    return None

from schemas import IntentResult

def generate_agent_text(intent: IntentResult, transcript: str) -> str:
    i = intent.intent
    e = intent.entities

    if i == "greeting":
        return "Assalam-o-Alaikum! Main hospital appointment assistant hoon. Aap appointment book, reschedule ya cancel karna chahtay hain?"

    if i == "list_doctors":
        return "Available doctors: Dr. Ahmed (Cardiology), Dr. Sana (Dermatology), Dr. Ali (General Physician)."

    if i == "check_availability":
        doc = e.get("doctor_name") or "doctor"
        day = e.get("date") or e.get("natural_date") or "aap ke kehne ke mutabiq"
        return f"Ji, {doc} ki availability check kar raha hoon for {day}. Aap preferred time bhi bata dein?"

    if i == "book_appointment":
        return "Theek hai. Appointment book karne ke liye doctor ka naam, date aur time bata dein. Agar aap chahein to department bhi."

    if i == "reschedule_appointment":
        return "Theek hai. Reschedule ke liye Appointment ID aur nayi date/time bata dein."

    if i == "cancel_appointment":
        return "Theek hai. Cancel ke liye Appointment ID bata dein."

    return "Mujhe samajh nahi aaya. Kya aap appointment book, reschedule, cancel, ya doctor list chahte hain?"
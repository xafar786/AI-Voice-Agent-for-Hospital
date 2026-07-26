from __future__ import annotations

import re


# These routes are for appointment discovery, not medical diagnosis. Department
# names intentionally match the values stored in the doctors collection.
DEPARTMENT_SYMPTOMS: dict[str, tuple[str, ...]] = {
    "Cardiology": (
        "chest pain", "heart pain", "heart problem", "palpitations",
        "seene mein dard", "dil mein dard", "dil ka masla",
        "سینے میں درد", "دل میں درد", "دل کا مسئلہ", "دھڑکن",
        "cardiology", "cardiac", "cardiologist", "heart",
        "کارڈیولوجسٹ", "کارڈیالوجسٹ",
    ),
    "Dermatology": (
        "skin problem", "skin issue", "skin allergy", "skin infection",
        "rash", "acne", "pimples", "eczema", "itching", "hair loss",
        "nail pain", "broken nail", "toenail", "nail infection", "nakhun",
        "dermatology", "dermatologist",
        "jild", "kharish", "danay", "baal gir",
        "جلد", "خارش", "دانے", "مہاسے", "ایگزیما", "بال گر", "ناخن",
    ),
    "Orthopedic Surgery": (
        "back pain", "pain in my back", "my back hurts", "back is hurting",
        "neck pain", "shoulder pain", "knee pain", "joint pain",
        "bone pain", "fracture", "sprain", "kamar dard", "gardan dard",
        "orthopedic", "orthopaedic",
        "ghutne", "haddi", "joron", "کمر درد", "کمر میں درد", "گردن میں درد",
        "گھٹنے", "ہڈی", "جوڑ", "فریکچر", "موچ",
    ),
    "ENT": (
        "ear pain", "hearing problem", "sore throat", "throat pain",
        "blocked nose", "sinus", "tonsil", "kaan dard", "gala kharab",
        "naak band", "کان میں درد", "کان درد", "گلا خراب", "گلے میں درد",
        "ناک بند", "سائنوس", "ٹانسل",
    ),
    "Gastroenterology and Hepatology": (
        "stomach pain", "abdominal pain", "stomach problem", "acidity",
        "stomach upset", "upset stomach", "heartburn", "indigestion",
        "constipation", "diarrhea", "vomiting",
        "jaundice", "liver problem", "pait dard", "meday", "qabz", "ulti",
        "pait kharab", "پیٹ میں درد", "پیٹ درد", "پیٹ خراب",
        "معدہ", "معدے", "تیزابیت", "قبض", "دست",
        "الٹی", "یرقان", "جگر",
    ),
    "Neurology": (
        "severe headache", "migraine", "seizure", "fits", "numbness",
        "tingling", "dizziness", "memory loss", "sar dard", "chakkar",
        "سر میں درد", "سر درد", "آدھے سر کا درد", "مرگی", "دورے",
        "سن ہونا", "چکر", "یادداشت",
    ),
    "Pulmonology": (
        "breathing problem", "shortness of breath", "difficulty breathing",
        "asthma", "lung problem", "persistent cough", "saans ka masla",
        "saans phool", "سانس کا مسئلہ", "سانس پھول", "سانس لینے میں دشواری",
        "دمہ", "پھیپھڑے", "مسلسل کھانسی",
    ),
    "Ophthalmology": (
        "eye pain", "eye problem", "blurred vision", "vision problem",
        "red eye", "aankh", "nazar kamzor", "آنکھ میں درد", "آنکھوں میں درد",
        "آنکھ", "نظر کمزور", "دھندلا دکھائی",
    ),
    "Dentistry and Orthodontics": (
        "tooth pain", "toothache", "tooth is hurting", "tooth hurts",
        "dental pain", "gum problem",
        "broken tooth", "daant dard", "masooray", "دانت میں درد",
        "دانت درد", "مسوڑھے", "دانت ٹوٹ",
    ),
    "Endocrinology and Diabetes": (
        "diabetes", "high sugar", "low sugar", "thyroid", "hormone problem",
        "sugar ka masla", "شوگر", "ذیابیطس", "تھائیرائڈ", "ہارمون",
    ),
    "Nephrology": (
        "kidney disease", "kidney failure", "creatinine", "dialysis",
        "gurday ki bimari", "گردے کی بیماری", "گردوں کی بیماری",
        "کریٹینین", "ڈائلیسس",
    ),
    "Urology": (
        "kidney stone", "urine problem", "painful urination", "blood in urine",
        "prostate", "peshab ka masla", "gurday ki pathri", "پیشاب کا مسئلہ",
        "پیشاب میں درد", "پیشاب میں خون", "گردے کی پتھری", "پروسٹیٹ",
    ),
    "Obstetrics and Gynecology": (
        "pregnancy problem", "pregnant", "period problem", "irregular periods",
        "women problem", "gynecology", "hamal", "mahina", "حمل", "حاملہ",
        "ماہواری", "پیریڈ", "خواتین کا مسئلہ",
    ),
    "Pediatrics": (
        "child is sick", "baby is sick", "child problem", "baby problem",
        "newborn", "my child", "my baby", "bacha bimar", "bachay ka masla",
        "بچہ بیمار", "بچے کا مسئلہ", "میرا بچہ", "نوزائیدہ",
    ),
    "Psychiatry": (
        "anxiety", "depression", "panic attack", "mental health",
        "cannot sleep", "insomnia", "stress", "ghabrahat", "udasi",
        "بے چینی", "گھبراہٹ", "ڈپریشن", "ذہنی دباؤ", "نیند نہیں",
    ),
    "Rheumatology": (
        "rheumatoid", "lupus", "autoimmune", "joint swelling",
        "جوڑوں میں سوجن", "رمیٹائڈ", "لیوپس", "آٹو امیون",
    ),
    "Oncology": (
        "cancer", "tumor", "chemotherapy", "radiotherapy",
        "کینسر", "ٹیومر", "کیموتھراپی", "ریڈیوتھراپی",
    ),
    "General Surgery": (
        "hernia", "appendix pain", "appendicitis", "gallbladder",
        "gallstone", "breast lump", "piles", "بواسیر", "ہرنیا",
        "اپینڈکس", "پتے کی پتھری", "چھاتی میں گلٹی",
    ),
    "Infectious Diseases": (
        "dengue", "malaria", "typhoid", "infectious disease",
        "ڈینگی", "ملیریا", "ٹائیفائڈ", "متعدی بیماری",
    ),
    "Plastic Surgery": (
        "burn scar", "severe burn", "facial injury", "reconstructive surgery",
        "جلنے کا نشان", "شدید جلن", "چہرے کی چوٹ",
    ),
    "Internal Medicine": (
        "fever", "flu", "general weakness", "body aches", "high blood pressure",
        "low blood pressure", "bukhar", "kamzori", "jism dard",
        "بخار", "نزلہ", "زکام", "کمزوری", "جسم میں درد", "بلڈ پریشر",
    ),
}


def _contains_phrase(text: str, phrase: str) -> bool:
    if phrase.isascii():
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])",
                text.lower(),
            )
        )
    # Urdu words must also be token-bounded. A raw substring check makes
    # "دست" (diarrhea) match "دستیاب" (available), which can silently change
    # the selected department and doctor.
    return bool(
        re.search(
            rf"(?<![\u0600-\u06FF]){re.escape(phrase)}(?![\u0600-\u06FF])",
            text,
        )
    )


def infer_department_from_symptoms(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    if not normalized:
        return None

    matches: list[tuple[int, int, str]] = []
    for priority, (department, phrases) in enumerate(DEPARTMENT_SYMPTOMS.items()):
        matching_lengths = [
            len(phrase)
            for phrase in phrases
            if _contains_phrase(normalized, phrase)
        ]
        if matching_lengths:
            matches.append((max(matching_lengths), -priority, department))
    if not matches:
        return None
    return max(matches)[2]

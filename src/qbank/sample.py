"""15 FAKE sample questions (3 regions) for tests and demos ONLY. Every one is marked sample = True and tagged "sample". Nothing here is ever written to the real bank:
scripts/bank_seed_sample.py needs an explicit throw-away database path."""
REGIONS = {
    "Lower limb": ("Lecture 08 - Anterior and Medial Thigh", [("Which muscle forms the lateral border of the femoral triangle?", ["Sartorius", "Gracilis", "Pectineus", "Adductor magnus"], "A"),
        ("Which nerve supplies the quadriceps femoris?", ["Femoral nerve", "Obturator nerve", "Tibial nerve", "Sciatic nerve"], "A"),
        ("Where does the great saphenous vein drain?", ["Femoral vein", "Popliteal vein", "External iliac artery", "Profunda femoris vein"], "A"),
        ("Which artery is the main blood supply of the thigh?", ["Femoral artery", "Obturator artery", "Popliteal artery", "Gluteal artery"], "A"),
        ("Which structure lies medial to the femoral vein?", ["Femoral canal", "Femoral nerve", "Sartorius", "Iliopsoas"], "A")]),
    "Upper limb": ("Lecture 09 - The Hand", [("Which nerve passes through the carpal tunnel?", ["Median nerve", "Ulnar nerve", "Radial nerve", "Axillary nerve"], "A"),
        ("Which muscle abducts the thumb?", ["Abductor pollicis brevis", "Adductor pollicis", "Opponens digiti minimi", "Palmaris brevis"], "A"),
        ("Which nerve supplies the hypothenar muscles?", ["Ulnar nerve", "Median nerve", "Radial nerve", "Musculocutaneous nerve"], "A"),
        ("What do the lumbricals flex?", ["Metacarpophalangeal joints", "Wrist", "Distal interphalangeal joints", "Elbow"], "A"),
        ("Which arch lies more distally in the palm?", ["Superficial palmar arch", "Deep palmar arch", "Dorsal carpal arch", "Radial recurrent arch"], "A")]),
    "Head and neck": ("Lecture 20 - The Neck", [("What forms the anterior border of the posterior triangle of the neck?", ["Sternocleidomastoid", "Trapezius", "Omohyoid", "Digastric"], "A"),
        ("Which nerve supplies the trapezius?", ["Accessory nerve", "Vagus nerve", "Phrenic nerve", "Hypoglossal nerve"], "A"),
        ("Which gland lies anterior to the trachea?", ["Thyroid gland", "Parotid gland", "Submandibular gland", "Thymus"], "A"),
        ("Which vessel runs in the carotid sheath with the vagus nerve?", ["Internal jugular vein", "External jugular vein", "Facial vein", "Subclavian vein"], "A"),
        ("Which muscle elevates the hyoid bone?", ["Mylohyoid", "Sternohyoid", "Omohyoid", "Thyrohyoid"], "A")]),
}


def sample_questions():
    out = []
    for region, (lecture, qs) in REGIONS.items():
        for i, (lead, options, ans) in enumerate(qs):
            out.append({"stem": "", "lead_in": lead, "options": [{"id": "ABCDE"[j], "text": t} for j, t in enumerate(options)], "answer": ans, "explanation": "SAMPLE explanation: not real course content.",
                        "lecture": lecture, "region": region, "tags": ["sample"], "difficulty": ["easy", "medium", "hard"][i % 3], "source": "instructor", "status": "approved" if i < 3 else "draft",
                        "use": "exam_secure" if i == 4 else "practice", "sample": True})
    return out
